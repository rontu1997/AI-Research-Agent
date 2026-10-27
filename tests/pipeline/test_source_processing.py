import dataclasses
import random
from datetime import UTC, datetime

import pytest

from core.models import EvidenceMode, Mode, RawResult
from core.settings import ModeConfig, mode_config
from core.tokens import estimate_tokens
from pipeline.source_processing import (
    build_registry,
    canonicalize_url,
    chunk_extracted,
    registrable_domain,
    usable_text,
)

NOW = datetime(2026, 10, 21, tzinfo=UTC)
TEXT = "Electric vehicle registrations grew strongly during the year according to the agency data. "


def _raw(url: str, text: str | None = None, **kw: object) -> RawResult:
    # Distinct default text per URL, so results are not treated as syndicated copies.
    body = text if text is not None else f"{TEXT * 2}Marker for {url}."
    return RawResult(title=kw.pop("title", "T"), url=url, snippet=body, **kw)  # type: ignore[arg-type]


def _cfg(**over: object) -> ModeConfig:
    return dataclasses.replace(mode_config(Mode.QUICK), **over)  # type: ignore[arg-type]


# --- urls and domains ------------------------------------------------------------------------


def test_canonicalize_strips_tracking_fragment_www_port_and_sorts_params() -> None:
    url = "HTTPS://WWW.Example.org:443/a/b/?utm_source=x&b=2&a=1&fbclid=z#frag"
    assert canonicalize_url(url) == "https://example.org/a/b?a=1&b=2"


def test_canonicalize_treats_root_path_consistently() -> None:
    assert canonicalize_url("https://example.org") == canonicalize_url("https://example.org/")


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://example.org/x",
        "javascript:alert(1)",
        "https://",
        "not a url",
        "https://user:pw@example.org/",
    ],
)
def test_canonicalize_rejects_unsafe_or_invalid_urls(bad: str) -> None:
    assert canonicalize_url(bad) is None


def test_registrable_domain_uses_the_public_suffix_list_offline() -> None:
    assert registrable_domain("https://news.bbc.co.uk/story") == "bbc.co.uk"
    assert registrable_domain("https://a.b.example.com/x") == "example.com"


def test_usable_text_requires_thirty_non_whitespace_characters() -> None:
    assert usable_text("x" * 30)
    assert not usable_text("x" * 29)
    assert not usable_text("   " + "x" * 10 + "   \n")


# --- chunking ----------------------------------------------------------------------------------


def test_extracted_text_is_chunked_on_sentence_boundaries_within_800_chars() -> None:
    sentences = [
        f"Sentence number {i} says something useful about the topic today." for i in range(40)
    ]
    chunks = chunk_extracted(" ".join(sentences))
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    assert all(c.endswith(".") for c in chunks)


def test_a_single_overlong_sentence_is_hard_split() -> None:
    chunks = chunk_extracted("w" * 2000)
    assert all(len(c) <= 800 for c in chunks)
    assert "".join(chunks) == "w" * 2000


def test_snippet_becomes_one_passage_and_is_truncated_at_1500() -> None:
    reg = build_registry(
        [[_raw("https://a.example.org/1", "s" * 2000)]], ["q"], "topic", _cfg(), NOW
    )
    src = reg.sources[0]
    assert src.evidence_mode is EvidenceMode.SNIPPET
    assert len(src.passages) == 1
    assert len(src.passages[0].text) == 1500
    assert src.passages[0].truncated


def test_extracted_text_wins_and_keeps_the_best_passages_per_source() -> None:
    relevant = "Electric vehicle charging infrastructure expanded rapidly across many cities."
    filler = "Weather was pleasant and the local festival drew large and cheerful crowds."
    body = " ".join([filler] * 12 + [relevant] + [filler] * 12)
    raw = RawResult(
        title="T",
        url="https://a.example.org/x",
        snippet="short snippet text that is long enough here",
        extracted_text=body,
    )
    reg = build_registry(
        [[raw]], ["electric vehicle charging"], "EV charging", _cfg(max_passages_per_source=2), NOW
    )
    src = reg.sources[0]
    assert src.evidence_mode is EvidenceMode.EXTRACTED
    assert len(src.passages) == 2
    assert any("charging infrastructure" in p.text for p in src.passages)
    assert [p.passage_id for p in src.passages] == ["1:p1", "1:p2"]


# --- eligibility and dedupe --------------------------------------------------------------------


def test_results_without_usable_text_are_listed_as_not_inspected() -> None:
    reg = build_registry(
        [[_raw("https://a.example.org/ok"), _raw("https://b.example.org/empty", "tiny")]],
        ["q"],
        "t",
        _cfg(),
        NOW,
    )
    assert [s.canonical_url for s in reg.sources] == ["https://a.example.org/ok"]
    assert [u.canonical_url for u in reg.not_inspected] == ["https://b.example.org/empty"]


def test_same_canonical_url_is_merged_keeping_the_better_result() -> None:
    lo = _raw("https://a.example.org/x?utm_source=1", score=0.2)
    hi = _raw("https://a.example.org/x", score=0.9)
    reg = build_registry([[lo], [hi]], ["q"], "t", _cfg(), NOW)
    assert len(reg.sources) == 1
    assert reg.sources[0].score >= 4 * 0.9


def test_syndicated_copies_share_a_group_and_only_one_is_selected() -> None:
    a = _raw("https://a.example.org/x", TEXT * 2, score=0.9)  # identical text = syndicated copy
    b = _raw("https://b.example.net/copy", TEXT * 2, score=0.8)
    c = _raw(
        "https://c.example.com/other",
        "A different report about charging networks in rural areas of the country.",
        score=0.7,
    )
    reg = build_registry([[a, b, c]], ["q"], "t", _cfg(), NOW)
    assert len(reg.sources) == 2
    assert len({s.evidence_group_id for s in reg.sources}) == 2
    assert reg.stats.syndicated_dropped == 1


# --- scoring and ordering ----------------------------------------------------------------------


def test_score_formula_matches_the_prd() -> None:
    plain = _raw("https://a.example.org/1", score=0.5)
    extracted = RawResult(
        title="T", url="https://b.example.net/1", snippet="", extracted_text=TEXT * 2, score=0.5
    )
    reg = build_registry([[plain, extracted]], ["q"], "t", _cfg(), NOW)
    by_url = {s.canonical_url: s for s in reg.sources}
    assert by_url["https://a.example.org/1"].score == pytest.approx(4 * 0.5)
    assert by_url["https://b.example.net/1"].score == pytest.approx(4 * 0.5 + 2)


def test_primary_allowlist_adds_one_point() -> None:
    gov = _raw("https://stats.example.gov/r", score=0.5)
    reg = build_registry([[gov]], ["q"], "t", _cfg(), NOW, primary_suffixes={"example.gov"})
    assert reg.sources[0].primary_evidence_verified
    assert reg.sources[0].score == pytest.approx(4 * 0.5 + 1)


def test_recency_counts_only_for_time_sensitive_topics_with_a_known_recent_date() -> None:
    recent = _raw("https://a.example.org/1", score=0.5, published_at="2026-09-01")
    old = _raw("https://b.example.net/1", score=0.5, published_at="2020-01-01")
    undated = _raw("https://c.example.com/1", score=0.5)
    reg = build_registry([[recent, old, undated]], ["q"], "t", _cfg(), NOW, time_sensitive=True)
    scores = {s.canonical_url: s.score for s in reg.sources}
    assert scores["https://a.example.org/1"] == pytest.approx(4 * 0.5 + 1)
    assert scores["https://b.example.net/1"] == pytest.approx(4 * 0.5)
    assert scores["https://c.example.com/1"] == pytest.approx(4 * 0.5)
    not_sensitive = build_registry([[recent]], ["q"], "t", _cfg(), NOW, time_sensitive=False)
    assert not_sensitive.sources[0].score == pytest.approx(4 * 0.5)


def test_rank_is_converted_to_relevance_when_no_score_is_given() -> None:
    results = [_raw(f"https://s{i}.example.org/1") for i in range(3)]
    reg = build_registry([results], ["q"], "t", _cfg(), NOW)
    assert [s.canonical_url for s in reg.sources] == [
        f"https://s{i}.example.org/1" for i in range(3)
    ]
    assert reg.sources[0].score == pytest.approx(4 * 1.0)
    assert reg.sources[1].score == pytest.approx(4 * 0.5)


def test_citation_ids_are_contiguous_and_follow_rank_order() -> None:
    results = [_raw(f"https://s{i}.example.org/1", score=1 - i / 10) for i in range(4)]
    reg = build_registry([results], ["q"], "t", _cfg(), NOW)
    assert [s.citation_id for s in reg.sources] == [1, 2, 3, 4]
    assert [s.score for s in reg.sources] == sorted((s.score for s in reg.sources), reverse=True)


def test_the_registry_order_is_identical_for_any_input_order() -> None:
    results = [
        _raw(
            f"https://s{i}.example.org/{i}",
            f"Distinct body number {i} about the topic and its details here.",
            score=(i % 3) / 3,
        )
        for i in range(9)
    ]
    first = build_registry([results], ["q"], "t", _cfg(), NOW)
    expected = [(s.canonical_url, s.citation_id) for s in first.sources]
    for seed in range(5):
        shuffled = results[:]
        random.Random(seed).shuffle(shuffled)
        again = build_registry([shuffled], ["q"], "t", _cfg(), NOW)
        assert [(s.canonical_url, s.citation_id) for s in again.sources] == expected


# --- diversity and caps ----------------------------------------------------------------------


def test_selection_respects_the_source_cap() -> None:
    results = [
        _raw(
            f"https://s{i}.example.org/1",
            f"Unique text {i} about the subject at hand and more words.",
            score=0.5,
        )
        for i in range(12)
    ]
    assert len(build_registry([results], ["q"], "t", _cfg(max_sources=5), NOW).sources) == 5


def test_every_domain_is_used_before_any_domain_gets_a_second_source() -> None:
    results = [
        _raw(
            "https://a.example.org/1",
            "Alpha text one about the subject at hand with many words.",
            score=0.99,
        ),
        _raw(
            "https://a.example.org/2",
            "Alpha text two about the subject at hand with many words.",
            score=0.98,
        ),
        _raw(
            "https://a.example.org/3",
            "Alpha text three about the subject at hand with many words.",
            score=0.97,
        ),
        _raw(
            "https://b.example.net/1",
            "Beta text one about the subject at hand with many words.",
            score=0.30,
        ),
        _raw(
            "https://c.example.com/1",
            "Gamma text one about the subject at hand with many words.",
            score=0.20,
        ),
    ]
    reg = build_registry([results], ["q"], "t", _cfg(max_sources=3), NOW)
    assert sorted(s.registrable_domain for s in reg.sources) == [
        "example.com",
        "example.net",
        "example.org",
    ]


# --- token trim ------------------------------------------------------------------------------


def _total_tokens(reg_sources: list, allowance: int) -> int:
    return allowance + sum(estimate_tokens(p.text) for s in reg_sources for p in s.passages)


def test_trim_drops_extra_passages_from_the_lowest_scored_source_first() -> None:
    sentences = " ".join(
        f"Sentence {i} about electric vehicles and charging networks in cities." for i in range(60)
    )
    hi = RawResult(title="T", url="https://hi.example.org/1", extracted_text=sentences, score=0.9)
    lo = RawResult(
        title="T",
        url="https://lo.example.net/1",
        extracted_text="A distinct opening paragraph for this source. " + sentences,
        score=0.1,
    )
    cfg = _cfg(max_passages_per_source=4, writer_input_cap=2500, prompt_allowance=1500)
    reg = build_registry([[hi, lo]], ["electric vehicles"], "t", cfg, NOW)
    assert _total_tokens(reg.sources, cfg.prompt_allowance) <= cfg.writer_input_cap
    counts = {s.canonical_url: len(s.passages) for s in reg.sources}
    assert counts["https://hi.example.org/1"] >= counts["https://lo.example.net/1"]
    assert all(len(s.passages) >= 1 for s in reg.sources)
    assert reg.stats.dropped_passages > 0


def test_trim_drops_whole_sources_when_one_passage_each_still_does_not_fit() -> None:
    results = [
        _raw(f"https://s{i}.example.org/1", f"Body {i} " + "word " * 250, score=1 - i / 10)
        for i in range(6)
    ]
    cfg = _cfg(writer_input_cap=2400, prompt_allowance=1500)
    reg = build_registry([results], ["q"], "t", cfg, NOW)
    assert _total_tokens(reg.sources, cfg.prompt_allowance) <= cfg.writer_input_cap
    assert 1 <= len(reg.sources) < 6
    kept = {s.canonical_url for s in reg.sources}
    assert "https://s0.example.org/1" in kept  # the best source survives
    assert reg.stats.dropped_sources > 0
    assert [s.citation_id for s in reg.sources] == list(range(1, len(reg.sources) + 1))
