"""Background run manager (PRD FR-36, NFR-17, NFR-19; ARCH §8.4).

Runs execute in a bounded worker pool outside the Streamlit script thread, so reruns, widget
clicks and double-clicks cannot start, duplicate or kill a run. A heartbeat watchdog stops runs
whose page went away; results expire after a TTL; drain mode stops admitting new runs.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from core.capacity import DailySpendGuard
from core.drain import DrainMarker
from core.errors import ErrorCode
from core.models import ResearchRequest, ResearchResult, RunStatus
from core.research_agent import run_research
from core.telemetry import Telemetry

ContextFactory = Callable[[ResearchRequest, Callable[[], bool]], Any]
Runner = Callable[..., ResearchResult]


@dataclass
class Submission:
    run_id: str | None = None
    error: ErrorCode | None = None


@dataclass
class RunView:
    state: str  # running | done | abandoned | expired | not_found
    stage: str = ""
    fraction: float = 0.0
    result: ResearchResult | None = None


@dataclass
class ServiceState:
    paused: bool
    draining: bool
    active: int
    capacity: int

    @property
    def accepting(self) -> bool:
        return not self.paused and not self.draining and self.active < self.capacity


@dataclass
class _Run:
    run_id: str
    session_id: str
    token: str
    started: float
    last_heartbeat: float
    cancelled: bool = False
    abandoned: bool = False
    stage: str = ""
    stage_started: float = 0.0
    fraction: float = 0.0
    result: ResearchResult | None = None
    finished_at: float | None = None
    done: threading.Event = field(default_factory=threading.Event)


class RunManager:
    def __init__(
        self,
        *,
        context_factory: ContextFactory,
        runner: Runner = run_research,
        max_concurrent: int = 5,
        heartbeat_timeout_s: float = 90.0,
        result_ttl_s: float = 1800.0,
        abandoned_ttl_s: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
        telemetry: Telemetry | None = None,
        spend_guard: DailySpendGuard | None = None,
        demo: bool = False,
        drain_marker: DrainMarker | None = None,
    ) -> None:
        self._factory = context_factory
        self._runner = runner
        self._capacity = max_concurrent
        self._heartbeat_timeout = heartbeat_timeout_s
        self._result_ttl = result_ttl_s
        self._abandoned_ttl = abandoned_ttl_s
        self._clock = clock
        self._telemetry = telemetry
        self._spend = spend_guard
        self._demo = demo
        self._marker = drain_marker
        self._pool = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="run")
        self._lock = threading.RLock()
        self._runs: dict[str, _Run] = {}
        self._tombstones: set[str] = set()
        self._tokens: dict[tuple[str, str], str] = {}
        self._draining = False
        self._watchdog: threading.Thread | None = None
        self._stop_watchdog = threading.Event()

    # -- submit and observe -----------------------------------------------------------------

    def submit(self, session_id: str, request: ResearchRequest) -> Submission:
        with self._lock:
            self._sweep_locked()
            self._check_marker()
            existing = self._tokens.get((session_id, request.idempotency_token))
            if existing is not None and existing in self._runs:
                return Submission(run_id=existing)
            if self._draining or self._paused():
                return self._reject(ErrorCode.SERVICE_PAUSED)
            if any(r.session_id == session_id and r.result is None for r in self._runs.values()):
                return self._reject(ErrorCode.SESSION_ACTIVE)
            if self._active_count() >= self._capacity:
                return self._reject(ErrorCode.BUSY)
            now = self._clock()
            run = _Run(uuid.uuid4().hex[:12], session_id, request.idempotency_token, now, now)
            self._runs[run.run_id] = run
            self._tokens[(session_id, request.idempotency_token)] = run.run_id
            self._publish_active()
        self._emit("run.started", run_id=run.run_id, mode=request.depth.value)
        self._pool.submit(self._execute, run, request)
        return Submission(run_id=run.run_id)

    def _reject(self, error: ErrorCode) -> Submission:
        self._emit("run.rejected", error_code=error.value)
        return Submission(error=error)

    def status(self, run_id: str, session_id: str) -> RunView:
        with self._lock:
            self._sweep_locked()
            run = self._runs.get(run_id)
            if run is None:
                return RunView("expired") if run_id in self._tombstones else RunView("not_found")
            if run.session_id != session_id:
                return RunView("not_found")
            if run.result is None:
                return RunView("running", run.stage, run.fraction)
            state = "abandoned" if run.abandoned else "done"
            return RunView(state, run.stage, 1.0, run.result)

    def heartbeat(self, run_id: str, session_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None and run.session_id == session_id:
                run.last_heartbeat = self._clock()

    def wait(self, run_id: str, timeout: float) -> bool:
        run = self._runs.get(run_id)
        return run.done.wait(timeout) if run is not None else True

    # -- service state ----------------------------------------------------------------------

    def get_service_state(self) -> ServiceState:
        with self._lock:
            self._check_marker()
            return ServiceState(
                self._paused(), self._draining, self._active_count(), self._capacity
            )

    def begin_drain(self) -> None:
        with self._lock:
            self._draining = True
        self._emit("service.drain", count=self._active_count())

    def active_runs(self) -> int:
        with self._lock:
            return self._active_count()

    def shutdown(self) -> None:
        self._stop_watchdog.set()
        self._pool.shutdown(wait=True, cancel_futures=False)

    # -- watchdog and expiry ----------------------------------------------------------------

    def sweep(self) -> None:
        with self._lock:
            self._sweep_locked()

    def start_watchdog(self, interval_s: float = 5.0) -> None:
        if self._watchdog is not None:
            return

        def loop() -> None:
            while not self._stop_watchdog.wait(interval_s):
                self.sweep()

        self._watchdog = threading.Thread(target=loop, name="run-watchdog", daemon=True)
        self._watchdog.start()

    def _check_marker(self) -> None:
        if self._marker is not None and not self._draining and self._marker.is_set():
            self._draining = True
            self._emit("service.drain", count=self._active_count())

    def _publish_active(self) -> None:
        if self._marker is not None:
            self._marker.publish_active(self._active_count())

    def _sweep_locked(self) -> None:
        self._check_marker()
        now = self._clock()
        for run in list(self._runs.values()):
            if run.result is None:
                if not run.cancelled and now - run.last_heartbeat > self._heartbeat_timeout:
                    run.cancelled = True
                    run.abandoned = True
                    self._emit("run.abandoned", run_id=run.run_id)
            elif run.finished_at is not None:
                ttl = self._abandoned_ttl if run.abandoned else self._result_ttl
                if now - run.finished_at > ttl:
                    del self._runs[run.run_id]
                    self._tokens.pop((run.session_id, run.token), None)
                    self._tombstones.add(run.run_id)

    # -- internals --------------------------------------------------------------------------

    def _active_count(self) -> int:
        return sum(1 for r in self._runs.values() if r.result is None)

    def _paused(self) -> bool:
        return self._spend is not None and not self._spend.allow_new_run()

    def _emit(self, event: str, **fields: object) -> None:
        if self._telemetry is not None:
            self._telemetry.emit(event, **fields)

    def _execute(self, run: _Run, request: ResearchRequest) -> None:
        ctx: Any = None
        try:
            ctx = self._factory(request, lambda: run.cancelled)

            def progress(stage: str, fraction: float) -> None:
                if stage != run.stage:
                    self._stage_done(run)
                    run.stage_started = self._clock()
                run.stage, run.fraction = stage, fraction

            result = self._runner(
                ctx, request, run_id=run.run_id, progress=progress, demo=self._demo
            )
        except Exception:  # noqa: BLE001 - a crash must become a failed result, never a lost run
            result = ResearchResult(
                run_id=run.run_id,
                mode=request.depth,
                status=RunStatus.FAILED,
                reason_codes=[ErrorCode.INTEGRITY_FAILED.value],
                error_code=ErrorCode.INTEGRITY_FAILED.value,
            )
        self._stage_done(run)
        self._record_spend(ctx)
        with self._lock:
            run.result = result
            run.finished_at = self._clock()
            self._publish_active()
        self._emit(
            "run.finished",
            run_id=run.run_id,
            mode=result.mode.value,
            status=result.status.value,
            error_code=result.error_code or "",
            elapsed_ms=result.metrics.elapsed_ms,
            supported_claims=result.metrics.supported_claims,
            usable_sources=result.metrics.usable_sources,
            unique_domains=result.metrics.unique_domains,
            repair_used=result.metrics.repair_used,
            replan_used=result.metrics.replan_used,
            **self._cost_fields(ctx),
        )
        run.done.set()

    def _stage_done(self, run: _Run) -> None:
        if run.stage:
            elapsed = int(max(0.0, self._clock() - run.stage_started) * 1000)
            self._emit("stage.finished", run_id=run.run_id, stage=run.stage, elapsed_ms=elapsed)

    @staticmethod
    def _cost_fields(ctx: Any) -> dict[str, object]:
        if ctx is None:
            return {}
        return {"cost_usd": round(float(ctx.guard.ledger.committed_usd), 6)}

    def _record_spend(self, ctx: Any) -> None:
        if self._spend is None or ctx is None:
            return
        ledger = ctx.guard.ledger
        for event in self._spend.add(
            float(ledger.committed_usd), unknown=bool(ledger.unknown_cost)
        ):
            self._emit(event)
