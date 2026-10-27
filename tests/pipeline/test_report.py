from __future__ import annotations

import re

from core.models import (
    ClaimRecord,
    DraftSentence,
    EvidenceMode,
    EvidenceRef,
    FacetCategory,
    FacetCoverage,
    Passage,
    RunStatus,
    SectionName,
    SourceRecord,
    Verdict,
)
from pipeline.report import assemble_sections, escape_md, render_markdown

PASSAGE = (
    "The pilot launched in March 2024 with 120 bikes at 15 docking stations in the harbor district."
)


def _source(cid: int, title: str = "City overview") -> SourceRecord:
    return SourceRecord(
        citation_id=cid,
        title=title,
        url=f"https://s{cid}.example.org/a(b)",
        canonical_url=f"https://s{cid}.example.org/a(b)",
        registrable_domain=f"s{cid}.example.org",
        retrieved_at="2025-01-01T00:00:00Z",
        evidence_mode=EvidenceMode.EXTRACTED,
        passages=[Passage(passage_id=f"{cid}:p1", text=PASSAGE)],
        evidence_group_id=f"g{cid}",
    )


def _claim(
    cid: str, text: str = PASSAGE, cites: tuple[int, ...] = (1,), section: SectionName = "findings"
) -> ClaimRecord:
    return ClaimRecord(
        claim_id=cid,
        text=text,
        facet_id="f1",
        section=section,
        evidence=[
            EvidenceRef(citation_id=n, passage_id=f"{n}:p1", quote=PASSAGE[:80]) for n in cites
        ],
        quote_match_ok=True,
        numeric_guard_ok=True,
        support_verdict=Verdict.SUPPORTED,
    )


def _claim_sentence(cid: str) -> DraftSentence:
    return DraftSentence(type="claim", claim_id=cid)


# --- escaping ----------------------------------------------------------------------------------


def test_escape_neutralizes_html_links_and_markup() -> None:
    out = escape_md("<script>alert(1)</script> [x](javascript:evil) *bold* `code` a|b\n# head")
    assert "<script>" not in out
    assert "](javascript" not in out
    for ch in "*`|":
        assert f"\\{ch}" in out
    assert "\n" not in out


def test_escape_strips_control_characters() -> None:
    assert "\x00" not in escape_md("a\x00b\x1fc")


# --- assembly ----------------------------------------------------------------------------------


def test_only_supported_claims_are_kept_and_numbered_in_order() -> None:
    claims = {"c1": _claim("c1"), "c2": _claim("c2", cites=(1, 2))}
    sections: dict[SectionName, list[DraftSentence]] = {
        "summary": [_claim_sentence("c1")],
        "findings": [_claim_sentence("ghost"), _claim_sentence("c2")],
    }
    rendered = assemble_sections(sections, claims, topic="bike share", flagged=set())
    items = [i for s in rendered for i in s.items]
    assert [(i.claim_id, i.claim_number) for i in items] == [("c1", 1), ("c2", 2)]
    assert items[1].citation_ids == [1, 2]


def test_interpretation_and_transition_rules_and_scan_flags_are_applied() -> None:
    claims = {"c1": _claim("c1")}
    sections: dict[SectionName, list[DraftSentence]] = {
        "findings": [
            _claim_sentence("c1"),
            DraftSentence(type="transition", text="Next, more detail."),
            DraftSentence(type="transition", text="In 2031 things changed."),
            DraftSentence(
                type="interpretation", text="Interpretation: that is the pilot.", refs=["c1"]
            ),
            DraftSentence(
                type="interpretation", text="Interpretation: that is the pilot.", refs=["gone"]
            ),
            DraftSentence(type="transition", text="Then a calm remark."),
        ]
    }
    rendered = assemble_sections(sections, claims, topic="bike share pilot", flagged={"findings:5"})
    texts = [i.text for s in rendered for i in s.items if i.kind != "claim"]
    assert texts == ["Next, more detail.", "Interpretation: that is the pilot."]


def test_empty_sections_are_omitted() -> None:
    assert assemble_sections({"summary": []}, {}, topic="t", flagged=set()) == []


# --- markdown ----------------------------------------------------------------------------------


def _render(**overrides):  # noqa: ANN003, ANN202
    claims = {
        "c1": _claim("c1"),
        "c2": _claim("c2", text="Second supported claim text here.", cites=(2,)),
    }
    sections = assemble_sections(
        {"summary": [_claim_sentence("c1")], "findings": [_claim_sentence("c2")]},
        claims,
        topic="Topic",
        flagged=set(),
    )
    args = dict(
        topic="Topic",
        mode_label="Quick",
        status=RunStatus.COMPLETED,
        reasons=[],
        researched_on="2025-02-02",
        sections=sections,
        claims=claims,
        sources={1: _source(1), 2: _source(2, "Second <b>source</b>")},
        not_inspected=[],
        coverage=[
            FacetCoverage(
                facet_id="f1",
                question="What is it?",
                category=FacetCategory.BACKGROUND,
                supported_claims=2,
            )
        ],
        warnings=[],
        demo=False,
    )
    args.update(overrides)
    return render_markdown(**args)


def test_markdown_has_ordered_headings_citations_and_appendix() -> None:
    md = _render()
    assert md.index("## Summary") < md.index("## Key findings") < md.index("## Competing views")
    assert "[1]" in md and "[2]" in md
    assert "## Evidence appendix" in md and "## Sources" in md
    assert "No material disagreement identified in selected evidence." in md
    assert "supported by the supplied passage" in md
    assert "1:p1" in md


def test_markdown_never_contains_raw_html_from_source_titles_or_topic() -> None:
    md = _render(topic="<img src=x onerror=1> Topic")
    unescaped_angle = re.compile(r"(?<!\\)<(?!https?://)")
    assert not unescaped_angle.search(md)
    assert "\\<b\\>" in md


def test_source_links_are_http_only_and_parentheses_are_encoded() -> None:
    md = _render()
    assert "https://s1.example.org/a%28b%29" in md
    bad = _source(3)
    bad = bad.model_copy(
        update={"url": "javascript:alert(1)", "canonical_url": "javascript:alert(1)"}
    )
    md = _render(sources={1: _source(1), 2: bad})
    assert "javascript:" not in md


def test_demo_banner_and_partial_reasons_are_shown() -> None:
    md = _render(demo=True, status=RunStatus.PARTIAL, reasons=["LOW_DOMAINS"])
    assert "Demo mode" in md
    assert "LOW_DOMAINS" in md
