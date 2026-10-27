from __future__ import annotations

import pytest

from adapters.fakes import FakeLLM, FakeSearch
from core.errors import ErrorCode, PipelineFailure
from core.models import Facet, FacetCategory, Mode, Plan
from pipeline.planner import PlanOutcome, make_plan, plan_is_viable


def _facets(*cats: FacetCategory) -> list[Facet]:
    return [
        Facet(facet_id=f"x{i}", question=f"Question {i}?", category=c)
        for i, c in enumerate(cats, 1)
    ]


GOOD = (
    FacetCategory.BACKGROUND,
    FacetCategory.EVIDENCE_TRENDS,
    FacetCategory.IMPACTS_RISKS,
    FacetCategory.CURRENT_STATE,
)


def test_viability_needs_distinct_categories_and_other_counts_once() -> None:
    quick, deep = Mode.QUICK, Mode.DEEP
    from core.settings import mode_config

    q, d = mode_config(quick), mode_config(deep)
    three = Plan(queries=["a b", "c d"], facets=_facets(*GOOD[:3]))
    assert plan_is_viable(three, q)
    assert not plan_is_viable(three, d)
    dup = Plan(queries=["a b", "c d"], facets=_facets(GOOD[0], GOOD[0], GOOD[1]))
    assert not plan_is_viable(dup, q)
    others = Plan(
        queries=["a b", "c d"], facets=_facets(GOOD[0], FacetCategory.OTHER, FacetCategory.OTHER)
    )
    assert not plan_is_viable(others, q)
    one_query = Plan(queries=["only"], facets=_facets(*GOOD[:3]))
    assert not plan_is_viable(one_query, q)


def test_default_fake_plan_is_viable_with_no_replan(make_ctx) -> None:
    ctx = make_ctx()
    outcome = make_plan(ctx, "bike share pilot")
    assert isinstance(outcome, PlanOutcome)
    assert not outcome.replan_used
    assert len(outcome.plan.queries) <= ctx.cfg.planned_queries
    assert [f.facet_id for f in outcome.plan.facets] == [
        f"f{i}" for i in range(1, len(outcome.plan.facets) + 1)
    ]


def test_short_plan_gets_exactly_one_replan(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    answers = [
        Plan(queries=["a b", "c d"], facets=_facets(*GOOD[:2])),
        Plan(queries=["a b", "c d"], facets=_facets(*GOOD)),
    ]
    writer.set_handler(Plan, lambda ctx: answers.pop(0))
    ctx = make_ctx(writer=writer)
    outcome = make_plan(ctx, "topic")
    assert outcome.replan_used
    assert len(writer.calls) == 2


def test_still_narrow_after_replan_fails_with_zero_search_spend(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    writer.set_handler(Plan, lambda ctx: Plan(queries=["a b", "c d"], facets=_facets(*GOOD[:2])))
    search = FakeSearch()
    ctx = make_ctx(writer=writer, search=search)
    with pytest.raises(PipelineFailure) as err:
        make_plan(ctx, "topic")
    assert err.value.code is ErrorCode.PLAN_TOO_NARROW
    assert len(writer.calls) == 2
    assert search.calls == []


def test_queries_are_deduplicated_and_capped(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    queries = ["Alpha  beta", "alpha beta", "gamma delta", "eps zeta", "eta theta", "iota kappa"]
    writer.set_handler(Plan, lambda ctx: Plan(queries=queries, facets=_facets(*GOOD)))
    ctx = make_ctx(writer=writer)
    plan = make_plan(ctx, "topic").plan
    assert len(plan.queries) == ctx.cfg.planned_queries
    assert len({q.lower().replace(" ", "") for q in plan.queries}) == len(plan.queries)


def test_topic_travels_in_a_data_block_not_the_system_prompt(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    ctx = make_ctx(writer=writer)
    make_plan(ctx, "SECRET-TOPIC-MARKER")
    record = writer.calls[0]
    assert "SECRET-TOPIC-MARKER" not in record.system
    assert "topic" in record.block_labels
