"""OpenAI-compatible endpoints (NVIDIA Build, OpenRouter, Ollama) behind the same strict contract."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from adapters.base import Block
from adapters.live import (
    NVIDIA_BASE_URL,
    AnthropicChat,
    OpenAIChat,
    OpenAICompatChat,
    build_live_providers,
    strip_reasoning,
)
from core.errors import (
    ContentRefused,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderRateLimit,
    ProviderServerError,
    ProviderTimeout,
    SchemaViolation,
)
from core.models import ScanOutput, VerifierOutput
from core.settings import load_settings

REQ = httpx.Request("POST", "https://example.invalid/")
GOOD = json.dumps({"results": [{"claim_id": "c1", "verdict": "supported", "reason": "ok"}]})


def _resp(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, request=REQ, headers=headers or {})


class _Fake:
    def __init__(
        self,
        content: str | None = GOOD,
        finish: str = "stop",
        error: Exception | None = None,
        refusal: str | None = None,
    ) -> None:
        self.kwargs: dict[str, object] = {}
        self._content, self._finish, self._error, self._refusal = content, finish, error, refusal
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        if self._error:
            raise self._error
        message = SimpleNamespace(content=self._content, refusal=self._refusal)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=self._finish)],
            usage=SimpleNamespace(prompt_tokens=50, completion_tokens=20),
            model="served-model",
        )


def _nvidia(client: _Fake, **over: object) -> OpenAICompatChat:
    args: dict[str, object] = dict(
        base_url=NVIDIA_BASE_URL, token_param="max_tokens", json_mode="none", send_temperature=True
    )
    args.update(over)
    return OpenAICompatChat(
        SecretStr("nvapi-test-key"), "google/gemma-4-31b-it", client=client, **args
    )


def _call(chat, schema=VerifierOutput, **over):  # noqa: ANN001, ANN003, ANN202
    args = dict(
        system="sys",
        blocks=[Block("claims", "[]")],
        schema=schema,
        max_output_tokens=500,
        temperature=0.0,
        timeout_s=10,
    )
    args.update(over)
    return chat.generate(**args)


# --- request shape ------------------------------------------------------------------------------------


def test_nvidia_profile_uses_max_tokens_temperature_and_no_response_format() -> None:
    client = _Fake()
    result = _call(_nvidia(client))
    assert client.kwargs["max_tokens"] == 500 and "max_completion_tokens" not in client.kwargs
    assert client.kwargs["temperature"] == 0.0
    assert "response_format" not in client.kwargs
    assert client.kwargs["model"] == "google/gemma-4-31b-it"
    system = client.kwargs["messages"][0]["content"]  # type: ignore[index]
    assert "JSON Schema" in system and "results" in system  # JSON is requested in the prompt
    assert (result.input_tokens, result.output_tokens) == (50, 20)


def test_json_object_mode_and_token_parameter_are_configurable() -> None:
    client = _Fake()
    _call(_nvidia(client, json_mode="json_object", token_param="max_completion_tokens"))
    assert client.kwargs["response_format"] == {"type": "json_object"}
    assert client.kwargs["max_completion_tokens"] == 500 and "max_tokens" not in client.kwargs


def test_extra_body_carries_the_thinking_switch() -> None:
    client = _Fake()
    _call(_nvidia(client, extra_body={"chat_template_kwargs": {"enable_thinking": False}}))
    assert client.kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    plain = _Fake()
    _call(_nvidia(plain))
    assert "extra_body" not in plain.kwargs


def test_base_url_reaches_the_sdk_client_and_retries_are_off() -> None:
    chat = OpenAICompatChat(SecretStr("nvapi-test-key"), "m", base_url=NVIDIA_BASE_URL)
    assert str(chat._client.base_url).rstrip("/") == NVIDIA_BASE_URL
    assert chat._client.max_retries == 0
    assert "nvapi-test-key" not in repr(chat)
    default = OpenAIChat(SecretStr("sk-test"), "gpt-test")
    assert "api.openai.com" in str(default._client.base_url)


# --- strict parsing with reasoning output ----------------------------------------------------------------


def test_reasoning_blocks_are_removed_before_the_json_is_located() -> None:
    think = '<think>maybe {"results": []} is the answer</think>\n' + GOOD
    gemma = '<|channel>thought\nI should output {"results": "x"}<channel|>' + GOOD
    assert strip_reasoning(think).strip() == GOOD
    assert strip_reasoning(gemma).strip() == GOOD
    for content in (think, gemma):
        assert _call(_nvidia(_Fake(content))).parsed.results[0].claim_id == "c1"


def test_unfinished_reasoning_or_reasoning_only_output_is_a_schema_violation() -> None:
    for content in (
        '<think>still thinking {"results": []}',
        "<|channel>thought\nno answer",
        "<think>x</think>",
    ):
        with pytest.raises(SchemaViolation):
            _call(_nvidia(_Fake(content)))


@pytest.mark.parametrize(
    "content",
    [
        "I think the claim is supported.",
        '{"results": [{"claim_id": "c1", "verdict": "maybe"}]}',
        '{"results": [{"claim_id": "c1", "verdict": "supported", "surprise": 1}]}',
        '{"results": [{"claim_id": "c1", "verdict": "supported"',
        '{"output": []}',
        "",
        None,
    ],
)
def test_anything_that_is_not_the_exact_schema_fails_closed(content: str | None) -> None:
    with pytest.raises(SchemaViolation):
        _call(_nvidia(_Fake(content)))


def test_other_schemas_validate_the_same_way() -> None:
    ok = json.dumps({"results": [{"sentence_ref": "findings:1", "contains_material_fact": False}]})
    assert (
        _call(_nvidia(_Fake(ok)), schema=ScanOutput).parsed.results[0].sentence_ref == "findings:1"
    )
    with pytest.raises(SchemaViolation):
        _call(_nvidia(_Fake(GOOD)), schema=ScanOutput)


# --- provider errors (the same mapping for every compatible endpoint) -------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (openai.AuthenticationError("x", response=_resp(401), body=None), ProviderAuthError),
        (openai.PermissionDeniedError("x", response=_resp(403), body=None), ProviderAuthError),
        (openai.BadRequestError("x", response=_resp(400), body=None), ProviderBadRequest),
        (openai.UnprocessableEntityError("x", response=_resp(422), body=None), ProviderBadRequest),
        (openai.NotFoundError("x", response=_resp(404), body=None), ProviderBadRequest),
        (
            openai.RateLimitError("x", response=_resp(429, {"retry-after": "7"}), body=None),
            ProviderRateLimit,
        ),
        (openai.InternalServerError("x", response=_resp(503), body=None), ProviderServerError),
        (openai.APITimeoutError(request=REQ), ProviderTimeout),
        (openai.APIConnectionError(request=REQ), ProviderServerError),
    ],
)
def test_sdk_errors_map_to_provider_errors(error: Exception, expected: type[Exception]) -> None:
    with pytest.raises(expected) as err:
        _call(_nvidia(_Fake(error=error)))
    if expected is ProviderRateLimit:
        assert err.value.retry_after_s == 7.0  # type: ignore[attr-defined]
    assert "x" not in str(err.value) or expected is ProviderRateLimit


def test_refusal_and_content_filter_are_content_refused() -> None:
    with pytest.raises(ContentRefused):
        _call(_nvidia(_Fake(None, refusal="no")))
    with pytest.raises(ContentRefused):
        _call(_nvidia(_Fake(GOOD, finish="content_filter")))


def test_an_empty_choices_list_is_a_provider_error_not_an_index_error() -> None:
    client = _Fake()
    original = client._create
    client.chat.completions.create = lambda **kw: SimpleNamespace(choices=[], usage=None, model="m")  # type: ignore[assignment]
    with pytest.raises(ProviderServerError):
        _call(_nvidia(client))
    assert original is not None


# --- building providers from settings --------------------------------------------------------------------------


def _env(**over: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "tvly",
        "NVIDIA_API_KEY": "nvapi-secret",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "nvidia",
        "WRITER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        "VERIFIER_MODEL": "google/gemma-4-31b-it",
    }
    env.update(over)
    return env


def test_nvidia_providers_are_built_from_the_environment() -> None:
    providers = build_live_providers(load_settings(_env()))
    writer, verifier = providers.writer, providers.verifier
    assert isinstance(writer, OpenAICompatChat) and isinstance(verifier, OpenAICompatChat)
    assert writer.base_url == NVIDIA_BASE_URL and verifier.base_url == NVIDIA_BASE_URL
    assert writer.token_param == "max_tokens" and writer.json_mode == "none"
    assert writer.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert (
        verifier.extra_body is None
    )  # Gemma's thinking switch is a prompt token, not a request field
    assert providers.writer_model == "nvidia/nemotron-3-ultra-550b-a55b"
    assert providers.verifier_model == "google/gemma-4-31b-it"


def test_thinking_switch_and_custom_base_urls_are_honoured() -> None:
    s = load_settings(
        _env(
            WRITER_THINKING="on",
            OPENAI_BASE_URL="http://localhost:11434/v1",
            VERIFIER_BASE_URL="https://example.org/v1",
        )
    )
    p = build_live_providers(s)
    assert p.writer.extra_body == {"chat_template_kwargs": {"enable_thinking": True}}  # type: ignore[attr-defined]
    assert p.writer.base_url == "http://localhost:11434/v1"  # type: ignore[attr-defined]
    assert p.verifier.base_url == "https://example.org/v1"  # type: ignore[attr-defined]


def test_original_providers_remain_available_as_alternatives() -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "a",
        "OPENAI_API_KEY": "b",
        "VERIFIER_API_KEY": "c",
        "WRITER_MODEL": "gpt-5",
        "VERIFIER_MODEL": "claude-sonnet-5-5",
    }
    p = build_live_providers(load_settings(env))
    assert isinstance(p.writer, OpenAIChat) and isinstance(p.verifier, AnthropicChat)
    custom = build_live_providers(
        load_settings(dict(env, OPENAI_BASE_URL="https://openrouter.ai/api/v1"))
    )
    assert custom.writer.base_url == "https://openrouter.ai/api/v1"  # type: ignore[attr-defined]
    openai_verifier = build_live_providers(
        load_settings(
            dict(
                env,
                VERIFIER_PROVIDER="openai",
                VERIFIER_MODEL="google/gemma-4-31b-it",
                VERIFIER_BASE_URL="https://integrate.api.nvidia.com/v1",
            )
        )
    )
    assert isinstance(openai_verifier.verifier, OpenAICompatChat)


def test_the_nvidia_key_never_appears_in_the_built_objects() -> None:
    p = build_live_providers(load_settings(_env(NVIDIA_API_KEY="nvapi-very-secret")))
    for obj in (p.writer, p.verifier, p):
        assert "nvapi-very-secret" not in repr(obj)


def test_the_configured_token_parameter_reaches_the_request() -> None:
    p = build_live_providers(load_settings(_env(VERIFIER_TOKEN_PARAM="max_completion_tokens")))
    assert p.verifier.token_param == "max_completion_tokens"  # type: ignore[attr-defined]
    assert p.writer.token_param == "max_tokens"  # type: ignore[attr-defined]
