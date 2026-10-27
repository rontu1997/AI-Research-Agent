import pytest
from pydantic import ValidationError

from core.models import (
    DraftClaim,
    EvidenceMode,
    EvidenceRef,
    FacetCategory,
    LedgerDraft,
    Mode,
    Plan,
    RunStatus,
    VerifierOutput,
)


def test_enum_values_match_the_prd() -> None:
    assert [m.value for m in EvidenceMode] == ["snippet", "extracted", "metadata-only"]
    assert [s.value for s in RunStatus] == ["completed", "partial", "failed"]
    assert [m.value for m in Mode] == ["quick", "deep"]


def test_facet_categories_match_the_fixed_enum() -> None:
    assert {c.value for c in FacetCategory} == {
        "background",
        "drivers_mechanisms",
        "evidence_trends",
        "impacts_risks",
        "perspectives_disputes",
        "current_state",
        "context_regional",
        "other",
    }


def test_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(
            {"citation_id": 1, "passage_id": "1:p1", "quote": "x" * 30, "url": "https://x.org"}
        )


def test_ledger_draft_parses_a_well_formed_payload() -> None:
    draft = LedgerDraft.model_validate(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Claim text.",
                    "facet_id": "f1",
                    "section": "findings",
                    "evidence": [{"citation_id": 1, "passage_id": "1:p1", "quote": "q" * 30}],
                }
            ],
            "sections": [
                {"section": "findings", "sentences": [{"type": "claim", "claim_id": "c1"}]}
            ],
        }
    )
    assert isinstance(draft.claims[0], DraftClaim)
    assert draft.sections[0].sentences[0].claim_id == "c1"


def test_draft_claim_rejects_an_invalid_section() -> None:
    with pytest.raises(ValidationError):
        DraftClaim.model_validate(
            {
                "claim_id": "c1",
                "text": "t",
                "facet_id": "f1",
                "section": "appendix",
                "evidence": [],
            }
        )


def test_plan_requires_valid_facet_categories() -> None:
    with pytest.raises(ValidationError):
        Plan.model_validate(
            {
                "queries": ["a", "b"],
                "facets": [{"facet_id": "f1", "question": "q", "category": "nonsense"}],
            }
        )


def test_verifier_output_only_allows_the_three_verdicts() -> None:
    ok = VerifierOutput.model_validate(
        {"results": [{"claim_id": "c1", "verdict": "supported", "reason": "r"}]}
    )
    assert ok.results[0].verdict.value == "supported"
    with pytest.raises(ValidationError):
        VerifierOutput.model_validate(
            {"results": [{"claim_id": "c1", "verdict": "maybe", "reason": "r"}]}
        )
