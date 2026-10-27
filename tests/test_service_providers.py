"""Service wiring for NVIDIA Build and the alternative providers."""

from __future__ import annotations

from pathlib import Path

from core.models import Mode
from core.settings import load_settings
from service import build_service

ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path, **over: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "tvly-test",
        "NVIDIA_API_KEY": "nvapi-secret-value",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "nvidia",
        "WRITER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        "VERIFIER_MODEL": "google/gemma-4-31b-it",
        "PRICE_SHEET_PATH": str(ROOT / "core" / "price_sheet_nvidia_free.json"),
        "STATE_DIR": str(tmp_path / "state"),
        "LOG_DIR": str(tmp_path / "logs"),
    }
    env.update(over)
    return env


def test_nvidia_service_is_ready_and_serves_both_modes(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path)))
    assert service.ready and not service.demo
    assert service.mode_servable == {Mode.QUICK: True, Mode.DEEP: True}
    service.shutdown()


def test_writer_and_verifier_share_one_rate_limiter_on_the_nvidia_endpoint(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path, NVIDIA_MAX_RPM="30")))
    gates = service._gates
    assert gates["writer"]._bucket is gates["verifier"]._bucket  # one request limit
    assert gates["writer"] is not gates["verifier"]  # but separate circuit breakers
    assert gates["writer"].rate_per_s == 0.5  # 30 requests per minute
    assert gates["search"] is not gates["writer"]
    service.shutdown()


def test_other_providers_keep_independent_limiters(tmp_path: Path) -> None:
    env = _env(
        tmp_path,
        WRITER_PROVIDER="openai",
        VERIFIER_PROVIDER="anthropic",
        OPENAI_API_KEY="k",
        VERIFIER_API_KEY="v",
        WRITER_MODEL="fake-writer",
        VERIFIER_MODEL="fake-verifier",
        PRICE_SHEET_PATH=str(ROOT / "core" / "price_sheet_placeholder.json"),
    )
    env["RESEARCH_PROVIDER_MODE"] = "fake"  # build wiring without live keys
    service = build_service(load_settings(env))
    assert service._gates["writer"] is not service._gates["verifier"]
    service.shutdown()


def test_demo_mode_ignores_the_nvidia_rate_limit(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path, RESEARCH_PROVIDER_MODE="fake")))
    assert service._gates["writer"].rate_per_s >= 1.0
    service.shutdown()


def test_the_about_page_can_name_the_configured_providers_without_secrets(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path)))
    text = " ".join(service.provider_labels)
    assert "Tavily" in text and "NVIDIA Build" in text
    assert "nvidia/nemotron-3-ultra-550b-a55b" in text and "google/gemma-4-31b-it" in text
    assert "nvapi-secret-value" not in text
    service.shutdown()
    demo = build_service(load_settings(_env(tmp_path, RESEARCH_PROVIDER_MODE="fake")))
    assert any("Scripted demo" in label for label in demo.provider_labels)
    demo.shutdown()


def test_free_prototype_pricing_is_disclosed_as_not_guaranteed(tmp_path: Path) -> None:
    service = build_service(load_settings(_env(tmp_path)))
    assert service.cost_note and "free" in service.cost_note.lower()
    assert "change" in service.cost_note.lower()
    service.shutdown()


def test_service_passes_the_timeout_factors_into_every_context(tmp_path: Path) -> None:
    from core.models import ResearchRequest

    service = build_service(
        load_settings(_env(tmp_path, VERIFIER_TIMEOUT_FACTOR="2", WRITER_TIMEOUT_FACTOR="1.5"))
    )
    ctx = service.new_context(
        ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="x"), lambda: False
    )
    assert ctx.verifier_timeout_factor == 2.0 and ctx.writer_timeout_factor == 1.5
    service.shutdown()
