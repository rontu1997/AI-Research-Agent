import dataclasses

from core.models import (
    DraftClaim,
    DraftSection,
    DraftSentence,
    EvidenceRef,
    Facet,
    FacetCategory,
    LedgerDraft,
    Mode,
    Plan,
)
from core.settings import mode_config
from pipeline.claim_ledger import normalize_draft

PLAN = Plan(
    queries=["a", "b"],
    facets=[
        Facet(facet_id="f1", question="q1", category=FacetCategory.BACKGROUND),
        Facet(facet_id="f2", question="q2", category=FacetCategory.IMPACTS_RISKS),
        Facet(facet_id="f3", question="q3", category=FacetCategory.CURRENT_STATE),
    ],
)
CFG = mode_config(Mode.QUICK)


def _claim(cid: str, section: str = "findings", facet: str = "f1") -> DraftClaim:
    return DraftClaim(
        claim_id=cid,
        text=f"Claim {cid}.",
        facet_id=facet,
        section=section,  # type: ignore[arg-type]
        evidence=[EvidenceRef(citation_id=1, passage_id="1:p1", quote="q" * 30)],
    )


def _sec(section: str, *sentences: DraftSentence) -> DraftSection:
    return DraftSection(section=section, sentences=list(sentences))  # type: ignore[arg-type]


def _cs(cid: str) -> DraftSentence:
    return DraftSentence(type="claim", claim_id=cid)


def _ids(result, section: str) -> list[str]:
    return [s.claim_id for s in result.sections[section] if s.type == "claim"]  # type: ignore[misc]


def test_a_well_formed_draft_passes_through_unchanged() -> None:
    draft = LedgerDraft(
        claims=[_claim("c1", "summary"), _claim("c2"), _claim("c3")],
        sections=[_sec("summary", _cs("c1")), _sec("findings", _cs("c2"), _cs("c3"))],
    )
    result = normalize_draft(draft, PLAN, CFG)
    assert [c.claim_id for c in result.claims] == ["c1", "c2", "c3"]
    assert result.rejected == {}
    assert _ids(result, "summary") == ["c1"]
    assert _ids(result, "findings") == ["c2", "c3"]


def test_duplicate_claim_ids_reject_the_later_one() -> None:
    draft = LedgerDraft(claims=[_claim("c1"), _claim("c1")], sections=[_sec("findings", _cs("c1"))])
    result = normalize_draft(draft, PLAN, CFG)
    assert [c.claim_id for c in result.claims] == ["c1"]
    assert result.rejected == {"c1": "DUPLICATE_ID"}


def test_claims_with_an_unknown_facet_are_rejected() -> None:
    draft = LedgerDraft(claims=[_claim("c1", facet="zzz"), _claim("c2")], sections=[])
    result = normalize_draft(draft, PLAN, CFG)
    assert [c.claim_id for c in result.claims] == ["c2"]
    assert result.rejected == {"c1": "UNKNOWN_FACET"}


def test_claims_beyond_the_mode_cap_are_rejected() -> None:
    claims = [_claim(f"c{i}") for i in range(CFG.max_claims + 2)]
    result = normalize_draft(LedgerDraft(claims=claims, sections=[]), PLAN, CFG)
    assert len(result.claims) == CFG.max_claims
    assert set(result.rejected.values()) == {"OVER_CAP"}
    assert len(result.rejected) == 2


def test_a_claim_printed_in_the_wrong_section_moves_to_its_own() -> None:
    draft = LedgerDraft(
        claims=[_claim("c1", "findings")],
        sections=[_sec("conclusion", _cs("c1"))],
    )
    result = normalize_draft(draft, PLAN, CFG)
    assert _ids(result, "findings") == ["c1"]
    assert _ids(result, "conclusion") == []


def test_a_claim_is_printed_once_even_if_the_writer_repeats_it() -> None:
    draft = LedgerDraft(
        claims=[_claim("c1")],
        sections=[_sec("findings", _cs("c1"), _cs("c1")), _sec("data", _cs("c1"))],
    )
    result = normalize_draft(draft, PLAN, CFG)
    assert sum(_ids(result, s).count("c1") for s in result.sections) == 1


def test_unplaced_claims_are_appended_to_their_section() -> None:
    draft = LedgerDraft(claims=[_claim("c1"), _claim("c2")], sections=[_sec("findings", _cs("c1"))])
    result = normalize_draft(draft, PLAN, CFG)
    assert _ids(result, "findings") == ["c1", "c2"]


def test_sentences_naming_unknown_claims_are_dropped() -> None:
    draft = LedgerDraft(claims=[_claim("c1")], sections=[_sec("findings", _cs("c9"), _cs("c1"))])
    assert _ids(normalize_draft(draft, PLAN, CFG), "findings") == ["c1"]


def test_claim_sentences_carry_no_text_of_their_own() -> None:
    draft = LedgerDraft(
        claims=[_claim("c1")],
        sections=[
            _sec("findings", DraftSentence(type="claim", claim_id="c1", text="Injected fact."))
        ],
    )
    result = normalize_draft(draft, PLAN, CFG)
    assert all(s.text is None for s in result.sections["findings"] if s.type == "claim")


def test_summary_and_conclusion_limits_move_overflow_to_findings() -> None:
    cfg = dataclasses.replace(CFG, summary_max_claims=2, conclusion_max_claims=1)
    claims = [_claim(f"s{i}", "summary") for i in range(4)] + [
        _claim(f"e{i}", "conclusion") for i in range(3)
    ]
    draft = LedgerDraft(
        claims=claims,
        sections=[
            _sec("summary", *[_cs(f"s{i}") for i in range(4)]),
            _sec("conclusion", *[_cs(f"e{i}") for i in range(3)]),
        ],
    )
    result = normalize_draft(draft, PLAN, cfg)
    assert _ids(result, "summary") == ["s0", "s1"]
    assert _ids(result, "conclusion") == ["e0"]
    assert _ids(result, "findings") == ["s2", "s3", "e1", "e2"]


def test_interpretation_and_transition_sentences_keep_their_position() -> None:
    draft = LedgerDraft(
        claims=[_claim("c1"), _claim("c2")],
        sections=[
            _sec(
                "findings",
                _cs("c1"),
                DraftSentence(type="transition", text="Next, costs."),
                _cs("c2"),
                DraftSentence(type="interpretation", text="Interpretation: growth.", refs=["c1"]),
            )
        ],
    )
    kinds = [(s.type, s.claim_id) for s in normalize_draft(draft, PLAN, CFG).sections["findings"]]
    assert kinds == [
        ("claim", "c1"),
        ("transition", None),
        ("claim", "c2"),
        ("interpretation", None),
    ]


def test_non_claim_sentences_without_text_are_dropped() -> None:
    draft = LedgerDraft(
        claims=[_claim("c1")],
        sections=[_sec("findings", DraftSentence(type="transition", text="  "), _cs("c1"))],
    )
    assert [s.type for s in normalize_draft(draft, PLAN, CFG).sections["findings"]] == ["claim"]
