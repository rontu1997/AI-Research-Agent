# Architecture: AI Research Agent

| Field | Value |
|---|---|
| Document | architecture.md |
| Version | 1.6 — v1.5 plus ADR-021 and §8.7 (local Ollama verifier, approved 2026-10-22) |
| Aligned with | prd.md v1.8 |
| Status | Proposed. Nothing here is approved or implemented. Decisions are recorded as ADRs in state Proposed (§13.5) |
| Updated | 2026-10-22 |
| Owner | Lead developer (name TBD; named at PRD milestone M0) |

**Scope.** This document describes the architecture of the access-restricted pilot (single process, session-only data) in full, and the path to a public launch at design level. The PRD wins on any conflict, except where §14 lists changes proposed to the PRD.

**Conventions.** `FR-nn`, `NFR-nn`, `D-nn`, `A-nn` and `PL-nn` refer to PRD identifiers. A section reference written "PRD §n" points to the PRD; a bare "§n" points to this document. "Proposed" means a recommendation that needs owner sign-off. Provider API details marked *verify at M0* come from general knowledge of the providers and must be checked against current documentation before build.

---

## 1. Architecture Principles and Constraints

### 1.1 Principles

| ID | Principle | What it means in the design |
|---|---|---|
| AP-1 | Evidence before eloquence; fail closed | A claim reaches the user only after deterministic checks and a `supported` verifier verdict. Anything else is removed, and a run with too little left ends Partial or Failed |
| AP-2 | Code decides, models propose | Citation IDs, URLs, counts, status, budgets and rendering are computed by deterministic code. Models only draft or judge inside strict schemas |
| AP-3 | Untrusted by default | The topic and all retrieved text are data. They are delimited, never executed, and models have no tools. Models never emit URLs; code inserts them from the registry |
| AP-4 | Everything bounded | Calls, tokens, wall-time, retries, concurrency and spend are limited, and the limit is checked before the call, not after |
| AP-5 | The UI is a thin client | No pipeline work runs in the Streamlit script thread. The UI talks to one facade (`RunManager`) |
| AP-6 | Session-only by default | Topics, passages and reports live in process memory with a TTL. Only redacted operational metadata is written to disk |
| AP-7 | Providers behind narrow interfaces | Search and LLM calls go through adapters with typed contracts, fakes and recorded fixtures |
| AP-8 | Observable without content | Telemetry is built from typed events with forbidden extra fields, so content cannot leak into logs by accident |
| AP-9 | Simplest thing that meets the PRD | One process, threads and in-memory state. Every simplification has a named upgrade path (§12.4) |
| AP-10 | Measurable | Every PRD target has a hook in the measurement harness (FR-42) |

### 1.2 Constraints

| ID | Constraint | Source |
|---|---|---|
| C-01 | Python application with a Streamlit UI | PRD §4 platform, §8.1 |
| C-02 | Single process, no replicas or multiple workers in the pilot | D-04, PRD §8.4 |
| C-03 | No database; no persistent topics, passages or reports | D-03 |
| C-04 | ≤5 active runs per process, one active run per session | NFR-11 |
| C-05 | Per-mode caps on queries, sources, claims, tokens, wall-time (Quick 120 s, Deep 360 s) and spend | PRD §6.1 |
| C-06 | English topics and reports only | D-01 |
| C-07 | No arbitrary server-side fetch; only the configured search provider | FR-14, PRD §12.1 |
| C-08 | Secrets stay server-side, out of the browser, prompts and logs | FR-14, NFR-10 |
| C-09 | Operational logs retained ≤7 days where the host permits | D-08, NFR-08 |
| C-10 | Excerpts bounded: snippet passage ≤1,500 characters, quote ≤300 characters | PRD §9.2, §12.4 |
| C-11 | Streamlit re-runs the script on every interaction and keeps state per browser session; a full reload starts a new session | PRD §8.4 |
| C-12 | WCAG 2.2 AA is a testing target; Streamlit compliance is not assumed | PRD §7.4 |
| C-13 | Provider prices, limits and behavior are unknown until M0 and may change | A-05, PRD §14.2 |

### 1.3 Quality-attribute priorities

In order, with the trade each priority accepts:

1. **Trust (grounding and provenance).** Accepts lower completion rate and terse reports.
2. **Safety and bounded cost.** Accepts refusing a mode at startup if its worst case does not fit the cap.
3. **Reliability under provider failure.** Accepts Partial results over retries without limit.
4. **Latency.** Accepts a fixed number of sequential model calls to keep verification independent.
5. **Readability.** Measured, with a trigger to improve it (PRD §11.7).
6. **Extensibility.** Provided by adapters and the upgrade path, not by building the public stack early.

### 1.4 Out of scope for this architecture

Authentication inside the app, a persistent store, a job queue, multi-region hosting, and any HTTP API for third parties. §12.4 and §6.6 sketch them for the public launch only.

---

## 2. Technology Stack with Selection Rationale

| Concern | Choice (proposed) | Why | Alternatives considered | Revisit when |
|---|---|---|---|---|
| Language | Python 3.11 or newer (any version the pinned Streamlit supports) | Mandated by the PRD; strong ecosystem for LLM and text work | — | — |
| UI | Streamlit, version pinned at M0 | Mandated; fast to build; fragments allow polling without a custom front end | Gradio, FastAPI + React | The public launch needs auth, accessibility depth or reconnect that Streamlit cannot give |
| Concurrency | `ThreadPoolExecutor` and locks in one process | Provider calls are I/O-bound; threads are simple and compatible with Streamlit's threading model | `asyncio` (a second runtime beside Streamlit's), Celery or RQ (needs a broker, breaks the single-process constraint) | More than 5 concurrent runs or more than one process |
| Schemas | Pydantic v2 with `extra="forbid"` and strict types | Validates every model output and every log event; one source of truth for contracts | dataclasses plus manual checks; JSON Schema only | — |
| HTTP | `httpx` (synchronous client, explicit timeouts) | Clean timeout control; `MockTransport` for tests | `requests` | — |
| LLM SDKs | Official SDKs with their built-in retries disabled (`max_retries=0`) | The app owns retries so each attempt is reserved against the budget (§10.2) | Raw HTTP | SDK retries become budget-aware |
| Search | Tavily behind `SearchProvider` | Named in the PRD; returns snippets and optional extracted text | Brave, Bing or SerpAPI adapters | A provider fails A-01 at the PoC |
| Writer and planner model | OpenAI model, pinned at M0, or any OpenAI-compatible endpoint (development default: Nemotron 3 Ultra on NVIDIA Build, ADR-020) | Named in the PRD; the compatible-endpoint option removes the paid-key requirement for development | Any model with reliable strict-schema output | PoC measurements (A-02, A-04) |
| Verifier and scan model | A different model family from the writer (D-11). Candidates: Claude Haiku 5.5 (`claude-haiku-5-5`), with Claude Sonnet 5.5 (`claude-sonnet-5-5`) as the fallback if the fixture gate fails | Independence reduces correlated errors; a small model keeps cost low | Same family with a different prompt (allowed only with disclosure per D-11) | Fixture scorecard, price sheet |
| Registrable domains | `tldextract` with its bundled suffix snapshot and network fetch disabled | Correct public-suffix handling without a runtime network call (verify the offline option at M0) | Splitting on dots (rejected by PRD §9.2) | — |
| URL canonicalization | Standard library `urllib.parse` plus a versioned tracking-parameter list | Deterministic and testable | Third-party URL libraries | — |
| Text normalization | Standard library `unicodedata` (NFKC) | Matches the PRD's `normalize_for_match` | — | — |
| Logging | Standard `logging` with a JSON formatter and typed event models | No extra runtime dependency; schema enforced by Pydantic | structlog | Need for processors or OpenTelemetry |
| Metrics and alerts | Metrics computed from the log files by a script; optional Prometheus client later | Pilot scale does not justify a metrics stack | Prometheus and Grafana from day one | Public launch (PL-09) |
| Evaluation stats | `numpy` for bootstrap (eval tooling only); own Wilson function | Small and auditable | scipy, statsmodels | — |
| Testing | `pytest`, `hypothesis`, `pytest-cov`, Streamlit `AppTest`, Playwright with axe-core | Covers units, properties, UI state and browser behavior (§13) | Selenium | — |
| Quality tools | `ruff`, `mypy` (strict on domain code), `import-linter`, `pip-audit`, a secret scanner | Enforces the layering rules and supply-chain hygiene | — | — |
| Dependencies | Lockfile with hashes (`uv` or `pip-tools`) | Reproducible builds; supports the dependency audit | — | — |
| Packaging | Docker image, non-root | Portable pilot hosting (NFR-14) | Bare virtualenv | — |
| Access gateway | Reverse proxy or platform auth (for example an OIDC proxy or SSO) in front of Streamlit | Streamlit has no built-in authentication | In-app login | Public launch |

Twelve open-source projects are proposed as references or tools. None is a dependency yet. §16 records the role, cautions and decision gate for each.

---

## 3. High-Level System Architecture

### 3.1 Context and containers

```
 Pilot user (browser)
        │ HTTPS
        ▼
 ┌───────────────────────────┐
 │ Access gateway            │  TLS, SSO or basic auth, rate limiting, WebSocket pass-through
 └──────────────┬────────────┘
                │ HTTP + WebSocket
                ▼
 ┌──────────────────────── One Python process (Streamlit server) ────────────────────────┐
 │                                                                                        │
 │  UI script (one per browser session)                                                   │
 │     │  calls only                                                                      │
 │     ▼                                                                                  │
 │  RunManager (singleton) ── worker threads ──► Pipeline (state machine)                 │
 │     │ locks, permits,                         planner → search → select → draft →      │
 │     │ idempotency, heartbeat                  checks → verify → assemble → scan →      │
 │     │                                         repair? → status → render                │
 │     ▼                                              │                                   │
 │  In-memory stores (TTL): runs, registry, ledger,   │ budget ledger, rate limiters      │
 │  results                                           ▼                                   │
 │                                              Provider adapters                         │
 │  Telemetry → JSON lines files (≤7 days)      (Protocol interfaces)                     │
 └────────────────────────────────────────────────┬──────────────┬─────────────┬──────────┘
                                                  ▼              ▼             ▼
                                          Search provider   Writer / planner   Verifier / scan
                                          (Tavily)          LLM (OpenAI)       LLM (other family)
```

In deployment, the container entrypoint is a small wrapper (`entrypoint.py`) that runs the startup check, starts the Streamlit process and handles shutdown (§12.2). It is not drawn above because it holds no application logic.

### 3.2 Trust boundaries

| Boundary | Between | Threat | Control |
|---|---|---|---|
| B1 | Browser and gateway | Eavesdropping, unauthorized access | TLS and gateway authentication (§9.1) |
| B2 | Gateway and process | Spoofed origin, abusive clients | Network restriction to the gateway; XSRF protection; proxy rate limits |
| B3 | Process and providers | Secret exposure, data leaving the system | Server-side keys, egress allowlist, content limited to what each call needs (§8) |
| B4 | Retrieved content and models | Prompt injection | Delimited data, strict JSON outputs, no tools, URLs inserted by code (§5.5, §9.3) |
| B5 | Model output and the user | Unsupported claims, hostile markup | Deterministic checks, verifier, typed sentences, escaped rendering (§5, §9.4) |

### 3.3 Component responsibilities

| Component | Module (PRD §8.2 name) | Layer | Responsibility |
|---|---|---|---|
| UI | `app.py`, `ui/*` (including `ui/theme.py` tokens and `ui/copy.py` strings) | Presentation | Layout, widgets, polling fragment, rendering; no business logic |
| Run manager | `run_manager.py` | Application service | Permits, session lock, idempotency, heartbeat watchdog, result TTL, authorization |
| Orchestrator | `research_agent.py` | Application | State machine, deadlines, safe snapshots |
| Capacity | `capacity.py` | Application | Budget ledger, reservations, call-graph startup check, daily spend guard, rate limiters |
| Planner | `pipeline/planner.py` | Domain service | Queries and facets from the topic |
| Source processing | `source_processing.py` | Domain | Canonicalization, dedupe, ranking, diversity, chunking, token trim |
| Claim ledger | `claim_ledger.py` | Domain | Claim and sentence models, placement rules |
| Claim checks | `claim_checks.py` | Domain | Quote match, numeric guard, sentence-type rules |
| Verifier | `passage_verifier.py` | Domain service | Batching, verdict parsing, in-run cache |
| Coverage scan | `coverage_scan.py` | Domain service | Second-layer scan of non-claim sentences |
| Citation validator | `citation_validator.py` | Domain | ID, URL and coverage checks |
| Status rules | `status_rules.py` | Domain | The single place PRD §6.4 is implemented |
| Report generator and export | `report_generator.py`, `export_markdown.py` | Domain | Rendering and escaping |
| Adapters | `adapters/*` | Infrastructure | Search and LLM clients behind Protocols, plus fakes |
| Telemetry | `telemetry.py` | Infrastructure | Typed events, JSON lines, redaction by construction |
| Settings | `settings.py` | Infrastructure | Environment configuration, price sheet, startup checks |

### 3.4 Runtime view of a successful run

```
User        UI script        RunManager          Worker thread             Providers
 │ submit      │                  │                    │                       │
 │────────────►│ validate topic   │                    │                       │
 │             │ (language, len)  │                    │                       │
 │             │─ submit(token) ─►│ idempotency check  │                       │
 │             │                  │ session lock       │                       │
 │             │                  │ permit (non-block) │                       │
 │             │                  │ admit budget       │                       │
 │             │                  │── start ──────────►│ PLANNING ────────────►│ planner call
 │             │◄─ run_id ────────│                    │ SEARCHING (parallel) ►│ search calls
 │             │ poll fragment    │                    │ SCREENING (local)     │
 │◄── stage ───│─ heartbeat ─────►│                    │ DRAFTING ────────────►│ writer call
 │             │                  │                    │ CHECKING (local)      │
 │             │                  │                    │ VERIFYING (parallel) ►│ verifier batches
 │             │                  │                    │ ASSEMBLING, SCANNING ►│ scan call
 │             │                  │                    │ STATUS, RENDER        │
 │             │                  │◄── result ─────────│ release permit        │
 │◄── report ──│◄─ result view ───│                    │                       │
```

---

## 4. Frontend and Backend Structure

### 4.1 Repository layout

PRD §8.2 module names are kept. They are grouped into packages so that the layering rules in §4.3 can be enforced by tooling.

```
ai-research-agent/
  app.py                       # Streamlit entrypoint: layout only
  service.py                   # composition root: settings -> providers, gates, run manager
  demo.py                      # one scripted run, `uv run demo.py`
  .streamlit/config.toml       # secure defaults (§9.5)
  ui/
    state.py                   # session_state keys, session_id, idempotency token
    components.py              # topic form, status fragment, report view, evidence panel, privacy/FAQ tabs
    copy.py                    # every user-facing string (PRD §7.3)
    theme.py                   # design tokens and the only allowed HTML templates (design.md §12)
  core/
    run_manager.py             # facade used by the UI
    research_agent.py          # state machine
    status_rules.py            # PRD §6.4, single implementation
    capacity.py                # budget ledger, reservations, spend guard, rate limiters
    settings.py                # env config, price sheet, startup checks
    telemetry.py               # typed events, JSON lines writer
    errors.py                  # error taxonomy (§6.4)
    models.py                  # Pydantic domain models (§7)
    tokens.py                  # token estimator and shared passage/quote size constants
    validation.py              # topic validation and language policy (FR-01, FR-30)
    text_safety.py             # escape_md and safe_url for third-party text (DR-9)
    drain.py                   # drain marker and active-run count shared with the wrapper (§12.2)
    demo.py                    # demo-mode notice shared by the UI and the report
  pipeline/
    planner.py
    source_processing.py
    claim_ledger.py
    claim_checks.py
    context.py                 # RunContext: budgeted, guarded access to providers
    writer.py
    verifier.py                # token-sized batches, in-run cache (was passage_verifier)
    scan.py                    # coverage scan (was coverage_scan)
    repair.py
    report.py                  # assembly, escaping, Markdown and Evidence appendix
    prompts.py                 # system prompts
  adapters/
    base.py                    # Protocols: SearchProvider, LLMClient
    live.py                    # Tavily search, OpenAI writer, Anthropic verifier (wire formats unverified)
    fakes.py                   # scripted fake providers for tests
  prompts/                     # versioned prompt templates and schema snapshots
  eval/                        # fixtures, benchmark runner, scorecards, KPI report, reference checks
  eval-data/                   # dev and sealed benchmark data (not in the image, git-ignored)
  docs/                        # runbook, accessibility report, reference-study notes
  tests/                       # mirrors the packages; also arch/, browser/, load/, security/
  entrypoint.py                # wrapper: starts Streamlit, traps SIGTERM, drains (§12.2)
  decision-log.md              # approved decisions with approver and date (PRD §19)
  .gitignore                   # excludes .env, logs/, state/, eval-data/
  pyproject.toml               # tool configuration
  .importlinter                # import-linter contracts (§4.3)
  Dockerfile
  requirements.txt             # hashed lockfile
  .env.example
  README.md
  prd.md
  architecture.md
  design.md
  rules.md
  memory.md
  tracker.md
```

### 4.2 Frontend (Streamlit)

**Structure.** A single page with three tabs, **Research**, **About / Privacy** and **FAQ**, so the privacy and FAQ content is always reachable (FR-28, FR-29). All strings come from `ui/copy.py`, so the copy in PRD §7.3 is reviewable in one file.

**Session state keys** (all created lazily by `ui/state.py`; none holds a secret):

| Key | Content |
|---|---|
| `session_id` | `uuid4` created on the first script run. Not Streamlit's internal session identifier, which is not a public API |
| `idem_token` | One token per form render, consumed on submit |
| `run_id` | Opaque ID of the active or last run |
| `evidence_open` | Map of claim ID to toggle state |
| `feedback_given` | Set of run IDs already voted on |
| `topic_draft`, `depth` | Form values kept across reruns |

**Results stay in `RunManager` (ADR-018).** The UI keeps only the `run_id`. On each render it calls `get_result`, which returns a read-only object, and builds the report, evidence panel and download bytes from it. A copy in `session_state` would outlive the 30-minute purge and escape Clear session, which breaks the session-only rule. When `get_result` returns `NOT_FOUND` for a `run_id` the UI still holds, the result has expired or been cleared, and the UI shows a "result expired" notice with the form. **Clear session** calls `RunManager.clear_session` and then deletes every key above except `session_id`.

**Polling.** While a run is active, a fragment decorated with `run_every` polls `RunManager.get_status` once per second, sends a heartbeat, and shows the stage line. When the status becomes terminal the fragment triggers one full rerun to draw the report, and polling stops. The pinned Streamlit version must support this (A-07).

**Evidence Details (ADR-012).** Streamlit's expander opens and closes in the browser and reports nothing to Python, so it cannot drive the `evidence_opened` counter (FR-44). Each claim therefore gets a labeled `st.toggle("Show evidence")`. The first activation calls `record_ui_event(..., "evidence_opened")`, which is idempotent per run. The panel body shows the claim, the quote in `st.text` (plain text, never Markdown), the source title and URL, the passage ID and the evidence mode. A native toggle is keyboard-operable, which meets FR-20 and PRD §7.4.

**Rendering the report.** On screen, the report is built from the structured result (sections and claims) one component at a time, so each claim can carry its own Evidence toggle, which a single Markdown block cannot. Each piece of third-party text goes through the one escaping function (§9.4) and is shown with HTML disabled (`unsafe_allow_html=False`). `export_markdown.render()` produces the escaped Markdown for the download only, using the same escaping function. Download uses `st.download_button`, which also reports the click for the `export_downloaded` counter.

**Progress stages.** `RunView.stage_index` (0 to 5) follows the mapping from internal states to the six user-visible stages in design.md §8.4. The UI never reads internal state names.

**Layout and states.** Screen layouts, components, tokens and the state catalog are specified in design.md. This document owns the contracts they rely on.

**Service state.** On each render the UI calls `RunManager.get_service_state()` (§6.3). It disables a depth whose mode failed its startup check and shows the "Service paused" state when the daily spend stop or a drain is active, before any submit.

**Disabled states.** While a run is active the Research button and Clear session are disabled. The state is a convenience only. The real locks live in `RunManager` (§4.3).

**Accessibility.** Native widgets, explicit labels, status text that is not color-only, and stage updates written to a text region. Whether Streamlit announces them to screen readers is verified, not assumed (PRD §7.4; tests in §13.1).

### 4.3 Backend structure and dependency rules

Layers, from top to bottom: **ui → core.run_manager → core.research_agent → pipeline → adapters**, with `core.models`, `core.errors` and `core.settings` usable by every layer.

Rules, enforced in CI by `import-linter`:

1. `pipeline/*`, `core/*` and `adapters/*` never import `streamlit`.
2. `ui/*` imports only `core.run_manager`, `core.models`, `core.errors` and `ui.*`.
3. `pipeline/*` reaches providers only through the Protocols in `adapters/base.py`.
4. `adapters/*` never import `pipeline/*` or `core/run_manager`.
5. `core.models` performs no I/O.

**`RunManager` responsibilities** (PRD §8.4): bounded `ThreadPoolExecutor(max_workers=5)`, `BoundedSemaphore(5)`, a lock-protected map of run records, a session-to-run map, idempotency tokens, heartbeat watchdog, result purge, and an ownership check on every call.

**Run record** (in memory):

| Field | Purpose |
|---|---|
| `run_id`, `session_id`, `mode` | Identity |
| `state`, `stage`, `stage_started_at` | Progress shown to the UI |
| `deadline` | Monotonic wall-clock limit |
| `cancel_flag` | Set by the watchdog |
| `last_heartbeat` | Updated by UI polls |
| `result` | Final `ResearchResult` |
| `created_at`, `finished_at` | TTL purge |

**Watchdog.** A daemon thread wakes every 5 seconds, sets `cancel_flag` for runs with no heartbeat for the timeout (default 90 s), and purges records per the TTL rules (PRD §8.4 item 7). It also checks for the drain sentinel and writes the active-run count (§12.2). It touches no Streamlit API.

---

## 5. AI Agents, Orchestration, and Workflows

### 5.1 ADR-001: a workflow, not an autonomous agent loop

The system is a fixed, deterministic pipeline that calls models for bounded, schema-checked steps. There is no open-ended "think and act" loop and no model-selected tools. This is what makes the cost cap, time cap and fail-closed behavior provable (AP-1, AP-4). The word "agent" in the product name refers to the overall behavior.

### 5.2 Model roles

| Role | Input | Output (strict schema) | Model | Temperature | Max output tokens (Quick / Deep) | On bad output |
|---|---|---|---|---|---|---|
| Planner | Topic, mode limits | `Plan` | Writer family | 0 | 800 | Schema retry within the 2 retries; then Failed `MODEL_FAILED` |
| Writer | Plan, selected passages (as data) | `LedgerDraft` | Writer family | 0.2 (proposed) | 3,000 / 7,000 | Schema retry within the 2 retries; then Failed `MODEL_FAILED` |
| Verifier | A batch of claims with their quoted passages | `VerifierOutput` | Verifier family (D-11) | 0 | 800 per batch | No retry; unparseable output makes the batch `unsupported` (PRD §13.2) |
| Coverage scanner | Interpretation and transition sentences | `ScanOutput` | Verifier family | 0 | 400 / 800 | Unparseable output removes the scanned sentences (fail closed) |
| Repairer | Up to 6 (Quick) or 12 (Deep) failed claims with reasons, plus only the passages those claims cite, within the repair input cap (§5.3) | `LedgerDraft` (subset) | Writer family | 0.2 (proposed) | 2,000 / 3,000 | One attempt only; failure leaves the removals in place |

### 5.3 State machine

| State | Entered when | Work | Next state or terminal |
|---|---|---|---|
| `SUBMITTED` | `submit()` called | Validate topic and language; idempotency; session lock; semaphore; budget admission | `ADMITTED`, or reject with `INPUT_INVALID`, `LANGUAGE_UNSUPPORTED`, `SESSION_ACTIVE`, `BUSY`, `SERVICE_PAUSED`, `CONFIG_INVALID` |
| `ADMITTED` | Permit and budget acquired | Hand off to a worker thread | `PLANNING` |
| `PLANNING` | Worker starts | Planner call; validate queries and facets (FR-03) | `SEARCHING`; one replan on a short plan (an extra planner call, funded from the pool, §10.4); still short ⇒ `FAILED(PLAN_TOO_NARROW)` |
| `SEARCHING` | Valid plan | Queries in parallel (inner pool, ≤4 workers); retry policy per call | `SCREENING`; all queries failed ⇒ `FAILED(SEARCH_FAILED)`; zero results ⇒ one distinct-query attempt within the cap, then `FAILED(NO_EVIDENCE)` |
| `SCREENING` | Raw results | Canonicalize, dedupe, rank, diversify, chunk, token trim (PRD §6.2) | `DRAFTING`; no usable evidence group ⇒ `FAILED(NO_EVIDENCE)` |
| `DRAFTING` | Registry built | Writer call; schema validation | `CHECKING`; failure after retries ⇒ `FAILED(MODEL_FAILED)` |
| `CHECKING` | Draft ledger | Deterministic checks per claim: IDs, URLs, quote match, numeric guard; placement and sentence-type rules | `VERIFYING` |
| `VERIFYING` | Claims that passed checks | Batched verifier calls (≤4 parallel) | `ASSEMBLING` |
| `ASSEMBLING` | Verdicts in | Remove non-`supported` claims; build sections from surviving claims and typed sentences; compute counts | `SCANNING` |
| `SCANNING` | Assembled report | Scan interpretation and transition sentences; remove flagged ones | `EVALUATING` |
| `EVALUATING` | Scan done | Run `status_rules` on the current state. If not Completed, repair has not been used, repairable rejections exist, and a reservation is admitted ⇒ repair | `REPAIRING`, else `FINALIZING` |
| `REPAIRING` | Repair admitted | One repair call; re-run `CHECKING`, `VERIFYING`, `ASSEMBLING`, `SCANNING` for affected items only | `FINALIZING` (no second repair) |
| `FINALIZING` | Final state chosen | Render report and export, store result, emit telemetry, release permit | `COMPLETED`, `PARTIAL` or `FAILED` |
| `ABANDONED` | `cancel_flag` seen at a stage boundary | Stop new calls; discard result; release permit | Terminal |

**Interrupts.** The deadline and the budget are checked before every state transition and before every external call. If either is exhausted, the run goes straight to `FINALIZING` using the latest **validated snapshot**: the state after the most recent completed `ASSEMBLING` and `SCANNING`. If none exists yet, the result is Failed. Reason codes `TIMEOUT` and `BUDGET_STOP` mark these cases.

**Repair trigger (proposed; the PRD leaves it open).** Repair is attempted only when the first-pass status is not Completed. This avoids spending the repair reservation on a run that already meets every Completed condition, and it keeps typical cost near the §12.5 estimates.

**Repair limits (proposed; they make the §12.5 worst case a bound).** The repairer receives at most 6 failed claims in Quick and 12 in Deep, taken in drafted order, and only the passages those claims cite, trimmed to a repair input cap of 5,000 tokens (Quick) or 8,000 (Deep) by the same trim rule as the writer input. Failed claims beyond the limit stay removed. Re-verification covers only the repaired claims, so it needs at most 2 batches in Quick and 3 in Deep at 4 claims per batch (§10.4).

### 5.4 Status evaluator

`status_rules.evaluate(state, mode) -> (status, reason_codes)` is the only implementation of PRD §6.4. It takes counts computed by deterministic code and returns reason codes for every unmet threshold.

```python
def evaluate(s: RunState, cfg: ModeConfig) -> tuple[Status, list[str]]:
    if s.fatal_error:  # config, plan, search, model
        return FAILED, [s.fatal_error]
    if s.supported_claims < 2:
        return FAILED, ["INSUFFICIENT_CLAIMS"]
    reasons = []
    if s.usable_groups < cfg.min_groups:
        reasons.append("LOW_EVIDENCE_GROUPS")
    if s.domains < cfg.min_domains:
        reasons.append("LOW_DOMAINS")
    if s.supported_claims < cfg.min_claims:
        reasons.append("INSUFFICIENT_CLAIMS")
    if s.supported_facets < cfg.min_facets:
        reasons.append("INCOMPLETE_FACETS")
    if s.snippet_only_share > cfg.max_snippet_share:
        reasons.append("SNIPPET_HEAVY")
    if s.timed_out:
        reasons.append("TIMEOUT")
    if s.budget_stopped:
        reasons.append("BUDGET_STOP")
    return (COMPLETED, []) if not reasons else (PARTIAL, reasons)
```

All counts use distinct `claim_id`s (PRD §6.4 counting rule). Boundary tests cover N−1, N and N+1 for every threshold in both modes.

### 5.5 Prompt architecture and injection defense

- **Templates** live in `prompts/` as versioned files. The prompt version, schema version and model ID are recorded in telemetry for every call.
- **Data is passed as structured blocks**, not concatenated prose: a JSON list of objects `{citation_id, passage_id, title, text}` inside clearly delimited sections. The system prompt states that block contents are untrusted data and any instructions inside them must be ignored.
- **Models never see an output field for URLs.** The writer cites `citation_id` and `passage_id` integers and strings only. URLs and titles are inserted by `export_markdown` from the registry. A model cannot invent a link.
- **Strict outputs.** Every call uses the provider's structured-output or forced-tool mechanism where available (verify at M0), then Pydantic validates with `extra="forbid"`. Any deviation is handled per §5.2.
- **No tools, no browsing, no memory.** Each call is stateless and sees only what the role needs. The verifier never sees other claims or the topic.
- **Fixtures** (PRD §11.2) include passages that try to command the verdict. The gate allows zero false accepts on them.

### 5.6 Schemas

```python
class FacetCategory(str, Enum):
    background = "background"
    drivers_mechanisms = "drivers_mechanisms"
    evidence_trends = "evidence_trends"
    impacts_risks = "impacts_risks"
    perspectives_disputes = "perspectives_disputes"
    current_state = "current_state"
    context_regional = "context_regional"
    other = "other"


class Facet(BaseModel, extra="forbid"):
    facet_id: str
    question: str
    category: FacetCategory


class Plan(BaseModel, extra="forbid"):
    queries: list[str]  # ≥2, ≤ mode cap, non-duplicate
    facets: list[Facet]  # ≥3 Quick / ≥4 Deep, distinct categories


class EvidenceRef(BaseModel, extra="forbid"):
    citation_id: int
    passage_id: str
    quote: str  # 25..300 chars


class DraftClaim(BaseModel, extra="forbid"):
    claim_id: str
    text: str
    facet_id: str
    section: Literal["summary", "findings", "data", "competing", "conclusion"]
    evidence: list[EvidenceRef]  # 1..3 Quick, 1..4 Deep


class DraftSentence(BaseModel, extra="forbid"):
    type: Literal["claim", "interpretation", "transition"]
    claim_id: str | None = None  # required for type=claim
    text: str | None = None  # interpretation / transition only
    refs: list[str] = []  # interpretation: supported claim_ids it builds on


class DraftSection(BaseModel, extra="forbid"):
    section: Literal["summary", "findings", "data", "competing", "conclusion"]
    sentences: list[DraftSentence]


class LedgerDraft(BaseModel, extra="forbid"):
    claims: list[DraftClaim]
    sections: list[DraftSection]


class VerifierItem(BaseModel, extra="forbid"):
    claim_id: str
    verdict: Literal["supported", "uncertain", "unsupported"]
    reason: str  # ≤200 chars


class VerifierOutput(BaseModel, extra="forbid"):
    results: list[VerifierItem]  # must match the batch's claim IDs exactly


class ScanItem(BaseModel, extra="forbid"):
    sentence_ref: str
    contains_material_fact: bool
    reason: str


class ScanOutput(BaseModel, extra="forbid"):
    results: list[ScanItem]
```

Deterministic validators added on top of the schemas: every `claim_id` appears in exactly one claim sentence, in the section matching its `section` field; summary and conclusion claim limits per mode; no `claim` sentence carries its own text; `meta` text never comes from a model.

### 5.7 Deterministic checks (PRD §8.3 steps 2 and 5)

- **Quote match:** `normalize_for_match` (NFKC, whitespace collapse, quote and dash unification, case-insensitive), quote length 25–300, quote lies entirely inside one stored passage.
- **Numeric guard:** every number, percentage, currency amount, range and date in the claim text must appear in the concatenated quotes after number-format normalization. Claims containing derived figures are rejected.
- **Sentence rules:** interpretation sentences start with "Interpretation:", cite supported claims, stay within 40 words, and introduce no digit-bearing or capitalized token absent from the cited claims, the topic or the headings. Transitions stay within 15 words with no digits, URLs or foreign capitalized words.

All of these are pure functions with property-based tests (§13.1).

### 5.8 Concurrency inside a run

Search queries use an inner pool of up to 4 workers. Verifier batches use up to 4. Every outbound call passes through the per-provider rate limiter (§10.3), so the combined load of 5 runs cannot exceed the provider limits. Worst-case thread count is about 5 × (1 + 4) = 25 plus UI and watchdog threads.

---

## 6. API Endpoints and Contracts

### 6.1 ADR-002: no public HTTP API in the pilot

The pilot exposes no REST API. The browser talks to Streamlit over its own HTTP and WebSocket protocol, and the UI calls the pipeline in-process through `RunManager`. Exposing an API would add authentication, versioning and abuse surface that the PRD does not require. §6.6 sketches the public API for later.

### 6.2 Network-visible surface

| Route | Provided by | Purpose | Notes |
|---|---|---|---|
| `/` | Streamlit | The app | Behind the access gateway |
| WebSocket stream (`/_stcore/stream`) | Streamlit | UI session transport | The gateway must pass WebSocket upgrades and keep idle timeouts above 360 s plus margin |
| `/_stcore/health` | Streamlit | Liveness probe | Verify the path for the pinned version. It does not prove the app is configured (see §12.2 startup check) |

### 6.3 Internal service contract: `RunManager`

```python
class RunManager:
    def submit(self, session_id: str, request: ResearchRequest) -> SubmitOutcome: ...
    def get_status(self, session_id: str, run_id: str) -> RunView: ...
    def get_result(self, session_id: str, run_id: str) -> ResearchResult | None: ...
    def heartbeat(self, session_id: str, run_id: str) -> None: ...
    def record_ui_event(
        self, session_id: str, run_id: str, event: Literal["evidence_opened", "export_downloaded"]
    ) -> None: ...
    def record_feedback(
        self, session_id: str, run_id: str, vote: Literal["useful", "not_useful"]
    ) -> FeedbackOutcome: ...
    def clear_session(self, session_id: str) -> ClearOutcome: ...
    def get_service_state(self) -> ServiceState: ...
```

| Type | Fields |
|---|---|
| `ResearchRequest` | `topic: str` (trimmed, 1–500), `depth: Literal["quick","deep"]`, `idempotency_token: str` |
| `SubmitOutcome` | `accepted: bool`, `run_id: str \| None`, `error_code: ErrorCode \| None`, `duplicate: bool` |
| `RunView` | `run_id`, `state`, `stage`, `stage_index`, `elapsed_ms`, `warnings: list[str]` |
| `ResearchResult` | As PRD §9.4, plus `report_markdown`, `claims` and `sources` for the evidence panel |
| `FeedbackOutcome`, `ClearOutcome` | `ok: bool`, `error_code` |
| `ServiceState` | `modes: dict[mode, bool]` (False when a mode failed its startup check), `paused: bool` (daily spend stop or draining). The UI reads it on each render to disable an unavailable depth and to show the "Service paused" state before a submit |

**Authorization.** Every method checks that `run_id` belongs to `session_id`. A mismatch returns `NOT_FOUND`, the same as an unknown ID, so run IDs cannot be probed. Run IDs are random, at least 128 bits. `clear_session` fails with `SESSION_ACTIVE` while a run is active.

### 6.4 Error taxonomy

| `ErrorCode` | Meaning | Terminal for run? | User-facing category (PRD §7.3) |
|---|---|---|---|
| `INPUT_INVALID` | Empty or over-long topic | Rejected before run | Invalid input |
| `LANGUAGE_UNSUPPORTED` | Script heuristic rejected the topic | Rejected | Invalid or unsupported language |
| `BUSY` | No permit free | Rejected | Busy |
| `SESSION_ACTIVE` | A run is already active in this session | Rejected | Running |
| `CONFIG_INVALID` | Missing key, unpriced model, failed call-graph check | Rejected or Failed | Provider failure (setup guidance, no secrets) |
| `PLAN_TOO_NARROW` | Plan still short after one replan | Failed | Failed |
| `NO_EVIDENCE` | No usable evidence group | Failed | Failed / no evidence |
| `SEARCH_FAILED` | All search calls failed after retries. Search runs before any evidence is validated, so this is always Failed | Failed | Provider failure |
| `MODEL_FAILED` | Planner or writer failed after retries | Failed | Provider failure |
| `VERIFIER_FAILED` | Verifier unavailable | Partial or Failed per §5.3 | Semantic mismatch or provider failure |
| `INTEGRITY_FAILED` | Final integrity check could not be made clean | Failed | Semantic mismatch |
| `BUDGET_STOP` | Reservation refused mid-run | Partial or Failed | Budget or timeout |
| `TIMEOUT` | Deadline reached | Partial or Failed | Budget or timeout |
| `SERVICE_PAUSED` | Daily spend stop reached, or the process is draining before shutdown | Rejected | Service paused |
| `ABANDONED` | Watchdog stopped the run | Terminal, no result | None (user is gone) |
| `NOT_FOUND` | Unknown, foreign or expired run ID | Not a run state | For a run ID the UI still holds: the "result expired" notice (§4.2). Otherwise none |

There is no `RUN_LOST` code. After a process restart or a browser reload, Streamlit starts a new session with empty state, so the UI holds no run ID and cannot tell a lost run from an idle form. Both cases show the idle form with the standing reload notice (PRD §7.3). PRD v1.7 removed the separate "Run lost" state.

### 6.5 Provider adapter contracts

```python
class SearchProvider(Protocol):
    def search(
        self, query: str, *, max_results: int, want_extracted: bool, timeout_s: float
    ) -> SearchResponse: ...


class RawResult(BaseModel):
    provider_result_id: str | None
    title: str
    url: str
    snippet: str
    extracted_text: str | None
    score: float | None
    published_at: str | None


class SearchResponse(BaseModel):
    results: list[RawResult]
    billed_units: float | None
    request_meta: dict


class LLMClient(Protocol):
    def generate(
        self,
        *,
        system: str,
        blocks: list[Block],
        schema: type[T],
        max_output_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> LLMResult[T]: ...


class LLMResult(BaseModel, Generic[T]):
    parsed: T
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str
```

Adapters raise only these exceptions: `ProviderAuthError`, `ProviderRateLimit(retry_after_s)`, `ProviderTimeout`, `ProviderServerError`, `ProviderBadRequest`, `SchemaViolation`, `ContentRefused`. The retry layer (§10.2) depends only on these types, never on a vendor's exception classes.

**Provider wire contracts (indicative, verify at M0).** The search adapter issues one authenticated POST per query with the query, the result limit and an extraction option, and reads back a list of results carrying title, URL, snippet text, an optional relevance score, an optional extracted text and an optional publication date. LLM adapters call each vendor's chat or messages endpoint with a system prompt, structured input blocks and a JSON schema for structured output (or a forced tool call), and read back the parsed object plus token usage. Field names and options are confirmed against current documentation at M0 and recorded in contract fixtures.

### 6.6 Future public API (non-binding sketch for PL-02)

If the public launch needs an HTTP API, the proposed shape is:

| Method and path | Purpose | Responses |
|---|---|---|
| `POST /v1/runs` | Start a run; body is `ResearchRequest`; `Idempotency-Key` header | `202` with `Location`; `400` invalid; `409` active run; `429` quota with `Retry-After`; `503` busy |
| `GET /v1/runs/{id}` | Status | `200` `RunView`; `404` |
| `GET /v1/runs/{id}/report?format=md` | Report and evidence appendix | `200`; `404`; `409` not ready |
| `POST /v1/runs/{id}/feedback` | Vote | `204`; `404`; `409` already voted |
| `DELETE /v1/runs/{id}` | Delete stored result | `204`; `404` |

Authentication would be OIDC bearer tokens; errors would use `application/problem+json` with the `ErrorCode` as the `type`. This replaces the reconnect-token idea in FR-38.

---

## 7. Database Schema and Data Models

### 7.1 ADR-003: no database in the pilot

D-03 forbids persistent topics, passages and reports, and no pilot requirement needs a database. All run data lives in process memory with a TTL. The only data written to disk is redacted telemetry (§11) and one small daily-spend counter file (§10.4). A relational schema is sketched in §7.5 for the opt-in history and the public launch, and is not built.

### 7.2 Logical data model

```
 ResearchRequest ──1:1── Run ──1:1── ResearchResult
                          │
                          ├──1:1── Plan ──1:N── Facet
                          ├──1:N── SourceRecord ──1:N── Passage
                          ├──1:N── ClaimRecord ──N:M── Passage   (via EvidenceRef: citation_id, passage_id, quote)
                          ├──1:N── SentenceRecord                  (typed report sentences)
                          ├──1:1── BudgetLedger ──1:N── Reservation
                          └──0:N── TelemetryEvent  (written to disk, content-free)
 FeedbackEvent: (run_id, vote, timestamp)  — written to disk, content-free
```

### 7.3 In-memory models

PRD §9 defines `ResearchRequest`, `SourceRecord`, `ClaimRecord` and `ResearchResult`. This document adds the following.

| Model | Fields | Notes |
|---|---|---|
| `Run` | `run_id`, `session_id`, `mode`, `state`, `stage`, `deadline`, `cancel_flag`, `last_heartbeat`, `result`, `created_at`, `finished_at` | The run record in §4.3 |
| `Plan` and `Facet` | As §5.6 | Kept for the facet coverage list |
| `Passage` | `passage_id`, `text`, `truncated`, `char_len`, `est_tokens`, `lexical_score` | Immutable; text is provider-verbatim |
| `SentenceRecord` | `section`, `index`, `type`, `claim_id`, `text`, `refs`, `dropped_reason` | Records why a sentence was removed |
| `BudgetLedger` | `mode`, `cap_usd`, `safety_factor`, `base: dict[stage, float]`, `pool_remaining`, `reservations`, `committed_usd`, `unknown_cost: bool` | Thread-safe; see §10.4 |
| `Reservation` | `id`, `stage`, `attempt`, `amount_usd`, `source: Literal["base","pool"]`, `state` | Released or committed after each call |
| `RunState` | Counts used by `status_rules` | Computed only by code |

**Lifecycle.** Run, registry, ledger and result are purged on Clear session, 10 minutes after heartbeat loss, or 30 minutes after completion, whichever is first (PRD §8.4 item 7). The size of one run is small: the largest case, Deep with 160 passages of up to 800 characters, is about 130 KB of passage text plus claims and sentences, well under 1 MB. Five active runs plus 30 minutes of finished results fit comfortably in memory. The UI keeps no copy of a result (§4.2), so the purge removes the last copy.

### 7.4 Files on disk (pilot)

| File | Content | Retention | Schema |
|---|---|---|---|
| `logs/events-YYYYMMDD.jsonl` | Typed `LogEvent` records (§11.2) | ≤7 days, rotated and deleted | Pydantic `LogEvent`, `extra="forbid"` |
| `state/spend-YYYYMMDD.json` | `{date, total_committed_usd, unknown_cost_runs}` written atomically | ≤7 days | Fixed |
| `eval-data/**` (outside the app image) | Benchmark topics, eligibility inventories, essential questions, fixtures, reviewer labels | Project life, access-controlled | JSON or JSONL with versioned schemas in `eval/schemas/` |

Evaluation files contain curated benchmark topics and passages, not user data. The spend counter prevents a restart from resetting the daily stop (§10.4) and holds no content, so it is operational metadata under D-08. §14 proposes stating this explicitly in D-03.

### 7.5 Future persistent schema (not part of the pilot)

For the opt-in history (FR-21) or the public launch. It needs a privacy review and a retention job first. PostgreSQL syntax:

```sql
CREATE TABLE users (
  user_id uuid PRIMARY KEY, external_subject text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz);

CREATE TABLE runs (
  run_id uuid PRIMARY KEY, user_id uuid REFERENCES users ON DELETE CASCADE,
  mode text NOT NULL CHECK (mode IN ('quick','deep')),
  status text NOT NULL CHECK (status IN ('completed','partial','failed')),
  reason_codes text[] NOT NULL DEFAULT '{}',
  topic_ciphertext bytea,                 -- stored only with opt-in; encrypted
  report_markdown_ciphertext bytea,
  created_at timestamptz NOT NULL, finished_at timestamptz,
  estimated_cost_usd numeric(10,4), modeled_ceiling_usd numeric(10,4),
  expires_at timestamptz NOT NULL);       -- retention schedule

CREATE TABLE sources (
  run_id uuid REFERENCES runs ON DELETE CASCADE, citation_id int,
  canonical_url text NOT NULL, registrable_domain text NOT NULL,
  title text, published_at timestamptz, retrieved_at timestamptz NOT NULL,
  evidence_mode text NOT NULL CHECK (evidence_mode IN ('snippet','extracted','metadata-only')),
  PRIMARY KEY (run_id, citation_id));

CREATE TABLE claims (                  -- only displayed, supported claims are stored
  run_id uuid REFERENCES runs ON DELETE CASCADE, claim_id text,
  facet_id text, section text NOT NULL, text text NOT NULL,
  PRIMARY KEY (run_id, claim_id));

CREATE TABLE claim_evidence (          -- 1..4 quotes per claim (one row per EvidenceRef)
  run_id uuid, claim_id text, ordinal smallint,
  citation_id int NOT NULL, passage_id text NOT NULL, quote text NOT NULL,
  PRIMARY KEY (run_id, claim_id, ordinal),
  FOREIGN KEY (run_id, claim_id) REFERENCES claims (run_id, claim_id) ON DELETE CASCADE,
  FOREIGN KEY (run_id, citation_id) REFERENCES sources (run_id, citation_id) ON DELETE CASCADE);

CREATE TABLE feedback (
  run_id uuid REFERENCES runs ON DELETE CASCADE,
  vote text NOT NULL CHECK (vote IN ('useful','not_useful')),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (run_id));

CREATE TABLE usage_ledger (            -- per-user quotas and spend (PL-02, PL-03)
  user_id uuid REFERENCES users, day date, runs int NOT NULL DEFAULT 0,
  committed_usd numeric(10,4) NOT NULL DEFAULT 0, PRIMARY KEY (user_id, day));
```

Row-level deletion (`ON DELETE CASCADE`), encrypted content columns and an `expires_at` sweep implement the deletion controls the PRD requires for any retained history.

---

## 8. Third-Party Integrations and AI Providers

### 8.1 Provider matrix

| Provider | Role | Data sent | Auth | Timeout (proposed) | Retry | Limits handling | Fallback |
|---|---|---|---|---|---|---|---|
| Tavily (search) | Retrieval of URLs, snippets, extracted text | Search queries only (derived from the topic) | API key in `SEARCH_API_KEY` | connect 5 s, read 20 s | ≤2 on 429, 5xx, timeout | Client-side token bucket; honor `Retry-After` within budget | Adapter swap; none at runtime |
| NVIDIA Build (alternative for both model roles; development default) | Same roles as the writer and verifier rows | Same data as those rows | `NVIDIA_API_KEY` | per role, as below | ≤2 on 429, 5xx, timeout; schema retry on malformed JSON | One shared limiter for both roles (`NVIDIA_MAX_RPM`); honors `Retry-After` | Switch to the OpenAI and Anthropic rows |
| OpenAI (writer, planner, repairer) | Plan, ledger draft, repair | Topic, selected passages (verbatim excerpts), schemas | `OPENAI_API_KEY` | read 60 s Quick / 90 s Deep for the writer; 20 s planner | ≤2 on 429, 5xx, timeout, schema violation | Token bucket; honor `Retry-After` within budget | None at runtime |
| Verifier provider (different family, D-11) | Verification and coverage scan | Claim text, quotes and their passages; scan sentences | `VERIFIER_API_KEY` | read 30 s | ≤2 on 429, 5xx, timeout; **no retry** on malformed output | Token bucket | Same family with disclosure, only if D-11 allows |

Per-call timeouts are the smaller of the value above and the time left before the run deadline.

### 8.2 Data minimization

Each provider receives only what its role needs. The search provider never sees passages or claims. The verifier never sees the topic. No provider receives secrets, session IDs or user identifiers. The privacy page (FR-28) lists exactly this.

### 8.3 Provider terms and settings

For each provider, record at M0 (PRD §12.4): retention of inputs, whether inputs are used for training, regional processing, subprocessors, and permitted use of returned content. Enable the available no-training and minimum-retention settings. A second vendor for the verifier adds a key, a terms review and one more failure mode.

### 8.4 Model and price governance

- Model IDs are pinned in configuration and recorded per call.
- The price sheet (`PRICE_SHEET_VERSION`) holds per-million-token prices and the search per-call price. A model without a price makes its mode refuse to start (`CONFIG_INVALID`).
- Any change of provider, model, extraction depth or price sheet triggers re-baselining (PRD §19): fixture scorecard, call-graph check, and a dev-set run.

### 8.5 Provider drift

A nightly canary run uses fakes for most paths and a very small live check (one search and one model call per provider, with a tiny spend cap) to detect API changes. Contract fixtures are re-recorded deliberately, never automatically.

---


### 8.6 NVIDIA Build and OpenAI-compatible providers (approved 2026-10-22)

**Configuration.** `WRITER_PROVIDER` is `openai` or `nvidia`; `VERIFIER_PROVIDER` is `anthropic`, `nvidia`, `openai` (any OpenAI-compatible server) or `ollama` (a local server, §8.7). `OPENAI_BASE_URL` and `VERIFIER_BASE_URL` set the endpoints (NVIDIA's default is `https://integrate.api.nvidia.com/v1`); `https` is required except for localhost, so a key can never travel in clear text. An NVIDIA key is sent only to `nvidia.com` or a local server and an OpenAI-style key is never sent to `nvidia.com`; a base URL that breaks this is refused at startup, which catches a URL left over from copying the other configuration. `NVIDIA_API_KEY` is read once into a `SecretStr`. The development default is `nvidia/nemotron-3-ultra-550b-a55b` (planner, writer, repair) with a local Ollama model as verifier and scan (§8.7). The hosted NVIDIA verifiers measured on 2026-10-22 (`openai/gpt-oss-20b`, `google/gemma-4-31b-it`) remain configurable alternatives, with the findings below. Startup refuses the pair if `model_family` returns the same value for both. The family comes from the model's own name (`llama-3.1-nemotron-70b-instruct` is Llama), never from a vendor, hosting or platform prefix or a tag, so `nvidia/llama-3.1-nemotron-70b-instruct` with `meta/llama-3.1-70b-instruct` is refused and a different hosting platform does not make two models independent.

**What NVIDIA's documentation says (read 2026-10-22; not yet confirmed by a live call).**

| Topic | Finding | What the code does |
|---|---|---|
| Endpoint and auth | Chat completions at `https://integrate.api.nvidia.com/v1`, `Authorization: Bearer <key>` | Same call as the OpenAI adapter with a base URL |
| Structured output | Gemma 4 31B model card: "Structured Output: Not supported". Nemotron: `response_format` json_object appears on the self-hosted NIM page; the hosted pages show no structured-output parameter | `json_mode` defaults to `none`: the schema is in the system prompt and the reply is parsed and validated strictly (extra keys, wrong enums and truncation all fail). `json_object` is an opt-in setting |
| Output-length parameter | Nemotron shows `max_tokens`; a Gemma snippet shows `max_completion_tokens` | `WRITER_TOKEN_PARAM` and `VERIFIER_TOKEN_PARAM`, defaulting to `max_tokens` |
| Reasoning | Nemotron: `chat_template_kwargs {"enable_thinking": bool}`. Gemma: thinking is a prompt token and disabling it can still emit an empty thought block | The writer sends `enable_thinking` (off unless `WRITER_THINKING=on`); reasoning blocks (`<think>`, `<|channel>thought...<channel|>`) are removed before the JSON is located; an unfinished block means no answer and fails closed |
| Rate limits and terms | No rate limit or quota stated; governed by the NVIDIA API Trial Terms of Service; NVIDIA's blog describes the hosted API as for prototyping and says production use is self-hosted NIM under an enterprise license | Writer and verifier share one request limit (`NVIDIA_MAX_RPM`, default 40, a guess) but keep separate circuit breakers; waits respect the run deadline and never hold the limiter's lock; `.env.example` sets `MAX_CONCURRENT_RUNS=2` because a worst-case run makes about 12 model calls; the UI and About page say the terms can change; treated as a development setting only |
| Usage fields | Standard `prompt_tokens` and `completion_tokens` expected | A missing usage field charges the full reservation (`unknown_cost`) |

**Live findings (probe and diagnostics run by the project user's request, 2026-10-22; tiny free-tier requests, no search).**

| Observation | Consequence |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b`: valid JSON in 2.5 to 3.2 s with `max_tokens`, no `response_format` and `enable_thinking` false; verdicts correct; usage reported | The writer configuration works as built |
| `google/gemma-4-31b-it` is listed on the key but every request timed out at 60 s (4 of 4, including a 16-token reply) | Not usable as the verifier today; the endpoint may recover, so it stays in the sheet |
| Several other listed models (`google/gemma-3-12b-it`, `mistralai/mistral-large`) return 404 | A listed model is not necessarily served |
| `openai/gpt-oss-20b`: about 8 tokens per second (112 completion tokens in 13.7 s); reasoning arrives in `reasoning_content`, the answer in `content`; roughly one request in three stalled past 60 s; reasoning-effort controls (a system-prompt `Reasoning: low`, `chat_template_kwargs`) made no material difference | Was the development verifier for part of 2026-10-22 and is now an alternative (§8.7 replaced it with a local model). Per-call timeouts can be scaled (`WRITER_TIMEOUT_FACTOR`, `VERIFIER_TIMEOUT_FACTOR`; `.env.example` doubles the verifier's to 60 s) but a stall still burns an attempt, so a Quick run (120 s) can end `VERIFIER_FAILED` or `TIMEOUT`; Deep (360 s) has more room |

**Replays with the real models (three runs of the scripted demo corpus through the pipeline, 2026-10-22; no search).** The writer drafted 2,240 to 2,355 claims-tokens in 25 to 52 s and one planner call timed out at 30 s. Verifier batches of about 160 to 240 output tokens took 8 to 21 s when they worked, but 2 of 4 (parallel), 3 of 4 (parallel) and 3 of 6 (one at a time) stalled until their 37 to 47 s timeout. Running batches one at a time did not help, so the stalls are not caused by concurrency; they are the free endpoint's behavior that day. Every run failed closed (`VERIFIER_FAILED` or `TIMEOUT`) and no unverified claim was published. A shared circuit breaker that opens after 5 consecutive failures turned third attempts into instant failures under these stalls.

**Budget controls on a free service.** `core/price_sheet_nvidia_free.json` is marked `free_prototype` and carries the PRD §10.3 rates as budgeting rates, not charges, so the per-mode caps, the startup call-graph check and the daily spend guard bind exactly as on a paid service and would still protect the operator if the free tier ended. It has a `review_after` date; live mode refuses an expired sheet until someone re-checks NVIDIA's terms and updates the file. A free-prototype sheet without a review date, or with zero rates (which would void every cap), is refused too, and a malformed sheet is a named startup problem. The date is checked again when each run is admitted, so a server started before the date stops admitting runs after it. When live mode refuses to start, the Research tab lists the setting names (never values). Estimated costs shown for this configuration are notional.

**Verification of these claims.** `uv run python -m eval.provider_probe --yes-call-live-providers` sends four tiny requests (two per model) and reports whether each model returns schema-valid JSON, reports usage, accepts a supported claim and rejects a contradicted one. It must be run by the owner of the key. It does not replace the PRD §11.2 verifier fixture gate.


### 8.7 Local Ollama verifier (approved 2026-10-22)

**Configuration.** `VERIFIER_PROVIDER=ollama`, `VERIFIER_MODEL=qwen3-vl:8b-instruct`, `VERIFIER_BASE_URL=http://localhost:11434/v1` (empty means this default; the `ollama` provider must be on this computer, a remote server uses provider `openai`), `VERIFIER_JSON_MODE=json_schema`, `VERIFIER_PARALLEL=1`, `VERIFIER_CONTEXT_TOKENS` equal to the server's `OLLAMA_CONTEXT_LENGTH` (4096 by default). The planner and writer stay on NVIDIA Build with `NVIDIA_API_KEY`; the Ollama client is built with the placeholder key `ollama`, never a real credential (a test asserts it). No `VERIFIER_API_KEY` is needed. If Ollama is down or slow the run ends `VERIFIER_FAILED` or `TIMEOUT`; the writer's endpoint is never asked to verify (a test asserts the writer's endpoint sees only planner and writer requests).

**Measured behavior of Ollama 0.40.6 (2026-10-22, local requests, no cost).**

| Question | Result |
|---|---|
| Does `/v1` enforce a JSON schema? | Yes: `response_format` `json_schema` returned schema-valid output; `json_object` and a plain request returned valid JSON of the wrong shape. The adapter uses `json_schema` and still validates every reply with Pydantic |
| Can the context window be set per request on `/v1`? | No: `options.num_ctx` and a top-level `num_ctx` were ignored. The server's `OLLAMA_CONTEXT_LENGTH` (default 4,096) decides |
| What happens to a prompt longer than the context? | It is cut silently (about 6,500 tokens sent, 2,050 processed). The adapter (a) refuses before the request a prompt that cannot fit `VERIFIER_CONTEXT_TOKENS` together with the output allowance, (b) raises `ContextTruncated` (never retried) if the reported prompt tokens are under 60 percent of its estimate, if prompt plus answer reach the window, or if no token count is reported for a prompt of 500 tokens or more |
| Does the PRD's Quick verifier batch fit? | Not at 4,096: a batch can reach 7,000 tokens. Set `OLLAMA_CONTEXT_LENGTH=8192` on the server; this uses more RAM and runs slower |

**Evaluation (development laptop: Core i7-12650H, 15.7 GB RAM, RTX 3050 Laptop 4 GB; reports in `eval/reports/`).** The measurements used the 45 pairs of `eval/fixtures/verifier_scripted_v1.jsonl`; `verifier_scripted.jsonl` now holds 53 (eight paraphrase pairs and a better injection pair were added after the review and have not been run on any model). The pairs are hand-written and synthetic: plain, overreach, contradiction, numeric, date and prompt-injection cases, including numeric and date negatives in which every figure appears in the quote and so passes the deterministic guard. `uv run python -m eval.verifier_eval --model <tag>` runs them through the production batching path (add `--stress` for production-sized prompts).

| Measurement (45 scripted pairs, version 1, synthetic) | qwen3-vl:8b-instruct | qwen3-vl:4b-instruct |
|---|---|---|
| Accuracy | 95.6 percent (43 of 45) | 80.0 percent (36 of 45) |
| False accepts, all 26 unsupported pairs | 2 (7.7 percent: N08, O02) | 9 (34.6 percent) |
| False accepts that reach the verifier in production (21 pairs the numeric guard does not already stop) | 1 (O02, a causal claim the passage does not state) | 5 |
| Prompt-injection pairs (6 unsupported) | 0 accepted; only 2 reach the verifier (I03, I06), the guard stops the other 4 | 5 accepted, 2 of them pairs that reach the verifier |
| False rejects, 19 supported pairs | 0 (all are near copies of the quote; the paraphrase pairs added later have not been run) | 0 |
| Time per full 4-claim batch, about 700-token prompts | mean 39.9 s (26.7 to 62.0 s, 11 batches) | mean 18.9 s (11.6 to 31.9 s) |
| Production-size batches (about 3,800 tokens, 8 plain pairs only) | about 67 to 69 s per call; 1 of 3 calls returned invalid JSON after 80 s; prompt plus answer used 4,085 of the 4,096-token window | not run |
| Loaded size and split (`ollama ps`) | 6.3 GB, 76 percent CPU and 24 percent GPU, context 4,096 | 4.0 GB, 53 percent CPU and 47 percent GPU |
| System RAM in use (15.7 GB machine; the baseline was not idle) | 13.5 GB before the run, 15.5 GB at peak | 14.9 GB |
| Verifier stage alone for Quick (4 batches, one at a time) | about 160 s (about 270 s at production size) against a 120 s limit | about 76 s |
| Verifier stage alone for Deep (9 batches) | about 360 s (about 600 s at production size) against a 360 s limit | not computed |
| Indicative PRD §2.6 check on rates (at most 3.3 percent false accepts, none on injection, at most 20 percent false rejects) | **fails** on false accepts (7.7 percent) | fails |

**Reading the numbers.** The 8B model is not shown to meet the screening thresholds of PRD §2.6. Its false-accept rate on this set (2 of 26, 7.7 percent) is above the gate's 2 in 60 (3.3 percent); one of the two (a derived claim) is stopped by the numeric guard before the verifier in production, the other (a causal claim the passage does not state) is a genuine weakness; and the set is far smaller than the sealed one, so it can neither certify nor clear the model. The injection result rests on two pairs: four of the six injection negatives are rejected by the numeric guard before the verifier would see them. The 8B model resisted the two that reach it and the 4B model accepted both. The 4B model fails outright and must not be the verifier. Supported pairs in this version are close copies of their quotes, so 0 false rejects says little about paraphrase; eight paraphrase pairs and a better injection pair were added after the review and have not been run on any model. The binding problem for the 8B model is time: the verifier stage alone is about 160 s against Quick's 120 s and about 360 s against Deep's 360 s, and a full replay on the demo corpus under the Quick limit ended `TIMEOUT` with one verifier batch finished (planner 4 s, Nemotron writer 68 s, first batch 40 s). The time limits were not relaxed.

**What is not measured.** Behavior at a context of 8,192 (memory, speed, schema failures) was never run; the production-size run covered 8 plain pairs on the default 4,096 window, where prompt plus answer filled the window to within 11 tokens and one of three calls returned invalid JSON (consistent with, but not proof of, the server shifting its context; the adapter now refuses such a call). Memory was measured from a non-idle baseline (another model had just run), so a clean per-model footprint is unknown; `--cold-start` exists to measure it, and the re-run that would have used it was stopped by the system for low memory and was not repeated.

**Options (untested where marked).** A GPU with 12 GB or more of memory running an 8B text model entirely on the GPU is the change that fixes the time (unmeasured, expected several times faster). On the present machine: a smaller text model that fits the 4 GB GPU (`qwen3:4b-instruct-2507`, `phi4-mini`, `gemma3:4b`) would be faster but the 4B Qwen3-VL result suggests the 4B class needs the same injection test before any trust; `qwen3:8b` (text only) is the quality candidate with the same speed limits as the 8B vision model. None of these was downloaded; each can be run through the same command once pulled. Relaxing the time limits with `RUN_TIME_FACTOR` (about 4 for Quick, 3 for Deep) is possible but is a PRD change for the owner to approve.

## 9. Authentication, Authorization, and Security

### 9.1 Authentication (ADR-009)

The pilot has no in-app accounts. Access control is delegated to the host: a network restriction (VPN or internal network) or a gateway that authenticates users (SSO, an OIDC proxy or basic auth) and forwards only authenticated traffic to the Streamlit process. The process must not be reachable except through the gateway. Hosting without this control is not allowed (D-04, A-11).

### 9.2 Authorization

- **Session ownership.** A run belongs to the session that created it. Every `RunManager` method checks ownership and returns `NOT_FOUND` on any mismatch (§6.3).
- **Unguessable IDs.** Run and session IDs are random, at least 128 bits.
- **No cross-session reads.** There is no admin view of other users' runs. Operators see only content-free telemetry.
- **Roles.** None in the pilot. Roles and per-user quotas arrive with the public launch (§12.4).

### 9.3 Threat model

| Threat | Vector | Controls | Verified by |
|---|---|---|---|
| Prompt injection from web content | Hostile snippet or extracted text | Data blocks, strict JSON outputs, no tools, no URL fields, verifier sees only claim and passages, fixtures with command-the-verdict passages | PRD tests 6, 25; verifier and scan fixtures |
| Fabricated citation | Model invents ID or URL | IDs checked against the registry; URLs inserted by code | PRD test 5 |
| Unsupported claim passes | Wrong number, scope, polarity | Quote match, numeric guard, independent verifier, human sampling | PRD tests 6–9; grounding gate |
| Secret leakage | Logs, errors, prompts, browser | Keys loaded once into `SecretStr`, never in session state; typed telemetry; generic user errors; secret scanner in CI | PRD test 16; secret-scan tests |
| SSRF or data exfiltration | App fetching model-chosen URLs | No fetch capability; egress allowlist limited to the three provider domains | Network policy check |
| Cost abuse | Floods of runs | Per-session lock, ≤5 runs, daily spend stop, gateway rate limits | PRD tests 17, 20 |
| XSS or Markdown injection | Hostile text in claims, quotes, titles | Escaped rendering and export; HTML disabled; links only from the registry | PRD tests 28, 35 |
| Cross-session data access | Guessing run IDs | Random IDs; ownership check; `NOT_FOUND` for all mismatches | Unit tests on `RunManager` |
| Resource exhaustion | Huge inputs, slow providers | Topic length cap, token caps, per-call timeouts, run deadline | PRD tests 1, 2, 16 |
| Supply-chain compromise | Malicious dependency | Hashed lockfile, `pip-audit`, minimal dependencies, container scan | CI |

### 9.4 Output safety

All third-party text (claim text, quotes, titles) passes through one escaping function before display or export. It neutralizes HTML, link and image syntax, code fences and Markdown control characters. Titles used as link labels have brackets escaped. Only registry URLs become links. The same function backs the panel, the report body and the export, so there is one place to test and fix.

### 9.5 Streamlit and container hardening

- `.streamlit/config.toml`: XSRF protection on, usage statistics off, headless mode, minimal toolbar. Verify each option against the pinned version.
- Container: non-root user, read-only root filesystem except the log and state directories, no inbound ports except the app port, outbound traffic limited to the provider allowlist.
- Gateway: TLS, WebSocket pass-through, request size limit, rate limit, security headers where Streamlit allows them (a strict content security policy may not be possible with Streamlit's inline scripts; record the limitation).
- Secrets: injected as environment variables or from the host's secret store. Never in the image, the repository, `session_state`, or logs.

### 9.6 Public-launch security (design level)

OIDC authentication, per-user quotas and a shared rate limiter backed by Redis, abuse challenges, an emergency kill switch, encrypted storage for any retained history, and the full PL-05 review. These come with the stateless-web, queue and worker architecture in §12.4.

---

## 10. Error Handling, Retries, and Rate Limits

### 10.1 Error handling rules

1. **One exception boundary per layer.** Adapters translate vendor errors into the provider exception types (§6.5). The pipeline translates those into `ErrorCode`s (§6.4). `RunManager` catches everything else, records `INTEGRITY_FAILED` or `MODEL_FAILED` as appropriate, and never lets an exception reach the UI.
2. **Generic user messages.** The UI maps each `ErrorCode` to fixed copy (PRD §7.3). It never shows provider text, stack traces, URLs of failed calls or keys.
3. **Release in `finally`.** The semaphore permit, session lock and reservations are released in `finally` blocks on every exit path.
4. **Partial over failure.** When validated evidence exists, a budget, timeout or provider failure yields Partial with reason codes. When it does not, the result is Failed with no synthesized report.
5. **Parse failures fail closed.** An unparseable verifier or scanner output removes the affected claims or sentences.

### 10.2 Retry policy

| Condition | Retry? | Detail |
|---|---|---|
| Timeout, connection error, HTTP 5xx | Yes, up to 2 more attempts | Exponential backoff with full jitter: base 1 s, cap 8 s |
| HTTP 429 | Yes, up to 2 more attempts | Wait for `Retry-After` if it fits in the remaining run time and budget, otherwise use the jittered backoff; if neither fits, stop |
| Writer or planner schema violation | Yes, within the same 2 | The retry prompt repeats the schema rules |
| Verifier or scanner malformed output | No | Treated as `unsupported` or removal (PRD §13.2) |
| HTTP 400, 401, 403, content refusal | No | `CONFIG_INVALID` or `MODEL_FAILED` with setup guidance and no secrets |

**Guarded call.** Every external call goes through one function:

1. Check `cancel_flag` and the run deadline.
2. Reserve the estimated worst-case cost (§10.4). If refused, raise `BUDGET_STOP`.
3. Acquire the provider rate limiter.
4. Call with `timeout = min(per_call_timeout, time_left)`.
5. On success, commit the reservation with actual usage (or mark `unknown_cost` if usage is missing).
6. On failure, classify the error, release or commit the reservation, and apply the retry rules, where each retry repeats steps 1–6.

SDK-level retries are disabled so that no attempt escapes the budget.

### 10.3 Rate limits

| Direction | Mechanism | Value (proposed) |
|---|---|---|
| Inbound, per session | One active run (`RunManager` lock) | 1 |
| Inbound, per process | Semaphore | 5 active runs; extra requests get `BUSY` immediately, never queued |
| Inbound, per client | Gateway rate limit | Set at deployment |
| Outbound, per provider | Shared token bucket in `capacity.py` | Configured below the provider's published limits, set at M0 |
| Spend | Daily alert and stop (§10.4) | `DAILY_SPEND_ALERT_USD`, `DAILY_SPEND_STOP_USD` |

A light circuit breaker is proposed per provider: after 5 consecutive failures, calls fail fast for 30 seconds. This protects the budget and the user from long hangs. It must not hide errors from telemetry.

### 10.4 Cost admission and the budget ledger

**Per call.** `max_possible_cost = (estimated_input_tokens × input_price + max_output_tokens × output_price) × safety_factor`, or the per-call search price. Input tokens are estimated as `ceil(characters ÷ 3.5)` plus a prompt allowance, the same estimator used for the trim and batching rules.

**Structure.** Per PRD §10.1: stage base reservations (first attempt, worst-case tokens, times 1.25) and a shared contingency pool equal to the mode's cap minus all base reservations. Retries, the planner replan (FR-03) and the repair branch draw on the pool.

**Startup check.** For each mode, require (i) the sum of base reservations ≤ the cap and (ii) the base plus worst-case pool demand ≤ the cap. The worst-case pool demand is two further attempts of every first-pass call, one planner replan, and the repair branch (bounded by the repair limits in §5.3), each with its own retries, all times the safety factor. The verifier's worst-case batch count is computed from token sizes, not assumed:

```
tokens_per_claim_max = ceil(max_quotes_per_claim × max_passage_chars / 3.5)
                     + ceil(300 / 3.5) + claim_text_allowance
claims_per_batch     = min(8, floor((verifier_cap − prompt_allowance) / tokens_per_claim_max))
batches_max          = ceil(max_claims / claims_per_batch)
```

With 1,500-character snippet passages, the worst case is 4 claims per batch, so 4 batches in Quick (14 claims) and 9 in Deep (36 claims). The PRD v1.6 tables assume 2 and 5. They also omit the planner replan that FR-03 allows, which adds one more planner call with its own retries to the worst case. §12.5 shows the corrected figures and §14 proposes updating the PRD.

**Daily spend guard (PRD FR-45).** An in-memory total for the day, written atomically to `state/spend-YYYYMMDD.json` after each run, is checked at admission. Reaching the alert threshold logs an alert event. Reaching the stop threshold rejects new runs with `SERVICE_PAUSED` and the generic "service paused" copy. Reading the file at startup stops a restart from resetting the day's spend.

**Unknown cost.** If a provider returns no usage data, the ledger records `unknown_cost`, charges the reserved ceiling, and raises an alert. If accounting becomes untrustworthy, further calls are blocked (PRD §10.1 item 5).

### 10.5 Idempotency

Duplicate submissions carry the same idempotency token and return the existing `run_id`. Feedback is one vote per run. UI events are idempotent per run. Tool-level retries never repeat a committed reservation.

---

## 11. Logging, Observability, and Monitoring

### 11.1 Design (ADR-011)

Logs are typed events, not formatted strings. Each event is a Pydantic model with `extra="forbid"`, so a developer cannot add a free-text field that might carry a topic, passage or report. Redaction works by allowlist, not by scrubbing.

**Never logged:** topics, queries, passages, quotes, claim text, report text, full URLs, API keys, IP addresses, session IDs, user identifiers. Domains (registrable only) and counts are allowed. Exceptions are logged as `error_code` plus the exception class name; stack traces appear only in local debug mode.

### 11.2 Event catalog

| Event | Fields (all allowlisted) |
|---|---|
| `run.rejected` | `run_id`, `mode`, `error_code` |
| `run.admitted` | `run_id`, `mode`, `modeled_ceiling_usd`, `base_reserved_usd`, `pool_usd` |
| `stage.finished` | `run_id`, `stage`, `elapsed_ms`, `outcome` |
| `provider.call` | `run_id`, `stage`, `provider`, `model_id`, `prompt_version`, `attempt`, `latency_ms`, `status_class`, `input_tokens`, `output_tokens`, `reserved_usd`, `committed_usd` |
| `run.finished` | The telemetry record of PRD §13.3 plus `reason_codes`, `removed_claim_count`, `drafted_claim_count`, `dropped_passage_count`, `estimator_error_ratio`, `replan_used`, `repair_used` |
| `run.ui_event` | `run_id`, `event` (`evidence_opened` or `export_downloaded`), once per run and event |
| `run.feedback` | `run_id`, `vote`, once per run |
| `service.draining` | `active_runs`, `drain_timeout_s` |
| `watchdog.abandoned` | `run_id`, `stage` |
| `spend.alert` / `spend.stop` | `day`, `total_usd`, `threshold_usd` |
| `startup.check` | `result`, `failed_checks` (names only) |

Every event carries `ts`, `run_id` where applicable, and `schema_version`. Files are JSON lines rotated daily and deleted after the configured retention (≤7 days). Logs are append-only, so events that happen after a run ends (`run.ui_event`, `run.feedback`) are separate lines. The metrics script joins them to `run.finished` by `run_id`, which satisfies FR-44's "stored with run metadata".

### 11.3 Metrics

Derived from the event files by `eval/metrics_report.py`, run on demand or by a scheduled job:

| Metric | Definition |
|---|---|
| Run outcome mix | Completed, Partial and Failed counts by mode and reason code |
| Latency | p50 and p95 per mode and per stage, with bootstrap intervals in benchmark runs |
| Cost | Median and p95 committed cost per mode; modeled ceiling per run; share of cap used |
| Provider health | Error rate and retry rate per provider and status class |
| Verifier behavior | `removed_claim_count ÷ drafted_claim_count`, verdict mix, false-accept and false-reject on fixtures |
| Capacity | `BUSY` rate, abandonment rate, peak active runs |
| Budget | Spurious budget-stop rate on healthy runs (target ≤2%) |
| KPIs | The PRD §2.7 table, from aggregate counters |
| Estimator | `estimated ÷ provider-reported` input tokens, to validate the 3.5 characters-per-token ratio |

### 11.4 Alerts and monitoring (pilot)

| Condition | Threshold (proposed) | Action |
|---|---|---|
| Daily spend | Alert at `DAILY_SPEND_ALERT_USD` (proposed default: 70% of the stop value); stop at `DAILY_SPEND_STOP_USD` | Log event; operator notice; new runs paused at the stop (PRD FR-45) |
| Failed share | >20% of runs in a rolling 24 h with at least 20 runs | Operator review |
| p95 latency | Above the §6.1 target for two consecutive daily reports | Operator review |
| Provider error rate | >10% of calls in an hour | Operator review; circuit breaker may already be open |
| Abandonment | >10% of runs | Check heartbeat timeout and browser throttling (A-07) |
| Integrity | Any `INTEGRITY_FAILED` | Immediate review; roll back if systemic (PRD §13.1) |
| Startup check failure | A mode disabled, or no servable mode | A disabled mode shows an unavailable notice and raises an alert. With no servable mode, or missing required configuration, the process does not start (§12.2) |

The pilot runs the metrics report on a schedule and delivers alerts by whatever channel the host offers. Public launch adds an alerting stack (PL-09).

### 11.5 Health

Liveness is Streamlit's health route. Readiness is established by the startup check before the server starts (§12.2). If required configuration is missing, or neither mode passes the call-graph check, the entrypoint exits non-zero, so the platform never routes traffic to an unconfigured instance. If only one mode fails, the process starts, the failing mode is disabled with an unavailable notice, and an alert is raised.

---

## 12. Infrastructure, Deployment, and Scaling

### 12.1 Environments

| Environment | Purpose | Providers | Notes |
|---|---|---|---|
| Local dev | Development | Fakes by default; live keys optional | `.env` from `.env.example` |
| CI | Every change | Fakes only; no network in unit tests | Lint, types, tests, audits |
| Pilot (hosted) | Access-restricted pilot | Live | One container, one process |
| Benchmark | Dev and holdout runs | Live, with spend caps | Same image as the pilot |

### 12.2 Pilot deployment

- **Image.** One non-root container, started by an entrypoint that first runs `python -m core.settings --check` and exits non-zero on failure, then launches `streamlit run app.py` in headless mode on one process.
- **Startup check** validates: required environment variables (without logging values), a priced model for every role, price sheet version, `CONTACT_URL` for hosted deployments, writable log and state directories, and the call-graph conditions (i) and (ii) for each mode (FR-37). A failing mode is disabled, and if both fail the process does not start.
- **Configuration** (environment variables):

| Variable | Purpose |
|---|---|
| `SEARCH_API_KEY`, `OPENAI_API_KEY`, `VERIFIER_API_KEY` | Provider credentials |
| `WRITER_MODEL`, `VERIFIER_MODEL`, `VERIFIER_PROVIDER` | Pinned models |
| `PRICE_SHEET_VERSION` | Versioned prices and safety factor |
| `MAX_CONCURRENT_RUNS` | Default 5 |
| `HEARTBEAT_TIMEOUT_S` | Default 90 |
| `RESULT_TTL_MIN`, `ABANDONED_TTL_MIN` | Defaults 30 and 10 |
| `EST_CHARS_PER_TOKEN` | Default 3.5 |
| `DAILY_SPEND_ALERT_USD`, `DAILY_SPEND_STOP_USD` | Spend guard |
| `LOG_DIR`, `LOG_RETENTION_DAYS` | Telemetry (≤7 days) |
| `CONTACT_URL` | Reporting contact for the privacy page |
| `DRAIN_TIMEOUT_S` | Default 120; time active runs may finish after SIGTERM |
| `STATE_DIR` | Default `state/`; holds the spend counter, the drain sentinel and the active-run count |
| `VERIFIER_MAX_PARALLEL` | Default 4; verifier calls in flight per run, within the provider's limits |

- **Gateway.** WebSocket pass-through, idle timeout above 360 s plus margin, authentication, rate limits, TLS.
- **Rollback.** Keep the previous image tag and its configuration. Roll back on systemic failure or any citation-integrity regression. State is in memory, so there is nothing to migrate; in-flight runs are lost, and users see the idle form with the standing reload notice (§4.2, §6.4).
- **Backups.** None needed for application data. Back up configuration, the price sheet and evaluation data.
- **Secrets rotation.** Rotate provider keys by changing the secret and restarting. A restart ends active runs.
- **Graceful shutdown (drain).** The app cannot trap SIGTERM itself: Streamlit manages its own shutdown, and Python installs signal handlers only on the main thread, while Streamlit runs scripts on other threads (confirm at M0). The container entrypoint is therefore a small wrapper process that starts Streamlit and traps SIGTERM. On SIGTERM the wrapper creates a drain sentinel file in `STATE_DIR`. The `RunManager` watchdog sees the sentinel within 5 s, stops admitting runs (`SERVICE_PAUSED`), logs `service.draining`, and writes the active-run count to a file in `STATE_DIR` every 5 s. The wrapper waits until that count reaches zero or `DRAIN_TIMEOUT_S` (default 120 s, proposed) passes, then forwards SIGTERM to Streamlit. Runs still active at that point are lost. Set the platform's termination grace period to at least the drain timeout plus a few seconds, and deploy when few runs are active. A Deep run can take up to 360 s, so a deploy during one may still cut it.

### 12.3 CI/CD

Stages on every change: lint and format (`ruff`), types (`mypy`), import rules (`import-linter`), unit and property tests, adapter contract tests against recorded fixtures, UI tests with `AppTest`, secret scan, `pip-audit`, image build and scan. A release candidate additionally runs the verifier and scan fixture scorecards, the concurrency tests and the browser tests. Benchmark runs are manual and follow PRD §11.1.

### 12.4 Scaling path

| Stage | Architecture | Trigger |
|---|---|---|
| 0. Local | One process on a developer machine | M1 |
| 1. Pilot | One container behind a gateway; threads; in-memory state; JSON-lines telemetry | PRD pilot |
| 2. Hardened internal | Same shape, larger host, more provider headroom; alerting stack | Sustained use near 5 concurrent runs |
| 3. Public | Stateless web tier (UI) plus a job queue and worker pool; Redis for shared admission, quotas, leases and reconnect; PostgreSQL for opt-in history and usage (§7.5); OIDC; shared rate limiter; central logs and metrics | PRD §17 gate |

What changes at stage 3: `RunManager` splits into a thin API client and a queue consumer; the budget ledger and rate limiters move to Redis; run records move to a shared store with the same TTL and ownership rules; the reload limitation disappears because any web instance can re-attach by `run_id`. The pipeline, checks, verifier, status rules and adapters are reused unchanged, which is the reason for the layering in §4.3.

### 12.5 Capacity and cost model

**Concurrency.** Five runs, each with up to four inner workers: about 25 threads for pipeline work. Provider limits, not threads, are the constraint, so the shared token buckets matter most.

**Memory.** Under 1 MB per run (§7.3). The in-memory stores are small.

**Cost, corrected worst case.** Using the illustrative prices in PRD §10.3, the token-based batch counts from §10.4 (4 verifier batches in Quick, 9 in Deep), and the planner replan that FR-03 allows:

| | Quick | Deep |
|---|---|---|
| Base reservations (first attempt × 1.25) | $0.177 | $0.421 |
| Shared pool (cap − base) | $0.573 | $2.579 |
| Pool demand: retries of first-pass calls | $0.354 | $0.842 |
| Pool demand: repair branch with retries (≤6 / ≤12 claims) | $0.149 | $0.237 |
| Pool demand: planner replan with retries | $0.044 | $0.044 |
| Worst-case pool demand | $0.547 | $1.123 |
| Pool spare | $0.026 | $1.456 |
| Worst case, base plus pool demand | $0.724 | $1.544 |
| Admitted cap | $0.75 | $3.00 |
| Share of cap used | about 97% | about 51% |

Both modes pass conditions (i) and (ii), but Quick has only about 3.5% headroom, roughly $0.03. That leaves almost no room for a price change. At the D-13 checkpoint, decide whether to raise Quick's admitted cap (PRD §6.1 sets $0.75), lower the Quick claim cap or the repair limit, or choose a cheaper writer. A writer model priced twice as high makes Quick fail the startup check (about $1.04 against $0.75). Without the repair limits in §5.3, repairing and re-verifying every claim with the full writer input would put Quick at about $0.78, above its cap, which is why the repair pass is capped. All prices here are placeholders; the M1 harness replaces them with measured values. PRD v1.7 carries the same figures in its §10.3.

**Latency.** The stage budgets in PRD §6.1 are the targets. The main risk is ledger output length (about 16 s for 2,400 output tokens at an assumed 150 tokens per second against a 14 s Quick budget). The PoC measures actual speed (A-04). Options if it misses: a lower Quick claim cap, shorter ledger fields, or parallel per-facet drafting.

**Verification waves.** With up to 4 verifier calls in flight, Quick's 4 batches fit in one wave and Deep's 9 batches take 3 waves. At an assumed 6–8 s per verifier call, that is about 6–8 s for Quick against a 9 s budget and about 18–24 s for Deep against a 25 s budget. Deep has little slack. If the harness shows a miss, raise `VERIFIER_MAX_PARALLEL` within the provider's limits or reduce the passages shown per claim. These timings are estimates for the harness to confirm.

---

## 13. Testing Strategy and Architecture Decisions

### 13.1 Strategy

Tests prove the trust properties without live providers wherever possible, and use live providers only for the benchmark and a small canary. The pyramid, from the base:

| Layer | Scope | Tooling | Runs |
|---|---|---|---|
| Unit and property | Pure functions: canonicalization, ranking, passage trim, normalization, quote match, numeric guard, sentence rules, status rules, budget ledger | `pytest`, `hypothesis` | Every change |
| Component | Pipeline stages with fake adapters; verifier batching; repair flow | Fakes from `adapters/fakes.py` | Every change |
| Contract | Adapters against recorded provider fixtures; error-type translation | `httpx.MockTransport`, fixture files | Every change; re-recorded deliberately |
| Run manager and concurrency | Semaphore, session lock, idempotency, watchdog, release on exception | Threads, barriers, injected clock | Every change |
| UI state | Form, disabled states, evidence toggle, clear session, idle and expired-result notices | Streamlit `AppTest` | Every change |
| Polling logic | `poll_once()` as a pure function: heartbeat, stage text, terminal detection, expired-result handling | `pytest` | Every change |
| Browser | Fragment polling and the terminal rerun, reload behavior, background-tab throttling, keyboard flow, 320 px and 200% zoom, accessibility scan | Playwright with axe-core | Release candidate |
| Security | Injection fixtures, export escaping across renderers, secret scans, dependency audit | Fixtures, `pip-audit`, secret scanner | Every change (static); release candidate (fixtures) |
| Fixture evaluation | Verifier and scan scorecards on sealed halves | `eval/` scripts | When prompts, models or verifier change; release candidate |
| Benchmark | Dev and sealed holdout runs, grounding and coverage review | Benchmark runner, reviewers | PoC and pilot gate |
| Canary | One live call per provider with a tiny cap | Scheduled job | Nightly |

`AppTest` drives widgets and session state well, but it may not drive timed fragment polling. The polling wrapper in `ui/components.py` is therefore kept thin: it calls the pure `poll_once()` function, which is unit-tested directly, and the real timer behavior is covered by the browser tests.

### 13.2 Mapping to PRD §11.4

| PRD tests | Layer |
|---|---|
| 1, 27, 39 | Unit and component (validation, plan breadth, failure paths) |
| 2, 20, 21, 32, 42 | Unit and component (caps, reservations, startup check, pool accounting, repair limits) |
| 3, 4, 14, 15 | Unit and property (ranking, chunking, thresholds at N−1, N, N+1) |
| 5–10, 34, 37 | Unit, property and component (citation, quote, numeric, repair, token caps, claim placement) |
| 11, 12 | Component with scan fixtures |
| 13 | Component (contradiction handling with scripted evidence) |
| 16, 38 | Component with scripted provider faults and outage simulation |
| 17–19, 40 | Run manager and concurrency tests, the drain test with the entrypoint wrapper, plus browser tests for reload and throttling (29) |
| 22–24, 28, 30, 35, 36, 41 | UI state, export golden files, counters, expired, paused and unavailable states |
| 25 | Security and fixture evaluation |
| 26, 29 | Browser |
| 31, 33 | Measurement harness and eval tooling tests with hand-computed fixtures |

### 13.3 Architecture fitness functions (run in CI)

- `import-linter` contracts from §4.3, including "no `streamlit` import below the UI".
- A test that fails if any `LogEvent` model gains a free-text field.
- A test that fails if any code path outside `export_markdown` builds a link from non-registry text.
- A test that fails if `unsafe_allow_html=True` appears anywhere except `ui/theme.py` and the status-banner and badge helpers, or if those helpers receive anything other than integers, fixed state names and strings from `ui/copy.py` (design.md §12.4).
- A test that recomputes every color-pair contrast ratio from the tokens in `ui/theme.py` and fails below the thresholds in design.md §5.2 and §5.3, and a test that `ui/theme.py` and `.streamlit/config.toml` agree.
- A test that fails if any adapter enables SDK-level retries.
- A test that runs the startup call-graph check against the shipped price sheet and mode configuration.
- A network guard that fails unit tests which attempt a real connection.

### 13.4 Test data and discipline

Fakes script behaviors: success, partial extraction, rate limit with `Retry-After`, timeout, malformed JSON, schema violation, injection text, refusal, missing usage. Test corpora are synthetic or curated benchmark text, never real user topics. Flaky tests are fixed or removed, not retried silently. Proposed coverage targets: at least 90% line coverage on `pipeline/` and `core/status_rules.py`, `core/capacity.py` and `core/run_manager.py`; no target on `ui/` beyond the `AppTest` scenarios.

### 13.5 Architecture decision records

All are Proposed and need owner sign-off.

| ID | Decision | Context | Consequences | Revisit when |
|---|---|---|---|---|
| ADR-001 | Fixed workflow, not an autonomous agent loop | Cost, time and trust must be provable | Predictable and testable; no open-ended exploration | Never for the pilot |
| ADR-002 | No public HTTP API in the pilot; in-process facade | The PRD needs only the Streamlit UI | Less attack surface; API deferred to the public launch | Public launch |
| ADR-003 | No database; in-memory state with TTL | D-03 forbids persistence | Simple and private; no recovery after restart | Opt-in history (FR-21) or public launch |
| ADR-004 | Threads and locks, not `asyncio` or a task queue | Single process; I/O-bound calls | Simple; scale limit of one process | More than 5 concurrent runs |
| ADR-005 | Report text is rendered from ledger claims verbatim | Prevents unverified prose | Terse output; measured by readability | Readability trigger (PRD §11.7) |
| ADR-006 | Verifier from a different model family | Reduces correlated errors | Second vendor, key and terms review | Fixture results, price |
| ADR-007 | Pydantic strict schemas plus deterministic validators | Models must not control structure | More upfront schema work | — |
| ADR-008 | Search provider behind an adapter | Provider risk and change | Small adapter surface | PoC finds A-01 false |
| ADR-009 | Access control delegated to the host | Streamlit has no auth; pilot is internal | Hosting requirement; no in-app user model | Public launch |
| ADR-010 | Base reservations plus shared pool for budgets | Fixed splits rejected viable configurations | Slightly more accounting code | PoC shows different retry behavior |
| ADR-011 | Typed log events with an allowlist; metrics derived from logs | Content must never reach logs | No ad-hoc debug logging in production | Public launch (PL-09) |
| ADR-012 | Evidence Details via a per-claim toggle, not an expander | Expanders do not report to Python | One rerun per toggle; counter works; keyboard-operable | Streamlit adds expander events |
| ADR-013 | Conservative token estimator (3.5 characters per token) with measured error | Caps must be enforceable without provider tokenizers | May under-use the cap by a small margin | D-13 checkpoint |
| ADR-014 | Public launch uses queue, Redis and PostgreSQL | Pilot constraints do not scale | Reuses the pipeline unchanged | PRD §17 |
| ADR-015 | Daily spend counter persisted as a small file | A restart must not reset the daily stop | Writes one non-content file | Redis at stage 3 |
| ADR-016 | Repair runs only when first-pass status is not Completed | Saves the repair reservation on healthy runs | Completed runs may keep some rejected claims | PoC measurements |
| ADR-017 | Open-source projects are references or dev tools by default; a runtime dependency needs the §16.3 adoption review | The proposed repositories overlap with, or conflict with, existing constraints | Slower adoption; no silent new data flows or fetch paths | Each adoption review |
| ADR-018 | The UI keeps no copy of a result; it fetches the read-only result from `RunManager` on each render | A session-state copy would outlive the TTL purge and escape Clear session | One in-memory read per rerun; expired results show a notice | Stage 3 shared store |
| ADR-021 | A local Ollama model may be the verifier: OpenAI-compatible endpoint on this computer, `json_schema` response format, strict Pydantic validation, a placeholder key, no fallback to any hosted provider, and a check that the server did not truncate the prompt | The user wants independent evidence checking on their own machine while a large hosted model writes; measuring first showed that Ollama enforces schemas but silently truncates prompts and that an 8B model is accurate but slow on a 4 GB GPU | Verification is only as strong as the local model (a 4B model obeyed injected instructions); the time limits are not met on the development laptop | A text-focused model or a larger GPU passes the sealed fixture gate within the time limits |
| ADR-020 | Model providers are OpenAI-compatible endpoints or Anthropic behind one `LLMClient` protocol; verifier independence is judged by model family; NVIDIA Build (Nemotron 3 Ultra writer) is the development writer and a local Ollama model the development verifier (ADR-021); JSON is requested in the prompt and validated strictly where an endpoint has no structured-output mode | The user asked to develop on NVIDIA's free hosted API instead of paid keys; PRD D-11 asks for a different family, not a different vendor; strict validation keeps the fail-closed rule independent of any provider feature | Hosted behavior (parameter names, structured output, limits) rests on NVIDIA's documentation and must be probed (`eval/provider_probe.py`); more schema retries on endpoints without a JSON mode | Live measurements show the verifier fixture gate failing with this pair, or NVIDIA ends or restricts the free tier |
| ADR-019 | App-owned HTML is allowed only for the status banner and badges, built from literal templates; all third-party text stays escaped plain text | Custom status colors need markup that Streamlit's native widgets cannot give | One narrow, testable exception to the no-HTML rule | A native status component that meets the contrast rules |

---

## 14. Open Items and Proposed PRD Changes

These came out of writing and reviewing this document. They were proposed for the PRD and are applied in PRD v1.7 (items 1–7, 9, 10 and 11). Item 8 is a standing rule.

| # | Item | Proposal |
|---|---|---|
| 1 | The PRD §10.3 worst case assumes 2 (Quick) and 5 (Deep) verifier batches and omits the planner replan that FR-03 allows. With 1,500-character snippet passages and up to 3 or 4 quotes per claim, the token-based bound is 4 and 9 batches. The repair branch also needs stated limits, otherwise Quick's worst case is about $0.78, above its cap | Compute batch counts from tokens (§10.4); add the replan and the repair limits (§5.3) to the FR-37 worst case; update the §10.3 tables to the §12.5 figures (Quick about $0.72, Deep about $1.54); Quick's headroom is about 3.5%, so decide at D-13 whether to raise its cap |
| 2 | `evidence_opened` cannot come from a Streamlit expander, and post-run events cannot be written into an append-only log line that already exists | Specify the widget-driven panel (ADR-012) in FR-20 and FR-44, and word FR-44 so the counters are joined to the run by `run_id` (§11.2) instead of stored on the run record |
| 3 | §12.4 of the PRD names a legal reviewer; §4 and §15.1 do not | Name the legal-review role at M0, or reduce §12.4 to the privacy reviewer |
| 4 | The daily spend stop needs a counter that survives restart | State in D-03 that a non-content spend counter file is operational metadata (ADR-015) |
| 5 | The PRD leaves the repair trigger open | Adopt ADR-016 or specify another rule |
| 6 | The PRD says "expose generic readiness failure" without a mechanism | Adopt the pre-start check and non-zero exit (§12.2) |
| 7 | The PRD does not say how a session identifier is obtained | Adopt the app-generated `session_id` (§4.2) |
| 8 | Several proposed repositories conflict with current PRD constraints: Crawl4AI, Docling and Trafilatura's fetching (C-07, D-02, NFR-13); Phoenix with content-free telemetry (AP-8); SearXNG with snippet-only evidence | Keep them out of the pilot. If the owner wants any of them, record it through PRD change control first (§16) |
| 9 | The PRD §7.3 "Run lost" state cannot be reached: after a restart or reload Streamlit starts a new session with no run ID, so the UI cannot tell a lost run from an idle form | Remove "Run lost" from PRD §7.3, the sentence in §8.4 item 7, and the restart row in §13.2, and rely on the idle state with the standing reload notice (§6.4) |
| 10 | The PRD has no copy for an expired result, a paused service (daily spend stop or draining) or a disabled mode | Add three states to PRD §7.3 and the FAQ: "Result expired" (results are kept 30 minutes), "Service paused" and "Mode unavailable" |
| 11 | Draining on shutdown needs a wrapper process, because the app cannot trap SIGTERM itself | Add NFR-19 and assumption A-13 to the PRD (§12.2 here) |

**Assumptions to validate at M0:** the pinned Streamlit version supports polling fragments and the configuration options in §9.5; each provider supports strict structured output and the extraction fields the adapters need; `tldextract` can run from its bundled snapshot without network access; the gateway passes WebSockets with a long idle timeout; Streamlit's SIGTERM handling is compatible with the wrapper-and-sentinel drain in §12.2.

---

## 15. Traceability to the PRD

| PRD area | Architecture section |
|---|---|
| Principles, scope, constraints (§1, §3, §4) | §1 |
| Technology choices (§8.1) | §2 |
| Pipeline and components (§8.1–8.3) | §3, §5 |
| Run model and concurrency (§8.4, FR-36, NFR-11, NFR-17) | §4.3, §10.1 |
| Claim ledger, checks, verifier, typed sentences (FR-08, FR-19, FR-33, FR-34) | §5.2–5.7 |
| Status rules (FR-31, §6.4) | §5.3, §5.4 |
| Source selection and trimming (§6.2, FR-05–07) | §5.3 `SCREENING`, §10.4 |
| Evidence Details and export (FR-12, FR-20, FR-44) | §4.2, §9.4 |
| Cost admission and budgets (FR-32, FR-37, NFR-04, NFR-05, §10.1) | §10.4, §12.5 |
| Data model and retention (§9, D-03, D-08, NFR-07) | §7 |
| Security and privacy (§12, NFR-09, NFR-10, NFR-13) | §8, §9 |
| Failure handling (§13.2, NFR-14, NFR-16) | §10 |
| Telemetry, KPIs, harness (§13.3, §2.7, FR-42) | §11 |
| Deployment and scaling (§13.1, §17, NFR-12) | §12 |
| Testing and gates (§11, NFR-02, NFR-03) | §13 |
| Evaluation data and fixtures (§11.1–11.2) | §7.4, §13.1 |
| Candidate open-source tools and references (§14.2) | §16 |

---

## 16. Reference Repositories and Reuse Decisions

Twelve open-source projects were proposed as references for this build. **None is a dependency today.** Every row below is a proposal, and any runtime dependency still needs the adoption review in §16.3. The descriptions come from the proposed list and from general knowledge, not from a fresh check of each repository. Confirm the canonical repository, license, maintenance activity and telemetry behavior at the adoption review. No links are given, except the Crawl4AI path that came with the list (`github.com/unclecode/crawl4ai`).

### 16.1 Summary

Roles: **Study** (read and borrow ideas, no code dependency), **Dev tool** (CI or local evaluation only, never in the pilot image), **Optional dependency** (may enter the runtime after review), **Deferred** (conflicts with a PRD constraint and needs change control), **Scaling candidate** (considered for the public-launch stack).

| # | Repository | Helps with | Role | When | Verdict against the PRD |
|---|---|---|---|---|---|
| 1 | GPT Researcher | End-to-end research workflow, multi-source retrieval, cited reports | Study | M1 | Compatible as a reference only. Its report writing and citation handling are not claim-verified |
| 2 | STORM | Research question generation, multi-perspective exploration, outlines | Study | M1 | Compatible as a reference for facet and essential-question design. Its multi-agent simulation exceeds our call budget |
| 3 | Trafilatura | Clean article text and metadata from HTML | Optional dependency (conditional) | M1/M2 | Compatible only for cleaning HTML the provider already returned. Its fetching must not be used |
| 4 | Instructor | Validated structured outputs for claim ledgers and verifier responses | Optional dependency | M1 | Compatible if its retry loop is disabled or bypassed. Overlaps with adapter-level Pydantic validation |
| 5 | DeepEval | Automated LLM evaluations, grounding tests, regression testing | Dev tool (recommended) | M1–M3 | Compatible as a non-gating aid. The judge-model data flow needs review |
| 6 | Promptfoo | Prompt-injection and adversarial tests, prompt comparison | Dev tool (recommended) | M2 | Compatible. Dev and CI only |
| 7 | Crawl4AI | Browser-based web content extraction into Markdown | Deferred | Later, if approved | Conflicts with C-07, D-02 and NFR-13 |
| 8 | Arize Phoenix | Tracing and debugging LLM calls, prompt and model experiments | Dev tool (optional) | M2/M3 | Conflicts with AP-8 for real user data. Benchmark and dev data only |
| 9 | Ragas | Retrieval and answer-quality evaluation | Dev tool (alternative to #5) | M1–M3, if chosen | Same cautions as DeepEval. Adopt one of the two, not both |
| 10 | Docling | Structured extraction, including tables, from PDFs and documents | Deferred | Phase 2 | Needs document ingestion, which the MVP excludes |
| 11 | LangGraph | Stateful multi-stage workflows, durable execution | Scaling candidate | Phase 2 / scaling | Not for the pilot (ADR-004, AP-9) |
| 12 | SearXNG | Self-hosted metasearch, alternate search discovery | Deferred (optional fallback) | Later | Snippet-only results, and it counts as a provider change |

### 16.2 Per-repository decisions

**1. GPT Researcher (Study, M1).**
- *Use:* Read its planner, sub-query fan-out, source aggregation and report stages. Write a short lessons note at M1 covering query-planning prompts, source scoring ideas and failure modes it handles. It can also serve as a baseline for the qualitative comparison in PRD §2.5, but only through a controlled side-by-side evaluation, which the PRD does not currently plan.
- *Cautions:* Do not import its agent loop, free-form report writing or citation handling. They conflict with ADR-001 and ADR-005, because its citations are not passage-verified. It may also fetch pages itself (C-07). Check the license before copying any code.
- *Gate:* None for study. Any code reuse needs the §16.3 review.

**2. STORM (Study, M1).**
- *Use:* Study how it derives perspectives and questions. Borrow the idea of perspective-guided facet generation inside the single planner call (FR-03), and as inspiration when authoring essential questions (§11.6 of the PRD).
- *Cautions:* Its multi-agent conversation simulation would multiply model calls and break the call graph and the budget model (§10.4, §12.5). Do not adopt it wholesale.
- *Gate:* None for study.

**3. Trafilatura (Optional dependency, M1/M2).**
- *Use:* Only if a search provider returns HTML or markup rather than clean text. Extract the readable text from provider-returned content so passage chunking is cleaner (PRD §9.2).
- *Cautions:* Never use its download or fetch functions (C-07, D-02). The cleaned text becomes the stored passage, and quote matching depends on that text being stable, so its output must be deterministic for a pinned version. It parses untrusted HTML inside the app process, so pin it, keep it audited, and fuzz-test it with the hostile fixtures. If the provider already returns clean text, skip it.
- *Gate:* §16.3 review, plus a lint rule that forbids its fetch functions.

**4. Instructor (Optional dependency, M1).**
- *Use:* Compare against native structured outputs and our own Pydantic validation at M1 (a 2–4 hour spike). It could reduce adapter code for the `LedgerDraft` and `VerifierOutput` schemas.
- *Cautions:* Its automatic retry on validation failure spends model calls outside our reservation system, which breaks AP-4 and the guarded call in §10.2. If adopted, set its retries to zero (or use only its parsing mode), keep it inside `adapters/llm_*.py`, and keep the retry layer in our code. It adds a layer over the vendor SDKs, so adopt it only if it removes more code than it adds.
- *Gate:* §16.3 review and a test that proves no retry escapes the budget.

**5. DeepEval (Dev tool, recommended, M1–M3).**
- *Use:* Regression and exploratory grounding checks on the dev set, wrapped as test cases. It can help track faithfulness-style metrics across prompt and model changes.
- *Cautions:* Model-judged metrics send claims and passages to a judge model. That is a data flow to document, and the judge must be a provider already approved in PRD §12.4. Its results are non-gating. The gates stay the human-labeled claim review and the sealed fixture halves. Never run it against the sealed halves while tuning (burn rule, PRD §11.1). Check its telemetry settings and disable them.
- *Gate:* Provider-terms checklist entry for the judge model; telemetry off in CI.

**6. Promptfoo (Dev tool, recommended, M2).**
- *Use:* Build adversarial and injection cases for the dev half of the verifier fixtures and the attack fixtures (PRD §11.2, tests 25 and 6), and compare prompt variants. Export cases into our own JSONL fixture format so the sealed halves stay ours.
- *Cautions:* It is likely a Node-based tool, so CI and dev machines may need a Node toolchain. Confirm that. Keep it out of the pilot image. Check and disable telemetry. Tuning against the sealed test half burns it. Its results are screening aids, not gates.
- *Gate:* §16.3 review; fixtures exported to `eval/` before any sealing.

**7. Crawl4AI (Deferred, later if approved).** Repository path: `github.com/unclecode/crawl4ai`.
- *Use:* Browser-based extraction of full pages into Markdown, which could raise the share of `extracted` evidence if search snippets prove too thin (A-01).
- *Cautions:* It requires server-side fetching of arbitrary pages and a headless browser. That conflicts with C-07 (no arbitrary fetch), D-02 (no crawling), the egress allowlist in §9.3 and NFR-13 (no bypassing access restrictions). It enlarges the attack surface (SSRF, browser exploits) and the legal exposure (robots rules, site terms, copyright). It also changes cost, latency and the status thresholds.
- *Gate:* A new PRD decision that changes D-02, then a re-run of security, grounding, latency and cost checks, per PRD §19 change control. Not before the pilot gate.

**8. Arize Phoenix (Dev tool, optional, M2/M3).**
- *Use:* Inspect traces of model calls and compare prompts on benchmark runs. It would speed up prompt debugging at M2.
- *Cautions:* A tracing tool stores prompts and outputs, which are the content that AP-8 and ADR-011 keep out of logs. Allow it only for dev and benchmark runs on benchmark data, in a local or self-hosted instance, behind an environment flag that defaults to off and is tested to be off in the pilot image. Never enable it for real user topics. PRD §13.3 already allows transient local debug detail, and this is the same boundary.
- *Gate:* §16.3 review and a test that the tracing exporter is inactive in the pilot configuration.

**9. Ragas (Dev tool, alternative to DeepEval).**
- *Use:* Only if DeepEval lacks a needed metric. Its retrieval and answer-quality metrics need reference contexts or answers, which our essential questions (§11.6 of the PRD) only loosely provide.
- *Cautions:* The same judge-model data-flow and telemetry cautions as DeepEval. Do not run both. Pick one at M1.
- *Gate:* Same as DeepEval.

**10. Docling (Deferred, Phase 2).**
- *Use:* Extract structure and tables from PDFs and documents, relevant to Phase 2 features.
- *Cautions:* The MVP does not ingest documents, and the PRD non-goals exclude private documents (§2.4). Fetching PDFs would also conflict with C-07. It brings heavy dependencies, so the image size and memory would grow beyond what the single-process pilot assumes.
- *Gate:* A Phase 2 scope decision.

**11. LangGraph (Scaling candidate, Phase 2).**
- *Use:* A candidate for the stage-3 queue-and-worker design, where durable execution and resume matter (§12.4). The state machine in §5.3 maps naturally to graph nodes.
- *Cautions:* Not for the pilot. ADR-004 and AP-9 choose plain threads, and a framework could blur the explicit deadline, budget and permit control that the guarded call (§10.2) provides. ADR-001 (a fixed workflow, not an agent loop) holds regardless of framework.
- *Preparation now:* Write each state as a pure function from `RunState` to `RunState`, so a later migration stays cheap. Evaluate it at stage 3 against a plain job queue.
- *Gate:* The public-launch architecture review (PRD §17).

**12. SearXNG (Deferred, optional fallback).**
- *Use:* A self-hosted fallback behind `SearchProvider` if the primary provider's outages or price become a problem.
- *Cautions:* It returns snippets only, with no extraction, so runs would end Partial with `SNIPPET_HEAVY` unless extraction comes from elsewhere. It needs its own hosting and upkeep, and upstream engines may block it or restrict use. It counts as a provider change, so PRD §19 re-baselining applies (fixture scorecard, call-graph check, dev-set run), and eligibility labels need a fresh extracted-mode check.
- *Gate:* PRD change control, an adapter with contract fixtures, and the outage rule in PRD §11.3.

### 16.3 Adoption review checklist

Before any of these projects, or any other new package, enters the runtime or CI:

1. Confirm the canonical repository and that the license permits our use.
2. Check maintenance: recent releases, open security issues, bus-factor risk.
3. Pin the version and hash in the lockfile, and run `pip-audit` (or the equivalent for other ecosystems).
4. Review data flow: does it call external services, send telemetry, or store prompts? Disable telemetry. Any new outbound domain needs approval, because the egress allowlist in §9.3 is a control.
5. Check the invariants: does it change stored passage text, retry calls, or alter token counts? Anything that spends model calls outside the guarded call (§10.2) is rejected or wrapped.
6. Check the footprint against the single-process pilot (memory, CPU, image size, a second language runtime).
7. Add adapter contract tests or fixtures, and an architecture-fitness test where a rule applies (for example "no fetch functions imported").
8. Record an ADR. If the change touches D-02, D-03, D-08, a provider, or extraction depth, run PRD change control first.

### 16.4 Where each tool touches the architecture

| Repository | Touches | Pilot image? |
|---|---|---|
| GPT Researcher, STORM | Documentation only (lessons note); optional input to `pipeline/planner.py` prompt design | No |
| Trafilatura | `pipeline/source_processing.py` (cleaning provider-returned HTML before chunking) | Yes, only if adopted |
| Instructor | `adapters/llm_openai.py`, `adapters/llm_anthropic.py` | Yes, only if adopted, with retries off |
| DeepEval or Ragas (choose one) | `eval/` regression tests and dev-set scoring | No |
| Promptfoo | `eval/` adversarial and prompt-comparison cases, exported to JSONL fixtures | No |
| Arize Phoenix | An optional, default-off tracing hook in `adapters/` and `core/telemetry.py` for dev and benchmark runs | No |
| Crawl4AI, Docling | Not placed. They would need new modules and a PRD change | No |
| LangGraph | Stage-3 `RunManager` and worker design (§12.4) | No |
| SearXNG | A future `adapters/search_searxng.py` behind `SearchProvider` | Only if adopted |

### 16.5 Effort and sequencing

| Item | When | Effort (proposed) |
|---|---|---|
| Study GPT Researcher and STORM, write the lessons note | M1 | 6–10 h |
| Spike: Instructor against native structured outputs | M1 | 2–4 h |
| Check whether Trafilatura is needed (depends on the provider's response format) | M1/M2 | 2–3 h |
| Set up DeepEval (or Ragas) for dev regression | M1–M3 | 4–8 h |
| Promptfoo adversarial cases and prompt comparisons | M2 | 4–8 h |
| Optional Phoenix tracing for dev runs | M2/M3 | 3–6 h |
| **Total if all of the above proceed** | | **21–39 h** |

These hours are not in the PRD §15 totals (299–462 person-hours). If the owner approves the work, add it to M1 and M2 and update the PRD estimates. Crawl4AI, Docling, LangGraph and SearXNG carry no pilot effort and wait for their gates.
