"""Fixes that came from running against the live NVIDIA free endpoint (2026-10-22)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adapters.fakes import FakeLLM
from core.capacity import BudgetLedger, CallGuard, Deadline, ProviderGate
from core.errors import DeadlineExceeded, ProviderServerError, ProviderTimeout
from core.models import Mode, ResearchRequest, VerifierOutput
from core.research_agent import run_research
from core.settings import load_settings, mode_config, scaled_config, startup_problems
from service import build_service

ROOT = Path(__file__).resolve().parents[1]


# --- a timeout that happens because the run's time ran out is a TIMEOUT, not a provider failure ----


def test_a_provider_timeout_after_the_deadline_is_reported_as_the_deadline() -> None:
    now = {"t": 0.0}
    guard = CallGuard(
        ledger=BudgetLedger(1.0, {}),
        deadline=Deadline(10.0, clock=lambda: now["t"]),
        is_cancelled=lambda: False,
        gates={"w": ProviderGate("w", 1000.0, 1000, sleep=lambda s: None)},
        sleep=lambda s: None,
        jitter=lambda u: 0.0,
    )

    def stalls(timeout: float) -> str:
        now["t"] += timeout + 1  # the call used up everything that was left
        raise ProviderTimeout("slow")

    with pytest.raises(DeadlineExceeded):
        guard.call(
            stage="s",
            provider="w",
            fn=stalls,
            est_cost_usd=0.1,
            actual_cost=lambda r: 0.1,
            per_call_timeout_s=60,
        )
    assert guard.ledger.pool_remaining == pytest.approx(1.0)


def test_a_run_that_runs_out_of_time_while_verifying_ends_as_timeout(make_ctx) -> None:
    from core.models import RunStatus

    ctx = make_ctx(wall_s=1000.0)
    ticks = {"n": 0}
    real_expired = ctx.guard.deadline.expired

    def expired_after_verifier_starts() -> bool:
        return ticks["n"] > 0 or real_expired()

    verifier = FakeLLM("fake-verifier")

    def stall(c):  # noqa: ANN001
        ticks["n"] += 1
        raise ProviderTimeout("slow")

    verifier.set_handler(VerifierOutput, stall)
    ctx.verifier = verifier
    ctx.guard.deadline.expired = expired_after_verifier_starts  # type: ignore[method-assign]
    result = run_research(
        ctx,
        ResearchRequest(
            topic="Harborview bike share pilot", depth=Mode.QUICK, idempotency_token="t"
        ),
        run_id="r",
    )
    assert result.status is RunStatus.FAILED and result.error_code == "TIMEOUT"


# --- the failure detail (an exception class name, never a message) is kept and shown ------------------------


def test_a_failed_run_keeps_the_provider_error_class_as_detail(make_ctx) -> None:
    verifier = FakeLLM("fake-verifier")

    def down(c):  # noqa: ANN001
        raise ProviderServerError("secret body text")

    verifier.set_handler(VerifierOutput, down)
    ctx = make_ctx(verifier=verifier)
    result = run_research(
        ctx,
        ResearchRequest(
            topic="Harborview bike share pilot", depth=Mode.QUICK, idempotency_token="t"
        ),
        run_id="r",
    )
    assert result.error_code == "VERIFIER_FAILED"
    assert result.detail == "ProviderServerError" and "secret" not in (result.detail or "")


def test_the_page_shows_the_failure_detail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import time

    import streamlit as st

    monkeypatch.setenv("RESEARCH_PROVIDER_MODE", "fake")
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "l"))
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    at.text_area(key="topic:input").set_value("AI in surfactants discovery")  # demo: no evidence
    [b for b in at.button if b.label == "Research"][0].click()
    at.run()
    for _ in range(60):
        if any("FAILED" in m.value for m in at.markdown):
            break
        time.sleep(0.5)
        at.run()
    captions = "\n".join(c.value for c in at.caption)
    assert "Detail: NO_EVIDENCE" in captions


# --- an operator override for slow endpoints ---------------------------------------------------------------


def test_run_time_factor_scales_only_the_wall_clock() -> None:
    cfg = mode_config(Mode.QUICK)
    scaled = scaled_config(cfg, 2.0)
    assert scaled.wall_clock_s == cfg.wall_clock_s * 2
    assert scaled.cost_cap_usd == cfg.cost_cap_usd and scaled.max_claims == cfg.max_claims
    assert scaled_config(cfg, 1.0) is cfg


def test_run_time_factor_is_validated_and_defaults_to_one() -> None:
    env = {"RESEARCH_PROVIDER_MODE": "live"}
    assert load_settings(env).run_time_factor == 1.0
    assert load_settings({"RUN_TIME_FACTOR": "2"}).run_time_factor == 2.0
    for bad in ("0", "-1", "20"):
        assert "RUN_TIME_FACTOR" in startup_problems(load_settings({**env, "RUN_TIME_FACTOR": bad}))


def test_the_service_gives_every_run_the_scaled_time_and_the_page_says_so(tmp_path: Path) -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "fake",
        "STATE_DIR": str(tmp_path / "s"),
        "LOG_DIR": str(tmp_path / "l"),
        "RUN_TIME_FACTOR": "2",
    }
    service = build_service(load_settings(env))
    ctx = service.new_context(
        ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="x"), lambda: False
    )
    assert ctx.cfg.wall_clock_s == 240
    assert ctx.guard.deadline.remaining() > 200
    service.shutdown()
    from ui.state import depth_caption

    assert "4 minutes" in depth_caption(Mode.QUICK, run_time_factor=2.0)
    assert "2 minutes" in depth_caption(Mode.QUICK)


def test_env_example_keeps_the_prd_time_limits_and_openai_parallelism() -> None:
    from core.settings import parse_env_file

    values = parse_env_file(ROOT / ".env.example")
    assert float(values["RUN_TIME_FACTOR"]) == 1.0  # PRD NFR-03: Quick 120 s, Deep 360 s
    assert values["VERIFIER_PARALLEL"] == "1"
