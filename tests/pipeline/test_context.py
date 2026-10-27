from __future__ import annotations

import pytest

from adapters.base import Block
from adapters.fakes import FakeLLM, FakeSearch
from core.errors import BudgetStop, ProviderServerError
from core.models import Plan


def test_generate_commits_actual_cost_and_returns_parsed(make_ctx) -> None:
    ctx = make_ctx()
    out = ctx.generate(
        stage="planner",
        role="writer",
        system="plan",
        blocks=[Block("topic", "tea"), Block("limits", '{"planned_queries": 3, "facets": 4}')],
        schema=Plan,
        max_output_tokens=800,
        input_cap=1500,
    )
    assert len(out.queries) >= 2
    assert 0 < ctx.guard.ledger.committed_usd < 0.05


def test_generate_uses_the_verifier_client_for_verifier_role(make_ctx) -> None:
    writer, verifier = FakeLLM("fake-writer"), FakeLLM("fake-verifier")
    ctx = make_ctx(writer=writer, verifier=verifier)
    from core.models import VerifierOutput

    ctx.generate(
        stage="verifier",
        role="verifier",
        system="v",
        blocks=[Block("claims", "[]")],
        schema=VerifierOutput,
        max_output_tokens=800,
        input_cap=7000,
    )
    assert verifier.calls and not writer.calls


def test_search_call_is_billed_per_call_and_returns_results(make_ctx) -> None:
    ctx = make_ctx()
    response = ctx.search_call("bike share pilot", max_results=5, want_extracted=True)
    assert response.results
    assert ctx.guard.ledger.committed_usd == pytest.approx(0.016)


def test_provider_failure_surfaces_after_retries_and_releases_budget(make_ctx) -> None:
    search = FakeSearch(fail_with=ProviderServerError("boom"))
    ctx = make_ctx(search=search)
    with pytest.raises(ProviderServerError):
        ctx.search_call("x", max_results=3, want_extracted=True)
    assert len(search.calls) == 3
    assert ctx.guard.ledger.committed_usd == 0


def test_budget_stop_when_the_cap_is_too_small(make_ctx) -> None:
    ctx = make_ctx(cap_usd=0.0001)
    with pytest.raises(BudgetStop):
        ctx.search_call("x", max_results=3, want_extracted=True)


def test_timeouts_scale_by_role_and_never_exceed_the_run_deadline(make_ctx) -> None:
    from adapters.fakes import FakeLLM
    from core.models import VerifierOutput

    seen: list[float] = []

    class Recording(FakeLLM):
        def generate(self, **kwargs):  # noqa: ANN003, ANN201
            seen.append(kwargs["timeout_s"])
            return super().generate(**kwargs)

    ctx = make_ctx(verifier=Recording("fake-verifier"), wall_s=1000.0)
    ctx.verifier_timeout_factor = 2.0
    ctx.generate(
        stage="verifier",
        role="verifier",
        system="v",
        blocks=[Block("claims", "[]")],
        schema=VerifierOutput,
        max_output_tokens=800,
        input_cap=7000,
    )
    assert seen[-1] == 60.0  # the 30 s verifier timeout, doubled
    short = make_ctx(verifier=Recording("fake-verifier"), wall_s=20.0)
    short.verifier_timeout_factor = 2.0
    short.generate(
        stage="verifier",
        role="verifier",
        system="v",
        blocks=[Block("claims", "[]")],
        schema=VerifierOutput,
        max_output_tokens=800,
        input_cap=7000,
    )
    assert seen[-1] <= 20.0  # never longer than the time left in the run
