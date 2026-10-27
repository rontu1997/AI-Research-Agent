"""Composition root: settings in, a ready service out (ARCH §4, §8.4).

Builds providers (scripted in demo mode), refuses any mode whose worst-case cost does not fit its
cap (PRD FR-37), shares per-provider rate limiters across runs, and owns the run manager.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date

from adapters.base import Providers
from core.capacity import (
    BudgetLedger,
    CallGraphReport,
    CallGuard,
    DailySpendGuard,
    Deadline,
    ProviderGate,
    TokenBucket,
    check_call_graph,
)
from core.drain import DrainMarker
from core.errors import ErrorCode
from core.models import Mode, ResearchRequest
from core.run_manager import RunManager, Submission
from core.settings import (
    Settings,
    mode_config,
    price_sheet_expired,
    scaled_config,
    startup_problems,
)
from core.telemetry import Telemetry
from pipeline.context import RunContext

# (requests per second, burst) per provider; conservative defaults, shared by every run.
GATE_LIMITS = {"search": (5.0, 5), "writer": (3.0, 3), "verifier": (5.0, 5)}
NVIDIA_BURST = 2

_PROVIDER_NAMES = {
    "openai": "OpenAI",
    "nvidia": "NVIDIA Build",
    "anthropic": "Anthropic",
}
FREE_PROTOTYPE_NOTE = (
    "Model calls use NVIDIA Build's free prototype API. Its availability, rate limits and "
    "terms can change, and estimated costs shown here are budgeting rates, not charges."
)


def make_gates(settings: Settings) -> dict[str, ProviderGate]:
    """Per-provider limiters, shared by every run. Roles on the NVIDIA endpoint share one limit."""
    gates = {name: ProviderGate(name, rate, burst) for name, (rate, burst) in GATE_LIMITS.items()}
    if settings.provider_mode == "live":
        rate = settings.nvidia_max_rpm / 60.0
        shared = TokenBucket(rate, NVIDIA_BURST)  # one request limit, separate breakers
        if settings.writer_provider == "nvidia":
            gates["writer"] = ProviderGate("writer", rate, NVIDIA_BURST, bucket=shared)
        if settings.verifier_provider == "nvidia":
            gates["verifier"] = ProviderGate("verifier", rate, NVIDIA_BURST, bucket=shared)
    return gates


def _verifier_label(settings: Settings, writer_name: str, verifier_name: str, model: str) -> str:
    if settings.verifier_provider == "ollama":
        return (
            f"Verifier and scan: Ollama on this computer, model {model}. Claims and quotes are "
            "checked on this computer. The topic, source passages and drafted claims are processed "
            f"by {writer_name} for planning and writing."
        )
    return f"Verifier and scan: {verifier_name}, model {model}."


def describe_providers(settings: Settings, models: tuple[str, str]) -> list[str]:
    """Plain-language provider list for the About page. Never includes a credential."""
    if settings.provider_mode == "fake":
        return ["Scripted demo providers (synthetic data; nothing is sent to a third party)."]
    writer, verifier = models
    w_name = _PROVIDER_NAMES.get(settings.writer_provider, "a model provider")
    v_name = _PROVIDER_NAMES.get(settings.verifier_provider, "a model provider")
    search_name = "OpenAI web search" if settings.search_provider == "openai" else "Tavily"
    verifier_label = _verifier_label(settings, w_name, v_name, verifier)
    if settings.writer_provider == settings.verifier_provider == "openai" and writer == verifier:
        verifier_label += " This is a same-model review; it is not independent verification."
    return [
        f"Search: {search_name}.",
        f"Planner and writer: {w_name}, model {writer}.",
        verifier_label,
    ]


@dataclass
class Service:
    settings: Settings
    ready: bool
    demo: bool
    problems: list[str]
    manager: RunManager | None = None
    mode_servable: dict[Mode, bool] = field(default_factory=dict)
    reports: dict[Mode, CallGraphReport] = field(default_factory=dict)
    telemetry: Telemetry | None = None
    provider_labels: list[str] = field(default_factory=list)
    cost_note: str | None = None
    today: Callable[[], date] = date.today
    _providers: Providers | None = None
    _gates: dict[str, ProviderGate] = field(default_factory=dict)

    # -- runs ----------------------------------------------------------------------------------

    def submit(self, session_id: str, request: ResearchRequest) -> Submission:
        if (
            not self.ready
            or self.manager is None
            or not self.mode_servable.get(request.depth, False)
        ):
            return Submission(error=ErrorCode.CONFIG_INVALID)
        if self.settings.provider_mode == "live" and price_sheet_expired(
            self.settings.price_sheet, self.today()
        ):
            # The sheet was valid at startup but its review date has passed: stop admitting runs.
            if self.telemetry is not None:
                self.telemetry.emit("run.rejected", error_code=ErrorCode.CONFIG_INVALID.value)
            return Submission(error=ErrorCode.CONFIG_INVALID)
        return self.manager.submit(session_id, request)

    def new_context(self, request: ResearchRequest, is_cancelled: Callable[[], bool]) -> RunContext:
        assert self._providers is not None
        cfg = scaled_config(mode_config(request.depth), self.settings.run_time_factor)
        if self.settings.verifier_parallel != cfg.verifier_parallel:
            cfg = replace(cfg, verifier_parallel=self.settings.verifier_parallel)
        report = self.reports[request.depth]
        guard = CallGuard(
            ledger=BudgetLedger(cfg.cost_cap_usd, report.base_by_stage),
            deadline=Deadline(cfg.wall_clock_s),
            is_cancelled=is_cancelled,
            gates=self._gates,
            on_event=self._forward_event,
        )
        p = self._providers
        return RunContext(
            cfg=cfg,
            prices=self.settings.price_sheet,
            guard=guard,
            search=p.search,
            writer=p.writer,
            verifier=p.verifier,
            writer_model=p.writer_model,
            verifier_model=p.verifier_model,
            chars_per_token=self.settings.est_chars_per_token,
            writer_timeout_factor=self.settings.writer_timeout_factor,
            verifier_timeout_factor=self.settings.verifier_timeout_factor,
        )

    def _forward_event(self, event: str, fields: dict[str, object]) -> None:
        if self.telemetry is not None:
            self.telemetry.emit(event, **fields)

    def shutdown(self) -> None:
        if self.manager is not None:
            self.manager.shutdown()


def _cost_note(settings: Settings) -> str | None:
    sheet = settings.price_sheet
    uses_nvidia = "nvidia" in {settings.writer_provider, settings.verifier_provider}
    if settings.provider_mode == "live" and sheet.free_prototype and uses_nvidia:
        return FREE_PROTOTYPE_NOTE
    return None


def build_providers(settings: Settings) -> Providers:
    if settings.provider_mode == "fake":
        from adapters.fakes import FakeLLM, FakeSearch

        writer_model = settings.writer_model or "fake-writer"
        verifier_model = settings.verifier_model or "fake-verifier"
        return Providers(
            search=FakeSearch(),
            writer=FakeLLM(writer_model),
            verifier=FakeLLM(verifier_model),
            writer_model=writer_model,
            verifier_model=verifier_model,
        )
    from adapters.live import build_live_providers  # imported lazily: needs real credentials

    return build_live_providers(settings)


def build_service(
    settings: Settings,
    *,
    providers: Providers | None = None,
    today: Callable[[], date] = date.today,
) -> Service:
    demo = settings.provider_mode == "fake"
    problems = startup_problems(settings, today())
    if problems:
        return Service(settings=settings, ready=False, demo=demo, problems=problems)

    chosen = providers or build_providers(settings)
    reports: dict[Mode, CallGraphReport] = {}
    servable: dict[Mode, bool] = {}
    for mode in Mode:
        report = check_call_graph(
            mode_config(mode),
            settings.price_sheet,
            chosen.writer_model,
            chosen.verifier_model,
            settings.est_chars_per_token,
        )
        reports[mode] = report
        servable[mode] = report.ok

    telemetry = Telemetry(settings.log_dir, retention_days=settings.log_retention_days)
    for mode, ok in servable.items():
        telemetry.emit("startup.check", mode=mode.value, status="ok" if ok else "refused")
    if not any(servable.values()):
        return Service(
            settings=settings,
            ready=False,
            demo=demo,
            problems=["NO_SERVABLE_MODE"],
            mode_servable=servable,
            reports=reports,
            telemetry=telemetry,
        )
    spend = DailySpendGuard(
        settings.state_dir,
        alert_usd=settings.daily_spend_alert_usd,
        stop_usd=settings.daily_spend_stop_usd,
    )
    service = Service(
        settings=settings,
        ready=True,
        demo=demo,
        problems=[],
        mode_servable=servable,
        reports=reports,
        telemetry=telemetry,
        _providers=chosen,
        provider_labels=describe_providers(settings, (chosen.writer_model, chosen.verifier_model)),
        cost_note=_cost_note(settings),
        today=today,
        _gates=make_gates(settings),
    )
    marker = DrainMarker(settings.state_dir)
    marker.publish_active(0)
    service.manager = RunManager(
        context_factory=service.new_context,
        max_concurrent=settings.max_concurrent_runs,
        heartbeat_timeout_s=settings.heartbeat_timeout_s,
        result_ttl_s=settings.result_ttl_min * 60,
        abandoned_ttl_s=settings.abandoned_ttl_min * 60,
        telemetry=telemetry,
        spend_guard=spend,
        demo=demo,
        drain_marker=marker,
    )
    service.manager.start_watchdog()
    return service
