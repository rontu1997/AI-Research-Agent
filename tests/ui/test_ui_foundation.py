from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from core.models import Mode, RunStatus
from eval.contrast import contrast_ratio, failing_pairs
from ui import copy as ui_copy
from ui import state as ui_state
from ui import theme

ROOT = Path(__file__).resolve().parents[2]


# --- theme and contrast ------------------------------------------------------------------------


def test_every_required_contrast_pair_passes_wcag() -> None:
    assert failing_pairs(theme.LIGHT) == []


def test_contrast_formula_matches_known_values() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#1B2330", "#FFFFFF") == pytest.approx(15.79, abs=0.02)


def test_streamlit_config_agrees_with_theme_tokens() -> None:
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))[
        "theme"
    ]
    assert config["primaryColor"].upper() == theme.LIGHT["primary"]
    assert config["backgroundColor"].upper() == theme.LIGHT["bg"]
    assert config["secondaryBackgroundColor"].upper() == theme.LIGHT["surface"]
    assert config["textColor"].upper() == theme.LIGHT["text"]


def test_unsafe_html_flag_appears_only_in_the_theme_module() -> None:
    offenders = []
    for path in ROOT.rglob("*.py"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & {".venv", "tests", "__pycache__"}:
            continue
        if "unsafe_allow_html=True" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == ["ui/theme.py"]


def test_no_hard_coded_hex_colors_outside_theme_and_eval() -> None:
    hexes = re.compile(r"#[0-9A-Fa-f]{6}\b")
    offenders = []
    for folder in ("ui",):
        for path in (ROOT / folder).glob("*.py"):
            if path.name == "theme.py":
                continue
            if hexes.search(path.read_text(encoding="utf-8")):
                offenders.append(path.name)
    assert offenders == []


def test_banner_html_inserts_only_known_values_and_escapes_the_rest() -> None:
    html = theme.banner_html(RunStatus.PARTIAL, "Headline <script>", ["Reason one", "<b>two</b>"])
    assert "<script>" not in html and "<b>" not in html
    assert "PARTIAL" in html and "Reason one" in html


# --- copy --------------------------------------------------------------------------------------


def test_copy_has_the_prd_messages_verbatim() -> None:
    assert (
        ui_copy.text("state.invalid_language") == "This pilot accepts English-language topics only."
    )
    assert ui_copy.text("state.busy") == "The service is at capacity. Please try again in a minute."
    assert ui_copy.text("state.failed") == (
        "No report was produced because the available evidence could not support two factual findings."
    )
    assert ui_copy.text("state.paused") == "Research is paused right now. Please try again later."


def test_every_reason_code_has_a_plain_sentence() -> None:
    for code in (
        "LOW_EVIDENCE_GROUPS",
        "LOW_DOMAINS",
        "INSUFFICIENT_CLAIMS",
        "INCOMPLETE_FACETS",
        "SNIPPET_HEAVY",
        "TIMEOUT",
        "BUDGET_STOP",
    ):
        assert ui_copy.reason(code)


def test_completed_copy_avoids_forbidden_words() -> None:
    forbidden = ("comprehensive", "exhaustive", "verified true")
    for key in ui_copy.COPY:
        if key.startswith(("state.completed", "label.")):
            # The PRD copy itself says "not exhaustive": a negated disclaimer is allowed (see ledger).
            body = ui_copy.COPY[key].lower().replace("not exhaustive", "")
            assert not any(w in body for w in forbidden), key


def test_evidence_mode_labels_follow_the_design() -> None:
    assert ui_copy.evidence_label("snippet") == "Search snippet"
    assert ui_copy.evidence_label("extracted") == "Extracted page text"
    assert ui_copy.evidence_label("metadata-only") == "Not inspected (title only)"


def test_error_codes_map_to_user_messages_without_internals() -> None:
    for code in (
        "SEARCH_FAILED",
        "MODEL_FAILED",
        "VERIFIER_FAILED",
        "INTEGRITY_FAILED",
        "NO_EVIDENCE",
        "PLAN_TOO_NARROW",
        "BUDGET_STOP",
        "TIMEOUT",
        "ABANDONED",
    ):
        message = ui_copy.failure_message(code)
        assert message and "Traceback" not in message and code not in message


# --- state -------------------------------------------------------------------------------------


def test_stage_index_maps_internal_stages_to_six_ui_stages() -> None:
    assert [
        ui_state.stage_index(s)
        for s in (
            "planning",
            "searching",
            "reading",
            "drafting",
            "verifying",
            "repairing",
            "finishing",
        )
    ] == [0, 1, 2, 3, 4, 4, 5]
    assert len(ui_state.UI_STAGES) == 6


def test_ensure_session_creates_a_stable_id_and_token() -> None:
    store: dict[str, object] = {}
    ui_state.ensure_session(store)
    first = (store["ui:session_id"], store["ui:token"])
    ui_state.ensure_session(store)
    assert (store["ui:session_id"], store["ui:token"]) == first


def test_new_attempt_rotates_the_idempotency_token() -> None:
    store: dict[str, object] = {}
    ui_state.ensure_session(store)
    old = store["ui:token"]
    ui_state.new_attempt(store)
    assert store["ui:token"] != old


def test_clear_session_removes_ui_state_but_keeps_nothing_sensitive() -> None:
    store: dict[str, object] = {"ui:session_id": "s", "ui:run_id": "r", "ui:topic": "t", "other": 1}
    ui_state.clear_session(store)
    assert "ui:run_id" not in store and "ui:topic" not in store
    assert store["other"] == 1


def test_export_filename_never_contains_the_topic() -> None:
    from datetime import datetime

    now = datetime(2026, 10, 21, 9, 5)
    assert ui_state.export_filename(RunStatus.COMPLETED, now) == "ai-research-20261021-0905.md"
    assert (
        ui_state.export_filename(RunStatus.PARTIAL, now) == "ai-research-PARTIAL-20261021-0905.md"
    )


def test_depth_caption_comes_from_the_mode_limits() -> None:
    assert "8 sources" in ui_state.depth_caption(
        Mode.QUICK
    ) and "2 minutes" in ui_state.depth_caption(Mode.QUICK)
    assert "20 sources" in ui_state.depth_caption(
        Mode.DEEP
    ) and "6 minutes" in ui_state.depth_caption(Mode.DEEP)
