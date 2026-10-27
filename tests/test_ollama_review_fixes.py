"""Regression tests for the review of the local Ollama verifier change set (see docs/build-ledger.md)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from adapters.base import Block
from adapters.live import OLLAMA_BASE_URL, OpenAICompatChat
from core.errors import ContextTruncated, ErrorCode, PipelineFailure
from core.models import ResearchRequest, VerifierOutput
from core.settings import load_settings, startup_problems
from service import describe_providers
from ui import copy as ui_copy

ROOT = Path(__file__).resolve().parents[1]
GOOD = json.dumps({"results": [{"claim_id": "c1", "verdict": "supported", "reason": "ok"}]})


class _Fake:
    def __init__(
        self, prompt_tokens: int | None, completion_tokens: int = 100, content: str = GOOD
    ) -> None:
        self.calls = 0
        self._p, self._c, self._content = prompt_tokens, completion_tokens, content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw: Any) -> SimpleNamespace:
        self.calls += 1
        usage = (
            None
            if self._p is None
            else SimpleNamespace(prompt_tokens=self._p, completion_tokens=self._c)
        )
        msg = SimpleNamespace(content=self._content, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=usage, model="m"
        )


def _chat(client: _Fake, context_tokens: int = 8192) -> OpenAICompatChat:
    return OpenAICompatChat(
        SecretStr("ollama"),
        "qwen3-vl:8b-instruct",
        client=client,
        base_url=OLLAMA_BASE_URL,
        token_param="max_tokens",
        json_mode="json_schema",
        send_temperature=True,
        check_truncation=True,
        context_tokens=context_tokens,
    )


def _call(chat: OpenAICompatChat, text: str = "x", max_out: int = 800) -> Any:
    return chat.generate(
        system="verify",
        blocks=[Block("claims", text)],
        schema=VerifierOutput,
        max_output_tokens=max_out,
        temperature=0.0,
        timeout_s=30,
    )


BIG = "evidence sentence about the harbor pilot. " * 700  # about 8,400 estimated tokens


# --- #1 the truncation guard knows the server's context window ------------------------------------------------


def test_a_prompt_that_cannot_fit_the_context_is_refused_before_any_request() -> None:
    client = _Fake(prompt_tokens=3000)
    with pytest.raises(ContextTruncated):
        _call(
            _chat(client, context_tokens=4096), BIG
        )  # about 5,000 tokens at least, plus 800 of output
    assert client.calls == 0  # no generation time is wasted on a call that cannot be trusted


def test_prompt_plus_output_reaching_the_window_means_context_shift_and_fails_closed() -> None:
    small = "short evidence. " * 200  # about 1,000 tokens, fits easily
    with pytest.raises(ContextTruncated):
        _call(_chat(_Fake(prompt_tokens=3837, completion_tokens=248), context_tokens=4096), small)
    _call(
        _chat(_Fake(prompt_tokens=3000, completion_tokens=248), context_tokens=4096), small
    )  # 3248 of 4096: fine


def test_a_window_big_enough_for_the_prd_batch_passes() -> None:
    est_prompt_tokens = 7000  # the PRD's Quick verifier batch cap
    reported = int(est_prompt_tokens * 0.85)
    text = "e" * int(est_prompt_tokens * 3.5)
    _call(_chat(_Fake(prompt_tokens=reported, completion_tokens=250), context_tokens=8192), text)


def test_missing_usage_cannot_be_checked_so_it_fails_closed_for_a_large_prompt() -> None:
    with pytest.raises(ContextTruncated):
        _call(_chat(_Fake(prompt_tokens=None), context_tokens=8192), BIG)
    _call(_chat(_Fake(prompt_tokens=None), context_tokens=8192))  # a tiny prompt needs no check


def test_context_length_is_a_validated_setting_that_reaches_the_adapter() -> None:
    from adapters.live import build_live_providers

    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "s",
        "NVIDIA_API_KEY": "k",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "ollama",
        "WRITER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        "VERIFIER_MODEL": "qwen3-vl:8b-instruct",
        "PRICE_SHEET_PATH": str(ROOT / "core" / "price_sheet_nvidia_free.json"),
    }
    assert load_settings(env).verifier_context_tokens == 4096  # Ollama's own default
    assert load_settings({**env, "VERIFIER_CONTEXT_TOKENS": "8192"}).verifier_context_tokens == 8192
    for bad in ("100", "0", "9999999"):
        assert "VERIFIER_CONTEXT_TOKENS" in startup_problems(
            load_settings({**env, "VERIFIER_CONTEXT_TOKENS": bad})
        )
    verifier = build_live_providers(
        load_settings({**env, "VERIFIER_CONTEXT_TOKENS": "8192"})
    ).verifier
    assert verifier.context_tokens == 8192  # type: ignore[attr-defined]


def test_the_failure_is_a_single_attempt_that_ends_the_run_as_verifier_failed(make_ctx) -> None:
    from core.models import ClaimRecord, EvidenceMode, EvidenceRef, Passage, SourceRecord
    from pipeline.verifier import verify_claims

    client = _Fake(prompt_tokens=2050)  # the server cut a long prompt
    chat = _chat(client, context_tokens=65536)
    ctx = make_ctx(cap_usd=100.0)
    ctx.verifier = chat  # type: ignore[assignment]
    text = "The harbor pilot launched with 120 bikes. " * 400
    src = SourceRecord(
        citation_id=1,
        title="t",
        url="https://a.example.org/x",
        canonical_url="https://a.example.org/x",
        registrable_domain="a.example.org",
        retrieved_at="2026-10-22T00:00:00Z",
        evidence_mode=EvidenceMode.EXTRACTED,
        passages=[Passage(passage_id="1:p1", text=text)],
        evidence_group_id="g",
    )
    claim = ClaimRecord(
        claim_id="c1",
        text="The pilot launched with 120 bikes.",
        facet_id="f1",
        section="findings",
        evidence=[
            EvidenceRef(
                citation_id=1, passage_id="1:p1", quote="The harbor pilot launched with 120 bikes."
            )
        ]
        * 3,
    )
    with pytest.raises(PipelineFailure) as err:
        verify_claims(ctx, [claim], {1: src})
    assert err.value.code is ErrorCode.VERIFIER_FAILED and err.value.detail == "ContextTruncated"
    assert client.calls == 1  # never retried


def test_the_page_tells_the_operator_how_to_fix_a_truncated_context() -> None:
    message = ui_copy.failure_message("VERIFIER_FAILED", "ContextTruncated")
    assert "context" in message.lower() and "OLLAMA_CONTEXT_LENGTH" in message
    assert "Try again in a moment" not in message
    assert (
        "checking service failed"
        in ui_copy.failure_message("VERIFIER_FAILED", "ProviderTimeout").lower()
    )


# --- #4 a local verifier is local, and the About page says exactly where data goes --------------------------------


def _env(**over: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "s",
        "NVIDIA_API_KEY": "k",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "ollama",
        "WRITER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        "VERIFIER_MODEL": "qwen3-vl:8b-instruct",
        "PRICE_SHEET_PATH": str(ROOT / "core" / "price_sheet_nvidia_free.json"),
    }
    env.update(over)
    return env


@pytest.mark.parametrize(
    ("url", "bad"),
    [
        (
            "https://ollama.example.com/v1",
            True,
        ),  # evidence would leave the machine while the page says local
        ("https://integrate.api.nvidia.com/v1", True),
        ("http://192.168.1.20:11434/v1", True),
        ("http://localhost:11434/v1", False),
        ("http://127.0.0.1:11434/v1", False),
        ("", False),
    ],
)
def test_the_ollama_provider_must_point_at_this_computer(url: str, bad: bool) -> None:
    assert (
        "VERIFIER_BASE_URL" in startup_problems(load_settings(_env(VERIFIER_BASE_URL=url)))
    ) is bad


def test_the_about_page_names_what_nvidia_receives_and_what_stays_local() -> None:
    text = " ".join(
        describe_providers(
            load_settings(_env()), ("nvidia/nemotron-3-ultra-550b-a55b", "qwen3-vl:8b-instruct")
        )
    )
    assert "NVIDIA Build" in text and "topic" in text and "passages" in text
    assert "this computer" in text and "qwen3-vl:8b-instruct" in text
    assert (
        "not sent to a third party" not in text
    )  # the old wording was wrong for the default setup


def test_the_env_example_validates_with_only_the_openai_key() -> None:
    from core.settings import parse_env_file

    values = parse_env_file(ROOT / ".env.example")
    live = dict(
        values,
        RESEARCH_PROVIDER_MODE="live",
        OPENAI_API_KEY="k",
        PRICE_SHEET_PATH=str(ROOT / values["PRICE_SHEET_PATH"]),
    )
    assert startup_problems(load_settings(live)) == []
    assert "VERIFIER_CONTEXT_TOKENS" not in values


_ = ResearchRequest  # keep the import used for type readers
