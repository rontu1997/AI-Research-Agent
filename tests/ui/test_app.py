"""End-to-end UI checks with Streamlit's AppTest over the scripted demo providers."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from adapters.fakes import DEMO_TOPIC

APP = str(Path(__file__).resolve().parents[2] / "app.py")


@pytest.fixture(autouse=True)
def demo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_PROVIDER_MODE", "fake")
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CONTACT_URL", "https://contact.example.org/report")
    st.cache_resource.clear()


def _app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _button(at: AppTest, label: str):  # noqa: ANN202
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button {label!r}; have {[b.label for b in at.button]}"
    return matches[0]


def _markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def _all_text(at: AppTest) -> str:
    return _markdown(at) + "\n" + "\n".join(c.value for c in at.caption)


def _run_to_result(at: AppTest, topic: str = DEMO_TOPIC, depth: str = "Quick") -> AppTest:
    at.text_area(key="topic:input").set_value(topic)
    at.radio(key="depth:select").set_value(depth)
    _button(at, "Research").click()
    at.run()
    for _ in range(120):
        text = _markdown(at)
        if any(word in text for word in ("COMPLETED", "PARTIAL", "FAILED")):
            return at
        time.sleep(0.5)
        at.run()
    raise AssertionError("run did not finish")


def test_idle_page_has_title_form_tabs_and_demo_label() -> None:
    at = _app()
    assert at.title[0].value == "AI Research Agent"
    assert [t.label for t in at.tabs] == ["Research", "About / Privacy", "FAQ"]
    assert at.text_area(key="topic:input").label.startswith("Topic (English")
    assert "Demo mode" in _markdown(at)
    assert not at.exception


def test_example_chip_fills_the_topic_without_starting_a_run() -> None:
    at = _app()
    chip = _button(at, "Urban heat islands")
    chip.click()
    at.run()
    assert at.text_area(key="topic:input").value == "Urban heat islands"
    assert not any("Researching" in m.value for m in at.markdown)


def test_empty_topic_shows_an_error_and_keeps_the_form() -> None:
    at = _app()
    _button(at, "Research").click()
    at.run()
    assert "Please enter a topic to research." in _markdown(at)


def test_unsupported_language_is_refused_before_any_run() -> None:
    at = _app()
    at.text_area(key="topic:input").set_value("これは日本語のトピックです。" * 4)
    _button(at, "Research").click()
    at.run()
    assert "This pilot accepts English-language topics only." in _markdown(at)


def test_demo_run_completes_with_banner_evidence_and_download() -> None:
    at = _run_to_result(_app())
    text = _markdown(at)
    assert "COMPLETED" in text and "Minimum evidence thresholds were met" in text
    assert "Demo mode" in text
    toggles = [t for t in at.toggle if t.label.startswith("Show evidence (C")]
    assert toggles, "expected one evidence toggle per displayed claim"
    toggles[0].set_value(True)
    at.run()
    shown = _all_text(at)
    assert "Passage 1:p" in shown or "Passage 2:p" in shown
    assert "Extracted page text" in shown or "Search snippet" in shown
    assert not at.exception


def test_clear_session_removes_the_report_and_confirms() -> None:
    at = _run_to_result(_app())
    _button(at, "Clear session").click()
    at.run()
    text = _markdown(at)
    assert "COMPLETED" not in text
    assert "Session cleared in this app; external provider processing is unchanged." in text


def test_feedback_vote_replaces_the_buttons_with_a_confirmation() -> None:
    at = _run_to_result(_app())
    _button(at, "Useful").click()
    at.run()
    assert "Thanks" in _markdown(at)
    assert not [b for b in at.button if b.label in {"Useful", "Not useful"}]


def test_privacy_and_faq_tabs_are_headed_documents_with_the_contact_link() -> None:
    at = _app()
    text = _markdown(at)
    assert "## Who processes your topic" in text
    assert "## Why is there no Cancel button?" in text
    assert "https://contact.example.org/report" in text


def test_off_topic_question_in_demo_mode_explains_the_demo_limit() -> None:
    at = _run_to_result(_app(), topic="AI in surfactants discovery")
    text = _markdown(at) + "\n" + "\n".join(c.value for c in at.caption)
    assert "FAILED" in text
    assert "Demo mode only has data about the Harborview bike-share pilot" in text
    assert "Harborview bike-share pilot: program overview" not in text


def test_about_page_names_the_configured_providers_in_demo_mode() -> None:
    at = _app()
    text = _markdown(at)
    assert "## Configured providers" in text
    assert "Scripted demo providers" in text


def test_live_nvidia_configuration_is_named_and_the_free_tier_caveat_is_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("RESEARCH_PROVIDER_MODE", "live")
    monkeypatch.setenv("SEARCH_API_KEY", "tvly-test")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secret-value")
    monkeypatch.setenv("WRITER_PROVIDER", "nvidia")
    monkeypatch.setenv("VERIFIER_PROVIDER", "nvidia")
    monkeypatch.setenv("WRITER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    monkeypatch.setenv("VERIFIER_MODEL", "google/gemma-4-31b-it")
    monkeypatch.setenv("PRICE_SHEET_PATH", str(root / "core" / "price_sheet_nvidia_free.json"))
    st.cache_resource.clear()
    at = _app()
    text = _all_text(at)
    assert "NVIDIA Build" in text and "google/gemma-4-31b-it" in text
    assert "free prototype API" in text and "can change" in text
    assert "nvapi-secret-value" not in text
    assert "Demo mode" not in text
