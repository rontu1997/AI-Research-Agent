"""Run one research pass on the scripted demo providers and print the report.

    uv run demo.py            # Quick mode
    uv run demo.py --deep     # Deep mode

Demo mode uses synthetic data about a fictional topic. It never calls a real provider.
Exit code: 0 Completed, 2 Partial, 1 Failed.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence

from adapters.fakes import DEMO_TOPIC
from core.models import Mode, ResearchRequest, RunStatus
from core.research_agent import run_research
from core.settings import load_settings_from_environment
from service import build_service


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the demo research pass.")
    parser.add_argument("--deep", action="store_true", help="use Deep mode instead of Quick")
    parser.add_argument(
        "--topic", default=DEMO_TOPIC, help="topic to research (the demo corpus is fixed)"
    )
    args = parser.parse_args(argv)

    settings = load_settings_from_environment()
    if settings.provider_mode != "fake":
        print(
            "demo.py only runs on the scripted providers. Set RESEARCH_PROVIDER_MODE=fake.",
            file=sys.stderr,
        )
        return 1
    service = build_service(settings)
    if not service.ready:
        print("Configuration problems: " + ", ".join(service.problems), file=sys.stderr)
        return 1

    mode = Mode.DEEP if args.deep else Mode.QUICK
    request = ResearchRequest(topic=args.topic, depth=mode, idempotency_token=uuid.uuid4().hex)
    ctx = service.new_context(request, lambda: False)
    result = run_research(
        ctx,
        request,
        run_id="demo",
        demo=True,
        progress=lambda stage, fraction: print(
            f"[{int(fraction * 100):3d}%] {stage}", file=sys.stderr
        ),
    )
    service.shutdown()
    print(result.report_markdown or f"No report. Reason: {', '.join(result.reason_codes)}")
    m = result.metrics
    print(
        f"\nStatus: {result.status.value} | supported claims: {m.supported_claims} | "
        f"sources: {m.usable_sources} | cost estimate: {m.estimated_actual_cost_usd}",
        file=sys.stderr,
    )
    return {RunStatus.COMPLETED: 0, RunStatus.PARTIAL: 2, RunStatus.FAILED: 1}[result.status]


if __name__ == "__main__":
    sys.exit(main())
