# Development Tracker: AI Research Agent

| Field | Value |
|---|---|
| Document | tracker.md |
| Version | 1.0 |
| Aligned with | prd.md v1.7, architecture.md v1.4, design.md v1.0, rules.md v1.0 |
| Updated | 2026-10-21 |
| Purpose | Track implementation work and say what to do next. It never defines requirements (rules.md §2.2) |

**How to update.** When a task changes state, edit its row, add the evidence to §9, and revise §12. End every session by updating memory.md. Task IDs never change and are never reused.

---

## 1. Current Milestone and Phase

| Item | State |
|---|---|
| Phase | Build: the user approved the six documents and asked for the project to be built with `uv` |
| Current milestone | **M1/M2 engineering slice built on scripted providers.** Decisions, live-provider checks, fixtures and evaluation (M0 decisions, M1-17 to M1-21, M2-18 onward, M3) are NOT done |
| Code written | Pipeline, run manager, capacity, adapters (scripted and live), Streamlit UI, eval tools; 533 tests |
| Repository | Not a git repository (task M0-03, awaiting the user's approval) |
| Approvals | The six documents are approved. D-01 to D-13 are still PROPOSED. No owner or reviewer is named (blocker B-01) |
| Last verification | §9.1, 2026-10-21 |

Milestones and the PRD effort estimates (PRD §15, person-hours): M0 engineering 8–12; M1 32–52; M2 63–99; M3 40–68. QA and annotation: M0 1–3; M1 23–36; M2 12–20; M3 100–138. Product, operations and privacy: M0 4–6; M1 2–4; M2 2–4; M3 12–20. Pilot total 299–462 person-hours, before the rework contingency. No effort is estimated per task, because the PRD gives only milestone totals and the M1 harness will give the first real measurements. Do not invent per-task hours.

---

## 2. Conventions and Workstreams

### 2.1 Legend

| Field | Values |
|---|---|
| ID | `M<milestone>-<nn>` for planned work, `DEF-<nn>` for deferred items |
| Priority | **P0** required for the pilot. **P1** optional or hardening. **P2** future |
| Status | `Not started`, `In progress`, `Blocked`, `Done`, `Deferred` |
| Depends on | Task IDs that must be Done first. Dependencies form a graph with no cycles (checked in §9) |
| Acceptance refs | PRD requirement, NFR and test numbers, plus ARCH and DESIGN sections, that define "done" for the task |
| Files | Planned paths (ARCH §4.1). They do not exist yet |

A task is Done only when it meets rules.md §12, and its evidence is in §9.

Section references: a prefix (PRD, ARCH, DESIGN, rules.md) covers the comma-separated sections that follow it; a bare "§n" means this file.

### 2.2 Workstreams

| ID | Workstream | Tasks |
|---|---|---|
| WS-A | Decisions, governance and compliance | M0-01, M0-02, M0-08, M0-11, M0-14, M3-13 |
| WS-B | Foundation and tooling | M0-03 to M0-05, M0-10, M0-12, M0-13, M1-01, M2-27 |
| WS-C | Retrieval, planning and source processing | M1-04, M1-07, M1-08, M1-24 |
| WS-D | Trust core (ledger, checks, verifier, repair, status) | M1-09 to M1-13, M2-04 to M2-08, M2-22, M2-26 |
| WS-E | Orchestration, run manager and capacity | M1-14, M1-15, M2-01 to M2-03, M2-21 |
| WS-F | User interface and design | M1-16, M2-09 to M2-15, M2-25 |
| WS-G | Observability and KPIs | M2-16, M2-17, M3-16 |
| WS-H | Evaluation and measurement | M1-17 to M1-21, M2-18, M2-19, M3-01 to M3-09 |
| WS-I | Security and resilience testing | M2-20, M2-23, M2-24 |
| WS-J | Deployment and release | M3-10 to M3-15, M2-28 |
| WS-K | Providers and models | M0-06, M0-07, M0-09, M1-02, M1-03, M1-05, M1-06 |
| WS-L | Optional reference tools (ARCH §16) | M1-22, M1-23, M2-29 to M2-31 |

---

## 3. M0 — Decisions and Foundation

Exit criteria: PRD §15 (signed decision log including reviewer availability, booting local app) and §11 of this file.

| ID | Task | Pri | Depends on | Status | Acceptance refs | Files |
|---|---|---|---|---|---|---|
| M0-01 | Name the product owner, engineering owner and two independent reviewers (privacy, legal and security review can be one person); agree a written availability schedule per milestone | P0 | — | Blocked (needs the user) | D-12; PRD §4, §15, §15.1 | `decision-log.md` |
| M0-02 | Record D-01 to D-05 and D-10 to D-12 as approved or replaced, each with approver and date | P0 | M0-01 | Not started | PRD §4, §19 | `decision-log.md` |
| M0-03 | Initialize the git repository with `.gitignore`, README skeleton and the folder layout | P0 | — | Partial: folder layout and `.gitignore` done; git NOT initialised (needs the user's approval, rules.md §10) | ARCH §4.1; rules.md §5 | `.gitignore`, `README.md` |
| M0-04 | Scaffolding and tooling: pinned Python, hashed lockfile, `ruff`, `mypy`, `pytest`, `import-linter` contracts from ARCH §4.3, canonical commands from rules.md §8.3 | P0 | M0-03 | Done (tests green, §9.1); `uv sync` works; ruff, mypy strict and import-linter pass | NFR-14; ARCH §2, §4.3 | `pyproject.toml`, `requirements.txt`, `.importlinter` |
| M0-05 | Pin Streamlit and verify the assumptions: polling fragments, theme options, health route, bundled font, layout width, SIGTERM handling (A-07, A-13); record results | P0 | M0-04 | Partial: app boots headless (health 200) and fragments work under AppTest; SIGTERM and fonts unverified | A-07, A-13; DESIGN §15 items 1–3; ARCH §14 | `decision-log.md` |
| M0-06 | Select and pin the writer, planner and verifier models; verify strict structured output (A-02); satisfy D-11 | P0 | M0-02 | Partial: NVIDIA Nemotron 3 Ultra (writer) works live; the verifier is a local Ollama `qwen3-vl:8b-instruct` (hosted NVIDIA verifiers were flaky); the sealed verifier fixture gate has not run | D-11, A-02; ARCH §2, §8 | `.env.example`, settings |
| M0-07 | Build the versioned price sheet and safety factor from current provider prices (A-05) | P0 | M0-06 | Partial: `core/price_sheet_nvidia_free.json` holds budgeting rates for the free prototype API (review by 2027-01-20); the Tavily rate is an unverified upper bound | D-07, A-05; ARCH §8.4, §10.4 | `core/settings.py`, price sheet |
| M0-08 | Provider terms checklist and the privacy and data-protection applicability note (PRD §12.4) | P0 | M0-06 | Not started | PRD §12.4; ARCH §8.3 | `decision-log.md` |
| M0-09 | Verify provider wire contracts (search response fields, structured-output options, usage fields); plan the contract fixtures | P0 | M0-06 | Partial: adapters built from documentation; hosted NVIDIA behavior unverified; `eval/provider_probe.py` is ready for the key owner to run | ARCH §6.5; A-01 | `tests/adapters/` fixtures plan |
| M0-10 | Verify `tldextract` offline mode and other library choices | P0 | M0-04 | Done (tests green, §9.1); offline suffix list in use | ARCH §2 | `decision-log.md` |
| M0-11 | Plan hosting and the access gateway for the pilot (A-11); define the drain wrapper approach | P0 | M0-02 | Not started | D-04, A-11, NFR-19; ARCH §9.1, §12.2 | `decision-log.md` |
| M0-12 | CI skeleton: lint, types, import rules, tests, secret scan, dependency audit, network guard | P0 | M0-04 | Not started | ARCH §12.3, §13.3 | CI config |
| M0-13 | Permanent cross-reference check and requirement-coverage check (the scratch versions used in §9 are throwaway) | P0 | M0-04 | Partial: `eval/doc_checks.py` covers requirement coverage; xref check not built | rules.md §9 | `eval/xref_check.py`, `eval/coverage_check.py` |
| M0-14 | Approve the design-owned copy lines and open items (DESIGN §9, §15) | P1 | M0-02 | Not started | DESIGN §9.1, §9.3, §15 | `ui/copy.py` plan |

---

## 4. M1 — Proof-of-Concept Slice

Exit criteria: PoC checkpoint decision recorded as Go, Adjust or Stop (D-13).

| ID | Task | Pri | Depends on | Status | Acceptance refs | Files |
|---|---|---|---|---|---|---|
| M1-01 | Domain models and the error taxonomy | P0 | M0-04 | Done (tests green, §9.1) | FR-07; ARCH §5.6, §6.4, §7.3 | `core/models.py`, `core/errors.py` |
| M1-02 | Settings loader with secrets in `SecretStr` and mode limits | P0 | M1-01 | Done (tests green, §9.1) | FR-14, FR-02; ARCH §9.5, §12.2 | `core/settings.py` |
| M1-03 | Adapter protocols and scripted fakes | P0 | M1-01 | Done (tests green, §9.1) | ARCH §6.5, §13.4 | `adapters/base.py`, `adapters/fakes.py` |
| M1-04 | Search adapter with contract fixtures | P0 | M1-03, M0-09 | Built, live wire format unverified (`adapters/live.py`, fake-transport tests green) | FR-04; ARCH §6.5, §8.1 | `adapters/search_tavily.py` |
| M1-05 | Writer and planner model adapter (SDK retries disabled, usage mapped) | P0 | M1-03, M0-06, M0-09 | Built, live wire format unverified (`OpenAICompatChat`: OpenAI, NVIDIA Build and compatible servers; scripted-client tests green) | ARCH §2, §10.2 | `adapters/llm_openai.py` |
| M1-06 | Verifier model adapter | P0 | M1-03, M0-06, M0-09 | Built, live wire format unverified (`AnthropicChat` and `OpenAICompatChat`; scripted-client tests green) | D-11; ARCH §8.1 | `adapters/llm_anthropic.py` |
| M1-07 | Planner with facet categories, minimum breadth and one replan | P0 | M1-05, M1-01 | Done (tests green, §9.1) | FR-03; tests 27, 39; ARCH §5.3 | `pipeline/planner.py` |
| M1-08 | Source processing: canonicalization, dedupe, ranking, diversity, chunking, token trim | P0 | M1-01, M1-04 | Done (tests green, §9.1) | FR-05, FR-06, FR-07, FR-16, D-06; tests 3, 4, 34; PRD §6.2 | `pipeline/source_processing.py` |
| M1-09 | Claim ledger, section placement and counting rules | P0 | M1-01 | Done (tests green, §9.1) | FR-08; test 37; ARCH §5.6 | `pipeline/claim_ledger.py` |
| M1-10 | Quote match and numeric guard, with property tests | P0 | M1-09, M1-08 | Done (tests green, §9.1) | FR-33; tests 7, 8, 9; ARCH §5.7 | `pipeline/claim_checks.py` |
| M1-11 | Batched verifier: token-based batches, strict JSON parsing, in-run cache | P0 | M1-06, M1-10 | Done (tests green, §9.1) | FR-19; tests 6, 7, 34; ARCH §10.4 | `pipeline/passage_verifier.py` |
| M1-12 | Report rendering and a first Markdown export | P0 | M1-09 | Done (tests green, §9.1) | FR-11, FR-12; PRD §6.3 | `pipeline/report_generator.py`, `pipeline/export_markdown.py` |
| M1-13 | Status rules with N−1, N, N+1 boundary tests | P0 | M1-01 | Done (tests green, §9.1) | FR-31; test 15; PRD §6.4; ARCH §5.4 | `core/status_rules.py` |
| M1-14 | Minimal orchestrator for both modes with deadline checks | P0 | M1-07, M1-08, M1-05, M1-11, M1-12, M1-13, M1-15 | Done (tests green, §9.1) | FR-02, FR-15; ARCH §5.3 | `core/research_agent.py` |
| M1-15 | Token estimator, budget ledger and guarded call (basic) for cost measurement | P0 | M1-01, M0-07 | Done (tests green, §9.1) | FR-15, FR-32; ARCH §10.2, §10.4 | `core/capacity.py` |
| M1-16 | UI shell with topic validation. It starts each run on a single background worker thread through a minimal run-manager stub, so the pipeline never runs in the Streamlit script thread. The full run manager arrives in M2-01 | P0 | M1-14 | Done (tests green, §9.1) | FR-01; test 1; PRD §9.5 invariant 9; DESIGN §4.1 | `app.py`, `ui/components.py` |
| M1-17 | Measurement harness: tokens, cost, retries, stage timings, removed claims, PoC report | P0 | M1-14, M1-15 | Not started | FR-42; test 31; ARCH §11.3 | `eval/harness.py` |
| M1-18 | Dev set (at least 20 topics) with per-mode eligibility labels and essential questions | P0 | M0-01, M0-02 | Not started | PRD §11.1, §11.6 | `eval-data/dev/` |
| M1-19 | Minimum verifier dev fixtures (at least 60 pairs) | P0 | M1-18, M0-01 | Not started | FR-35; PRD §11.2 | `eval/fixtures/verifier_dev.jsonl` |
| M1-20 | Dev grounding sample (at least 40 claims) and dev readability scoring | P0 | M1-18 | Not started | PRD §11.7, §15 | `eval-data/dev/labels/` |
| M1-21 | Run the PoC on the dev set in both modes; write the PoC report; record Go, Adjust or Stop | P0 | M1-17, M1-18, M1-19, M1-20, M1-16 | Not started | D-13; PRD §15 | `eval/reports/poc.md` |
| M1-22 | Study GPT Researcher and STORM; write a lessons note | P1 | — | Not started | ARCH §16.2 items 1–2 | `docs/` |
| M1-23 | Spike: Instructor against native structured outputs | P1 | M1-05 | Not started | ARCH §16.2 item 4 | spike notes |
| M1-24 | Decide whether Trafilatura is needed, based on the provider's response format | P1 | M1-04 | Not started | ARCH §16.2 item 3 | decision note |

---

## 5. M2 — Trust Core and Failure Handling

Exit criteria: fixture, adversarial and boundary tests pass (PRD §15). Starts only after an M1 Go or Adjust.

| ID | Task | Pri | Depends on | Status | Acceptance refs | Files |
|---|---|---|---|---|---|---|
| M2-01 | Run manager: worker pool, permits, session lock, idempotency, heartbeat watchdog, TTL purge, ownership checks | P0 | M1-21 | Done (tests green, §9.1) | FR-36, NFR-11, NFR-17, D-03; tests 17, 19; ARCH §4.3, §6.3 | `core/run_manager.py` |
| M2-02 | Capacity: budget ledger with base reservations and pool, call-graph startup check, daily spend guard, pre-call admission | P0 | M1-15, M1-21 | Done (tests green, §9.1) | FR-32, FR-37, FR-45, NFR-04, NFR-05, D-07; tests 2, 20, 21, 32, 41; ARCH §10.4 | `core/capacity.py` |
| M2-03 | Guarded call, retry policy, per-provider rate limiters, light circuit breaker | P0 | M2-02 | Done (tests green, §9.1) | FR-15, NFR-16; ARCH §10.2, §10.3 | `core/capacity.py`, `adapters/*` |
| M2-04 | Sentence typing and the sentence rules | P0 | M1-09, M1-21 | Done (tests green, §9.1) | FR-34; test 11; ARCH §5.7 | `pipeline/claim_ledger.py`, `pipeline/claim_checks.py` |
| M2-05 | Coverage scan | P0 | M2-04 | Done (tests green, §9.1) | FR-34; test 12 | `pipeline/coverage_scan.py` |
| M2-06 | Repair pass with the 6 and 12 claim limits and input caps | P0 | M2-05, M2-03 | Done (tests green, §9.1) | FR-17; tests 10, 42; ARCH §5.3 | `pipeline/report_generator.py` |
| M2-07 | Full state machine: interrupts, safe snapshots, abandon, replan, no-evidence paths | P0 | M2-01, M2-03, M2-06, M1-14 | Done (tests green, §9.1) | NFR-03; test 39; ARCH §5.3 | `core/research_agent.py` |
| M2-08 | Citation validator | P0 | M1-09 | Partial: reference checks live inside `check_claim` and the registry; no separate validator module | FR-09; test 5 | `pipeline/citation_validator.py` |
| M2-09 | Final export with escaping and the Evidence appendix; final report generator | P0 | M1-12, M2-08 | Done (tests green, §9.1) | FR-11, FR-12; tests 22, 35; ARCH §9.4 | `pipeline/export_markdown.py` |
| M2-10 | UI: polling fragment, session state, progress stages and `poll_once()`, completing the M1 shell on top of the full run manager | P0 | M2-01, M1-16 | Done (tests green, §9.1) | FR-13, NFR-01; test 18; DESIGN §8; ARCH §4.2 | `app.py`, `ui/state.py`, `ui/components.py` |
| M2-11 | UI: Evidence Details toggles | P0 | M2-10, M2-09 | Done (tests green, §9.1) | FR-20; test 28; DESIGN §7 | `ui/components.py` |
| M2-12 | UI: status banner, scorecard, facet coverage list, references, notices | P0 | M2-14, M2-10, M2-09 | Done (tests green, §9.1) | FR-10, FR-13, FR-39; tests 22, 30; DESIGN §4, §9 | `ui/components.py` |
| M2-13 | UI: feedback, Clear session, privacy and FAQ tabs, `copy.py`, expired, paused and unavailable states | P0 | M2-12, M2-14, M2-01 | Done (tests green, §9.1) | FR-26, FR-27, FR-28, FR-29; tests 23, 24, 41; DESIGN §9 | `ui/components.py`, `ui/copy.py` |
| M2-14 | Design tokens, Streamlit theme config, contrast and agreement tests | P0 | M0-04 | Done (tests green, §9.1) | DESIGN §5, §12; DR-12 | `ui/theme.py`, `.streamlit/config.toml` |
| M2-15 | Language policy | P0 | M1-01 | Done (tests green, §9.1) | FR-30, D-01; test 1; PRD §6.7 | `core/settings.py`, `ui/state.py` |
| M2-16 | Typed telemetry events, JSON lines, retention and redaction tests | P0 | M1-01 | Partial: run, stage, provider, breaker, startup and rejection events emitted; per-run cost and counts on `run.finished`; some ARCH §11.2 fields not recorded | NFR-08, NFR-09, D-08; ARCH §11 | `core/telemetry.py` |
| M2-17 | KPI event counters | P0 | M2-16, M2-11, M2-13 | Partial: evidence-opened and feedback events exist; no KPI aggregation | FR-44; test 36; PRD §2.7 | `core/telemetry.py` |
| M2-18 | Expand verifier fixtures to at least 200 pairs, with a sealed test half and the scorecard script | P0 | M1-19 | Partial: scorecard script, a 45-pair synthetic development set and `eval/verifier_eval.py` built and run on two local models; the 200-pair sealed set is not (needs human labels) | FR-35; PRD §11.2 | `eval/fixtures/`, `eval/scorecard.py` |
| M2-19 | Scan fixtures (40 planted, 40 clean) and scorecard | P0 | M2-05 | Not started | FR-35; PRD §11.2 | `eval/fixtures/` |
| M2-20 | Attack fixtures and security tests: injection, secrets, export | P0 | M2-09, M2-05, M1-11 | Partial: escaping, injection-fence and secret-handling tests exist; attack fixtures not built | NFR-10; tests 25, 35; ARCH §9.3 | `tests/security/` |
| M2-21 | Bootstrap check, entrypoint wrapper and drain | P0 | M2-01 | Partial: `entrypoint.py` and drain handshake built and tested; process wrapper itself not auto-tested | NFR-19, A-13; test 40; ARCH §12.2 | `core/settings.py`, `entrypoint.py` |
| M2-22 | Status boundary tests and status-correctness fixtures (at least 20) | P0 | M1-13, M2-07 | Partial: boundary tests done; the 20 status fixtures are not built | test 14, test 15; PRD §11.3 | `tests/core/`, `eval/fixtures/` |
| M2-23 | Provider fault tests: rate limit, timeout, malformed output, invalid key, outage | P0 | M2-03, M2-07 | Partial: guard, adapter and orchestrator fault tests done; no recorded-fixture suite | tests 16, 38, 39; ARCH §10 | `tests/` |
| M2-24 | Concurrency tests: permits, session lock, idempotency, rerun and double-click | P0 | M2-01 | Partial: permit, session-lock, idempotency and heartbeat tests done; no browser double-click test | NFR-11, NFR-17; tests 17, 18 | `tests/core/` |
| M2-25 | Accessibility pass 1 and browser tests: keyboard, axe, reload, background-tab throttling | P0 | M2-12, M2-13, M2-11 | Not started | NFR-15; tests 26, 29; DESIGN §11 | `tests/browser/` |
| M2-26 | Contradiction handling in drafting and rendering | P0 | M1-09, M2-07 | Partial: writer prompt and the empty-state sentence are in; no conflicting-source fixture | FR-18; test 13; PRD §6.5 | `pipeline/report_generator.py` |
| M2-27 | Finish CI: dependency audit, secret scan, network guard, architecture fitness functions | P0 | M0-12, M2-16 | Partial: import-linter contracts and fitness tests done; no CI config | ARCH §13.3 | CI config, `tests/arch/` |
| M2-28 | Runbook and README drafts, including drain and rollback | P0 | M2-21 | Partial: README written; runbook not written | PRD §16; ARCH §12.2 | `README.md`, `docs/runbook.md` |
| M2-29 | Dev regression setup with DeepEval (or Ragas) | P1 | M1-18 | Not started | ARCH §16.2 items 5, 9 | `eval/` |
| M2-30 | Promptfoo adversarial cases and prompt comparison, exported to our fixture format | P1 | M1-19 | Not started | ARCH §16.2 item 6 | `eval/fixtures/` |
| M2-31 | Optional Phoenix tracing hook, default off, dev and benchmark runs only | P1 | M2-16 | Not started | ARCH §16.2 item 8 | `adapters/`, `core/telemetry.py` |

---

## 6. M3 — Evaluation and Private Pilot

Exit criteria: PRD §11 evidence and the PRD §16 checklist signed.

| ID | Task | Pri | Depends on | Status | Acceptance refs | Files |
|---|---|---|---|---|---|---|
| M3-01 | Holdout set (at least 80 topics): per-mode eligibility inventories, essential questions, second-annotator audit | P0 | M0-01, M1-21 | Not started | PRD §11.1, §11.6 | `eval-data/holdout/` |
| M3-02 | Seal the holdout; freeze thresholds (D-10); start the burn history | P0 | M3-01, M2-22 | Not started | D-10; PRD §11.1 | `decision-log.md` |
| M3-03 | Benchmark runner and holdout runs in both modes, with the outage rule | P0 | M3-02, M2-07, M2-09, M2-16 | Not started | NFR-06; test 38; PRD §11.3 | `eval/benchmark.py` |
| M3-04 | Sample and label claims (at least 160 from at least 50 reports, at least 50% double-labeled) | P0 | M3-03 | Not started | PRD §11.2, §11.3 | `eval-data/holdout/labels/` |
| M3-05 | Evaluation tooling: cluster bootstrap, Wilson intervals, coverage and readability scoring | P0 | M1-17 | Partial: Wilson and bootstrap tools built; coverage and readability scoring not | FR-40; test 33 | `eval/stats.py` |
| M3-06 | Essential-question coverage and readability scoring | P0 | M3-03, M3-05 | Not started | PRD §11.6, §11.7 | `eval-data/holdout/labels/` |
| M3-07 | Latency and cost measurement with bootstrap intervals; spurious budget-stop rate | P0 | M3-03 | Not started | NFR-01, NFR-02, NFR-18; PRD §10.2 | `eval/reports/` |
| M3-08 | Sealed verifier and scan scorecards | P0 | M2-18, M2-19 | Not started | FR-35; PRD §2.6 | `eval/reports/` |
| M3-09 | Status correctness on hard cases and fixtures | P0 | M2-22, M3-03 | Not started | PRD §11.3 | `eval/reports/` |
| M3-10 | Hosting: gateway, container, secrets, log retention | P0 | M0-11, M2-21 | Not started | NFR-14, D-04, D-08; ARCH §12 | deployment config |
| M3-11 | Full accessibility audit and defect log | P0 | M2-25, M3-10 | Not started | NFR-15; test 26; DESIGN §11 | `docs/a11y-report.md` |
| M3-12 | Load test: 5 concurrent runs and BUSY handling | P0 | M2-24, M3-10 | Not started | NFR-11 | `tests/load/` |
| M3-13 | Compliance checklist filed | P0 | M0-08 | Not started | PRD §12.4 | `decision-log.md` |
| M3-14 | Release documents: runbook, FAQ and privacy content, README | P0 | M2-28, M3-10 | Not started | PRD §16 | `docs/`, `README.md` |
| M3-15 | Pilot readiness review against PRD §11.5 and PRD §16, with sign-offs | P0 | M3-03 to M3-14 | Not started | PRD §11.5, §16 | review record |
| M3-16 | KPI baseline setup and first report | P1 | M2-17, M3-10 | Not started | PRD §2.7 | `eval/metrics_report.py` |

---

## 7. Deferred and Backlog

| ID | Item | Pri | Source | Status |
|---|---|---|---|---|
| DEF-01 | Opt-in research history | P1 | FR-21 | Deferred |
| DEF-02 | PDF export | P1 | FR-22 | Deferred |
| DEF-03 | Source and date filters | P1 | FR-23 | Deferred |
| DEF-04 | Follow-up grounded Q&A | P2 | FR-24 | Deferred |
| DEF-05 | Scheduled research | P2 | FR-25 | Deferred |
| DEF-06 | Reload-recovery token | P1 | FR-38 | Deferred |
| DEF-07 | Two-verifier agreement for high-risk claims | P1 | FR-41 | Deferred (enable if fixtures or cost warrant) |
| DEF-08 | Verified aggregation (composite claims) | P1 | FR-43 | Deferred (readability trigger, PRD §11.7) |
| DEF-09 | Public launch: shared queue, Redis, PostgreSQL, OIDC, quotas, monitoring (PL-01 to PL-11, D-09, NFR-12) | P2 | PRD §17; ARCH §12.4 | Deferred |
| DEF-10 | Dark theme | P1 | DESIGN §5.3 | Deferred |
| DEF-11 | Master "Show all evidence" toggle | P1 | DESIGN §15 item 10 | Deferred |
| DEF-12 | Crawl4AI, Docling, SearXNG, LangGraph | P2 | ARCH §16 | Deferred (need PRD change control or the public-launch review) |

---

## 8. Requirement Coverage

Every PRD identifier maps to at least one task here. The check in §9 confirms nothing is missing.

| PRD identifiers | Tasks |
|---|---|
| FR-01 | M1-16 |
| FR-02 | M1-02, M1-14 |
| FR-03 | M1-07 |
| FR-04 | M1-04 |
| FR-05, FR-06, FR-07, FR-16 | M1-08 (FR-07 also M1-01) |
| FR-08 | M1-09 |
| FR-09 | M2-08 |
| FR-10 | M2-12 |
| FR-11, FR-12 | M1-12, M2-09 |
| FR-13 | M2-10, M2-12 |
| FR-14 | M1-02 |
| FR-15 | M1-14, M1-15, M2-03 |
| FR-17 | M2-06 |
| FR-18 | M2-26 |
| FR-19 | M1-11 |
| FR-20 | M2-11 |
| FR-21 to FR-25 | DEF-01 to DEF-05 |
| FR-26, FR-27, FR-28, FR-29 | M2-13 |
| FR-30 | M2-15 |
| FR-31 | M1-13 |
| FR-32, FR-37 | M1-15, M2-02 |
| FR-33 | M1-10 |
| FR-34 | M2-04, M2-05 |
| FR-35 | M1-19, M2-18, M2-19, M3-08 |
| FR-36 | M2-01 |
| FR-38 | DEF-06 |
| FR-39 | M2-12 |
| FR-40 | M3-05 |
| FR-41 | DEF-07 |
| FR-42 | M1-17 |
| FR-43 | DEF-08 |
| FR-44 | M2-17 |
| FR-45 | M2-02, M2-13 |
| NFR-01 | M2-10, M3-07 |
| NFR-02, NFR-18 | M3-07 |
| NFR-03 | M2-07 |
| NFR-04, NFR-05 | M2-02 |
| NFR-06 | M3-03 |
| NFR-07 | M2-01 |
| NFR-08, NFR-09 | M2-16 |
| NFR-10 | M2-20 |
| NFR-11 | M2-01, M2-24, M3-12 |
| NFR-12 | DEF-09 |
| NFR-13 | M3-13 |
| NFR-14 | M0-04, M3-10 |
| NFR-15 | M2-25, M3-11 |
| NFR-16 | M2-03 |
| NFR-17 | M2-01, M2-24 |
| NFR-19 | M2-21 |
| D-01 | M0-02, M2-15 |
| D-02, D-05 | M0-02 |
| D-03 | M0-02, M2-01 |
| D-04 | M0-11, M3-10 |
| D-06 | M1-08 |
| D-07 | M0-07, M2-02 |
| D-08 | M2-16, M3-10 |
| D-09 | DEF-09 |
| D-10 | M0-02, M3-02 |
| D-11 | M0-06 |
| D-12 | M0-01 |
| D-13 | M1-21 |
| PL-01 to PL-11 | DEF-09 |
| PRD tests 1 to 42 | See the "Acceptance refs" column; test 1 M1-16 and M2-15; 2 M2-02; 3, 4 M1-08; 5 M2-08; 6 M1-11; 7 M1-10 and M1-11; 8, 9 M1-10; 10 M2-06; 11 M2-04; 12 M2-05; 13 M2-26; 14 M2-22; 15 M1-13 and M2-22; 16 M2-23; 17 M2-01 and M2-24; 18 M2-10 and M2-24; 19 M2-01; 20, 21 M2-02; 22 M2-09 and M2-12; 23, 24 M2-13; 25 M2-20; 26 M2-25 and M3-11; 27 M1-07; 28 M2-11; 29 M2-25; 30 M2-12; 31 M1-17; 32 M2-02; 33 M3-05; 34 M1-08 and M1-11; 35 M2-09 and M2-20; 36 M2-17; 37 M1-09; 38 M2-23 and M3-03; 39 M1-07, M2-07 and M2-23; 40 M2-21; 41 M2-13; 42 M2-06 |

---

## 9. Test and Verification Results

### 9.1 Runs so far

Build verification, 2026-10-21, from the project root. Commands are the canonical ones from rules.md §8.3 run through `uv`.

| Check | Command | Result |
|---|---|---|
| Tests | `uv run pytest` | 533 passed |
| Lint | `uv run ruff check .` | All checks passed |
| Types | `uv run mypy .` | no issues in 77 source files (strict for application code; relaxed for tests) |
| Layering | `uv run lint-imports` | 6 contracts kept, 0 broken |
| Local verifier | `uv run python -m eval.verifier_eval --model qwen3-vl:8b-instruct` | 45 scripted pairs: 95.6 percent accurate, 2 of 26 false accepts (above the gate's rate), 0 of the 2 injection pairs that reach the verifier accepted; 39.9 s mean per full batch (reports in `eval/reports/`, rescored without a model) |
| NVIDIA path | `uv run pytest tests/test_nvidia_end_to_end.py` | A full run through the NVIDIA-configured service with a scripted SDK client completes; truncated JSON is retried and charged; a verifier that never returns valid JSON fails the run closed |
| Demo | `uv run demo.py` | Quick run completes: 8 supported claims, 5 sources, estimated cost $0.063 (scripted providers, synthetic data) |
| App boot | `uv run streamlit run app.py --server.headless true` | `/_stcore/health` and `/` return 200 |
| Dependency audit | `uv run pip-audit` | 8 advisories, all in `pillow 12.3.0`, a Streamlit dependency pinned below the fixed 13.0.0 (see B-09) |
| Contrast | `uv run python -m eval.contrast` | every design-token pair passes (test `test_every_required_contrast_pair_passes_wcag`) |

Not run: any live provider call (no approved spend cap, rules.md §6), browser or screen-reader tests, the holdout benchmark.

The earlier document checks below were run with throwaway scripts; `eval/doc_checks.py` now repeats the requirement-coverage part (FR 45 of 45 and NFR 19 of 19 referenced by this tracker).

| Date | Check | Result |
|---|---|---|
| 2026-10-21 | WCAG contrast ratios for every token pair in DESIGN §5.2 and DESIGN §5.3, plus hover and pressed pairs | All pairs pass their thresholds |
| 2026-10-21 | Section and identifier cross-references in design.md and architecture.md | No broken section references; no FR, NFR, D, A, PL or ADR identifier missing from its source file |
| 2026-10-21 | PRD §7.3 states mapped in DESIGN §3.3 | 16 of 16 states mapped |
| 2026-10-21 | Task graph, requirement coverage and cross-references across all six files | See §9.3 |

### 9.2 Document quality log

Scores are spec-quality estimates by the same agent that wrote the documents, using a rubric of completeness, consistency with the source documents, specificity, verifiability, honesty about unknowns and governance. They are not independent reviews and measure no running software.

| Document | Version | Scores by round |
|---|---|---|
| prd.md | 1.7 | v1.1: 81. v1.2: 86. v1.3: 87 and v1.4: 90 (independent reviews pasted by the user). v1.5: 91. v1.6: 92. v1.7: 93 on the strict category scale, 95.5 on the rubric |
| architecture.md | 1.4 | v1.0: 89. v1.2: 90. v1.4: 92 on the strict category scale, 95 on the rubric |
| design.md | 1.0 | 91 first pass, 96 after fixes |
| memory.md | 1.0 | 94 first pass, 97 after fixes |
| rules.md | 1.0 | 92 first pass, 96 after fixes |
| tracker.md | 1.0 | 91 first pass, 96 after fixes |

Two scales are in use. The **strict category scale** (weighted categories, with penalties for unverified runtime assumptions) produced the earlier PRD and architecture scores and cannot honestly pass the low 90s before the M1 proof of concept measures anything. The **rubric** (completeness, consistency, specificity, verifiability, internal consistency, honesty about unknowns, governance, concision, maintainability) was used for the four new files, and for the last PRD and architecture figures shown above. Compare scores only within one scale.

The PRD and architecture defects fixed in the latest pass: a decision-order step that contradicted the FR-17 repair trigger, test 32 missing the planner replan, estimates that ignored the v1.7 additions, no requirement for the daily spend stop (FR-45), no way for the UI to learn that a mode is unavailable (`get_service_state`), a mapping that omitted tests 40 to 42, and an alert threshold that disagreed with its environment variable.

The first-pass defects that were fixed: **design.md** (wording that conflicted with PRD copy, missing hover and pressed tokens, non-unique toggle names, a banner that contained a widget, a report layout that contradicted the architecture, missing WCAG rows). **memory.md** (ambiguous section references). **rules.md** (an unverified tool command, a test map that omitted many PRD tests, no explicit rule against building before approval). **tracker.md** (an M1 UI shell that broke PRD invariant 9, two tasks outside any workstream, unfilled placeholders, wrong score attribution, a missing decision-log path).

### 9.3 Results recorded after the checks

Scripted checks run on 2026-10-21 (throwaway scripts, see §9.1):

- **Task graph:** 85 tasks (M0 14, M1 24, M2 31, M3 16). No empty fields, no dependency on an unknown task, no cycle, no dependency on a later milestone, and every task belongs to a workstream.
- **Requirement coverage:** FR 45 of 45, NFR 19 of 19, decisions D-01 to D-13 13 of 13, PL-01 to PL-11 11 of 11, PRD tests 42 of 42 (in this file and in rules.md §8.2).
- **Cross-references:** no broken section reference among the six files. memory.md, rules.md and design.md name only tasks that exist.
- **PRD §16 Definition of Done:** 27 items.
- **Design contrast:** every pair in DESIGN §5.2 and DESIGN §5.3, plus hover and pressed pairs, passed its threshold.
- **Not verified:** anything that needs running software, a real Streamlit version, a provider API, or a screen reader.

---

## 10. Bugs, Blockers and Risks

| ID | Type | Description | Impact | Next step |
|---|---|---|---|---|
| B-01 | Blocker | No owner, engineer or independent reviewers are named | PRD blocks M1 start and the grounding sign-off | M0-01 (needs the user) |
| B-02 | Blocker | The folder is not a git repository | No version control or commits | M0-03 (needs the user's approval) |
| B-03 | Risk | Quick's worst-case cost is about $0.724 against a $0.75 cap on placeholder prices | A price change or a pricier writer makes Quick refuse to start | M0-07 (real prices), M1-21 and D-13 decide the cap |
| B-04 | Risk | Provider and Streamlit facts are unverified (wire formats, fragments, SIGTERM handling, theme options, fonts) | Design and architecture assumptions may fail | M0-05, M0-09, M0-10 |
| B-05 | Risk | Reviewer availability is unknown | Grounding sign-off may fall back to evaluation-only (D-12) | M0-01 |
| B-06 | Risk | Documents were scored only by their author | Scores may be optimistic | An independent review at M0 or M1 |
| B-07 | Risk | Placeholder numbers (prices, token speed, verifier latency, token estimator) | Cost and latency targets may move | M1-17 and M1-21 |
| B-08 | Risk | Terse reports may disappoint users | Low usefulness | Readability scoring (M1-20, M3-06); FR-43 trigger |

| B-09 | Risk | `pillow 12.3.0` (a Streamlit dependency) has 8 published advisories fixed in 13.0.0, which Streamlit 1.66.0 does not allow | Low here: the app renders no user-supplied images | Re-check when Streamlit supports Pillow 13; do not override the constraint |
| B-10 | Risk | Live adapters were written from documentation and tested only against fake transports | A wire-format difference would fail at the first live call | M0-09: one supervised request per adapter after the user approves a spend cap |
| B-11 | Risk | The price sheet holds placeholder prices and live mode refuses to start on it | No live run is possible until real prices are entered | M0-07 |

| B-14 | Risk | Local verifier on the development laptop (4 GB GPU, 15.7 GB RAM): `qwen3-vl:8b-instruct` is accurate on 45 synthetic pairs (95.6 percent) but its false-accept rate (2 of 26, 7.7 percent; 1 of 21 once the numeric guard is applied) is above the gate's 3.3 percent and the set is too small to certify, and a 4-claim batch takes 40 s on average (67 s at production size), so its verifier stage needs 160 to 270 s for Quick (limit 120 s) and 360 to 600 s for Deep (limit 360 s); `qwen3-vl:4b-instruct` obeyed 5 of 6 injections and is unusable; system RAM reached 15.5 of 15.7 GB | Every Quick and Deep run on this machine ends `TIMEOUT`; nothing unverified is published | Owner decision: stronger hardware, a different local text model (needs a download the owner must approve), a hosted verifier, or relaxing NFR-03 with `RUN_TIME_FACTOR` |
| B-13 | Risk | Live runs 2026-10-22: the free NVIDIA endpoint stalled 30 to 50 percent of verifier requests (and once a planner request) whatever the concurrency; Gemma 4 31B timed out on every request; every run so far failed closed | No real report has completed on the NVIDIA free tier yet | Retry at another time of day; consider a local verifier (Ollama) or another provider; decide whether to allow more attempts per call (NFR-16 says 2 retries) |
| B-12 | Risk | NVIDIA's hosted trial API: no published rate limit or quota; Gemma 4 is documented as having no structured-output mode and a forum post says its thinking cannot be fully disabled; terms can change and NVIDIA says production use is self-hosted | More schema retries, throttling, a free tier that ends, and a development-only setting | Run `eval/provider_probe.py`, then the verifier fixture gate (M2-18); re-check terms before `review_after` |

No open code defects are known. Rulings taken during the build are in `docs/build-ledger.md`.

---

## 11. Milestone Completion Criteria

| Milestone | Complete when |
|---|---|
| M0 | Decision log signed with named owner, implementer, two independent reviewers and their availability schedule; D-01 to D-05 and D-10 to D-12 recorded; Streamlit and models pinned; price sheet and provider facts verified; local app boots; CI skeleton runs (PRD §15) |
| M1 | The PoC slice runs both modes on the dev set; the measurement harness produces the PoC report; the checkpoint is recorded as Go, Adjust or Stop, with any one-time target revisions logged before the holdout exists (D-13) |
| M2 | Fixture, adversarial, boundary, concurrency and provider-fault tests pass; verifier and scan fixtures are built; the UI covers every state in DESIGN §9.1; accessibility pass 1 done (PRD §15, §11.4) |
| M3 | The sealed holdout is run and graded; all PRD §11.5 gates are met or an approved evaluation-only exception is recorded; the hosted pilot is configured; the PRD §16 checklist is signed (PRD §15) |

---

## 12. Immediate Next Tasks

1. **M0-03** (user approval needed): initialize the git repository; nothing has been committed.
2. **M0-01** (user input needed): name the owners and two reviewers and agree their availability. The questions are in memory.md §5.
3. **Verifier decision** (user): choose between a stronger GPU, testing a text model such as `qwen3:8b` or `qwen3:4b-instruct-2507` with `eval.verifier_eval` (each needs a download you must approve), a hosted verifier, or a relaxed time limit (B-14).
3a. **M0-09** (user action needed): copy `.env.example` to `.env`, add `NVIDIA_API_KEY` and `SEARCH_API_KEY`, set `RESEARCH_PROVIDER_MODE=live`, then run `uv run python -m eval.provider_probe --yes-call-live-providers` (four tiny model calls) and report the output. The NVIDIA models and budgeting rates are already configured (M0-06, M0-07).
4. **M0-02** (after M0-01): record the proposed decisions in `decision-log.md`.
5. **M0-12**: add a CI configuration that runs the commands in §9.1.
6. **M1-18, M1-19, M2-18, M2-19**: build the dev set and the verifier and scan fixtures. They need human labels and are not fabricated.

---

## 13. Release Readiness

| Gate | Status |
|---|---|
| Pilot, hard safety (PRD §11.5) | Not started |
| Pilot, hard status | Not started |
| Pilot, screening (verifier and scan scorecards) | Not started |
| Pilot, measured quality (grounding, completion, coverage, readability) | Not started |
| Pilot, performance and cost | Not started |
| Pilot, UX and privacy | Not started |
| PRD §16 Definition of Done | 0 of 27 items complete |
| Public launch (PRD §17) | Not ready. Deferred (DEF-09) |

The pilot is not approved. The documents are a specification only.
