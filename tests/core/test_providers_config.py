"""Provider selection: NVIDIA Build and other OpenAI-compatible endpoints, model families, price sheets."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.capacity import check_call_graph
from core.models import Mode
from core.settings import (
    PriceSheet,
    load_settings,
    mode_config,
    model_family,
    parse_env_file,
    startup_problems,
)

ROOT = Path(__file__).resolve().parents[2]
NVIDIA_SHEET = ROOT / "core" / "price_sheet_nvidia_free.json"
WRITER = "nvidia/nemotron-3-ultra-550b-a55b"
VERIFIER = "openai/gpt-oss-20b"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"


def _nvidia_env(**over: str) -> dict[str, str]:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "tvly-test",
        "NVIDIA_API_KEY": "nvapi-test",
        "WRITER_PROVIDER": "nvidia",
        "VERIFIER_PROVIDER": "nvidia",
        "WRITER_MODEL": WRITER,
        "VERIFIER_MODEL": VERIFIER,
        "PRICE_SHEET_PATH": str(NVIDIA_SHEET),
    }
    env.update(over)
    return env


# --- model families -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("nvidia/nemotron-3-ultra-550b-a55b", "nemotron"),
        ("google/gemma-4-31b-it", "google"),
        ("meta/llama-3.1-70b-instruct", "meta"),
        ("gpt-5", "openai"),
        ("openai/gpt-oss-20b", "openai"),
        ("claude-sonnet-5-5", "anthropic"),
        ("gemma-4", "google"),
        ("llama3.2:3b", "meta"),
        ("nvidia/llama-3.1-nemotron-70b-instruct", "meta"),
        ("ollama/llama3", "meta"),
        ("fake-writer", "fake"),
    ],
)
def test_model_family_comes_from_the_vendor_prefix_or_the_model_name(
    model: str, family: str
) -> None:
    assert model_family(model) == family


def test_same_family_writer_and_verifier_is_refused() -> None:
    same = _nvidia_env(
        WRITER_MODEL="meta/llama-3.1-70b-instruct", VERIFIER_MODEL="meta/llama-3.3-70b"
    )
    assert "VERIFIER_NOT_INDEPENDENT" in startup_problems(load_settings(same))
    cross = _nvidia_env(WRITER_MODEL="gpt-5", VERIFIER_MODEL="openai/gpt-oss-20b")
    assert "VERIFIER_NOT_INDEPENDENT" in startup_problems(load_settings(cross))


def test_nemotron_with_gemma_on_nvidia_build_is_accepted() -> None:
    assert startup_problems(load_settings(_nvidia_env())) == []


# --- keys, providers, urls --------------------------------------------------------------------------


def test_nvidia_roles_need_only_the_nvidia_and_search_keys() -> None:
    problems = startup_problems(load_settings(_nvidia_env(NVIDIA_API_KEY="")))
    assert "NVIDIA_API_KEY" in problems
    assert "OPENAI_API_KEY" not in problems and "VERIFIER_API_KEY" not in problems
    assert "SEARCH_API_KEY" not in problems


def test_original_openai_and_anthropic_configuration_still_validates() -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "a",
        "OPENAI_API_KEY": "b",
        "VERIFIER_API_KEY": "c",
        "WRITER_MODEL": "gpt-5",
        "VERIFIER_MODEL": "claude-sonnet-5-5",
        "PRICE_SHEET_PATH": str(ROOT / "core" / "price_sheet_placeholder.json"),
    }
    problems = startup_problems(load_settings(env))
    assert "NVIDIA_API_KEY" not in problems
    assert "OPENAI_API_KEY" not in problems and "VERIFIER_NOT_INDEPENDENT" not in problems


def test_unknown_providers_and_json_modes_are_named() -> None:
    problems = startup_problems(
        load_settings(_nvidia_env(WRITER_PROVIDER="x", VERIFIER_PROVIDER="y", WRITER_JSON_MODE="z"))
    )
    assert {"WRITER_PROVIDER", "VERIFIER_PROVIDER", "WRITER_JSON_MODE"} <= set(problems)


@pytest.mark.parametrize(
    ("name", "value", "bad"),
    [
        ("OPENAI_BASE_URL", "http://example.org/v1", True),
        ("VERIFIER_BASE_URL", "ftp://example.org", True),
        ("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1", False),
        ("OPENAI_BASE_URL", "http://localhost:11434/v1", False),
        ("VERIFIER_BASE_URL", "http://127.0.0.1:8000/v1", False),
        ("OPENAI_BASE_URL", "", False),
    ],
)
def test_base_urls_must_be_https_unless_local(name: str, value: str, bad: bool) -> None:
    problems = startup_problems(load_settings(_nvidia_env(**{name: value})))
    assert (name in problems) is bad


def test_api_keys_never_appear_in_settings_repr_or_problems() -> None:
    settings = load_settings(_nvidia_env(NVIDIA_API_KEY="nvapi-super-secret"))
    assert "nvapi-super-secret" not in repr(settings)
    assert "nvapi-super-secret" not in " ".join(
        startup_problems(load_settings(_nvidia_env(WRITER_MODEL="")))
    )


def test_defaults_for_urls_json_modes_thinking_and_rate() -> None:
    s = load_settings(_nvidia_env())
    assert s.openai_base_url == "" and s.verifier_base_url == ""
    assert (
        s.writer_json_mode == "none" and s.verifier_json_mode == "none"
    )  # NVIDIA: prompt-instructed JSON
    assert s.writer_thinking is False
    assert s.nvidia_max_rpm == 40
    openai = load_settings({"WRITER_MODEL": "gpt-5"})
    assert openai.writer_provider == "openai" and openai.writer_json_mode == "json_object"
    assert (
        load_settings(_nvidia_env(WRITER_JSON_MODE="json_object")).writer_json_mode == "json_object"
    )
    assert load_settings(_nvidia_env(WRITER_THINKING="on")).writer_thinking is True


def test_nonsense_request_rate_is_a_named_problem() -> None:
    for bad in ("0", "-5", "100000"):
        assert "NVIDIA_MAX_RPM" in startup_problems(load_settings(_nvidia_env(NVIDIA_MAX_RPM=bad)))


# --- the free-prototype price sheet ----------------------------------------------------------------------


def test_free_prototype_price_sheet_keeps_budget_controls_and_an_expiry() -> None:
    sheet = PriceSheet.from_file(NVIDIA_SHEET)
    assert sheet.free_prototype and not sheet.placeholder
    assert sheet.has_model(WRITER) and sheet.has_model(VERIFIER)
    assert sheet.review_after is not None and sheet.review_after > date(2026, 10, 22)
    # Budgeting rates are not zero: the caps must still bind if the free tier ends.
    assert sheet.token_cost(WRITER, 1000, 1000) > 0 and sheet.token_cost(VERIFIER, 1000, 1000) > 0
    for mode in Mode:
        assert check_call_graph(mode_config(mode), sheet, WRITER, VERIFIER).ok


def test_an_expired_price_sheet_refuses_live_mode_until_rechecked() -> None:
    settings = load_settings(_nvidia_env())
    assert "PRICE_SHEET_EXPIRED" not in startup_problems(settings, today=date(2026, 10, 22))
    assert "PRICE_SHEET_EXPIRED" in startup_problems(settings, today=date(2035, 1, 1))


# --- the shipped .env.example ----------------------------------------------------------------------------


def test_env_example_describes_one_key_openai_setup_without_other_providers() -> None:
    values = parse_env_file(ROOT / ".env.example")
    assert values["WRITER_MODEL"] == values["VERIFIER_MODEL"] == "gpt-6-luna"
    assert values["WRITER_PROVIDER"] == values["VERIFIER_PROVIDER"] == "openai"
    assert values["SEARCH_PROVIDER"] == "openai"
    assert values["VERIFIER_PARALLEL"] == "1"
    assert values["RUN_TIME_FACTOR"] == "1.0"  # the PRD wall-clock limits are not relaxed
    assert values["RESEARCH_PROVIDER_MODE"] == "live"
    assert values["OPENAI_API_KEY"] == ""
    assert not any(
        name in values for name in ("NVIDIA_API_KEY", "SEARCH_API_KEY", "VERIFIER_API_KEY")
    )
    live = dict(values, OPENAI_API_KEY="k")
    live["PRICE_SHEET_PATH"] = str(ROOT / values["PRICE_SHEET_PATH"])
    assert startup_problems(load_settings(live)) == []


def test_token_parameter_name_is_configurable_with_provider_defaults() -> None:
    nvidia = load_settings(_nvidia_env())
    assert nvidia.writer_token_param == "max_tokens" and nvidia.verifier_token_param == "max_tokens"
    openai = load_settings({"WRITER_MODEL": "gpt-5"})
    assert openai.writer_token_param == "max_completion_tokens"
    flipped = load_settings(_nvidia_env(VERIFIER_TOKEN_PARAM="max_completion_tokens"))
    assert flipped.verifier_token_param == "max_completion_tokens"
    bad = load_settings(_nvidia_env(WRITER_TOKEN_PARAM="tokens"))
    assert "WRITER_TOKEN_PARAM" in startup_problems(bad)


def test_model_call_timeouts_scale_by_role_with_named_validation() -> None:
    s = load_settings(_nvidia_env())
    assert s.writer_timeout_factor == 1.0 and s.verifier_timeout_factor == 1.0
    slow = load_settings(_nvidia_env(VERIFIER_TIMEOUT_FACTOR="2.5", WRITER_TIMEOUT_FACTOR="1.5"))
    assert slow.verifier_timeout_factor == 2.5 and slow.writer_timeout_factor == 1.5
    for name in ("WRITER_TIMEOUT_FACTOR", "VERIFIER_TIMEOUT_FACTOR"):
        for bad in ("0", "-1", "50"):
            assert name in startup_problems(load_settings(_nvidia_env(**{name: bad})))
