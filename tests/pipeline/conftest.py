"""Shared fixtures for pipeline tests: a fully wired RunContext over the fake providers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from adapters.fakes import FakeLLM, FakeSearch
from core.capacity import BudgetLedger, CallGuard, Deadline, ProviderGate, check_call_graph
from core.models import Mode
from core.settings import PriceSheet, mode_config
from pipeline.context import RunContext

SHEET = PriceSheet.from_file(Path("core/price_sheet_placeholder.json"))


@pytest.fixture
def make_ctx() -> Callable[..., RunContext]:
    def _make(
        mode: Mode = Mode.QUICK,
        *,
        search: FakeSearch | None = None,
        writer: FakeLLM | None = None,
        verifier: FakeLLM | None = None,
        cap_usd: float | None = None,
        wall_s: float = 1000.0,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> RunContext:
        cfg = mode_config(mode)
        report = check_call_graph(cfg, SHEET, "fake-writer", "fake-verifier")
        if cap_usd is None:
            ledger = BudgetLedger(cfg.cost_cap_usd, report.base_by_stage)
        else:  # an explicit tiny cap models a run that has no base reservations left
            ledger = BudgetLedger(cap_usd, {})
        gates = {
            "search": ProviderGate("search", 1000.0, 1000, sleep=lambda s: None),
            "writer": ProviderGate("writer", 1000.0, 1000, sleep=lambda s: None),
            "verifier": ProviderGate("verifier", 1000.0, 1000, sleep=lambda s: None),
        }
        guard = CallGuard(
            ledger=ledger,
            deadline=Deadline(wall_s),
            is_cancelled=cancelled,
            gates=gates,
            sleep=lambda s: None,
            jitter=lambda upper: 0.0,
        )
        return RunContext(
            cfg=cfg,
            prices=SHEET,
            guard=guard,
            search=search or FakeSearch(),
            writer=writer or FakeLLM("fake-writer"),
            verifier=verifier or FakeLLM("fake-verifier"),
            writer_model="fake-writer",
            verifier_model="fake-verifier",
        )

    return _make
