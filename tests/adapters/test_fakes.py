import json

import pytest

from adapters.base import Block, LLMResult
from adapters.fakes import DEMO_TOPIC, FakeLLM, FakeSearch
from core.errors import ProviderRateLimit, SchemaViolation
from core.models import LedgerDraft, Plan, ScanOutput, SearchResponse, Verdict, VerifierOutput
from pipeline.claim_checks import normalize_for_match


def test_fake_search_returns_synthetic_example_sources_only() -> None:
    resp = FakeSearch().search("bike-share pilot", max_results=6, want_extracted=True, timeout_s=5)
    assert isinstance(resp, SearchResponse)
    assert 1 <= len(resp.results) <= 6
    for r in resp.results:
        # Only reserved names (RFC 2606): example.* and the .example and .test TLDs.
        assert any(marker in r.url for marker in (".example", "example.", ".test"))


def test_fake_search_can_withhold_extracted_text() -> None:
    resp = FakeSearch().search("bike-share pilot", max_results=6, want_extracted=False, timeout_s=5)
    assert all(r.extracted_text is None for r in resp.results)
    assert any(r.snippet for r in resp.results)


def test_fake_search_failures_are_scriptable() -> None:
    fake = FakeSearch(fail_with=ProviderRateLimit(retry_after_s=1.0))
    with pytest.raises(ProviderRateLimit):
        fake.search("q", max_results=3, want_extracted=True, timeout_s=5)
    assert len(fake.calls) == 1


def _plan_blocks(topic: str) -> list[Block]:
    return [Block("topic", topic), Block("limits", json.dumps({"planned_queries": 3, "facets": 3}))]


def test_fake_planner_returns_a_valid_plan_with_distinct_categories() -> None:
    llm = FakeLLM()
    result = llm.generate(
        system="plan",
        blocks=_plan_blocks(DEMO_TOPIC),
        schema=Plan,
        max_output_tokens=800,
        temperature=0,
        timeout_s=5,
    )
    assert isinstance(result, LLMResult)
    plan = result.parsed
    assert len(plan.queries) >= 2
    assert len({f.category for f in plan.facets}) >= 3
    assert result.input_tokens and result.output_tokens


def test_unknown_schema_is_a_scripting_error() -> None:
    from pydantic import BaseModel

    class Other(BaseModel):
        x: int

    with pytest.raises(NotImplementedError):
        FakeLLM().generate(
            system="s", blocks=[], schema=Other, max_output_tokens=10, temperature=0, timeout_s=1
        )


def test_handlers_can_be_overridden_to_inject_failures() -> None:
    llm = FakeLLM()

    def boom(_ctx: object) -> VerifierOutput:
        raise SchemaViolation("bad json")

    llm.set_handler(VerifierOutput, boom)
    with pytest.raises(SchemaViolation):
        llm.generate(
            system="v",
            blocks=[],
            schema=VerifierOutput,
            max_output_tokens=10,
            temperature=0,
            timeout_s=1,
        )


def _writer_blocks(search: FakeSearch) -> tuple[list[Block], list[dict[str, str | int]]]:
    results = search.search(
        "bike-share pilot", max_results=4, want_extracted=True, timeout_s=5
    ).results
    passages = [
        {
            "citation_id": i,
            "passage_id": f"{i}:p1",
            "title": r.title,
            "text": r.extracted_text or r.snippet,
        }
        for i, r in enumerate(results, start=1)
    ]
    plan = {
        "facets": [
            {"facet_id": "f1", "question": "What is it?", "category": "background"},
            {"facet_id": "f2", "question": "What changed?", "category": "evidence_trends"},
            {"facet_id": "f3", "question": "Risks?", "category": "impacts_risks"},
        ]
    }
    blocks = [
        Block("plan", json.dumps(plan)),
        Block("passages", json.dumps(passages)),
        Block("limits", json.dumps({"max_claims": 8, "max_quotes": 3})),
    ]
    return blocks, passages  # type: ignore[return-value]


def test_fake_writer_quotes_appear_verbatim_in_the_passages_it_was_given() -> None:
    blocks, passages = _writer_blocks(FakeSearch())
    draft = (
        FakeLLM()
        .generate(
            system="w",
            blocks=blocks,
            schema=LedgerDraft,
            max_output_tokens=3000,
            temperature=0,
            timeout_s=5,
        )
        .parsed
    )
    by_pid = {str(p["passage_id"]): normalize_for_match(str(p["text"])) for p in passages}
    assert len(draft.claims) >= 4
    for claim in draft.claims:
        for ref in claim.evidence:
            assert normalize_for_match(ref.quote) in by_pid[ref.passage_id]


def test_fake_verifier_supports_matching_claims_and_rejects_altered_ones() -> None:
    payload = [
        {
            "claim_id": "c1",
            "claim": "The pilot launched in March 2024 with 120 bikes available.",
            "evidence": [
                {
                    "passage_text": "The pilot launched in March 2024 with 120 bikes available across the harbor.",
                    "quote": "The pilot launched in March 2024 with 120 bikes available",
                }
            ],
        },
        {
            "claim_id": "c2",
            "claim": "The pilot launched in March 2024 with 900 bikes available.",
            "evidence": [
                {
                    "passage_text": "The pilot launched in March 2024 with 120 bikes available across the harbor.",
                    "quote": "The pilot launched in March 2024 with 120 bikes available",
                }
            ],
        },
    ]
    out = (
        FakeLLM()
        .generate(
            system="v",
            blocks=[Block("claims", json.dumps(payload))],
            schema=VerifierOutput,
            max_output_tokens=800,
            temperature=0,
            timeout_s=5,
        )
        .parsed
    )
    verdicts = {r.claim_id: r.verdict for r in out.results}
    assert verdicts["c1"] is Verdict.SUPPORTED
    assert verdicts["c2"] is Verdict.UNSUPPORTED


def test_fake_scanner_flags_sentences_with_embedded_facts() -> None:
    payload = [
        {"ref": "s1", "text": "Costs rose 40 percent."},
        {"ref": "s2", "text": "Next, further evidence."},
    ]
    out = (
        FakeLLM()
        .generate(
            system="x",
            blocks=[Block("sentences", json.dumps(payload))],
            schema=ScanOutput,
            max_output_tokens=400,
            temperature=0,
            timeout_s=5,
        )
        .parsed
    )
    flags = {r.sentence_ref: r.contains_material_fact for r in out.results}
    assert flags == {"s1": True, "s2": False}


def test_calls_are_recorded_for_assertions() -> None:
    llm = FakeLLM()
    llm.generate(
        system="plan",
        blocks=_plan_blocks("t"),
        schema=Plan,
        max_output_tokens=10,
        temperature=0,
        timeout_s=1,
    )
    assert [c.schema_name for c in llm.calls] == ["Plan"]


def test_fake_search_returns_nothing_for_an_off_topic_query() -> None:
    from adapters.fakes import FakeSearch

    out = FakeSearch().search(
        "AI in surfactants discovery overview and history",
        max_results=10,
        want_extracted=True,
        timeout_s=5,
    )
    assert out.results == []


def test_fake_search_still_answers_the_demo_topic() -> None:
    from adapters.fakes import DEMO_TOPIC, FakeSearch

    out = FakeSearch().search(DEMO_TOPIC, max_results=10, want_extracted=True, timeout_s=5)
    assert len(out.results) >= 5
