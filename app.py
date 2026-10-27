"""Streamlit entry point. Run with: uv run streamlit run app.py

The UI never runs pipeline work itself: it submits to the run manager, polls by run ID, and
renders the result (ARCH §4.2).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import streamlit as st

from core.errors import ErrorCode
from core.models import Mode, ResearchRequest, RunStatus
from core.run_manager import RunView
from core.settings import load_settings_from_environment, mode_config, scaled_config
from core.validation import validate_topic
from service import Service, build_service
from ui import components, copy, state, theme

st.set_page_config(page_title="AI Research Agent", layout="centered")

_SUBMIT_ERRORS = {
    ErrorCode.BUSY: ("warn", "state.busy"),
    ErrorCode.SESSION_ACTIVE: ("warn", "state.session_active"),
    ErrorCode.SERVICE_PAUSED: ("warn", "state.paused"),
    ErrorCode.CONFIG_INVALID: ("err", "state.config_invalid"),
}


@st.cache_resource
def get_service() -> Service:
    return build_service(load_settings_from_environment())


def _mode() -> Mode:
    return Mode.DEEP if st.session_state.get("depth:select") == "Deep" else Mode.QUICK


def _set_example(text: str) -> None:
    st.session_state["topic:input"] = text


def _start(service: Service) -> None:
    store = st.session_state
    check = validate_topic(store.get("topic:input", ""))
    if not check.ok:
        code = check.error.value if check.error is not None else ErrorCode.INPUT_INVALID.value
        key = (
            "state.invalid_language"
            if code == ErrorCode.LANGUAGE_UNSUPPORTED.value
            else (
                "state.invalid_long"
                if len(store.get("topic:input", "").strip()) > 500
                else "state.invalid_empty"
            )
        )
        store["ui:notice"] = ("err", copy.text(key))
        return
    mode = _mode()
    if not service.mode_servable.get(mode, False):
        store["ui:notice"] = ("warn", copy.text("state.mode_unavailable"))
        return
    if store.get("ui:run_id"):
        state.new_attempt(store)  # a finished earlier run exists: this click is a new search
    request = ResearchRequest(topic=check.topic, depth=mode, idempotency_token=store["ui:token"])
    submission = service.submit(store["ui:session_id"], request)
    if submission.error is not None:
        kind, key = _SUBMIT_ERRORS.get(submission.error, ("err", "state.config_invalid"))
        store["ui:notice"] = (kind, copy.text(key))
        return
    store.pop("ui:notice", None)
    store.pop("ui:feedback", None)
    store["ui:run_id"] = submission.run_id
    store["ui:started_at"] = time.monotonic()


def _clear() -> None:
    state.clear_session(st.session_state)
    st.session_state["ui:notice"] = (
        "info",
        copy.text("state.cleared") + " " + copy.text("next.cleared"),
    )


def _try_again() -> None:
    st.session_state.pop("ui:run_id", None)
    state.new_attempt(st.session_state)


def _evidence_opened(service: Service, claim_id: str) -> None:
    if st.session_state.get(f"evidence:{claim_id}") and service.telemetry is not None:
        service.telemetry.emit("ui.evidence_opened", run_id=st.session_state.get("ui:run_id", ""))


def _vote(service: Service, vote: str) -> None:
    st.session_state["ui:feedback"] = vote
    if service.telemetry is not None:
        service.telemetry.emit(
            "ui.feedback", run_id=st.session_state.get("ui:run_id", ""), vote=vote
        )


@st.fragment(run_every=1)
def _progress(service: Service, run_id: str, session_id: str) -> None:
    manager = service.manager
    assert manager is not None
    manager.heartbeat(run_id, session_id)
    view = manager.status(run_id, session_id)
    if view.state != "running":
        st.rerun()
        return
    elapsed = time.monotonic() - st.session_state.get("ui:started_at", time.monotonic())
    limit = scaled_config(mode_config(_mode()), service.settings.run_time_factor).wall_clock_s
    components.progress_stages(view.stage, elapsed, limit)


def _form(service: Service, running: bool) -> None:
    st.text_area(copy.text("label.topic"), key="topic:input", height=90, disabled=running)
    chips = st.columns(len(copy.EXAMPLES))
    for column, example in zip(chips, copy.EXAMPLES, strict=True):
        column.button(
            example,
            key=f"example:{example}",
            on_click=_set_example,
            args=(example,),
            disabled=running,
        )
    st.radio(
        copy.text("label.depth"),
        ["Quick", "Deep"],
        key="depth:select",
        horizontal=True,
        disabled=running,
    )
    mode = _mode()
    st.caption(state.depth_caption(mode, service.settings.run_time_factor))
    unavailable = not service.mode_servable.get(mode, False)
    if unavailable:
        theme.render_notice("warn", copy.text("state.mode_unavailable"))
    paused = (
        service.manager is not None
        and not service.manager.get_service_state().accepting
        and not running
    )
    left, right = st.columns(2)
    left.button(
        copy.text("label.research"),
        type="primary",
        key="action:research",
        on_click=_start,
        args=(service,),
        disabled=running or unavailable,
        use_container_width=True,
    )
    right.button(
        copy.text("label.clear"),
        key="action:clear",
        on_click=_clear,
        disabled=running,
        use_container_width=True,
    )
    if running:
        st.caption(copy.text("label.research_disabled") + " " + copy.text("label.clear_disabled"))
    elif paused:
        st.caption(copy.text("state.paused"))


def _result(service: Service, result_view: RunView) -> None:
    result = result_view.result
    assert result is not None
    if result_view.state == "abandoned":
        theme.render_notice("info", copy.text("state.abandoned"))
    components.status_banner(result)
    if result.status is RunStatus.FAILED:
        if service.demo and result.error_code == ErrorCode.NO_EVIDENCE.value:
            theme.render_notice("info", copy.text("state.demo_offtopic"))
        detail = result.error_code or ""
        if result.detail:
            detail += f" ({result.detail})"
        if detail:
            st.caption(f"Detail: {detail}")
        st.button(copy.text("label.try_again"), key="action:retry", on_click=_try_again)
        st.caption(copy.text("next.failed"))
        return
    components.scorecard(result)
    if result.report_markdown:
        st.download_button(
            copy.text("label.download"),
            data=result.report_markdown.encode("utf-8"),
            file_name=state.export_filename(result.status, datetime.now(UTC)),
            mime="text/markdown",
            key="action:download",
        )
    components.report_view(result, lambda claim_id: _evidence_opened(service, claim_id))
    components.unused_sources(result)
    components.feedback_bar(
        "feedback", lambda vote: _vote(service, vote), recorded="ui:feedback" in st.session_state
    )


def _research_tab(service: Service) -> None:
    store = st.session_state
    if not service.ready or service.manager is None:
        theme.render_notice("err", copy.text("state.config_invalid"))
        if service.problems:  # setting names only, never values
            st.caption("Setting problems: " + ", ".join(service.problems))
        return
    run_id = store.get("ui:run_id")
    view = service.manager.status(run_id, store["ui:session_id"]) if run_id else None
    if view is not None and view.state in {"expired", "not_found"}:
        if view.state == "expired":
            store["ui:notice"] = ("info", copy.text("state.expired"))
        store.pop("ui:run_id", None)
        view = None
    running = view is not None and view.state == "running"

    notice = store.get("ui:notice")
    if notice:
        theme.render_notice(*notice)
    _form(service, running)
    if running:
        assert isinstance(run_id, str)
        _progress(service, run_id, store["ui:session_id"])
    elif view is not None:
        _result(service, view)
    else:
        st.caption(copy.text("state.idle") + " " + copy.text("next.idle"))
    st.caption(copy.text("label.standing"))
    if service.cost_note:
        st.caption(service.cost_note)
    st.caption(copy.text("state.reload_notice"))


def main() -> None:
    theme.inject_css()
    service = get_service()
    state.ensure_session(st.session_state)
    st.title(copy.text("app.title"))
    st.write(copy.text("app.tagline"))
    if service.demo:
        theme.render_notice("info", copy.text("state.demo"))
    research, about, faq = st.tabs(
        [copy.text("label.tab_research"), copy.text("label.tab_about"), copy.text("label.tab_faq")]
    )
    contact = service.settings.contact_url
    with research:
        _research_tab(service)
    with about:
        components.privacy_tab(contact, service.provider_labels, service.cost_note)
    with faq:
        components.faq_tab(contact)


main()
