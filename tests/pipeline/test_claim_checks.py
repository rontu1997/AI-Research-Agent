import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.models import ClaimRecord, EvidenceMode, EvidenceRef, Passage, SourceRecord
from pipeline.claim_checks import (
    check_claim,
    check_interpretation,
    check_transition,
    normalize_for_match,
    numeric_guard,
    quote_in_passage,
)

QUOTE = "The agency reported that 3.5 million vehicles were registered in 2023."


def _source(
    cid: int = 1, mode: EvidenceMode = EvidenceMode.EXTRACTED, text: str = ""
) -> SourceRecord:
    body = text or f"Intro sentence here. {QUOTE} Closing sentence follows."
    passages = (
        [] if mode is EvidenceMode.METADATA_ONLY else [Passage(passage_id=f"{cid}:p1", text=body)]
    )
    return SourceRecord(
        citation_id=cid,
        title="T",
        url="https://example.org/a",
        canonical_url="https://example.org/a",
        registrable_domain="example.org",
        retrieved_at="2026-10-21T00:00:00Z",
        evidence_mode=mode,
        passages=passages,
        evidence_group_id="g1",
    )


def _claim(text: str, quote: str = QUOTE, cid: int = 1, pid: str = "1:p1") -> ClaimRecord:
    return ClaimRecord(
        claim_id="c1",
        text=text,
        facet_id="f1",
        section="findings",
        evidence=[EvidenceRef(citation_id=cid, passage_id=pid, quote=quote)],
    )


# --- normalization and quote matching -------------------------------------------------------


def test_normalize_unifies_quotes_dashes_case_and_whitespace() -> None:
    assert normalize_for_match("“Hello”  —  World\n") == '"hello" - world'


@given(st.text())
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize_for_match(text)
    assert normalize_for_match(once) == once


def test_quote_must_appear_in_the_passage() -> None:
    assert quote_in_passage(QUOTE, f"x {QUOTE} y")
    assert not quote_in_passage(
        QUOTE, "A completely different passage about something else entirely."
    )


def test_quote_match_ignores_case_and_curly_quotes() -> None:
    passage = "She said “the policy was adopted in 2021 by the council” in the report."
    assert quote_in_passage("the policy was adopted in 2021 by the council", passage)
    assert quote_in_passage("THE POLICY WAS ADOPTED IN 2021 BY THE COUNCIL", passage)


@given(st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=30, max_size=120))
def test_any_substring_of_the_passage_matches_itself(quote: str) -> None:
    passage = f"prefix words {quote} suffix words"
    assert quote_in_passage(quote, passage)


# --- numeric guard -----------------------------------------------------------------------------


def test_numbers_present_in_the_quote_pass() -> None:
    assert numeric_guard("3.5 million vehicles were registered in 2023.", [QUOTE]).ok


def test_a_number_missing_from_the_quote_fails() -> None:
    result = numeric_guard("4 million vehicles were registered in 2023.", [QUOTE])
    assert not result.ok
    assert "4" in result.missing


def test_derived_figures_are_rejected() -> None:
    quote = "Sales were 10 units in 2022 and 15 units in 2023, according to the report."
    assert not numeric_guard("Sales grew by 5 units.", [quote]).ok
    assert not numeric_guard("Sales grew 50% in a year.", [quote]).ok


def test_thousands_separators_and_trailing_zeros_normalize() -> None:
    assert numeric_guard(
        "The budget was 1,000 dollars.", ["The budget was 1000 dollars in total."]
    ).ok
    assert numeric_guard("The rate was 1.50 percent.", ["The rate was 1.5 percent this year."]).ok


def test_percent_sign_and_word_are_interchangeable_but_required() -> None:
    assert numeric_guard("It rose 12%.", ["It rose by 12 percent last quarter."]).ok
    assert not numeric_guard("It rose 12%.", ["It rose by 12 last quarter."]).ok


def test_currency_symbols_must_match_the_quote() -> None:
    assert numeric_guard("It cost $5.", ["It cost $5 per unit in the report."]).ok
    assert not numeric_guard("It cost $5.", ["It cost 5 rupees per unit in the report."]).ok


def test_magnitude_words_must_match() -> None:
    assert not numeric_guard(
        "It reached 3 billion.", ["It reached 3 million people in the survey."]
    ).ok


def test_number_words_two_to_ten_are_checked() -> None:
    assert numeric_guard(
        "Five countries joined.", ["In total 5 countries joined the pact in 2020."]
    ).ok
    assert not numeric_guard(
        "Six countries joined.", ["In total 5 countries joined the pact in 2020."]
    ).ok


def test_month_names_must_match() -> None:
    assert numeric_guard(
        "It happened in March 2023.", ["It happened in March 2023 in the capital."]
    ).ok
    assert not numeric_guard(
        "It happened in May 2023.", ["It happened in March 2023 in the capital."]
    ).ok


def test_claim_without_numbers_always_passes() -> None:
    assert numeric_guard("The agency published a report.", ["Some unrelated quote text."]).ok


@given(st.integers(min_value=0, max_value=10**9))
def test_any_integer_in_the_quote_passes(n: int) -> None:
    assert numeric_guard(
        f"The count was {n}.", [f"Officials said the count was {n} at the time."]
    ).ok


# --- whole-claim checks ------------------------------------------------------------------------


def test_a_good_claim_passes_all_deterministic_checks() -> None:
    result = check_claim(
        _claim("3.5 million vehicles were registered in 2023."),
        {1: _source()},
        max_quotes=3,
    )
    assert result.ok
    assert result.quote_match_ok and result.numeric_guard_ok


def test_unknown_citation_is_rejected() -> None:
    result = check_claim(_claim("x", cid=99), {1: _source()}, max_quotes=3)
    assert not result.ok
    assert result.reason == "UNKNOWN_CITATION"


def test_passage_must_belong_to_the_cited_source() -> None:
    result = check_claim(_claim("x", pid="2:p1"), {1: _source()}, max_quotes=3)
    assert result.reason == "UNKNOWN_PASSAGE"


def test_metadata_only_sources_cannot_support_a_claim() -> None:
    result = check_claim(_claim("x"), {1: _source(mode=EvidenceMode.METADATA_ONLY)}, max_quotes=3)
    assert not result.ok
    assert result.reason in {"UNKNOWN_PASSAGE", "METADATA_ONLY"}


def test_quote_length_bounds_are_enforced() -> None:
    short = check_claim(_claim("x", quote="too short"), {1: _source()}, max_quotes=3)
    assert short.reason == "QUOTE_LENGTH"
    long_text = "word " * 100
    long = check_claim(
        _claim("x", quote=long_text.strip()),
        {1: _source(text=long_text)},
        max_quotes=3,
    )
    assert long.reason == "QUOTE_LENGTH"


def test_missing_quote_in_passage_is_rejected_before_any_model_call() -> None:
    claim = _claim("A claim.", quote="This sentence does not occur anywhere in the passage at all.")
    result = check_claim(claim, {1: _source()}, max_quotes=3)
    assert result.reason == "QUOTE_NOT_IN_PASSAGE"


def test_a_claim_needs_at_least_one_and_at_most_max_quotes() -> None:
    empty = ClaimRecord(claim_id="c", text="t", facet_id="f", section="findings", evidence=[])
    assert check_claim(empty, {1: _source()}, max_quotes=3).reason == "NO_EVIDENCE"
    many = ClaimRecord(
        claim_id="c",
        text="t",
        facet_id="f",
        section="findings",
        evidence=[EvidenceRef(citation_id=1, passage_id="1:p1", quote=QUOTE)] * 4,
    )
    assert check_claim(many, {1: _source()}, max_quotes=3).reason == "TOO_MANY_QUOTES"


def test_numeric_mismatch_is_reported_with_the_reason() -> None:
    result = check_claim(
        _claim("9 million vehicles were registered."), {1: _source()}, max_quotes=3
    )
    assert not result.ok
    assert result.reason == "NUMERIC_MISMATCH"
    assert result.quote_match_ok and not result.numeric_guard_ok


# --- sentence rules ----------------------------------------------------------------------------

HEADINGS = ["Executive summary", "Key findings", "Conclusion"]


def test_interpretation_must_start_with_the_label() -> None:
    ok = check_interpretation(
        "Interpretation: registrations are growing.",
        ["c1"],
        {"c1": "Registrations grew in 2023."},
        topic="EV adoption",
        headings=HEADINGS,
    )
    assert ok.ok
    bad = check_interpretation(
        "Registrations are growing.",
        ["c1"],
        {"c1": "Registrations grew in 2023."},
        topic="EV adoption",
        headings=HEADINGS,
    )
    assert not bad.ok


def test_interpretation_must_cite_a_supported_claim() -> None:
    result = check_interpretation(
        "Interpretation: growth continues.",
        ["c9"],
        {"c1": "Growth was recorded."},
        topic="EV adoption",
        headings=HEADINGS,
    )
    assert not result.ok
    assert result.reason == "NO_VALID_REF"


def test_interpretation_is_capped_at_forty_words() -> None:
    text = "Interpretation: " + " ".join(["word"] * 41)
    result = check_interpretation(text, ["c1"], {"c1": "word"}, topic="t", headings=HEADINGS)
    assert not result.ok
    assert result.reason == "TOO_LONG"


def test_interpretation_may_not_introduce_a_new_number() -> None:
    result = check_interpretation(
        "Interpretation: growth reached 40 percent.",
        ["c1"],
        {"c1": "Registrations grew in 2023."},
        topic="EV adoption",
        headings=HEADINGS,
    )
    assert not result.ok
    assert result.reason == "NEW_TOKEN"


def test_interpretation_may_not_introduce_a_new_named_entity() -> None:
    result = check_interpretation(
        "Interpretation: this resembles the Tesla pattern.",
        ["c1"],
        {"c1": "Registrations grew."},
        topic="EV adoption",
        headings=HEADINGS,
    )
    assert not result.ok
    assert result.reason == "NEW_TOKEN"


def test_interpretation_may_reuse_entities_from_cited_claims_and_topic() -> None:
    result = check_interpretation(
        "Interpretation: India shows the same pattern as the market for EV adoption.",
        ["c1"],
        {"c1": "In India, registrations grew in 2023."},
        topic="EV adoption",
        headings=HEADINGS,
    )
    assert result.ok


def test_transition_rules() -> None:
    assert check_transition(
        "Next, the evidence on costs.", topic="EV adoption", headings=HEADINGS
    ).ok
    assert not check_transition("Costs rose 5 percent.", topic="t", headings=HEADINGS).ok
    assert not check_transition(
        "See https://example.org for more.", topic="t", headings=HEADINGS
    ).ok
    assert not check_transition(" ".join(["word"] * 16), topic="t", headings=HEADINGS).ok
    assert not check_transition("Then Microsoft entered.", topic="t", headings=HEADINGS).ok


@pytest.mark.parametrize("text", ["Next, costs.", "Now to the data."])
def test_short_plain_transitions_pass(text: str) -> None:
    assert check_transition(text, topic="t", headings=HEADINGS).ok
