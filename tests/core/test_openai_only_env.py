"""The shipped configuration starts live with one OpenAI API key."""

from pathlib import Path

from adapters.live import OpenAIChat, OpenAIWebSearch, build_live_providers
from core.capacity import check_call_graph
from core.models import Mode
from core.settings import load_settings, mode_config, parse_env_file, startup_problems

ROOT = Path(__file__).resolve().parents[2]


def test_env_template_needs_only_openai_api_key() -> None:
    values = parse_env_file(ROOT / ".env.example")
    assert values["RESEARCH_PROVIDER_MODE"] == "live"
    assert values["SEARCH_PROVIDER"] == "openai"
    assert values["WRITER_PROVIDER"] == values["VERIFIER_PROVIDER"] == "openai"
    assert values["WRITER_MODEL"] == values["VERIFIER_MODEL"] == "gpt-6-luna"
    assert values["OPENAI_API_KEY"] == ""
    assert not any(
        name in values for name in ("SEARCH_API_KEY", "VERIFIER_API_KEY", "NVIDIA_API_KEY")
    )
    configured = dict(values, OPENAI_API_KEY="sk-test")
    configured["PRICE_SHEET_PATH"] = str(ROOT / values["PRICE_SHEET_PATH"])
    assert startup_problems(load_settings(configured)) == []


def test_same_luna_model_is_allowed_for_openai_verifier() -> None:
    settings = load_settings(
        {
            "RESEARCH_PROVIDER_MODE": "live",
            "SEARCH_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-test",
            "WRITER_MODEL": "gpt-6-luna",
            "VERIFIER_MODEL": "gpt-6-luna",
            "PRICE_SHEET_PATH": str(ROOT / "core" / "price_sheet_openai.json"),
        }
    )
    assert settings.verifier_api_key is not None
    assert settings.verifier_api_key.get_secret_value() == "sk-test"
    assert startup_problems(settings) == []
    providers = build_live_providers(settings)
    assert isinstance(providers.search, OpenAIWebSearch)
    assert isinstance(providers.writer, OpenAIChat)
    assert isinstance(providers.verifier, OpenAIChat)
    assert providers.writer_model == providers.verifier_model == "gpt-6-luna"
    for mode in Mode:
        assert check_call_graph(
            mode_config(mode), settings.price_sheet, "gpt-6-luna", "gpt-6-luna"
        ).ok


def test_one_key_profile_does_not_use_a_stale_verifier_key_or_custom_endpoint() -> None:
    settings = load_settings(
        {
            "RESEARCH_PROVIDER_MODE": "live",
            "SEARCH_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-openai",
            "VERIFIER_API_KEY": "stale-old-key",
            "WRITER_MODEL": "gpt-6-luna",
            "VERIFIER_MODEL": "gpt-6-luna",
            "PRICE_SHEET_PATH": str(ROOT / "core" / "price_sheet_openai.json"),
            "OPENAI_BASE_URL": "https://example.org/v1",
            "VERIFIER_BASE_URL": "https://example.org/v1",
        }
    )
    assert settings.verifier_api_key is not None
    assert settings.verifier_api_key.get_secret_value() == "sk-openai"
    assert {"OPENAI_BASE_URL", "VERIFIER_BASE_URL"} <= set(startup_problems(settings))
