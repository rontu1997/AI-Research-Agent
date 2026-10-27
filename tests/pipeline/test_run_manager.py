from __future__ import annotations

import threading
from datetime import date
from pathlib import Path

import pytest

from core.capacity import DailySpendGuard
from core.errors import ErrorCode
from core.models import Mode, ResearchRequest, ResearchResult, RunStatus
from core.run_manager import RunManager


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class FakeCtx:
    """Stands in for RunContext: the manager only reads the ledger's committed cost from it."""

    def __init__(self, cancelled, cost: float = 0.1) -> None:  # noqa: ANN001
        self.cancelled = cancelled
        self.cost = cost

        class _L:
            committed_usd = cost
            unknown_cost = False

        class _G:
            ledger = _L()

        self.guard = _G()


def _request(token: str = "t1") -> ResearchRequest:
    return ResearchRequest(topic="a topic", depth=Mode.QUICK, idempotency_token=token)


def _manager(runner, clock=None, **kw) -> RunManager:  # noqa: ANN001, ANN003
    clock = clock or Clock()
    return RunManager(
        context_factory=lambda request, is_cancelled: FakeCtx(is_cancelled),
        runner=runner,
        clock=clock,
        **kw,
    )


def _ok(ctx, request, *, run_id, progress=None, demo=False, **_):  # noqa: ANN001, ANN002, ANN003
    if progress:
        progress("planning", 0.05)
    return ResearchResult(
        run_id=run_id, mode=request.depth, status=RunStatus.COMPLETED, report_markdown="# r"
    )


def test_submit_runs_in_the_background_and_returns_the_result() -> None:
    m = _manager(_ok)
    sub = m.submit("s1", _request())
    assert sub.run_id and sub.error is None
    assert m.wait(sub.run_id, 5)
    view = m.status(sub.run_id, "s1")
    assert view.state == "done" and view.result and view.result.status is RunStatus.COMPLETED
    m.shutdown()


def test_same_token_is_idempotent_and_a_second_run_in_a_session_is_refused() -> None:
    gate = threading.Event()

    def slow(ctx, request, *, run_id, **_):  # noqa: ANN001, ANN003
        gate.wait(5)
        return ResearchResult(run_id=run_id, mode=request.depth, status=RunStatus.COMPLETED)

    m = _manager(slow)
    first = m.submit("s1", _request("a"))
    again = m.submit("s1", _request("a"))
    other = m.submit("s1", _request("b"))
    assert again.run_id == first.run_id
    assert other.error is ErrorCode.SESSION_ACTIVE
    gate.set()
    m.wait(first.run_id, 5)
    assert m.submit("s1", _request("c")).run_id  # the permit and the session slot are free again
    m.shutdown()


def test_busy_when_the_worker_pool_is_full() -> None:
    gate = threading.Event()

    def slow(ctx, request, *, run_id, **_):  # noqa: ANN001, ANN003
        gate.wait(5)
        return ResearchResult(run_id=run_id, mode=request.depth, status=RunStatus.COMPLETED)

    m = _manager(slow, max_concurrent=1)
    assert m.submit("s1", _request("a")).run_id
    assert m.submit("s2", _request("b")).error is ErrorCode.BUSY
    gate.set()
    m.shutdown()


def test_other_sessions_cannot_read_a_run() -> None:
    m = _manager(_ok)
    sub = m.submit("s1", _request())
    m.wait(sub.run_id, 5)
    assert m.status(sub.run_id, "s2").state == "not_found"
    m.shutdown()


def test_missing_heartbeat_abandons_the_run_and_a_heartbeat_keeps_it_alive() -> None:
    clock = Clock()
    stop = threading.Event()

    def polling(ctx, request, *, run_id, **_):  # noqa: ANN001, ANN003
        while not ctx.cancelled():
            if stop.wait(0.01):
                break
        return ResearchResult(
            run_id=run_id,
            mode=request.depth,
            status=RunStatus.FAILED,
            error_code=ErrorCode.ABANDONED.value,
        )

    m = _manager(polling, clock=clock, heartbeat_timeout_s=90)
    sub = m.submit("s1", _request())
    clock.t += 60
    m.heartbeat(sub.run_id, "s1")
    clock.t += 60  # 60 s since the last heartbeat: still alive
    m.sweep()
    assert m.status(sub.run_id, "s1").state == "running"
    clock.t += 100  # now over the timeout
    m.sweep()
    assert m.wait(sub.run_id, 5)
    assert m.status(sub.run_id, "s1").result.error_code == ErrorCode.ABANDONED.value
    stop.set()
    m.shutdown()


def test_results_expire_after_the_ttl_and_leave_an_expired_marker() -> None:
    clock = Clock()
    m = _manager(_ok, clock=clock, result_ttl_s=1800)
    sub = m.submit("s1", _request())
    m.wait(sub.run_id, 5)
    clock.t += 1801
    m.sweep()
    assert m.status(sub.run_id, "s1").state == "expired"
    m.shutdown()


def test_a_crashing_run_becomes_a_failed_result_not_a_lost_run() -> None:
    def crash(ctx, request, *, run_id, **_):  # noqa: ANN001, ANN003
        raise RuntimeError("boom")

    m = _manager(crash)
    sub = m.submit("s1", _request())
    m.wait(sub.run_id, 5)
    view = m.status(sub.run_id, "s1")
    assert view.result.status is RunStatus.FAILED
    assert view.result.error_code == ErrorCode.INTEGRITY_FAILED.value
    m.shutdown()


def test_drain_refuses_new_runs_and_reports_service_state() -> None:
    m = _manager(_ok)
    m.begin_drain()
    assert m.submit("s1", _request()).error is ErrorCode.SERVICE_PAUSED
    state = m.get_service_state()
    assert state.draining and not state.accepting
    m.shutdown()


def test_daily_stop_pauses_the_service_and_committed_cost_is_recorded(tmp_path: Path) -> None:
    guard = DailySpendGuard(tmp_path, alert_usd=0.05, stop_usd=0.15, today=lambda: date(2026, 1, 1))
    m = _manager(_ok, spend_guard=guard)
    first = m.submit("s1", _request("a"))
    m.wait(first.run_id, 5)
    assert guard.total_usd == pytest.approx(0.1)
    second = m.submit("s1", _request("b"))
    m.wait(second.run_id, 5)
    assert guard.total_usd == pytest.approx(0.2)
    assert m.submit("s1", _request("c")).error is ErrorCode.SERVICE_PAUSED
    assert m.get_service_state().paused
    m.shutdown()


def test_drain_marker_stops_admission_and_publishes_the_active_count(tmp_path: Path) -> None:
    from core.drain import DrainMarker

    marker = DrainMarker(tmp_path)
    gate = threading.Event()

    def slow(ctx, request, *, run_id, **_):  # noqa: ANN001, ANN003
        gate.wait(5)
        return ResearchResult(run_id=run_id, mode=request.depth, status=RunStatus.COMPLETED)

    m = _manager(slow, drain_marker=marker, max_concurrent=3)
    first = m.submit("s1", _request("a"))
    assert marker.read_active() == 1
    marker.set()
    assert m.submit("s2", _request("b")).error is ErrorCode.SERVICE_PAUSED
    assert m.get_service_state().draining
    gate.set()
    m.wait(first.run_id, 5)
    assert marker.read_active() == 0
    m.shutdown()
