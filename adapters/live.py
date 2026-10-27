"""Live provider adapters: Tavily search, OpenAI writer, Anthropic verifier (ARCH §6.5).

UNVERIFIED AGAINST THE LIVE SERVICES. These wire formats were written from the providers' public
documentation as understood at build time and are tested only against fake transports. Before the
first live call (rules.md: ask for an approved spend cap), run one supervised request per
adapter and confirm the request body, response fields and usage/billing fields below.
Known assumptions:

* Tavily: POST https://api.tavily.com/search, Bearer auth, `results[].content` is the snippet,
  `results[].raw_content` is extracted text, `usage.credits` is the billed unit count.
* OpenAI: chat completions in JSON mode with `max_completion_tokens`; no temperature is sent.
* Ollama (local): the same call at `http://localhost:11434/v1` with `max_tokens` and
  `response_format` json_schema, which Ollama enforces; the reply is still validated here.
  Ollama truncates prompts that exceed its context window without an error, so the reported
  prompt tokens are compared with our estimate and a cut prompt fails closed.
* NVIDIA Build (and other OpenAI-compatible servers): the same chat-completions call at
  `https://integrate.api.nvidia.com/v1` with `max_tokens` and `temperature`. NVIDIA documents
  Gemma 4 as having no structured-output support, so JSON is requested in the prompt and checked
  strictly here (`json_mode="none"`); `response_format` is sent only if configured. Reasoning
  (`<think>` or `<|channel>thought` blocks) is removed before the JSON is located.
* Anthropic: Messages API with `max_tokens` and text content blocks; no temperature is sent.

Rules every adapter keeps: SDK retries are off (the CallGuard owns retries), failures surface
only as `ProviderError` subclasses, response bodies never enter an exception message, and a
key is read once at construction and never logged.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import anthropic
import httpx
import openai
from pydantic import SecretStr, ValidationError

from adapters.base import Block, LLMResult, Providers, SearchProvider, T
from core.errors import (
    ContentRefused,
    ContextTruncated,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimit,
    ProviderServerError,
    ProviderTimeout,
    SchemaViolation,
)
from core.models import RawResult, SearchResponse
from core.settings import Settings
from core.tokens import estimate_tokens

TAVILY_URL = "https://api.tavily.com/search"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
TRUNCATION_RATIO = (
    0.6  # reported prompt tokens below this share of our estimate mean the server cut it
)
TRUNCATION_MIN_TOKENS = 500
CONTEXT_MARGIN_TOKENS = 16
MAX_EXTRACTED_CHARS = 60_000
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


# --- shared helpers -------------------------------------------------------------------


def render_blocks(blocks: Sequence[Block]) -> str:
    """Untrusted data goes in labeled fences; content cannot close its own fence."""
    parts = []
    for block in blocks:
        safe = block.content.replace("</data>", "<\\/data>")
        parts.append(f'<data label="{block.label}">\n{safe}\n</data>')
    return "\n\n".join(parts)


def _schema_instruction(schema: type[Any]) -> str:
    return (
        "Respond with exactly one JSON object that validates against this JSON Schema. "
        "No prose and no code fences.\n"
        + json.dumps(schema.model_json_schema(), separators=(",", ":"))
    )


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CHANNEL_BLOCK = re.compile(r"<\|channel>.*?<channel\|>", re.DOTALL)


def strip_reasoning(text: str) -> str:
    """Drop reasoning blocks so only the final answer is searched for JSON.

    Reasoning text can contain JSON-looking fragments; an unfinished block means the model never
    reached its answer, so nothing is returned (the caller then fails closed).
    """
    if "</think>" in text.lower() and "<think>" not in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    if "<channel|>" in text and "<|channel>" not in text:
        text = text.rsplit("<channel|>", 1)[-1]
    text = _THINK_BLOCK.sub("", text)
    text = _CHANNEL_BLOCK.sub("", text)
    if "<think>" in text.lower() or "<|channel>" in text:
        return ""
    return text


def _parse_json(text: str | None, schema: type[T]) -> T:
    if not text:
        raise SchemaViolation("empty model output")
    text = strip_reasoning(text)
    if not text.strip():
        raise SchemaViolation("model output contained no answer")
    body = _FENCE.sub("", text.strip())
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise SchemaViolation("no JSON object in model output")
    try:
        return schema.model_validate(json.loads(body[start : end + 1]))
    except (ValueError, ValidationError) as err:
        raise SchemaViolation("model output does not match the schema") from err


def _retry_after(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    try:
        return max(0.0, float(response.headers.get("retry-after", "")))
    except ValueError:
        return None


# --- search ---------------------------------------------------------------------------


class TavilySearch:
    def __init__(self, api_key: SecretStr, *, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client()

    def search(
        self, query: str, *, max_results: int, want_extracted: bool, timeout_s: float
    ) -> SearchResponse:
        body = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_raw_content": want_extracted,
            "include_answer": False,
        }
        headers = {"Authorization": f"Bearer {self._key.get_secret_value()}"}
        try:
            response = self._client.post(TAVILY_URL, json=body, headers=headers, timeout=timeout_s)
        except httpx.TimeoutException as err:
            raise ProviderTimeout("search timed out") from err
        except httpx.HTTPError as err:
            raise ProviderServerError("search connection failed") from err

        status = response.status_code
        if status in (401, 403):
            raise ProviderAuthError("search credentials rejected")
        if status == 429:
            raise ProviderRateLimit(_retry_after(response))
        if status >= 500:
            raise ProviderServerError(f"search service error {status}")
        if status >= 400:
            raise ProviderBadRequest(f"search request rejected {status}")
        try:
            data = response.json()
            results = [
                RawResult(
                    title=str(item.get("title") or ""),
                    url=str(item["url"]),
                    snippet=str(item.get("content") or ""),
                    extracted_text=(
                        str(item["raw_content"])[:MAX_EXTRACTED_CHARS]
                        if item.get("raw_content")
                        else None
                    ),
                    score=float(item["score"]) if item.get("score") is not None else None,
                    published_at=str(item["published_date"])
                    if item.get("published_date")
                    else None,
                )
                for item in data["results"]
            ]
            credits = (data.get("usage") or {}).get("credits")
            billed = float(credits) if credits is not None else None
        except (ValueError, KeyError, TypeError, ValidationError) as err:
            raise ProviderServerError("search response was malformed") from err
        return SearchResponse(results=results, billed_units=billed)


class OpenAIWebSearch:
    """Use OpenAI's hosted web search snippets as source passages.

    Only text returned as a search result becomes evidence. The model's answer is not treated as
    source text, and this adapter never follows a URL returned by the search tool.
    """

    def __init__(self, api_key: SecretStr, model: str, *, client: Any = None) -> None:
        self.model_id = model
        self._client = client or openai.OpenAI(api_key=api_key.get_secret_value(), max_retries=0)

    def search(
        self, query: str, *, max_results: int, want_extracted: bool, timeout_s: float
    ) -> SearchResponse:
        del want_extracted  # hosted search returns snippets, not extracted pages
        try:
            response = self._client.responses.create(
                model=self.model_id,
                input=f"Search the public web for: {query}",
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.results"],
                max_output_tokens=500,
                reasoning={"effort": "low"},
                store=False,
                timeout=timeout_s,
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError) as err:
            raise ProviderAuthError("search credentials rejected") from err
        except (
            openai.BadRequestError,
            openai.UnprocessableEntityError,
            openai.NotFoundError,
        ) as err:
            raise ProviderBadRequest("search request rejected") from err
        except openai.RateLimitError as err:
            raise ProviderRateLimit(_retry_after(getattr(err, "response", None))) from err
        except openai.APITimeoutError as err:
            raise ProviderTimeout("search timed out") from err
        except (openai.APIConnectionError, openai.InternalServerError) as err:
            raise ProviderServerError("search service unavailable") from err
        except openai.APIStatusError as err:
            raise ProviderBadRequest(f"search request failed {err.status_code}") from err

        results: list[RawResult] = []
        calls = 0
        for item in getattr(response, "output", ()):
            if getattr(item, "type", None) != "web_search_call":
                continue
            calls += 1
            for source in getattr(item, "results", None) or ():
                data = (
                    source
                    if isinstance(source, dict)
                    else (source.model_dump() if hasattr(source, "model_dump") else vars(source))
                )
                url = str(data.get("url") or "")
                parts = urlsplit(url)
                snippet = str(data.get("snippet") or data.get("content") or "").strip()
                if parts.scheme not in {"http", "https"} or not parts.netloc or not snippet:
                    continue
                results.append(
                    RawResult(
                        title=str(data.get("title") or parts.netloc),
                        url=url,
                        snippet=snippet,
                    )
                )
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        if not calls:
            raise ProviderServerError("search returned no web search call")
        return SearchResponse(results=results, billed_units=float(calls))


# --- OpenAI writer --------------------------------------------------------------------


class OpenAICompatChat:
    """Chat completions against any OpenAI-compatible endpoint (OpenAI, NVIDIA Build, ...)."""

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        *,
        base_url: str | None = None,
        token_param: str = "max_completion_tokens",
        json_mode: str = "json_object",
        send_temperature: bool = False,
        extra_body: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        check_truncation: bool = False,
        context_tokens: int | None = None,
        client: Any = None,
    ) -> None:
        self.check_truncation = check_truncation
        self.context_tokens = context_tokens
        self.model_id = model
        self.base_url = base_url or ""
        self.token_param = token_param
        self.json_mode = json_mode
        self.send_temperature = send_temperature
        self.extra_body = extra_body
        self.reasoning_effort = reasoning_effort
        self._client = client or openai.OpenAI(
            api_key=api_key.get_secret_value(), base_url=base_url or None, max_retries=0
        )

    def generate(
        self,
        *,
        system: str,
        blocks: Sequence[Block],
        schema: type[T],
        max_output_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> LLMResult[T]:
        messages = [
            {"role": "system", "content": f"{system}\n\n{_schema_instruction(schema)}"},
            {"role": "user", "content": render_blocks(blocks)},
        ]
        estimate = estimate_tokens(messages[0]["content"] + messages[1]["content"])
        if self.check_truncation:
            self._check_fits_context(estimate, max_output_tokens)
        request: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            self.token_param: max_output_tokens,
            "timeout": timeout_s,
        }
        if self.json_mode == "json_object":
            request["response_format"] = {"type": "json_object"}
        elif self.json_mode == "json_schema":
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        if self.send_temperature:
            request["temperature"] = temperature
        if self.extra_body:
            request["extra_body"] = self.extra_body
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        try:
            response = self._client.chat.completions.create(**request)
        except (openai.AuthenticationError, openai.PermissionDeniedError) as err:
            raise ProviderAuthError("model credentials rejected") from err
        except (
            openai.BadRequestError,
            openai.UnprocessableEntityError,
            openai.NotFoundError,
        ) as err:
            raise ProviderBadRequest("model request rejected") from err
        except openai.RateLimitError as err:
            raise ProviderRateLimit(_retry_after(getattr(err, "response", None))) from err
        except openai.APITimeoutError as err:
            raise ProviderTimeout("model call timed out") from err
        except (openai.APIConnectionError, openai.InternalServerError) as err:
            raise ProviderServerError("model service unavailable") from err
        except openai.APIStatusError as err:
            raise ProviderBadRequest(f"model request failed {err.status_code}") from err

        choices = getattr(response, "choices", None)
        if not choices:
            raise ProviderServerError("model returned no choices")
        choice = choices[0]
        message = getattr(choice, "message", None)
        if choice.finish_reason == "content_filter" or getattr(message, "refusal", None):
            raise ContentRefused("model declined")
        usage = getattr(response, "usage", None)
        if self.check_truncation:
            self._check_not_truncated(estimate, usage)
        parsed = _parse_json(getattr(message, "content", None), schema)
        return LLMResult(
            parsed=parsed,
            model_id=str(getattr(response, "model", self.model_id)),
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            finish_reason=str(choice.finish_reason),
        )

    def _check_fits_context(self, estimate: int, max_output_tokens: int) -> None:
        """Refuse, before any request, a prompt that cannot fit the server's context window."""
        if self.context_tokens is None or estimate < TRUNCATION_MIN_TOKENS:
            return
        # Real prompts measured at 0.65 to 0.9 of our estimate, so 0.6 is a safe lower bound.
        if estimate * TRUNCATION_RATIO + max_output_tokens > self.context_tokens:
            raise ContextTruncated("prompt and output cannot fit the configured context window")

    def _check_not_truncated(self, estimate: int, usage: Any) -> None:
        """Ollama silently cuts prompts that exceed its context window: detect that afterwards."""
        if estimate < TRUNCATION_MIN_TOKENS:
            return
        seen = getattr(usage, "prompt_tokens", None)
        if seen is None:
            raise ContextTruncated(
                "the server did not report prompt tokens, so truncation cannot be ruled out"
            )
        if seen < estimate * TRUNCATION_RATIO:
            raise ContextTruncated("server processed only part of the prompt")
        done = getattr(usage, "completion_tokens", None) or 0
        if (
            self.context_tokens is not None
            and seen + done >= self.context_tokens - CONTEXT_MARGIN_TOKENS
        ):
            # The window filled while generating: the server may have dropped part of the prompt.
            raise ContextTruncated("prompt and answer filled the context window")


class OpenAIChat(OpenAICompatChat):
    """OpenAI proper: JSON mode, `max_completion_tokens`, no temperature."""

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        *,
        base_url: str | None = None,
        json_mode: str = "json_object",
        token_param: str = "max_completion_tokens",
        client: Any = None,
    ) -> None:
        super().__init__(
            api_key,
            model,
            base_url=base_url,
            json_mode=json_mode,
            token_param=token_param,
            reasoning_effort="none",
            client=client,
        )


# --- Anthropic verifier ---------------------------------------------------------------


class AnthropicChat:
    def __init__(self, api_key: SecretStr, model: str, *, client: Any = None) -> None:
        self.model_id = model
        self._client = client or anthropic.Anthropic(
            api_key=api_key.get_secret_value(), max_retries=0
        )

    def generate(
        self,
        *,
        system: str,
        blocks: Sequence[Block],
        schema: type[T],
        max_output_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> LLMResult[T]:
        del temperature  # the installed SDK's Messages.create takes no temperature argument
        try:
            request: dict[str, Any] = {
                "model": self.model_id,
                "max_tokens": max_output_tokens,
                "system": f"{system}\n\n{_schema_instruction(schema)}",
                "messages": [{"role": "user", "content": render_blocks(blocks)}],
                "timeout": timeout_s,
            }
            response = self._client.messages.create(**request)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as err:
            raise ProviderAuthError("model credentials rejected") from err
        except anthropic.BadRequestError as err:
            raise ProviderBadRequest("model request rejected") from err
        except anthropic.RateLimitError as err:
            raise ProviderRateLimit(_retry_after(getattr(err, "response", None))) from err
        except anthropic.APITimeoutError as err:
            raise ProviderTimeout("model call timed out") from err
        except (anthropic.APIConnectionError, anthropic.InternalServerError) as err:
            raise ProviderServerError("model service unavailable") from err
        except anthropic.APIStatusError as err:
            raise ProviderBadRequest(f"model request failed {err.status_code}") from err

        if response.stop_reason == "refusal":
            raise ContentRefused("model declined")
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        parsed = _parse_json(text, schema)
        usage = getattr(response, "usage", None)
        return LLMResult(
            parsed=parsed,
            model_id=str(getattr(response, "model", self.model_id)),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            finish_reason=str(response.stop_reason),
        )


def build_writer(settings: Settings) -> OpenAICompatChat:
    if settings.writer_provider == "nvidia":
        assert settings.nvidia_api_key
        return OpenAICompatChat(
            settings.nvidia_api_key,
            settings.writer_model,
            base_url=settings.openai_base_url or NVIDIA_BASE_URL,
            token_param=settings.writer_token_param,
            json_mode=settings.writer_json_mode,
            send_temperature=True,
            # Nemotron's documented reasoning switch; off keeps the answer short and parseable.
            extra_body={"chat_template_kwargs": {"enable_thinking": settings.writer_thinking}},
        )
    assert settings.openai_api_key
    return OpenAIChat(
        settings.openai_api_key,
        settings.writer_model,
        base_url=settings.openai_base_url or None,
        json_mode=settings.writer_json_mode,
        token_param=settings.writer_token_param,
    )


def build_verifier(settings: Settings) -> OpenAICompatChat | AnthropicChat:
    if settings.verifier_provider == "nvidia":
        assert settings.nvidia_api_key
        return OpenAICompatChat(
            settings.nvidia_api_key,
            settings.verifier_model,
            base_url=settings.verifier_base_url or NVIDIA_BASE_URL,
            token_param=settings.verifier_token_param,
            json_mode=settings.verifier_json_mode,
            send_temperature=True,
        )
    if settings.verifier_provider == "ollama":
        # A local server: it gets a placeholder key, never the NVIDIA or any other credential.
        return OpenAICompatChat(
            SecretStr("ollama"),
            settings.verifier_model,
            base_url=settings.verifier_base_url or OLLAMA_BASE_URL,
            token_param=settings.verifier_token_param,
            json_mode=settings.verifier_json_mode,
            send_temperature=True,
            check_truncation=True,
            context_tokens=settings.verifier_context_tokens,
        )
    assert settings.verifier_api_key
    if settings.verifier_provider == "openai":
        return OpenAIChat(
            settings.verifier_api_key,
            settings.verifier_model,
            base_url=settings.verifier_base_url or None,
            json_mode=settings.verifier_json_mode,
            token_param=settings.verifier_token_param,
        )
    return AnthropicChat(settings.verifier_api_key, settings.verifier_model)


def build_live_providers(settings: Settings) -> Providers:
    """Construct the live providers. Callers have already passed `startup_problems`."""
    search: SearchProvider
    if settings.search_provider == "openai":
        assert settings.openai_api_key
        search = OpenAIWebSearch(settings.openai_api_key, settings.writer_model)
    else:
        assert settings.search_api_key
        search = TavilySearch(settings.search_api_key)
    return Providers(
        search=search,
        writer=build_writer(settings),
        verifier=build_verifier(settings),
        writer_model=settings.writer_model,
        verifier_model=settings.verifier_model,
    )


__all__ = [
    "NVIDIA_BASE_URL",
    "OLLAMA_BASE_URL",
    "AnthropicChat",
    "OpenAIChat",
    "OpenAIWebSearch",
    "OpenAICompatChat",
    "ProviderError",
    "TavilySearch",
    "build_live_providers",
    "build_verifier",
    "build_writer",
    "render_blocks",
    "strip_reasoning",
]
