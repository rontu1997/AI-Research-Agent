import json
from datetime import date
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.capacity import (
    BudgetLedger,
    CallGuard,
    DailySpendGuard,
    Deadline,
    ProviderGate,
    TokenBucket,
    check_call_graph,
)
from core.errors import (
    BudgetStop,
    DeadlineExceeded,
    ErrorCode,
    PipelineFailure,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderRateLimit,
    ProviderServerError,
    ProviderTimeout,
    RunCancelled,
    SchemaViolation,
)
from core.models import Mode
from core.settings import PriceSheet, load_settings, mode_config


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


# --- budget ledger -----------------------------------------------------------------------------


def _ledger(cap: float = 1.0, base: dict[str, float] | None = None) -> BudgetLedger:
    return BudgetLedger(cap_usd=cap, base_by_stage=base or {"writer": 0.3, "search": 0.1})


def test_pool_is_the_cap_minus_all_base_reservations() -> None:
    ledger = _ledger(1.0, {"writer": 0.3, "search": 0.1})
    assert ledger.pool_remaining == pytest.approx(0.6)


def test_first_attempt_draws_on_its_stage_base_first() -> None:
    ledger = _ledger()
    res = ledger.reserve("writer", 0.2, attempt=1)
    assert res.from_base == pytest.approx(0.2)
    assert res.from_pool == 0
    assert ledger.base_remaining["writer"] == pytest.approx(0.1)
    assert ledger.pool_remaining == pytest.approx(0.6)


def test_base_overflow_spills_into_the_pool() -> None:
    ledger = _ledger()
    res = ledger.reserve("search", 0.25, attempt=1)
    assert res.from_base == pytest.approx(0.1)
    assert res.from_pool == pytest.approx(0.15)


def test_retries_and_pool_only_stages_draw_on_the_pool() -> None:
    ledger = _ledger()
    retry = ledger.reserve("writer", 0.1, attempt=2)
    assert retry.from_base == 0 and retry.from_pool == pytest.approx(0.1)
    repair = ledger.reserve("repair", 0.1, attempt=1)
    assert repair.from_base == 0 and repair.from_pool == pytest.approx(0.1)


def test_reservation_beyond_what_is_left_raises_budget_stop() -> None:
    ledger = _ledger(0.5, {"writer": 0.1})
    with pytest.raises(BudgetStop):
        ledger.reserve("writer", 0.6, attempt=1)
    assert ledger.pool_remaining == pytest.approx(0.4)  # a refused reservation changes nothing


def test_commit_refunds_the_unused_part_to_where_it_came_from() -> None:
    ledger = _ledger()
    res = ledger.reserve("search", 0.25, attempt=1)  # 0.1 base + 0.15 pool
    ledger.commit(res, actual_usd=0.05)
    assert ledger.committed_usd == pytest.approx(0.05)
    assert ledger.base_remaining[
        "search"
    ] + ledger.pool_remaining + ledger.committed_usd == pytest.approx(0.1 + 0.6)


def test_release_returns_everything() -> None:
    ledger = _ledger()
    res = ledger.reserve("writer", 0.2, attempt=1)
    ledger.release(res)
    assert ledger.base_remaining["writer"] == pytest.approx(0.3)
    assert ledger.pool_remaining == pytest.approx(0.6)
    assert ledger.committed_usd == 0


def test_unknown_cost_charges_the_reserved_ceiling_and_flags_it() -> None:
    ledger = _ledger()
    res = ledger.reserve("writer", 0.2, attempt=1)
    ledger.commit(res, actual_usd=None)
    assert ledger.committed_usd == pytest.approx(0.2)
    assert ledger.unknown_cost is True


def test_an_overrun_is_recorded_not_hidden() -> None:
    ledger = _ledger()
    res = ledger.reserve("writer", 0.1, attempt=1)
    ledger.commit(res, actual_usd=0.15)
    assert ledger.committed_usd == pytest.approx(0.15)
    assert ledger.overrun_usd == pytest.approx(0.05)


@settings(
    suppress_health_check=[HealthCheck.too_slow], deadline=None
)  # timing only; assertions unchanged
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["writer", "search", "repair", "planner"]),
            st.floats(min_value=0.001, max_value=0.3),
            st.integers(min_value=1, max_value=3),
            st.floats(min_value=0.0, max_value=1.0),
        ),
        max_size=25,
    )
)
def test_money_is_conserved_under_any_sequence_of_reserve_and_commit(
    ops: list[tuple[str, float, int, float]],
) -> None:
    cap = 2.0
    ledger = BudgetLedger(cap_usd=cap, base_by_stage={"writer": 0.4, "search": 0.2})
    for stage, amount, attempt, fraction in ops:
        try:
            res = ledger.reserve(stage, amount, attempt)
        except BudgetStop:
            continue
        ledger.commit(res, actual_usd=amount * fraction)
        total = sum(ledger.base_remaining.values()) + ledger.pool_remaining + ledger.committed_usd
        assert total == pytest.approx(cap, abs=1e-9)


# --- call-graph startup check (FR-37) ----------------------------------------------------------

PLACEHOLDER = PriceSheet("p", True, 1.25, {"w": (2.5, 10.0), "v": (0.3, 1.2)}, 0.016)


def test_quick_call_graph_matches_the_prd_figures() -> None:
    r = check_call_graph(mode_config(Mode.QUICK), PLACEHOLDER, "w", "v")
    assert r.verifier_batches == 4
    assert r.repair_batches == 2
    assert r.base_total == pytest.approx(0.177, abs=0.002)
    assert r.pool == pytest.approx(0.573, abs=0.002)
    assert r.worst_case_total == pytest.approx(0.724, abs=0.003)
    assert r.condition_i and r.condition_ii and r.ok


def test_deep_call_graph_matches_the_prd_figures() -> None:
    r = check_call_graph(mode_config(Mode.DEEP), PLACEHOLDER, "w", "v")
    assert r.verifier_batches == 9
    assert r.repair_batches == 3
    assert r.base_total == pytest.approx(0.421, abs=0.003)
    assert r.worst_case_total == pytest.approx(1.544, abs=0.005)
    assert r.ok


def test_a_writer_priced_twice_as_high_makes_quick_fail_but_not_deep() -> None:
    pricey = PriceSheet("p", True, 1.25, {"w": (5.0, 20.0), "v": (0.3, 1.2)}, 0.016)
    quick = check_call_graph(mode_config(Mode.QUICK), pricey, "w", "v")
    assert not quick.ok
    assert quick.condition_i and not quick.condition_ii
    assert check_call_graph(mode_config(Mode.DEEP), pricey, "w", "v").ok


def test_an_unpriced_model_is_a_config_error() -> None:
    with pytest.raises(PipelineFailure) as exc:
        check_call_graph(mode_config(Mode.QUICK), PLACEHOLDER, "unknown", "v")
    assert exc.value.code is ErrorCode.CONFIG_INVALID


def test_the_base_reservations_per_stage_add_up_to_the_base_total() -> None:
    r = check_call_graph(mode_config(Mode.QUICK), PLACEHOLDER, "w", "v")
    assert sum(r.base_by_stage.values()) == pytest.approx(r.base_total)
    assert set(r.base_by_stage) == {"planner", "search", "writer", "verifier", "scan"}


# --- deadline, token bucket, gate ----------------------------------------------------------------


def test_deadline_counts_down_with_the_clock() -> None:
    clock = FakeClock()
    d = Deadline(10.0, clock=clock.time)
    assert d.remaining() == pytest.approx(10.0)
    clock.now += 4
    assert d.remaining() == pytest.approx(6.0)
    clock.now += 7
    assert d.expired()
    assert d.remaining() == 0.0


def test_token_bucket_allows_a_burst_then_waits() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_s=2.0, burst=2, clock=clock.time, sleep=clock.sleep)
    bucket.acquire()
    bucket.acquire()
    assert clock.sleeps == []
    bucket.acquire()
    assert clock.sleeps and clock.sleeps[0] == pytest.approx(0.5)


# --- call guard --------------------------------------------------------------------------------


def _guard(
    clock: FakeClock,
    *,
    cap: float = 1.0,
    deadline_s: float = 100.0,
    cancelled: bool = False,
) -> tuple[CallGuard, BudgetLedger]:
    ledger = BudgetLedger(cap_usd=cap, base_by_stage={"writer": 0.4})
    gate = ProviderGate("p", rate_per_s=1000, burst=1000, clock=clock.time, sleep=clock.sleep)
    guard = CallGuard(
        ledger=ledger,
        deadline=Deadline(deadline_s, clock=clock.time),
        is_cancelled=lambda: cancelled,
        gates={"p": gate},
        sleep=clock.sleep,
        jitter=lambda upper: upper,  # deterministic: full upper bound
    )
    return guard, ledger


def test_a_successful_call_commits_the_actual_cost() -> None:
    clock = FakeClock()
    guard, ledger = _guard(clock)
    out = guard.call(
        stage="writer",
        provider="p",
        fn=lambda timeout: "ok",
        est_cost_usd=0.2,
        actual_cost=lambda _r: 0.05,
        per_call_timeout_s=30,
    )
    assert out == "ok"
    assert ledger.committed_usd == pytest.approx(0.05)


def test_the_provider_timeout_is_capped_by_the_time_left() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock, deadline_s=12.0)
    seen: list[float] = []
    guard.call(
        stage="writer",
        provider="p",
        fn=lambda t: seen.append(t) or "ok",
        est_cost_usd=0.1,
        actual_cost=lambda _r: 0.01,
        per_call_timeout_s=30,
    )
    assert seen == [pytest.approx(12.0)]


def test_transient_errors_retry_twice_with_backoff_then_raise() -> None:
    clock = FakeClock()
    guard, ledger = _guard(clock)
    attempts: list[int] = []

    def flaky(_t: float) -> str:
        attempts.append(1)
        raise ProviderTimeout()

    with pytest.raises(ProviderTimeout):
        guard.call(
            stage="writer",
            provider="p",
            fn=flaky,
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.01,
            per_call_timeout_s=30,
        )
    assert len(attempts) == 3
    assert clock.sleeps == [pytest.approx(1.0), pytest.approx(2.0)]
    assert ledger.committed_usd == 0  # failed attempts are released, not charged


def test_a_retry_that_succeeds_returns_the_result() -> None:
    clock = FakeClock()
    guard, ledger = _guard(clock)
    state = {"n": 0}

    def fn(_t: float) -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise ProviderServerError()
        return "done"

    out = guard.call(
        stage="writer",
        provider="p",
        fn=fn,
        est_cost_usd=0.1,
        actual_cost=lambda _r: 0.02,
        per_call_timeout_s=30,
    )
    assert out == "done"
    assert ledger.committed_usd == pytest.approx(0.02)


@pytest.mark.parametrize("error", [ProviderAuthError(), ProviderBadRequest()])
def test_auth_and_bad_request_errors_are_never_retried(error: Exception) -> None:
    clock = FakeClock()
    guard, ledger = _guard(clock)
    calls: list[int] = []

    def fn(_t: float) -> str:
        calls.append(1)
        raise error

    with pytest.raises(type(error)):
        guard.call(
            stage="writer",
            provider="p",
            fn=fn,
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert len(calls) == 1
    assert clock.sleeps == []


def test_rate_limit_waits_for_retry_after_when_it_fits() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock, deadline_s=60)
    state = {"n": 0}

    def fn(_t: float) -> str:
        state["n"] += 1
        if state["n"] == 1:
            raise ProviderRateLimit(retry_after_s=5.0)
        return "ok"

    assert (
        guard.call(
            stage="writer",
            provider="p",
            fn=fn,
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
        == "ok"
    )
    assert clock.sleeps == [pytest.approx(5.0)]


def test_rate_limit_that_cannot_fit_in_the_time_left_stops_retrying() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock, deadline_s=3.0)

    def fn(_t: float) -> str:
        raise ProviderRateLimit(retry_after_s=30.0)

    with pytest.raises(ProviderRateLimit):
        guard.call(
            stage="writer",
            provider="p",
            fn=fn,
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert clock.sleeps == []


def test_schema_violations_retry_only_when_asked() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock)
    calls: list[int] = []

    def fn(_t: float) -> str:
        calls.append(1)
        raise SchemaViolation("bad")

    with pytest.raises(SchemaViolation):
        guard.call(
            stage="writer",
            provider="p",
            fn=fn,
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert len(calls) == 1
    calls.clear()
    with pytest.raises(SchemaViolation):
        guard.call(
            stage="writer",
            provider="p",
            fn=fn,
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
            retry_on_schema=True,
        )
    assert len(calls) == 3


def test_an_expired_deadline_stops_before_any_provider_call() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock, deadline_s=5.0)
    clock.now += 10
    called: list[int] = []
    with pytest.raises(DeadlineExceeded):
        guard.call(
            stage="writer",
            provider="p",
            fn=lambda t: called.append(1) or "x",
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert called == []


def test_a_cancelled_run_issues_no_new_calls() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock, cancelled=True)
    called: list[int] = []
    with pytest.raises(RunCancelled):
        guard.call(
            stage="writer",
            provider="p",
            fn=lambda t: called.append(1) or "x",
            est_cost_usd=0.1,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert called == []


def test_a_refused_reservation_means_no_provider_call() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock, cap=0.05)
    called: list[int] = []
    with pytest.raises(BudgetStop):
        guard.call(
            stage="writer",
            provider="p",
            fn=lambda t: called.append(1) or "x",
            est_cost_usd=0.5,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert called == []


def test_missing_usage_marks_the_ledger_unknown_cost() -> None:
    clock = FakeClock()
    guard, ledger = _guard(clock)
    guard.call(
        stage="writer",
        provider="p",
        fn=lambda t: "ok",
        est_cost_usd=0.2,
        actual_cost=lambda _r: None,
        per_call_timeout_s=30,
    )
    assert ledger.unknown_cost
    assert ledger.committed_usd == pytest.approx(0.2)


def test_circuit_opens_after_five_consecutive_failures_and_recovers() -> None:
    clock = FakeClock()
    guard, _ = _guard(clock)
    calls: list[int] = []

    def bad(_t: float) -> str:
        calls.append(1)
        raise ProviderServerError()

    for _ in range(2):  # 2 calls x 3 attempts = 6 failures, the breaker opens at 5
        with pytest.raises(ProviderServerError):
            guard.call(
                stage="writer",
                provider="p",
                fn=bad,
                est_cost_usd=0.01,
                actual_cost=lambda _r: 0.0,
                per_call_timeout_s=30,
            )
    before = len(calls)
    with pytest.raises(ProviderServerError):
        guard.call(
            stage="writer",
            provider="p",
            fn=bad,
            est_cost_usd=0.01,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
    assert len(calls) == before  # failed fast, no provider call
    clock.now += 31
    assert (
        guard.call(
            stage="writer",
            provider="p",
            fn=lambda t: "ok",
            est_cost_usd=0.01,
            actual_cost=lambda _r: 0.0,
            per_call_timeout_s=30,
        )
        == "ok"
    )


# --- daily spend guard -------------------------------------------------------------------------


def test_spend_total_persists_across_restarts(tmp_path: Path) -> None:
    g1 = DailySpendGuard(tmp_path, alert_usd=5, stop_usd=8, today=lambda: date(2026, 10, 21))
    g1.add(1.25)
    g2 = DailySpendGuard(tmp_path, alert_usd=5, stop_usd=8, today=lambda: date(2026, 10, 21))
    assert g2.total_usd == pytest.approx(1.25)
    data = json.loads((tmp_path / "spend-20261021.json").read_text(encoding="utf-8"))
    assert data["total_committed_usd"] == pytest.approx(1.25)


def test_alert_fires_once_and_stop_blocks_new_runs(tmp_path: Path) -> None:
    g = DailySpendGuard(tmp_path, alert_usd=5, stop_usd=8, today=lambda: date(2026, 10, 21))
    assert g.add(4.0) == []
    assert g.add(1.5) == ["spend.alert"]
    assert g.allow_new_run()
    assert g.add(0.1) == []  # no repeat alert
    assert g.add(3.0) == ["spend.stop"]
    assert not g.allow_new_run()


def test_a_new_day_starts_at_zero(tmp_path: Path) -> None:
    day = {"d": date(2026, 10, 21)}
    g = DailySpendGuard(tmp_path, alert_usd=5, stop_usd=8, today=lambda: day["d"])
    g.add(9.0)
    assert not g.allow_new_run()
    day["d"] = date(2026, 10, 22)
    assert g.allow_new_run()
    assert g.total_usd == 0


def test_stop_threshold_zero_disables_the_stop(tmp_path: Path) -> None:
    g = DailySpendGuard(tmp_path, alert_usd=0, stop_usd=0, today=lambda: date(2026, 10, 21))
    g.add(1000.0)
    assert g.allow_new_run()


def test_old_spend_files_are_purged_after_seven_days(tmp_path: Path) -> None:
    (tmp_path / "spend-20260101.json").write_text("{}", encoding="utf-8")
    (tmp_path / "spend-20261020.json").write_text("{}", encoding="utf-8")
    DailySpendGuard(tmp_path, alert_usd=5, stop_usd=8, today=lambda: date(2026, 10, 21))
    names = {p.name for p in tmp_path.iterdir()}
    assert "spend-20260101.json" not in names
    assert "spend-20261020.json" in names


def test_settings_defaults_drive_the_guard_thresholds() -> None:
    s = load_settings({})
    assert s.daily_spend_alert_usd < s.daily_spend_stop_usd


def test_call_guard_check_raises_for_cancel_and_expired_deadline() -> None:
    from core.errors import DeadlineExceeded, RunCancelled

    ledger = BudgetLedger(1.0, {})
    gates = {"x": ProviderGate("x", 100.0, 10, sleep=lambda s: None)}
    flag = {"cancel": False}
    guard = CallGuard(
        ledger=ledger, deadline=Deadline(60), is_cancelled=lambda: flag["cancel"], gates=gates
    )
    guard.check()
    flag["cancel"] = True
    with pytest.raises(RunCancelled):
        guard.check()
    expired = CallGuard(
        ledger=ledger, deadline=Deadline(0), is_cancelled=lambda: False, gates=gates
    )
    with pytest.raises(DeadlineExceeded):
        expired.check()
