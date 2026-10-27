"""Query planner with one replan (PRD FR-03; ARCH §5.3).

A viable plan has at least two distinct queries and enough facets in distinct categories
(``other`` counts at most once). A short plan gets one replan, funded from the contingency pool;
a second shortfall fails the run before any search spend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from adapters.base import Block
from core.errors import ErrorCode, PipelineFailure, ProviderError
from core.models import Facet, FacetCategory, Plan
from core.settings import ModeConfig
from pipeline.context import RunContext
from pipeline.prompts import PLANNER_SYSTEM

MIN_QUERIES = 2
MAX_QUERY_CHARS = 200
MAX_FACET_CHARS = 200


@dataclass(frozen=True)
class PlanOutcome:
    plan: Plan
    replan_used: bool


def _query_key(query: str) -> str:
    return re.sub(r"\W+", "", query.casefold())


def plan_is_viable(plan: Plan, cfg: ModeConfig) -> bool:
    if len({_query_key(q) for q in plan.queries if q.strip()}) < MIN_QUERIES:
        return False
    categories = {f.category for f in plan.facets}
    non_other = {c for c in categories if c is not FacetCategory.OTHER}
    distinct = len(non_other) + (1 if FacetCategory.OTHER in categories else 0)
    # Duplicate categories do not count twice, so facets-in-distinct-categories == `distinct`.
    return distinct >= cfg.required_planned_facets


def _clean(plan: Plan, cfg: ModeConfig) -> Plan:
    seen: set[str] = set()
    queries: list[str] = []
    for raw in plan.queries:
        query = " ".join(raw.split())[:MAX_QUERY_CHARS]
        key = _query_key(query)
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
    facets = [
        Facet(
            facet_id=f"f{index}",
            question=" ".join(facet.question.split())[:MAX_FACET_CHARS],
            category=facet.category,
        )
        for index, facet in enumerate(plan.facets, 1)
    ]
    return Plan(queries=queries[: cfg.planned_queries], facets=facets)


def _ask(ctx: RunContext, topic: str, *, replan: bool) -> Plan:
    limits = {
        "planned_queries": ctx.cfg.planned_queries,
        "facets": ctx.cfg.required_planned_facets + 1,
        "required_distinct_categories": ctx.cfg.required_planned_facets,
        "replan": replan,
    }
    try:
        return ctx.generate(
            stage="planner",
            role="writer",
            system=PLANNER_SYSTEM,
            blocks=[Block("topic", topic), Block("limits", json.dumps(limits))],
            schema=Plan,
            max_output_tokens=ctx.cfg.planner_max_output,
            input_cap=ctx.cfg.planner_input_cap,
            reservation_stage="replan" if replan else "planner",
        )
    except ProviderError as err:
        raise PipelineFailure(ErrorCode.MODEL_FAILED, type(err).__name__) from err


def make_plan(ctx: RunContext, topic: str) -> PlanOutcome:
    plan = _clean(_ask(ctx, topic, replan=False), ctx.cfg)
    if plan_is_viable(plan, ctx.cfg):
        return PlanOutcome(plan, replan_used=False)
    plan = _clean(_ask(ctx, topic, replan=True), ctx.cfg)
    if plan_is_viable(plan, ctx.cfg):
        return PlanOutcome(plan, replan_used=True)
    raise PipelineFailure(ErrorCode.PLAN_TOO_NARROW)
