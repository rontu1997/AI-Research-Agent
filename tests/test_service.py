from __future__ import annotations

import json
from pathlib import Path

from core.errors import ErrorCode
from core.models import Mode, ResearchRequest, RunStatus
from core.settings import load_settings
from service import build_service


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "fake",
        "STATE_DIR": str(tmp_path / "state"),
        "LOG_DIR": str(tmp_path / "logs"),
    }
    env.update(extra)
    return env


def _request(mode: Mode = Mode.QUICK, token: str = "t1") -> ResearchRequest:
    return ResearchRequest(topic="Harborview bike share pilot", depth=mode, idempotency_token=token)


def test_fake_service_is_ready_serves_both_modes_and_runs_end_to_end(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path)))
    assert service.ready and service.demo
    assert service.mode_servable == {Mode.QUICK: True, Mode.DEEP: True}
    sub = service.submit("session-1", _request())
    assert sub.run_id
    assert service.manager is not None and service.manager.wait(sub.run_id, 30)
    view = service.manager.status(sub.run_id, "session-1")
    assert view.result is not None and view.result.status is RunStatus.COMPLETED
    service.shutdown()


def test_missing_live_configuration_is_reported_by_name_only(tmp_path: Path) -> None:
    secret = "sk-very-secret-value"
    service = build_service(
        load_settings(_env(tmp_path, RESEARCH_PROVIDER_MODE="live", SEARCH_API_KEY=secret))
    )
    assert not service.ready
    assert "OPENAI_API_KEY" in service.problems
    assert secret not in " ".join(service.problems)
    assert service.submit("s", _request()).error is ErrorCode.CONFIG_INVALID


def test_a_mode_whose_worst_case_exceeds_its_cap_is_refused(tmp_path: Path) -> None:
    sheet = tmp_path / "prices.json"
    sheet.write_text(
        json.dumps(
            {
                "version": "t",
                "placeholder": False,
                "safety_factor": 1.25,
                "models": {
                    "fake-writer": {"in_per_m": 40.0, "out_per_m": 160.0},
                    "fake-verifier": {"in_per_m": 0.3, "out_per_m": 1.2},
                },
                "search_per_call": 0.016,
            }
        ),
        encoding="utf-8",
    )
    service = build_service(load_settings(_env(tmp_path, PRICE_SHEET_PATH=str(sheet))))
    assert service.mode_servable[Mode.QUICK] is False
    assert service.submit("s", _request(Mode.QUICK)).error is ErrorCode.CONFIG_INVALID
    service.shutdown()


def test_provider_gates_are_shared_across_runs(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path)))
    a = service.new_context(_request(), lambda: False)
    b = service.new_context(_request(), lambda: False)
    assert a.guard._gates is b.guard._gates
    assert a.guard.ledger is not b.guard.ledger
    service.shutdown()
