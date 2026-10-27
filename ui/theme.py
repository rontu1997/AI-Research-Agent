"""Design tokens and the only place app-owned HTML is produced (design.md §12).

`unsafe_allow_html=True` appears in this module and nowhere else. Markup is built from literal
templates; only fixed state names, integers and strings from `ui/copy.py` are inserted, and
anything else is HTML-escaped first.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

import streamlit as st

from core.models import EvidenceMode, RunStatus

LIGHT: dict[str, str] = {
    "bg": "#FFFFFF",
    "surface": "#F3F5F8",
    "text": "#1B2330",
    "text2": "#475467",
    "primary": "#0B5CAD",
    "primary_text": "#FFFFFF",
    "primary_hover": "#094C8F",
    "primary_active": "#073D73",
    "surface_hover": "#E6EAF0",
    "border": "#667085",
    "divider": "#D5DAE1",
    "ok_fg": "#0B5D2A",
    "ok_bg": "#E7F5EC",
    "ok_bd": "#2E7D4F",
    "warn_fg": "#7A4300",
    "warn_bg": "#FFF3DC",
    "warn_bd": "#B26A00",
    "err_fg": "#9B1C1C",
    "err_bg": "#FDECEC",
    "err_bd": "#C62828",
    "info_fg": "#0B4A7A",
    "info_bg": "#E8F1FA",
    "info_bd": "#2F6FA8",
}
SPACE = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48}
RADIUS = {1: 6, 2: 10}

_STATUS_STYLE = {
    RunStatus.COMPLETED: ("ok", "\u2713", "COMPLETED"),
    RunStatus.PARTIAL: ("warn", "!", "PARTIAL"),
    RunStatus.FAILED: ("err", "\u2715", "FAILED"),
}
_BADGE_STYLE = {
    EvidenceMode.SNIPPET: ("info", "Search snippet"),
    EvidenceMode.EXTRACTED: ("ok", "Extracted page text"),
    EvidenceMode.METADATA_ONLY: ("muted", "Not inspected (title only)"),
}


def css() -> str:
    t = LIGHT
    return f"""
:root {{
  --ar-color-primary: {t["primary"]}; --ar-color-text-2: {t["text2"]};
  --ar-color-border: {t["border"]}; --ar-color-divider: {t["divider"]};
  --ar-color-surface: {t["surface"]};
}}
.block-container {{ max-width: 46rem; padding-top: {SPACE[5]}px; }}
h1 {{ font-size: 1.75rem; line-height: 1.25; font-weight: 700; }}
h2 {{ font-size: 1.375rem; line-height: 1.3; font-weight: 700; }}
h3 {{ font-size: 1.125rem; line-height: 1.35; font-weight: 600; }}
a {{ overflow-wrap: anywhere; }}
:focus-visible {{ outline: 3px solid {t["primary"]} !important; outline-offset: 2px !important; }}
.ar-banner {{ border: 2px solid; border-radius: {RADIUS[2]}px; padding: {SPACE[4]}px {SPACE[5]}px;
  margin: {SPACE[4]}px 0; }}
.ar-banner h2 {{ margin: 0 0 {SPACE[2]}px 0; padding: 0; font-size: 1.375rem; }}
.ar-banner p, .ar-banner li {{ margin: {SPACE[1]}px 0; }}
.ar-ok {{ background: {t["ok_bg"]}; border-color: {t["ok_bd"]}; color: {t["ok_fg"]}; }}
.ar-warn {{ background: {t["warn_bg"]}; border-color: {t["warn_bd"]}; color: {t["warn_fg"]}; }}
.ar-err {{ background: {t["err_bg"]}; border-color: {t["err_bd"]}; color: {t["err_fg"]}; }}
.ar-info {{ background: {t["info_bg"]}; border-color: {t["info_bd"]}; color: {t["info_fg"]}; }}
.ar-badge {{ display: inline-block; font-size: 0.875rem; border: 1px solid; border-radius: {RADIUS[1]}px;
  padding: 0 {SPACE[2]}px; }}
.ar-muted {{ background: {t["surface"]}; border-color: {t["border"]}; color: {t["text2"]}; }}
.ar-quote {{ border-left: 4px solid {t["divider"]}; padding-left: {SPACE[3]}px; margin: {SPACE[2]}px 0; }}
.ar-claim-no {{ color: {t["text2"]}; font-size: 0.875rem; }}
"""


def inject_css() -> None:
    st.markdown(f"<style>{css()}</style>", unsafe_allow_html=True)


def banner_html(status: RunStatus, headline: str, reasons: Sequence[str] = ()) -> str:
    kind, glyph, label = _STATUS_STYLE[status]
    items = "".join(f"<li>{escape(r)}</li>" for r in reasons)
    reason_block = f"<p>Why this is {label.lower()}:</p><ul>{items}</ul>" if items else ""
    return (
        f'<div class="ar-banner ar-{kind}" role="status">'
        f"<h2>{glyph} {label}</h2><p>{escape(headline)}</p>{reason_block}</div>"
    )


def notice_html(kind: str, message: str) -> str:
    glyph = {"info": "i", "warn": "!", "err": "\u2715"}.get(kind, "i")
    kind = kind if kind in {"info", "warn", "err"} else "info"
    return f'<div class="ar-banner ar-{kind}" role="status"><p>{glyph} {escape(message)}</p></div>'


def badge_html(mode: EvidenceMode) -> str:
    kind, label = _BADGE_STYLE[mode]
    return f'<span class="ar-badge ar-{kind}">{escape(label)}</span>'


def render_banner(status: RunStatus, headline: str, reasons: Sequence[str] = ()) -> None:
    st.markdown(banner_html(status, headline, reasons), unsafe_allow_html=True)


def render_notice(kind: str, message: str) -> None:
    st.markdown(notice_html(kind, message), unsafe_allow_html=True)


def render_badge(mode: EvidenceMode) -> None:
    st.markdown(badge_html(mode), unsafe_allow_html=True)
