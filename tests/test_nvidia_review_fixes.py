"""Regression tests for the review of the NVIDIA Build change set (see docs/build-ledger.md)."""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from core.capacity import BudgetLedger, CallGuard, Deadline, ProviderGate, TokenBucket
from core.errors import DeadlineExceeded, ErrorCode, ProviderServerError
from core.models import Mode, ResearchRequest
from core.settings import load_settings, model_family, startup_problems
from service import build_service, make_gates

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "core" / "price_sheet_nvidia_free.json"


def _env(tmp_path: Path | None = None, **over: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "tvly",
        "NVIDIA_API_KEY": "nvapi-test",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "nvidia",
        "WRITER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        "VERIFIER_MODEL": "google/gemma-4-31b-it",
        "PRICE_SHEET_PATH": str(SHEET),
    }
    if tmp_path is not None:
        env.update(STATE_DIR=str(tmp_path / "state"), LOG_DIR=str(tmp_path / "logs"))
    env.update(over)
    return env


# --- #1 model families -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("writer", "verifier"),
    [
        ("nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.1-70b-instruct"),
        ("nv-mistralai/mistral-nemo-12b-instruct", "mistralai/mistral-7b-instruct"),
        ("microsoft/phi-4", "phi-4"),
        ("nvidia/nemotron-3-ultra-550b-a55b", "nemotron-mini"),
        ("openai/gpt-oss-20b:free", "gpt-5"),
        ("ollama/llama3", "meta-llama/Llama-3.3-70B-Instruct"),
        ("anthropic/claude-3-haiku", "claude-sonnet-5-5"),
    ],
)
def test_same_family_pairs_are_refused_whatever_the_hosting_prefix(
    writer: str, verifier: str
) -> None:
    assert model_family(writer) == model_family(verifier)
    problems = startup_problems(load_settings(_env(WRITER_MODEL=writer, VERIFIER_MODEL=verifier)))
    assert "VERIFIER_NOT_INDEPENDENT" in problems


@pytest.mark.parametrize(
    ("writer", "verifier"),
    [
        ("nvidia/nemotron-3-ultra-550b-a55b", "google/gemma-4-31b-it"),
        ("gpt-5", "claude-sonnet-5-5"),
        ("meta/llama-3.1-70b-instruct", "google/gemma-4-31b-it"),
        ("openai/gpt-oss-20b", "meta/llama-3.3-70b-instruct"),
    ],
)
def test_genuinely_different_families_are_accepted(writer: str, verifier: str) -> None:
    assert model_family(writer) != model_family(verifier)


# --- #2 a key is only ever sent to a matching host ------------------------------------------------------


@pytest.mark.parametrize(
    ("over", "problem"),
    [
        (
            {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1"},
            "OPENAI_BASE_URL",
        ),  # nvidia key, wrong host
        ({"VERIFIER_BASE_URL": "https://example.org/v1"}, "VERIFIER_BASE_URL"),
        (
            {
                "WRITER_PROVIDER": "openai",
                "OPENAI_API_KEY": "sk",
                "OPENAI_BASE_URL": "https://integrate.api.nvidia.com/v1",
            },
            "OPENAI_BASE_URL",  # openai key would go to nvidia
        ),
        (
            {
                "VERIFIER_PROVIDER": "openai",
                "VERIFIER_API_KEY": "k",
                "VERIFIER_BASE_URL": "https://integrate.api.nvidia.com/v1",
            },
            "VERIFIER_BASE_URL",
        ),
    ],
)
def test_a_key_cannot_be_sent_to_the_other_providers_host(
    over: dict[str, str], problem: str
) -> None:
    assert problem in startup_problems(load_settings(_env(**over)))


@pytest.mark.parametrize(
    "over",
    [
        {
            "OPENAI_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "VERIFIER_BASE_URL": "https://integrate.api.nvidia.com/v1",
        },
        {"OPENAI_BASE_URL": "http://localhost:8000/v1"},  # self-hosted NIM
        {
            "WRITER_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            "WRITER_MODEL": "openai/gpt-oss-20b",
        },
    ],
)
def test_matching_and_local_hosts_are_accepted(over: dict[str, str]) -> None:
    problems = startup_problems(load_settings(_env(**over)))
    assert "OPENAI_BASE_URL" not in problems and "VERIFIER_BASE_URL" not in problems


def test_env_example_uses_only_openai_and_keeps_the_load_modest() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "WRITER_PROVIDER=openai" in text
    assert "VERIFIER_PROVIDER=openai" in text
    assert "SEARCH_PROVIDER=openai" in text
    assert "NVIDIA_API_KEY=" not in text and "SEARCH_API_KEY=" not in text
    values = {
        k: v
        for k, _, v in (
            line.partition("=")
            for line in text.splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    assert int(values["MAX_CONCURRENT_RUNS"]) <= 2


# --- #3 a free-prototype sheet must expire and keep non-zero budgeting rates -----------------------------


def _sheet(tmp_path: Path, **over: object) -> str:
    data: dict[str, object] = json.loads(SHEET.read_text(encoding="utf-8"))
    data.update(over)
    path = tmp_path / "sheet.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_free_sheet_without_a_review_date_or_with_zero_rates_is_refused(tmp_path: Path) -> None:
    no_date = load_settings(_env(PRICE_SHEET_PATH=_sheet(tmp_path, review_after=None)))
    assert "PRICE_SHEET_NO_REVIEW_DATE" in startup_problems(no_date)
    zero = _sheet(
        tmp_path,
        models={
            "nvidia/nemotron-3-ultra-550b-a55b": {"in_per_m": 0.0, "out_per_m": 0.0},
            "google/gemma-4-31b-it": {"in_per_m": 0.0, "out_per_m": 0.0},
        },
    )
    assert "PRICE_SHEET_ZERO_RATES" in startup_problems(load_settings(_env(PRICE_SHEET_PATH=zero)))


def test_a_malformed_or_missing_sheet_is_a_named_problem_not_a_crash(tmp_path: Path) -> None:
    bad_date = load_settings(_env(PRICE_SHEET_PATH=_sheet(tmp_path, review_after="soon")))
    assert "PRICE_SHEET_INVALID" in startup_problems(bad_date)
    missing = load_settings(_env(PRICE_SHEET_PATH=str(tmp_path / "nope.json")))
    assert "PRICE_SHEET_INVALID" in startup_problems(missing)
    assert (
        startup_problems(
            load_settings(
                _env(RESEARCH_PROVIDER_MODE="fake", PRICE_SHEET_PATH=str(tmp_path / "nope.json"))
            )
        )
        == []
    )


def test_a_running_service_stops_admitting_runs_once_the_sheet_expires(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path)), today=lambda: date(2026, 10, 22))
    assert service.ready
    request = ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="a")
    service.today = lambda: date(2035, 1, 1)
    assert service.submit("s", request).error is ErrorCode.CONFIG_INVALID
    service.shutdown()


# --- #4 the UI says why the service refused to start -----------------------------------------------------


def test_startup_problems_are_shown_by_name_and_secrets_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in _env(tmp_path, NVIDIA_API_KEY="").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-appear")
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    text = "\n".join(m.value for m in at.markdown) + "\n".join(c.value for c in at.caption)
    assert "NVIDIA_API_KEY" in text and "not configured correctly" in text
    assert "sk-must-not-appear" not in text and "tvly" not in text


# --- #5 limiter and breaker --------------------------------------------------------------------------------


def test_waiting_for_the_limiter_never_holds_its_lock() -> None:
    state: dict[str, bool] = {}
    holder: list[TokenBucket] = []

    def sleep(seconds: float) -> None:
        free = holder[0]._lock.acquire(blocking=False)
        state["lock_free_while_sleeping"] = free
        if free:
            holder[0]._lock.release()

    bucket = TokenBucket(1.0, 1, clock=lambda: 0.0, sleep=sleep)
    holder.append(bucket)
    bucket.acquire()
    bucket.acquire()  # must wait about one second
    assert state["lock_free_while_sleeping"] is True


def test_a_wait_longer_than_the_deadline_is_refused_without_spending_a_slot_or_budget() -> None:
    bucket = TokenBucket(0.1, 1, clock=lambda: 0.0, sleep=lambda s: None)
    bucket.acquire()
    with pytest.raises(DeadlineExceeded):
        bucket.acquire(max_wait=1.0)
    gate = ProviderGate("w", 0.1, 1, bucket=bucket)
    guard = CallGuard(
        ledger=BudgetLedger(1.0, {}),
        deadline=Deadline(1.0),
        is_cancelled=lambda: False,
        gates={"w": gate},
        sleep=lambda s: None,
        jitter=lambda u: 0.0,
    )
    with pytest.raises(DeadlineExceeded):
        guard.call(
            stage="s",
            provider="w",
            fn=lambda t: "x",
            est_cost_usd=0.1,
            actual_cost=lambda r: 0.1,
            per_call_timeout_s=5,
        )
    assert guard.ledger.pool_remaining == pytest.approx(1.0) and guard.ledger.committed_usd == 0


def test_nvidia_roles_share_one_rate_limit_but_keep_separate_breakers() -> None:
    gates = make_gates(load_settings(_env()))
    assert gates["writer"] is not gates["verifier"]
    assert gates["writer"]._bucket is gates["verifier"]._bucket
    for _ in range(5):
        gates["verifier"].record_failure()
    with pytest.raises(ProviderServerError):
        gates["verifier"].before_call()
    gates["writer"].before_call()  # an outage seen by the verifier does not close the writer


def test_the_shared_limiter_serves_concurrent_callers_without_deadlock() -> None:
    bucket = TokenBucket(1000.0, 2)
    done: list[int] = []

    def work() -> None:
        for _ in range(10):
            bucket.acquire()
        done.append(1)

    threads = [threading.Thread(target=work) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert len(done) == 5
