"""Cost admission, retries, rate limits and the daily spend guard (PRD §10.1, ARCH §10).

Budget model: each stage has a *base reservation* (its first-attempt worst case) and the rest of the
mode's cap is a *shared contingency pool*. Retries, the planner replan and the repair branch draw on
the pool. Every external call is reserved before it is made, so the modeled bound is never crossed
knowingly.
"""

from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from core.errors import (
    BudgetStop,
    ContentRefused,
    DeadlineExceeded,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderCircuitOpen,
    ProviderRateLimit,
    ProviderServerError,
    ProviderTimeout,
    RunCancelled,
    SchemaViolation,
)
from core.settings import ModeConfig, PriceSheet
from core.tokens import (
    DEFAULT_CHARS_PER_TOKEN,
    MAX_PASSAGE_CHARS,
    QUOTE_MAX_CHARS,
)

T = TypeVar("T")

MAX_ATTEMPTS = 3  # the first attempt plus at most two retries (NFR-16)
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 8.0
BREAKER_THRESHOLD = 5
BREAKER_OPEN_S = 30.0
SPEND_RETENTION_DAYS = 7

# Stages whose first attempt draws on a base reservation. Everything else is pool-funded.
BASE_STAGES = ("planner", "search", "writer", "verifier", "scan")


# --- budget ledger -----------------------------------------------------------------------------


@dataclass
class Reservation:
    stage: str
    attempt: int
    amount: float
    from_base: float
    from_pool: float
    state: str = "open"  # open | committed | released


class BudgetLedger:
    """Thread-safe base-plus-pool ledger.

    Money is conserved (base + pool + committed = cap) until a call costs more than its reservation;
    that overrun is charged to the pool, which may go negative, and later reservations then fail.
    """

    def __init__(self, cap_usd: float, base_by_stage: dict[str, float]) -> None:
        self.cap_usd = cap_usd
        self.base_remaining: dict[str, float] = dict(base_by_stage)
        self.pool_remaining = max(0.0, cap_usd - sum(base_by_stage.values()))
        self.committed_usd = 0.0
        self.overrun_usd = 0.0
        self.unknown_cost = False
        self._lock = threading.Lock()

    def reserve(self, stage: str, amount: float, attempt: int) -> Reservation:
        with self._lock:
            base_avail = self.base_remaining.get(stage, 0.0) if attempt == 1 else 0.0
            from_base = min(amount, base_avail)
            need_pool = amount - from_base
            if need_pool > self.pool_remaining + 1e-12:
                raise BudgetStop(f"{stage}: reservation {amount:.4f} exceeds what is left")
            if from_base:
                self.base_remaining[stage] -= from_base
            self.pool_remaining -= need_pool
            return Reservation(stage, attempt, amount, from_base, need_pool)

    def commit(self, res: Reservation, actual_usd: float | None) -> None:
        with self._lock:
            if res.state != "open":
                return
            if actual_usd is None:
                charged = res.amount
                self.unknown_cost = True
            else:
                charged = max(0.0, actual_usd)
            if charged <= res.amount:
                refund = res.amount - charged
                share = res.from_pool / res.amount if res.amount else 0.0
                refund_pool = refund * share
                self.pool_remaining += refund_pool
                if res.from_base:
                    self.base_remaining[res.stage] += refund - refund_pool
            else:
                over = charged - res.amount
                self.overrun_usd += over
                self.pool_remaining -= over
            self.committed_usd += charged
            res.state = "committed"

    def release(self, res: Reservation) -> None:
        with self._lock:
            if res.state != "open":
                return
            if res.from_base:
                self.base_remaining[res.stage] += res.from_base
            self.pool_remaining += res.from_pool
            res.state = "released"


# --- startup call-graph check (FR-37) ------------------------------------------------------------


@dataclass(frozen=True)
class CallGraphReport:
    verifier_batches: int
    repair_batches: int
    claims_per_batch: int
    base_by_stage: dict[str, float]
    base_total: float
    pool: float
    pool_demand: float
    worst_case_total: float
    condition_i: bool
    condition_ii: bool

    @property
    def ok(self) -> bool:
        return self.condition_i and self.condition_ii

    @property
    def spare(self) -> float:
        return self.pool - self.pool_demand


def claims_per_verifier_batch(
    cfg: ModeConfig, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN
) -> int:
    """Worst-case claims in one verifier batch, from token sizes (ARCH §10.4)."""
    per_claim = (
        math.ceil(cfg.max_quotes_per_claim * MAX_PASSAGE_CHARS / chars_per_token)
        + math.ceil(QUOTE_MAX_CHARS / chars_per_token)
        + cfg.claim_text_allowance
    )
    fit = (cfg.verifier_input_cap - cfg.verifier_prompt_allowance) // per_claim
    return max(1, min(cfg.verifier_batch_size, fit))


def check_call_graph(
    cfg: ModeConfig,
    prices: PriceSheet,
    writer_model: str,
    verifier_model: str,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
) -> CallGraphReport:
    """Conditions (i) and (ii) of PRD FR-37, computed at maximum token settings."""
    per_batch = claims_per_verifier_batch(cfg, chars_per_token)
    batches = math.ceil(cfg.max_claims / per_batch)
    repair_batches = math.ceil(cfg.repair_max_claims / per_batch)
    safety = prices.safety_factor

    def writer_cost(i: int, o: int) -> float:
        return prices.token_cost(writer_model, i, o)

    def verifier_cost(i: int, o: int) -> float:
        return prices.token_cost(verifier_model, i, o)

    planner = writer_cost(cfg.planner_input_cap, cfg.planner_max_output)
    search = cfg.search_query_cap * prices.search_per_call
    writer = writer_cost(cfg.writer_input_cap, cfg.writer_max_output)
    verifier = batches * verifier_cost(cfg.verifier_input_cap, cfg.verifier_max_output)
    scan = verifier_cost(cfg.scan_input_cap, cfg.scan_max_output)
    repair = (
        writer_cost(cfg.repair_input_cap, cfg.repair_max_output)
        + repair_batches * verifier_cost(cfg.verifier_input_cap, cfg.verifier_max_output)
        + scan
    )

    singles = {
        "planner": planner,
        "search": search,
        "writer": writer,
        "verifier": verifier,
        "scan": scan,
    }
    first_pass = sum(singles.values())
    base_by_stage = {k: v * safety for k, v in singles.items()}
    base_total = first_pass * safety
    demand = (
        first_pass * (MAX_ATTEMPTS - 1) * safety  # retries of every first-pass call
        + planner * MAX_ATTEMPTS * safety  # one replan with its own retries
        + repair * MAX_ATTEMPTS * safety  # the repair branch with its own retries
    )
    return CallGraphReport(
        verifier_batches=batches,
        repair_batches=repair_batches,
        claims_per_batch=per_batch,
        base_by_stage=base_by_stage,
        base_total=base_total,
        pool=cfg.cost_cap_usd - base_total,
        pool_demand=demand,
        worst_case_total=base_total + demand,
        condition_i=base_total <= cfg.cost_cap_usd,
        condition_ii=base_total + demand <= cfg.cost_cap_usd,
    )


# --- deadline, rate limiter, circuit breaker ----------------------------------------------------


class Deadline:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds

    def remaining(self) -> float:
        return max(0.0, self._end - self._clock())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


class TokenBucket:
    def __init__(
        self,
        rate_per_s: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rate = rate_per_s
        self._burst = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self, max_wait: float | None = None) -> None:
        """Take a slot, sleeping (outside the lock) until it is due.

        The slot is reserved before sleeping, so waiters queue in order. If the wait would exceed
        ``max_wait`` (the run's remaining time) nothing is reserved and DeadlineExceeded is raised.
        """
        with self._lock:
            self._refill()
            wait = 0.0 if self._tokens >= 1.0 else (1.0 - self._tokens) / self._rate
            if max_wait is not None and wait > max_wait:
                raise DeadlineExceeded()
            self._tokens -= 1.0  # may go negative: a reserved future slot
        if wait > 0:
            self._sleep(wait)

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
        self._last = now


class ProviderGate:
    """Shared per-provider rate limiter plus a light circuit breaker (ARCH §10.3)."""

    def __init__(
        self,
        name: str,
        rate_per_s: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        bucket: TokenBucket | None = None,
    ) -> None:
        """``bucket`` lets several gates share one rate limit while keeping separate breakers."""
        self.name = name
        self.rate_per_s = rate_per_s
        self._bucket = bucket or TokenBucket(rate_per_s, burst, clock, sleep)
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def before_call(self, max_wait: float | None = None) -> None:
        with self._lock:
            if self._clock() < self._open_until:
                raise ProviderCircuitOpen(f"{self.name} circuit is open")
        self._bucket.acquire(max_wait)

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0

    def record_failure(self) -> bool:
        """Count a failure. Returns True if this failure opened the breaker."""
        with self._lock:
            self._failures += 1
            if self._failures >= BREAKER_THRESHOLD:
                self._open_until = self._clock() + BREAKER_OPEN_S
                self._failures = 0
                return True
            return False


# --- guarded call (ARCH §10.2) ------------------------------------------------------------------


class CallGuard:
    """Every external call goes through here: reserve, rate-limit, call, commit, retry."""

    def __init__(
        self,
        *,
        ledger: BudgetLedger,
        deadline: Deadline,
        is_cancelled: Callable[[], bool],
        gates: dict[str, ProviderGate],
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
        on_event: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._on_event = on_event
        self.ledger = ledger
        self.deadline = deadline
        self._is_cancelled = is_cancelled
        self._gates = gates
        self._sleep = sleep
        self._jitter = jitter or (lambda upper: random.uniform(0.0, upper))

    def check(self) -> None:
        """Stage-boundary check: stop at once if the run was abandoned or its time is up."""
        if self._is_cancelled():
            raise RunCancelled()
        if self.deadline.expired():
            raise DeadlineExceeded()

    def call(
        self,
        *,
        stage: str,
        provider: str,
        fn: Callable[[float], T],
        est_cost_usd: float,
        actual_cost: Callable[[T], float | None],
        per_call_timeout_s: float,
        retry_on_schema: bool = False,
    ) -> T:
        gate = self._gates[provider]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.check()
            reservation = self.ledger.reserve(stage, est_cost_usd, attempt)
            started = time.monotonic()
            try:
                gate.before_call(self.deadline.remaining())
                timeout = min(per_call_timeout_s, self.deadline.remaining())
                result = fn(timeout)
            except ProviderCircuitOpen:
                self.ledger.release(reservation)
                self._emit_call(provider, stage, attempt, started, "ProviderCircuitOpen")
                raise
            except ProviderRateLimit as err:
                self._record_failure(gate, provider)
                self.ledger.release(reservation)  # a 429 is not billed
                self._emit_call(provider, stage, attempt, started, "ProviderRateLimit")
                if attempt == MAX_ATTEMPTS:
                    raise
                wait = (
                    err.retry_after_s if err.retry_after_s is not None else self._backoff(attempt)
                )
                if wait >= self.deadline.remaining():
                    raise
                self._sleep(wait)
                continue
            except (ProviderTimeout, ProviderServerError) as err:
                self._record_failure(gate, provider)
                # Residual risk (ledger ruling 24): a timed-out call may be billed by the provider.
                self.ledger.release(reservation)
                self._emit_call(provider, stage, attempt, started, type(err).__name__)
                if self.deadline.expired():
                    raise DeadlineExceeded() from err  # the run's time ran out, not the provider
                if attempt == MAX_ATTEMPTS:
                    raise
                wait = self._backoff(attempt)
                if wait >= self.deadline.remaining():
                    raise
                self._sleep(wait)
                continue
            except (SchemaViolation, ContentRefused) as err:
                # The provider produced (and billed) a response: charge the full reservation.
                self.ledger.commit(reservation, None)
                self._emit_call(provider, stage, attempt, started, type(err).__name__)
                if isinstance(err, SchemaViolation) and retry_on_schema and attempt < MAX_ATTEMPTS:
                    continue
                raise
            except (ProviderAuthError, ProviderBadRequest) as err:
                self.ledger.release(reservation)
                self._emit_call(provider, stage, attempt, started, type(err).__name__)
                raise
            except BaseException:
                self.ledger.release(reservation)
                raise
            try:
                cost = actual_cost(result)
            except BaseException:
                self.ledger.release(reservation)
                raise
            gate.record_success()
            self.ledger.commit(reservation, cost)
            self._emit_call(provider, stage, attempt, started, None)
            return result
        raise AssertionError("unreachable")  # pragma: no cover

    def _record_failure(self, gate: ProviderGate, provider: str) -> None:
        if gate.record_failure():
            self._emit("provider.breaker", provider=provider)

    def _emit_call(
        self, provider: str, stage: str, attempt: int, started: float, error: str | None
    ) -> None:
        fields: dict[str, object] = {
            "provider": provider,
            "stage": stage,
            "attempt": attempt,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "status": "ok" if error is None else "error",
        }
        if error is not None:
            fields["error_code"] = error
        self._emit("provider.call", **fields)

    def _emit(self, event: str, **fields: object) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event, fields)
            except Exception:  # noqa: BLE001 - telemetry must never break a call
                pass

    def _backoff(self, attempt: int) -> float:
        upper = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** (attempt - 1)))
        return self._jitter(upper)


# --- daily spend guard (PRD FR-45, ARCH §10.4) -------------------------------------------------


@dataclass
class _DayState:
    day: date
    total: float = 0.0
    unknown_cost_runs: int = 0
    alerted: bool = False
    stopped: bool = False
    extra: dict[str, object] = field(default_factory=dict)


class DailySpendGuard:
    """Committed spend per day, persisted so a restart cannot reset the daily stop."""

    def __init__(
        self,
        state_dir: Path | str,
        *,
        alert_usd: float,
        stop_usd: float,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._dir = Path(state_dir)
        self._alert = alert_usd
        self._stop = stop_usd
        self._today = today
        self._lock = threading.Lock()
        self._state = self._load(today())
        self._purge(today())

    @property
    def total_usd(self) -> float:
        with self._lock:
            self._roll()
            return self._state.total

    def allow_new_run(self) -> bool:
        with self._lock:
            self._roll()
            return not (self._stop > 0 and self._state.total >= self._stop)

    def add(self, usd: float, *, unknown: bool = False) -> list[str]:
        with self._lock:
            self._roll()
            st = self._state
            st.total += max(0.0, usd)
            if unknown:
                st.unknown_cost_runs += 1
            events: list[str] = []
            if self._alert > 0 and st.total >= self._alert and not st.alerted:
                st.alerted = True
                events.append("spend.alert")
            if self._stop > 0 and st.total >= self._stop and not st.stopped:
                st.stopped = True
                events.append("spend.stop")
            self._save(st)
            return events

    # -- persistence --------------------------------------------------------------------------

    def _path(self, day: date) -> Path:
        return self._dir / f"spend-{day:%Y%m%d}.json"

    def _load(self, day: date) -> _DayState:
        path = self._path(day)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return _DayState(
                    day=day,
                    total=float(data.get("total_committed_usd", 0.0)),
                    unknown_cost_runs=int(data.get("unknown_cost_runs", 0)),
                    alerted=bool(data.get("alerted", False)),
                    stopped=bool(data.get("stopped", False)),
                )
            except (ValueError, OSError):
                pass
        return _DayState(day=day)

    def _save(self, st: _DayState) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(st.day)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "date": st.day.isoformat(),
                    "total_committed_usd": round(st.total, 6),
                    "unknown_cost_runs": st.unknown_cost_runs,
                    "alerted": st.alerted,
                    "stopped": st.stopped,
                }
            ),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def _roll(self) -> None:
        today = self._today()
        if today != self._state.day:
            self._state = self._load(today)
            self._purge(today)

    def _purge(self, today: date) -> None:
        if not self._dir.is_dir():
            return
        cutoff = datetime.combine(today, datetime.min.time()) - timedelta(days=SPEND_RETENTION_DAYS)
        for path in self._dir.glob("spend-*.json"):
            try:
                file_day = datetime.strptime(path.stem[len("spend-") :], "%Y%m%d")
            except ValueError:
                continue
            if file_day < cutoff:
                path.unlink(missing_ok=True)
