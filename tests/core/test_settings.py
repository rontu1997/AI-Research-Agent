import json
from pathlib import Path

import pytest

from core.errors import ErrorCode
from core.models import Mode
from core.settings import (
    PriceSheet,
    load_settings,
    mode_config,
    parse_env_file,
    startup_problems,
)


def test_quick_mode_config_matches_prd_table() -> None:
    q = mode_config(Mode.QUICK)
    assert (q.planned_queries, q.search_query_cap, q.max_sources) == (3, 4, 8)
    assert q.max_passages_per_source == 6
    assert (q.max_claims, q.max_quotes_per_claim) == (14, 3)
    assert (q.writer_input_cap, q.verifier_input_cap) == (9000, 7000)
    assert (q.repair_max_claims, q.repair_input_cap) == (6, 5000)
    assert q.wall_clock_s == 120
    assert q.cost_cap_usd == 0.75
    assert (q.min_groups, q.min_domains, q.min_claims, q.min_facets) == (3, 2, 4, 2)
    assert q.max_snippet_share == 0.80
    assert q.required_planned_facets == 3


def test_deep_mode_config_matches_prd_table() -> None:
    d = mode_config(Mode.DEEP)
    assert (d.planned_queries, d.search_query_cap, d.max_sources) == (8, 10, 20)
    assert d.max_passages_per_source == 8
    assert (d.max_claims, d.max_quotes_per_claim) == (36, 4)
    assert (d.writer_input_cap, d.verifier_input_cap) == (24000, 9000)
    assert (d.repair_max_claims, d.repair_input_cap) == (12, 8000)
    assert d.wall_clock_s == 360
    assert d.cost_cap_usd == 3.00
    assert (d.min_groups, d.min_domains, d.min_claims, d.min_facets) == (6, 3, 8, 3)
    assert d.max_snippet_share == 0.70
    assert d.required_planned_facets == 4


def test_parse_env_file_handles_comments_quotes_and_blank_lines(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text('# comment\n\nA=1\nB="two words"\nC=\nexport D=x\n', encoding="utf-8")
    assert parse_env_file(f) == {"A": "1", "B": "two words", "C": "", "D": "x"}


def test_parse_env_file_missing_file_returns_empty(tmp_path: Path) -> None:
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_defaults_come_from_the_documented_values() -> None:
    s = load_settings({})
    assert s.provider_mode == "fake"
    assert s.max_concurrent_runs == 5
    assert s.heartbeat_timeout_s == 90
    assert s.result_ttl_min == 30
    assert s.abandoned_ttl_min == 10
    assert s.est_chars_per_token == 3.5
    assert s.drain_timeout_s == 120
    assert s.log_retention_days == 7


def test_secrets_never_appear_in_repr_or_str() -> None:
    s = load_settings({"OPENAI_API_KEY": "sk-super-secret", "SEARCH_API_KEY": "tvly-secret"})
    text = repr(s) + str(s)
    assert "sk-super-secret" not in text
    assert "tvly-secret" not in text
    assert s.openai_api_key is not None
    assert s.openai_api_key.get_secret_value() == "sk-super-secret"


def test_fake_mode_needs_no_keys() -> None:
    assert startup_problems(load_settings({"RESEARCH_PROVIDER_MODE": "fake"})) == []


def test_live_mode_reports_missing_settings_by_name_only() -> None:
    s = load_settings({"RESEARCH_PROVIDER_MODE": "live"})
    problems = startup_problems(s)
    assert "SEARCH_API_KEY" not in problems
    assert "OPENAI_API_KEY" in problems
    assert "VERIFIER_API_KEY" not in problems
    assert "WRITER_MODEL" in problems
    assert "VERIFIER_MODEL" in problems


def test_live_mode_flags_unpriced_models() -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "a",
        "OPENAI_API_KEY": "b",
        "VERIFIER_API_KEY": "c",
        "WRITER_MODEL": "some-writer",
        "VERIFIER_MODEL": "some-verifier",
    }
    problems = startup_problems(load_settings(env))
    assert "PRICE:some-writer" in problems
    assert "PRICE:some-verifier" in problems


def test_invalid_provider_mode_is_a_problem() -> None:
    assert "RESEARCH_PROVIDER_MODE" in startup_problems(
        load_settings({"RESEARCH_PROVIDER_MODE": "x"})
    )


def test_price_sheet_cost_uses_per_million_prices() -> None:
    sheet = PriceSheet(
        version="t",
        placeholder=False,
        safety_factor=1.25,
        models={"m": (2.5, 10.0)},
        search_per_call=0.016,
    )
    assert sheet.token_cost("m", 1_000_000, 0) == pytest.approx(2.5)
    assert sheet.token_cost("m", 0, 1_000_000) == pytest.approx(10.0)
    assert sheet.token_cost("m", 1000, 500) == pytest.approx(0.0075)


def test_unpriced_model_raises_config_invalid() -> None:
    sheet = PriceSheet("t", False, 1.25, {}, 0.016)
    with pytest.raises(Exception) as exc:
        sheet.token_cost("unknown", 1, 1)
    assert getattr(exc.value, "code", None) is ErrorCode.CONFIG_INVALID


def test_price_sheet_loads_from_json_file(tmp_path: Path) -> None:
    p = tmp_path / "prices.json"
    p.write_text(
        json.dumps(
            {
                "version": "real-1",
                "placeholder": False,
                "safety_factor": 1.25,
                "models": {"w": {"in_per_m": 1.0, "out_per_m": 2.0}},
                "search_per_call": 0.01,
            }
        ),
        encoding="utf-8",
    )
    s = load_settings({"PRICE_SHEET_PATH": str(p)})
    assert s.price_sheet.version == "real-1"
    assert s.price_sheet.token_cost("w", 1_000_000, 1_000_000) == pytest.approx(3.0)


def test_bundled_placeholder_sheet_is_marked_placeholder() -> None:
    s = load_settings({})
    assert s.price_sheet.placeholder is True
    assert s.price_sheet.search_per_call == pytest.approx(0.016)


def test_live_mode_refuses_the_placeholder_price_sheet() -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "k1",
        "OPENAI_API_KEY": "k2",
        "VERIFIER_API_KEY": "k3",
        "WRITER_MODEL": "fake-writer",
        "VERIFIER_MODEL": "fake-verifier",
    }
    problems = startup_problems(load_settings(env))
    assert "PRICE_SHEET_PLACEHOLDER" in problems
    assert not any("k1" in p or "k2" in p or "k3" in p for p in problems)


def test_live_mode_requires_a_verifier_from_a_different_model_family() -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "live",
        "SEARCH_API_KEY": "a",
        "OPENAI_API_KEY": "b",
        "VERIFIER_API_KEY": "c",
        "WRITER_MODEL": "gpt-5",
        "VERIFIER_MODEL": "openai/gpt-oss-20b",
        "VERIFIER_PROVIDER": "openai",
    }
    assert "VERIFIER_NOT_INDEPENDENT" in startup_problems(load_settings(env))
    env["VERIFIER_MODEL"] = "claude-sonnet-5-5"
    env["VERIFIER_PROVIDER"] = "anthropic"
    assert "VERIFIER_NOT_INDEPENDENT" not in startup_problems(load_settings(env))
    env["VERIFIER_PROVIDER"] = "mystery"
    assert "VERIFIER_PROVIDER" in startup_problems(load_settings(env))


def test_env_file_location_can_be_chosen_with_env_file(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    from core.settings import load_settings_from_environment

    custom = tmp_path / "custom.env"
    custom.write_text("WRITER_MODEL=from-custom-file\n", encoding="utf-8")
    monkeypatch.delenv("WRITER_MODEL", raising=False)
    monkeypatch.setenv("ENV_FILE", str(custom))
    assert load_settings_from_environment().writer_model == "from-custom-file"
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "missing.env"))
    assert load_settings_from_environment().writer_model == ""
