"""Reusable UI components (design.md §7). Plain data in, widgets out; no provider calls here.

Third-party text (claims, quotes, titles) is always passed through `escape_md` and rendered as
plain text (DR-9). App-owned HTML lives only in `ui/theme.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import streamlit as st

from core.models import (
    SECTION_TITLES,
    ClaimRecord,
    EvidenceMode,
    FacetCoverage,
    ResearchResult,
    RunStatus,
    SourceRecord,
)
from core.text_safety import escape_md, safe_url
from ui import copy, state, theme

# --- progress ----------------------------------------------------------------------------------


def progress_stages(stage: str, elapsed_s: float, max_s: int) -> None:
    current = state.stage_index(stage)
    parts = []
    for index, name in enumerate(state.UI_STAGES):
        glyph = "✓" if index < current else ("●" if index == current else "○")
        parts.append(f"{glyph} {name}")
    minutes, seconds = divmod(int(elapsed_s), 60)
    max_m, max_sec = divmod(max_s, 60)
    st.markdown(f"**Researching…** Elapsed {minutes}:{seconds:02d} (maximum {max_m}:{max_sec:02d})")
    st.markdown("  \n".join(parts))
    st.markdown(f"Current step: {state.UI_STAGES[current]}…")
    st.caption(copy.text("state.running"))


# --- status ------------------------------------------------------------------------------------


def status_banner(result: ResearchResult) -> None:
    m = result.metrics
    if result.status is RunStatus.COMPLETED:
        headline = (
            f"Completed: {m.usable_sources} usable sources, {m.unique_domains} domains, "
            f"{m.supported_claims} supported claims. {copy.text('state.completed')}"
        )
        theme.render_banner(result.status, headline)
    elif result.status is RunStatus.PARTIAL:
        reasons = [copy.reason(code) for code in result.reason_codes]
        headline = f"{m.supported_claims} supported claims. {copy.text('state.partial')}"
        theme.render_banner(result.status, headline, reasons)
    else:
        theme.render_banner(
            result.status,
            copy.failure_message(result.error_code or _first(result.reason_codes), result.detail),
        )


def _first(codes: Sequence[str]) -> str | None:
    return codes[0] if codes else None


def scorecard(result: ResearchResult) -> None:
    m = result.metrics
    mode = "Quick" if result.mode.value == "quick" else "Deep"
    st.caption(
        f"{mode} · researched {result.researched_on} · usable sources: {m.usable_sources} · "
        f"domains: {m.unique_domains} · supported claims: {m.supported_claims} · "
        f"search snippets: {round(m.snippet_only_claim_share * 100)}% of claims · "
        f"questions covered: {m.supported_facets} of {m.planned_facets}"
    )
    for warning in result.warnings:
        theme.render_notice("warn", warning)


# --- report ------------------------------------------------------------------------------------


def _source_link(source: SourceRecord) -> str:
    url = safe_url(source.url)
    title = escape_md(source.title)
    if url is None:
        return f"{title} — {escape_md(source.registrable_domain)} (link withheld)"
    domain = escape_md(source.registrable_domain)
    return f"[{title}]({url}) — {domain} {copy.text('label.link_new_tab')}"


def evidence_panel(claim: ClaimRecord, number: int, sources: dict[int, SourceRecord]) -> None:
    with st.container(border=True):
        for ref in claim.evidence:
            source = sources.get(ref.citation_id)
            if source is None:
                continue
            theme.render_badge(source.evidence_mode)
            st.markdown(f"Source [{ref.citation_id}]")
            st.markdown("> " + escape_md(ref.quote))
            st.markdown(_source_link(source))
            st.caption(f"Passage {ref.passage_id} · Claim C{number}")


def claim_item(
    claim: ClaimRecord,
    number: int,
    citations: Sequence[int],
    sources: dict[int, SourceRecord],
    on_open: Callable[[str], None],
) -> None:
    cites = "".join(f"[{c}]" for c in citations)
    left, right = st.columns([5, 2])
    left.markdown(f"**C{number}** {escape_md(claim.text)} {cites}")
    key = f"evidence:{claim.claim_id}"
    shown = right.toggle(
        f"Show evidence (C{number})", key=key, on_change=on_open, args=(claim.claim_id,)
    )
    if shown:
        evidence_panel(claim, number, sources)


def facet_list(coverage: Sequence[FacetCoverage]) -> None:
    st.markdown("## Scope and questions researched")
    for facet in coverage:
        count = (
            f"{facet.supported_claims} supported claims"
            if facet.supported_claims
            else copy.text("label.not_covered")
        )
        st.markdown(f"- {escape_md(facet.question)} — {count}")


def references(result: ResearchResult) -> None:
    by_id = {s.citation_id: s for s in result.sources}
    st.markdown("## References")
    for cid in result.source_ids:
        source = by_id[cid]
        date = source.published_at or copy.text("label.date_unknown")
        st.markdown(
            f"[{cid}] {_source_link(source)} — {date} — retrieved {source.retrieved_at[:10]}"
        )
        theme.render_badge(source.evidence_mode)


def report_view(result: ResearchResult, on_open: Callable[[str], None]) -> None:
    sources = {s.citation_id: s for s in result.sources}
    claims = {c.claim_id: c for c in result.claims}
    has_competing = False
    for section in result.sections:
        st.markdown(f"## {SECTION_TITLES[section.section]}")
        has_competing = has_competing or section.section == "competing"
        for item in section.items:
            if item.kind == "claim" and item.claim_id in claims:
                claim_item(
                    claims[item.claim_id],
                    item.claim_number or 0,
                    item.citation_ids,
                    sources,
                    on_open,
                )
            elif item.kind == "interpretation":
                st.markdown(f"*{escape_md(item.text)}*")
            else:
                st.markdown(escape_md(item.text))
    if not has_competing:
        st.markdown(f"## {SECTION_TITLES['competing']}")
        st.markdown(copy.text("label.no_disagreement"))
    facet_list(result.facet_coverage)
    references(result)


def feedback_bar(vote_key: str, on_vote: Callable[[str], None], recorded: bool) -> None:
    if recorded:
        st.markdown(copy.text("state.feedback"))
        return
    st.markdown(copy.text("label.feedback_prompt"))
    left, right, _ = st.columns([1, 1, 3])
    left.button(
        copy.text("label.useful"), key=f"{vote_key}:useful", on_click=on_vote, args=("useful",)
    )
    right.button(
        copy.text("label.not_useful"),
        key=f"{vote_key}:not_useful",
        on_click=on_vote,
        args=("not_useful",),
    )


def unused_sources(result: ResearchResult) -> None:
    """Failed runs list nothing; completed runs list sources found but not used."""
    leftover = [s for s in result.sources if s.citation_id in result.unused_source_ids]
    if not leftover or result.status is RunStatus.FAILED:
        return
    st.markdown("## Sources found but not used")
    for source in leftover:
        mode = copy.evidence_label(source.evidence_mode.value)
        if source.evidence_mode is EvidenceMode.METADATA_ONLY:
            mode = copy.evidence_label("metadata-only")
        st.markdown(f"- {_source_link(source)} — {mode}")


# --- trust documents ---------------------------------------------------------------------------


def _document(sections: tuple[tuple[str, tuple[str, ...]], ...], contact_url: str) -> None:
    for heading, paragraphs in sections:
        st.markdown(f"## {heading}")
        for paragraph in paragraphs:
            st.markdown(paragraph)
    link = safe_url(contact_url) if contact_url else None
    st.markdown("## Reporting a problem")
    st.markdown(
        f"[Contact the maintainers]({link})" if link else "No contact address is configured."
    )


def privacy_tab(
    contact_url: str, providers: Sequence[str] = (), cost_note: str | None = None
) -> None:
    """The trust document, with the configured providers named (PRD §7.5)."""
    sections = list(copy.PRIVACY_SECTIONS)
    if providers:
        paragraphs = tuple(providers) + ((cost_note,) if cost_note else ())
        sections.insert(2, ("Configured providers", paragraphs))
    _document(tuple(sections), contact_url)


def faq_tab(contact_url: str) -> None:
    _document(copy.FAQ_SECTIONS, contact_url)
