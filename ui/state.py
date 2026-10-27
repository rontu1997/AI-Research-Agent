"""Session state helpers (ARCH §4.2). Pure functions over a mapping so they test without Streamlit.

Keys follow `component:id` (design DR-11). The session holds a run ID and form values only, never
secrets, provider objects or the report itself (the run manager holds results for a short TTL).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.models import Mode, RunStatus
from core.settings import mode_config, scaled_config

Store = Any  # st.session_state or a plain dict (both support item access, get, pop, setdefault)

UI_STAGES: tuple[str, ...] = (
    "Planning",
    "Searching",
    "Screening sources",
    "Drafting",
    "Verifying claims",
    "Finalizing",
)
_STAGE_INDEX = {
    "planning": 0,
    "searching": 1,
    "reading": 2,
    "drafting": 3,
    "verifying": 4,
    "repairing": 4,
    "finishing": 5,
}
_UI_KEYS = ("ui:run_id", "ui:topic", "ui:notice", "ui:feedback", "ui:started_at")


def stage_index(stage: str) -> int:
    return _STAGE_INDEX.get(stage, 0)


def ensure_session(store: Store) -> None:
    store.setdefault("ui:session_id", uuid.uuid4().hex)
    store.setdefault("ui:token", uuid.uuid4().hex)


def new_attempt(store: Store) -> None:
    store["ui:token"] = uuid.uuid4().hex


def clear_session(store: Store) -> None:
    for key in list(store):
        if key in _UI_KEYS or key.startswith(("evidence:", "topic:", "depth:")):
            del store[key]
    store["ui:token"] = uuid.uuid4().hex


def export_filename(status: RunStatus, now: datetime) -> str:
    tag = "PARTIAL-" if status is RunStatus.PARTIAL else ""
    return f"ai-research-{tag}{now:%Y%m%d-%H%M}.md"


def depth_caption(mode: Mode, run_time_factor: float = 1.0) -> str:
    cfg = scaled_config(mode_config(mode), run_time_factor)
    label = "Quick" if mode is Mode.QUICK else "Deep"
    minutes = cfg.wall_clock_s // 60
    unit = "minute" if minutes == 1 else "minutes"
    return f"{label}: up to {cfg.max_sources} sources, stops after {minutes} {unit}."
