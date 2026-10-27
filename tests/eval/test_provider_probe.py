from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from adapters.live import OpenAICompatChat
from core.errors import ProviderAuthError, SchemaViolation
from eval.provider_probe import main, probe_llm

GOOD_SUPPORTED = json.dumps(
    {"results": [{"claim_id": "p1", "verdict": "supported", "reason": "ok"}]}
)
GOOD_UNSUPPORTED = json.dumps(
    {"results": [{"claim_id": "p2", "verdict": "unsupported", "reason": "no"}]}
)


class _Client:
    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = list(replies)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: object) -> SimpleNamespace:
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=reply, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            model="m",
        )


def _chat(replies: list[str | Exception]) -> OpenAICompatChat:
    return OpenAICompatChat(SecretStr("k"), "m", client=_Client(replies), json_mode="none")


def test_probe_reports_parse_usage_and_verdict_quality() -> None:
    report = probe_llm(_chat([GOOD_SUPPORTED, GOOD_UNSUPPORTED]), label="verifier")
    assert report["label"] == "verifier"
    assert report["json_parses"] is True and report["usage_reported"] is True
    assert (
        report["supported_claim_accepted"] is True and report["contradicted_claim_rejected"] is True
    )
    assert report["errors"] == []


def test_probe_reports_only_error_class_names_never_messages_or_keys() -> None:
    report = probe_llm(
        _chat([SchemaViolation("secret detail nvapi-123"), ProviderAuthError("bad key nvapi-123")]),
        label="writer",
    )
    assert report["json_parses"] is False
    assert report["errors"] == ["SchemaViolation", "ProviderAuthError"]
    assert "nvapi" not in json.dumps(report)


def test_probe_flags_a_model_that_accepts_a_contradicted_claim() -> None:
    bad = json.dumps({"results": [{"claim_id": "p2", "verdict": "supported", "reason": "x"}]})
    report = probe_llm(_chat([GOOD_SUPPORTED, bad]), label="verifier")
    assert report["contradicted_claim_rejected"] is False


def test_the_command_refuses_to_call_providers_without_an_explicit_flag(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESEARCH_PROVIDER_MODE", "live")
    assert main([]) == 2
    assert "--yes-call-live-providers" in capsys.readouterr().err


def test_the_command_needs_live_mode_even_with_the_flag(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESEARCH_PROVIDER_MODE", "fake")
    assert main(["--yes-call-live-providers"]) == 1
    assert "live" in capsys.readouterr().err
