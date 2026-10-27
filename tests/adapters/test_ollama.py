"""A local Ollama verifier behind the OpenAI-compatible adapter (scripted; no Ollama, no network)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from adapters.base import Block, Providers
from adapters.fakes import DEMO_TOPIC, CallContext, FakeLLM, FakeSearch
from adapters.live import (
    NVIDIA_BASE_URL,
    OLLAMA_BASE_URL,
    OpenAICompatChat,
    build_live_providers,
)
from core.errors import ContextTruncated, ErrorCode, ProviderServerError
from core.models import Mode, ResearchRequest, RunStatus, VerifierOutput
from core.research_agent import run_research
from core.settings import load_settings, model_family, startup_problems
from core.tokens import estimate_tokens
from service import build_service

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "core" / "price_sheet_nvidia_free.json"
GOOD = json.dumps({"results": [{"claim_id": "c1", "verdict": "supported", "reason": "ok"}]})


class _Fake:
    def __init__(
        self, content: str = GOOD, prompt_tokens: int | None = 120, error: Exception | None = None
    ) -> None:
        self.kwargs: dict[str, Any] = {}
        self._content, self._prompt_tokens, self._error = content, prompt_tokens, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.kwargs = kwargs
        if self._error:
            raise self._error
        message = SimpleNamespace(content=self._content, refusal=None)
        usage = SimpleNamespace(prompt_tokens=self._prompt_tokens, completion_tokens=20)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=usage,
            model="qwen3-vl:8b-instruct",
        )


def _ollama(client: _Fake, **over: Any) -> OpenAICompatChat:
    args: dict[str, Any] = dict(
        base_url=OLLAMA_BASE_URL,
        token_param="max_tokens",
        json_mode="json_schema",
        send_temperature=True,
        check_truncation=True,
    )
    args.update(over)
    return OpenAICompatChat(SecretStr("ollama"), "qwen3-vl:8b-instruct", client=client, **args)


def _call(chat: OpenAICompatChat, blocks: list[Block] | None = None) -> Any:
    return chat.generate(
        system="verify",
        blocks=blocks or [Block("claims", "[]")],
        schema=VerifierOutput,
        max_output_tokens=400,
        temperature=0.0,
        timeout_s=30,
    )


# --- schema-constrained output -----------------------------------------------------------------------


def test_json_schema_mode_sends_the_pydantic_schema_as_a_strict_response_format() -> None:
    client = _Fake()
    _call(_ollama(client))
    fmt = client.kwargs["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "VerifierOutput" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == VerifierOutput.model_json_schema()
    assert client.kwargs["max_tokens"] == 400 and client.kwargs["temperature"] == 0.0


def test_the_reply_is_still_validated_strictly_even_when_the_server_constrains_output() -> None:
    for bad in (
        '{"results": [{"claim_id": "c1", "verdict": "maybe"}]}',
        '{"claim_id": "c1"}',
        "yes",
    ):
        with pytest.raises(Exception) as err:  # noqa: PT011
            _call(_ollama(_Fake(bad)))
        assert type(err.value).__name__ == "SchemaViolation"


def test_json_object_and_none_modes_remain_available() -> None:
    a, b = _Fake(), _Fake()
    _call(_ollama(a, json_mode="json_object"))
    _call(_ollama(b, json_mode="none"))
    assert (
        a.kwargs["response_format"] == {"type": "json_object"} and "response_format" not in b.kwargs
    )


# --- silent truncation by the server is detected and fails closed -------------------------------------------


def test_a_prompt_the_server_cut_short_is_reported_not_verified() -> None:
    big = "evidence sentence about the harbor pilot. " * 900  # about 9,000 tokens
    client = _Fake(prompt_tokens=2050)  # the server processed only part of it
    with pytest.raises(ContextTruncated):
        _call(_ollama(client), [Block("claims", big)])


def test_a_full_prompt_passes_and_a_missing_usage_report_fails_closed() -> None:
    big = "evidence sentence about the harbor pilot. " * 900
    full = estimate_tokens("verify" + big)
    _call(_ollama(_Fake(prompt_tokens=int(full * 0.85))), [Block("claims", big)])
    _call(_ollama(_Fake(prompt_tokens=30)))  # short prompt: template overhead is not truncation
    with pytest.raises(
        ContextTruncated
    ):  # no usage: truncation cannot be ruled out, so fail closed
        _call(_ollama(_Fake(prompt_tokens=None)), [Block("claims", big)])


# --- configuration -------------------------------------------------------------------------------------------


def _env(**over: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "tvly-test",
        "NVIDIA_API_KEY": "nvapi-secret-value",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "ollama",
        "WRITER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        "VERIFIER_MODEL": "qwen3-vl:8b-instruct",
        "PRICE_SHEET_PATH": str(SHEET),
    }
    env.update(over)
    return env


def test_ollama_needs_no_key_and_defaults_to_the_local_endpoint_and_schema_mode() -> None:
    settings = load_settings(_env())
    assert startup_problems(settings) == []
    assert (
        settings.verifier_json_mode == "json_schema"
        and settings.verifier_token_param == "max_tokens"
    )
    assert settings.verifier_base_url == ""  # filled with the local default at build time
    assert "VERIFIER_API_KEY" not in startup_problems(load_settings(_env(NVIDIA_API_KEY="")))


def test_qwen_is_a_different_family_from_nemotron_and_the_check_still_applies() -> None:
    assert (
        model_family("qwen3-vl:8b-instruct")
        == "qwen"
        != model_family("nvidia/nemotron-3-ultra-550b-a55b")
    )
    same = _env(
        WRITER_PROVIDER="openai",
        OPENAI_API_KEY="k",
        WRITER_MODEL="qwen3-vl:4b-instruct",
        VERIFIER_MODEL="qwen3-vl:8b-instruct",
    )
    assert "VERIFIER_NOT_INDEPENDENT" in startup_problems(load_settings(same))


@pytest.mark.parametrize(
    ("over", "bad"),
    [
        (
            {"VERIFIER_BASE_URL": "http://192.168.1.20:11434/v1"},
            True,
        ),  # plain http off this machine
        (
            {"VERIFIER_BASE_URL": "https://ollama.example.org/v1"},
            True,
        ),  # evidence would leave this computer
        ({"VERIFIER_BASE_URL": "http://localhost:11434/v1"}, False),
        ({"VERIFIER_BASE_URL": "https://integrate.api.nvidia.com/v1"}, True),
        ({"VERIFIER_JSON_MODE": "grammar"}, True),
    ],
)
def test_ollama_endpoint_and_mode_validation(over: dict[str, str], bad: bool) -> None:
    problems = startup_problems(load_settings(_env(**over)))
    assert bool({"VERIFIER_BASE_URL", "VERIFIER_JSON_MODE"} & set(problems)) is bad


def test_the_ollama_verifier_is_built_with_a_dummy_key_never_the_nvidia_key() -> None:
    providers = build_live_providers(load_settings(_env()))
    verifier, writer = providers.verifier, providers.writer
    assert isinstance(verifier, OpenAICompatChat) and verifier.base_url == OLLAMA_BASE_URL
    assert verifier.json_mode == "json_schema" and verifier.check_truncation is True
    assert verifier._client.api_key == "ollama"
    assert "nvapi-secret-value" not in repr(verifier) + str(verifier._client.api_key)
    assert writer.base_url == NVIDIA_BASE_URL and writer._client.api_key == "nvapi-secret-value"


def test_the_about_page_says_verification_stays_on_this_computer() -> None:
    from service import describe_providers

    labels = " ".join(
        describe_providers(
            load_settings(_env()), ("nvidia/nemotron-3-ultra-550b-a55b", "qwen3-vl:8b-instruct")
        )
    )
    assert "Ollama" in labels and "this computer" in labels and "qwen3-vl:8b-instruct" in labels


def test_the_verifier_can_be_limited_to_one_request_at_a_time(tmp_path: Path) -> None:
    from core.settings import mode_config

    env = _env(VERIFIER_PARALLEL="1", STATE_DIR=str(tmp_path / "s"), LOG_DIR=str(tmp_path / "l"))
    assert startup_problems(load_settings(env)) == []
    assert "VERIFIER_PARALLEL" in startup_problems(load_settings(_env(VERIFIER_PARALLEL="0")))
    service = build_service(load_settings(env))
    ctx = service.new_context(
        ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="x"), lambda: False
    )
    assert ctx.cfg.verifier_parallel == 1 and mode_config(Mode.QUICK).verifier_parallel == 4
    service.shutdown()


# --- a failing local verifier never falls back to NVIDIA ---------------------------------------------------------


class _Writer:
    """Scripted NVIDIA SDK: answers planner and writer schemas, records every schema it was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self._brain = FakeLLM("scripted")
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw: Any) -> SimpleNamespace:
        import re

        from core.models import LedgerDraft, Plan

        system, user = kw["messages"][0]["content"], kw["messages"][1]["content"]
        schemas = {"Plan": Plan, "LedgerDraft": LedgerDraft, "VerifierOutput": VerifierOutput}
        name = next(n for n in schemas if f'"title":"{n}"' in system)
        self.asked.append(name)
        blocks = {
            m.group(1): m.group(2)
            for m in re.finditer(r'<data label="(.*?)">\n(.*?)\n</data>', user, re.DOTALL)
        }
        parsed = self._brain._handlers[schemas[name]](CallContext(system, blocks, 0))
        text = parsed.model_dump_json()
        msg = SimpleNamespace(content=text, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="stop")],
            usage=SimpleNamespace(
                prompt_tokens=estimate_tokens(system + user),
                completion_tokens=estimate_tokens(text),
            ),
            model=kw["model"],
        )


def test_when_the_local_verifier_is_down_the_run_fails_closed_and_nvidia_never_verifies(
    tmp_path: Path,
) -> None:
    import openai

    settings = load_settings(_env(STATE_DIR=str(tmp_path / "s"), LOG_DIR=str(tmp_path / "l")))
    nvidia = _Writer()
    down = _Fake(
        error=openai.APIConnectionError(
            request=__import__("httpx").Request("POST", OLLAMA_BASE_URL)
        )
    )
    kw: dict[str, Any] = dict(token_param="max_tokens", send_temperature=True, json_mode="none")
    providers = Providers(
        search=FakeSearch(),
        writer=OpenAICompatChat(
            SecretStr("nvapi-x"),
            settings.writer_model,
            client=nvidia,
            base_url=NVIDIA_BASE_URL,
            **kw,
        ),
        verifier=_ollama(down),
        writer_model=settings.writer_model,
        verifier_model=settings.verifier_model,
    )
    service = build_service(settings, providers=providers)
    request = ResearchRequest(topic=DEMO_TOPIC, depth=Mode.QUICK, idempotency_token="t")
    ctx = service.new_context(request, lambda: False)
    result = run_research(ctx, request, run_id="r")
    assert (
        result.status is RunStatus.FAILED and result.error_code == ErrorCode.VERIFIER_FAILED.value
    )
    assert result.report_markdown is None
    assert "VerifierOutput" not in nvidia.asked  # no silent fallback to the writer's endpoint
    assert result.detail in {"ProviderServerError", "ProviderCircuitOpen"}
    service.shutdown()


def test_a_connection_failure_is_a_provider_error_and_a_truncation_stops_the_run(
    tmp_path: Path,
) -> None:
    from core.errors import ProviderError

    assert issubclass(ContextTruncated, ProviderError) and issubclass(
        ProviderServerError, ProviderError
    )
