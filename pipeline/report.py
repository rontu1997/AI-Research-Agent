"""Report assembly and Markdown rendering (PRD FR-10..FR-13, FR-20; ARCH §5.10).

Only text that survived every check reaches a section. All model and source text is escaped as
plain text before it enters Markdown; links are limited to http(s) and percent-encoded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.demo import DEMO_NOTICE
from core.models import (
    SECTION_ORDER,
    SECTION_TITLES,
    ClaimRecord,
    DraftSentence,
    EvidenceMode,
    FacetCoverage,
    RenderedItem,
    RenderedSection,
    RunStatus,
    SectionName,
    SourceRecord,
)
from core.text_safety import escape_md, safe_url
from pipeline.claim_checks import check_interpretation, check_transition
from pipeline.source_processing import NotInspected

NO_DISAGREEMENT = "No material disagreement identified in selected evidence."
VERIFIED_NOTE = (
    "Verified means supported by the supplied passage. It does not mean independently proven true."
)


def sentence_ref(section: SectionName, index: int) -> str:
    return f"{section}:{index}"


# --- assembly ----------------------------------------------------------------------------------


def assemble_sections(
    sections: Mapping[SectionName, Sequence[DraftSentence]],
    supported: Mapping[str, ClaimRecord],
    *,
    topic: str,
    flagged: set[str],
) -> list[RenderedSection]:
    headings = list(SECTION_TITLES.values())
    claim_texts = {cid: c.text for cid, c in supported.items()}
    rendered: list[RenderedSection] = []
    number = 0
    for name in SECTION_ORDER:
        items: list[RenderedItem] = []
        for index, sentence in enumerate(sections.get(name, [])):
            if sentence.type == "claim":
                claim = supported.get(sentence.claim_id or "")
                if claim is None:
                    continue
                number += 1
                cites = sorted({e.citation_id for e in claim.evidence})
                items.append(
                    RenderedItem(
                        kind="claim",
                        claim_id=claim.claim_id,
                        claim_number=number,
                        text=claim.text,
                        citation_ids=cites,
                    )
                )
                continue
            if sentence_ref(name, index) in flagged:
                continue
            text = (sentence.text or "").strip()
            if sentence.type == "interpretation":
                ok = check_interpretation(
                    text, sentence.refs, claim_texts, topic=topic, headings=headings
                ).ok
            else:
                ok = check_transition(text, topic=topic, headings=headings).ok
            if ok:
                items.append(RenderedItem(kind=sentence.type, text=text))
        if items:
            rendered.append(RenderedSection(section=name, items=items))
    return rendered


# --- markdown ----------------------------------------------------------------------------------


def _citations(ids: Sequence[int]) -> str:
    return "".join(f"[{i}]" for i in ids)


def render_markdown(
    *,
    topic: str,
    mode_label: str,
    status: RunStatus,
    reasons: Sequence[str],
    researched_on: str,
    sections: Sequence[RenderedSection],
    claims: Mapping[str, ClaimRecord],
    sources: Mapping[int, SourceRecord],
    not_inspected: Sequence[NotInspected],
    coverage: Sequence[FacetCoverage],
    warnings: Sequence[str],
    demo: bool,
) -> str:
    prefix = "PARTIAL \u2014 " if status is RunStatus.PARTIAL else ""
    lines: list[str] = [f"# {prefix}Research report: {escape_md(topic)}", ""]
    if demo:
        lines += [f"> **{escape_md(DEMO_NOTICE)}**", ""]
    meta = (
        f"Researched on {researched_on} · {mode_label} mode · Status: {status.value.capitalize()}"
    )
    lines += [meta, ""]
    if reasons:
        lines += ["Unmet thresholds: " + ", ".join(f"`{r}`" for r in reasons), ""]
    for warning in warnings:
        lines += [f"> {escape_md(warning)}", ""]
    lines += [f"_{VERIFIED_NOTE}_", ""]

    present = {s.section for s in sections}
    for section in sections:
        lines += [f"## {SECTION_TITLES[section.section]}", ""]
        for item in section.items:
            if item.kind == "claim":
                lines += [f"{escape_md(item.text)} {_citations(item.citation_ids)}", ""]
            elif item.kind == "interpretation":
                lines += [f"_{escape_md(item.text)}_", ""]
            else:
                lines += [escape_md(item.text), ""]
    if "competing" not in present:
        lines += [f"## {SECTION_TITLES['competing']}", "", NO_DISAGREEMENT, ""]

    lines += ["## Evidence appendix", ""]
    for section in sections:
        for item in section.items:
            if item.kind != "claim" or item.claim_id is None:
                continue
            claim = claims[item.claim_id]
            lines += [f"**Claim {item.claim_number}.** {escape_md(claim.text)}", ""]
            for ref in claim.evidence:
                source = sources.get(ref.citation_id)
                title = escape_md(source.title) if source else "unknown source"
                mode = source.evidence_mode.value if source else "unknown"
                lines.append(
                    f"- [{ref.citation_id}] {title} · passage `{ref.passage_id}` · {mode}: "
                    f"“{escape_md(ref.quote)}”"
                )
            lines.append("")

    if coverage:
        lines += ["## Facet coverage", ""]
        for facet in coverage:
            lines.append(
                f"- {escape_md(facet.question)} ({facet.category.value}): "
                f"{facet.supported_claims} supported"
            )
        lines.append("")

    cited = sorted({cid for s in sections for i in s.items for cid in i.citation_ids})
    lines += ["## Sources", ""]
    for cid in cited:
        source = sources.get(cid)
        if source is None:
            continue
        link = safe_url(source.url)
        shown = f"<{link}>" if link else "(link withheld: not an http or https address)"
        snippet_note = " · snippet only" if source.evidence_mode is EvidenceMode.SNIPPET else ""
        lines.append(
            f"{cid}. {escape_md(source.title)} · {escape_md(source.registrable_domain)} · "
            f"retrieved {source.retrieved_at[:10]}{snippet_note} · {shown}"
        )
    lines.append("")
    if not_inspected:
        lines += ["## Found but not inspected", ""]
        for entry in not_inspected:
            link = safe_url(entry.url)
            lines.append(
                f"- {escape_md(entry.title)} · {f'<{link}>' if link else '(link withheld)'}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
