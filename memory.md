# Project Memory: AI Research Agent

| Field | Value |
|---|---|
| Document | memory.md |
| Purpose | Let a new session recover context fast. It summarizes decisions and state; the other files hold the detail |
| Updated | 2026-10-21 |
| Maintenance | Update at the end of every session (rules.md §9). Keep it under about 200 lines. Link instead of copying. Delete entries that stop being true |

**Read order for a new session:** rules.md, then this file, then tracker.md "Immediate next tasks", then only the sections of prd.md, architecture.md and design.md that the task touches. Section references written "PRD §n", "ARCH §n" and "DESIGN §n" point to those files, and the prefix covers the comma-separated sections that follow it.

---

## 1. Current Project State

- **Phase:** the user approved the six documents (2026-10-21) and the project was built with `uv`. The engineering slice runs end to end on scripted providers; live providers have never been called.
- **Code:** built and tested (533 tests; ruff, mypy and import-linter clean). **Git:** the folder is not a git repository; nothing is committed (awaiting the user's approval). **Dependencies:** `uv sync` from `uv.lock`.
- **Approval:** the documents are approved. Decisions D-01 to D-13 are still PROPOSED. No owner or reviewer is named (the PRD's M0 blocker).
- **Documents:**

| File | Version | Role |
|---|---|---|
| prd.md | 1.7 | Requirements, metrics, gates, estimates. Highest authority |
| architecture.md | 1.4 | Structure, contracts, cost model, ADR-001 to ADR-019, open-source reference decisions (ARCH §16) |
| design.md | 1.0 | UX, components, tokens, accessibility, state catalog |
| rules.md | 1.0 | Agent guardrails |
| tracker.md | 1.0 | Tasks, status, verification results, next actions |
| memory.md | 1.0 | This file |

- **Review history (self-assessed, not independent):** PRD v1.7 scored 93 on the strict category scale and 95.5 on the rubric. Architecture v1.4 scored 92 and 95. The four newer files are in tracker.md §9.2, which also explains the two scales. Treat all scores as spec quality only. Nothing has been measured.

## 2. Decisions Made and Why

| Decision | Reason | Source |
|---|---|---|
| Every factual sentence is a ledger claim with a verbatim quote, a numeric guard and an independent verifier verdict; anything else is removed | The MVP must reject unsupported claims. Citations show provenance, not truth | PRD §8.3, ARCH §5 |
| Fixed workflow, not an autonomous agent loop | Cost, time and fail-closed behavior must be provable | ARCH ADR-001 |
| Streamlit UI with a background worker pool; the UI never runs pipeline work | Streamlit reruns the script on every interaction and would kill a run | PRD §8.4, ARCH ADR-002, ADR-004 |
| No database; session-only data with a TTL | PRD D-03; less privacy exposure | ARCH ADR-003 |
| Budget = per-stage base reservations plus a shared pool | A fixed percentage split rejected viable configurations | ARCH ADR-010 and ARCH §10.4 |
| Verifier batch counts come from token sizes; repair limited to 6 or 12 claims; planner replan counted | Three earlier worst-case figures were not real bounds | ARCH §5.3, §10.4, §12.5 |
| Evidence Details is a per-claim toggle, not an expander | Expanders do not report opens to Python | ARCH ADR-012 |
| Verifier from a different model family than the writer | Reduces correlated errors. Candidates: Claude Haiku 5.5, fallback Sonnet 5.5 | PRD D-11, ARCH §2 |
| Access control delegated to the host or gateway | Streamlit has no authentication | ARCH ADR-009 |
| No "Run lost" state | After a restart or reload the new session has no run ID, so it cannot be detected | PRD v1.7 |
| The 12 proposed open-source repositories are references or dev tools; none is adopted | Several conflict with no-fetch and content-free-logging rules | ARCH §16, ADR-017 |
| App-owned HTML only for the status banner and badges | Custom status colors need markup; everything third-party stays escaped text | ARCH ADR-019, DESIGN §12.4 |
| UI uses PRD copy verbatim and the labels "Search snippet", "Extracted page text", "Not inspected (title only)" | Keeps copy reviewable and consistent | DESIGN DR-3, DR-4 |
| Development models: NVIDIA Build, Nemotron 3 Ultra (writer) + local Ollama qwen3-vl:8b-instruct (verifier); the hosted NVIDIA verifiers (gpt-oss-20b, Gemma 4 31B) were flaky and stay as alternatives; independence is judged by model family; free-tier prices are budgeting rates with a review date | The user wants to develop without paid keys and check evidence locally; D-11 asks for a different family, not vendor; caps must still bind if the free tier ends | ARCH ADR-020, ADR-021, §8.6, §8.7, PRD v1.8 |
| Documents are normal prose; the terse chat style applies to conversation only | Files persist outside the chat | rules.md §9 |

## 3. Implemented Features and Current Behavior

Built and tested on scripted providers (`RESEARCH_PROVIDER_MODE=fake`, synthetic corpus about a fictional topic, always labeled demo):

- Run pipeline: plan (one replan) -> search -> registry -> ledger draft -> deterministic checks -> independent verifier -> status rules -> one repair -> scan -> cited Markdown report with an Evidence appendix.
- Cost control: base-plus-pool budget ledger, startup call-graph check per mode, retries and rate limits in one `CallGuard`, a persisted daily spend guard.
- Run manager: worker pool, session lock, idempotency, heartbeat watchdog, TTL, drain marker.
- Streamlit UI: Research, About/Privacy and FAQ tabs, polling progress, status banner, Evidence toggles, download, feedback, clear session.
- Live adapters (Tavily, OpenAI, Anthropic) exist and pass fake-transport tests only. Their wire formats are UNVERIFIED; live mode refuses to start on the placeholder price sheet.
- Not built: anything needing people, money or decisions (owners, models, real prices, fixtures, holdout, benchmarks, hosting, CI, browser and screen-reader audits). See `docs/build-ledger.md` and tracker.md §9, §13.

Run it: `uv sync`, then `uv run demo.py`, `uv run streamlit run app.py`, `uv run pytest`.

## 4. Known Limitations and Technical Debt

- **Cost margin:** Quick's worst case is about $0.724 against a $0.75 cap (about 3.5% spare), computed on placeholder prices (ARCH §12.5). A price change or a 2× writer price makes Quick refuse to start. D-13 decides the cap.
- **Placeholders:** prices, 150 output tokens per second, 6 to 8 s verifier calls, the 3.5 characters-per-token estimator, and the 90 s heartbeat and 120 s drain defaults are all proposals to measure at M1.
- **Local verifier (Ollama, qwen3-vl:8b-instruct): accurate on a small set, not shown to meet the gate, too slow on this laptop** (4 GB GPU, 15.7 GB RAM, model 76 percent on CPU): 40 s per batch (67 s at production size), verifier stage 160 to 270 s against Quick's 120 s; false-accept rate 7.7 percent on 26 pairs; the 4B model accepted 5 of 6 injections. A re-run on the expanded 53-pair set was stopped for low memory and not repeated. Ollama truncates prompts silently above its 4,096-token default context (set `OLLAMA_CONTEXT_LENGTH=8192`); the app detects it. PRD time limits were not relaxed. Details: ARCH §8.7, `eval/reports/`.
- **NVIDIA free endpoint is slow and flaky:** about 8 tokens per second and 30 to 50 percent of verifier requests stalled to their timeout on 2026-10-22, with or without concurrency; no real report has completed on it yet (every run failed closed). `.env.example` keeps `RUN_TIME_FACTOR=1.0` (PRD limits) with `VERIFIER_TIMEOUT_FACTOR=3.0` for the local verifier. Tests never read the real `.env` (they use `ENV_FILE`).
- **NVIDIA trial API:** parameter names, structured output and rate limits rest on documentation only (ARCH §8.6). Run `eval/provider_probe.py` before trusting them. Budgeting rates in `core/price_sheet_nvidia_free.json` expire on 2027-01-20.
- **Open advisories:** `pillow` (a Streamlit dependency) has 8 advisories fixed only in a version Streamlit 1.66.0 does not allow (ledger ruling 21).
- **Unverified outside facts:** Tavily and LLM wire formats, Streamlit options (fragments, health route, theme sections, SIGTERM handling), `tldextract` offline mode, and each open-source repository's license, telemetry and activity. Flagged "verify at M0" in the documents.
- **Product tradeoffs:** reports are terse lists of verified claims; a reload or restart ends a run; English only; one process; dark theme is P1.
- **Process debt:** the documents were scored by the same agent that wrote them. An independent review has not happened.

## 5. Unresolved Questions (need the user)

1. Who are the product owner, engineering owner and the two independent reviewers, and what is their availability?
2. ~~Which models?~~ Decided for development (2026-10-22): Nemotron 3 Ultra and Gemma 4 31B on NVIDIA Build. Still open: models for the pilot, since NVIDIA's trial API is for prototyping.
3. Where will the pilot be hosted, and what gateway provides access control?
4. Raise Quick's admitted cap above $0.75, or lower its claim cap or repair limit?
5. Which privacy and data-protection rules apply to the pilot users?
6. Initialize a git repository here, and what branch and commit conventions does the user prefer?
7. Adopt any of Instructor, DeepEval or Promptfoo, or Trafilatura (conditional)?
8. Approve the design-owned "next step" lines and plain-language reason sentences in DESIGN §9.

## 6. Important Discoveries and Lessons

- Streamlit reruns the script on every widget event, and a full reload creates a new session. Anything that must survive lives outside the script thread.
- Worst-case cost figures were wrong three times (batch counts, the replan, repair). Derive every bound from an enforced cap, then recompute.
- Append-only logs cannot hold events that happen after a run ends. Use separate events and join by run ID.
- The review-and-fix loop found real defects at every round. Scores plateau near 90 to 92 until measurements exist, so the PoC (M1) is the next real evidence.
- Cross-references drift. Run the cross-reference check (tracker task M0-13) after any edit that moves a section.
- On this Windows machine use `uv run ...` for everything (the project venv is Python 3.11); a bare `python` is a different interpreter and `python3` does not exist.
- The installed Anthropic SDK's `messages.create` takes no `temperature`, and the `openai`/`anthropic` packages in this environment are newer than most documentation. Check the installed signature before trusting an example.
- `ruff format` rewrites many files at once; run tests after it, and re-read a file before editing it.

## 7. Paths and Conventions

- **Project folder:** `D:\Rontu\Python\AI-Agent\AI-Reserach-Agent` (the folder name is spelled "Reserach"; keep it).
- **Code layout:** ARCH §4.1 (updated to the built tree). Entry points: `app.py`, `demo.py`, `entrypoint.py`.
- **Planned code layout:** ARCH §4.1. Import rules: ARCH §4.3. Naming and standards: rules.md §4.
- **Citations of requirements:** write "PRD FR-20", "ARCH §10.4", "DESIGN §9.1".
- **Prices, models and provider facts** belong in the price sheet and decision log once they exist, not in these files.

## 8. Recent Meaningful Changes (newest first)

- 2026-10-22 (verifier): added the Ollama verifier provider (placeholder key, json_schema, truncation guard, `VERIFIER_PARALLEL`), a 45-pair synthetic development set and `eval/verifier_eval.py`, measured two local models, set `.env.example` and the user's `.env` to NVIDIA writer plus local 8B verifier with the PRD time limits unchanged; ledger rulings 59 to 70.
- 2026-10-22 (latest): ran the pipeline against the live endpoint three times (demo corpus, no Tavily): stalls, not concurrency, break the verifier stage; a timeout at the run's deadline now reports TIMEOUT, failures show their exception class on the page, `RUN_TIME_FACTOR` scales only the wall clock; ledger rulings 54 to 58.
- 2026-10-22 (later): probed the live NVIDIA endpoint at the user's request (writer works; Gemma 4 31B unusable), switched the verifier to `openai/gpt-oss-20b`, added per-role timeout factors and `ENV_FILE`, made tests ignore the real `.env`; ledger rulings 48 to 53.
- 2026-10-22: added NVIDIA Build support (OpenAI-compatible adapter with base URLs, model-family independence check, free-prototype price sheet with expiry, shared rate limiter, provider disclosure on the About page, `eval/provider_probe.py`); PRD v1.8, ARCH v1.5 (ADR-020, §8.6), rules and design updated; ledger rulings 33 to 47.
- 2026-10-21: built the project (see `docs/build-ledger.md` for 32 rulings). ARCH §4.1 updated to the built tree; tracker statuses and §9 evidence updated; README written.
- 2026-10-21: created design.md, memory.md, rules.md and tracker.md. Architecture v1.4 added `ui/theme.py`, the narrow HTML rule (ADR-019), per-component report rendering, and the folder-layout entries those files need.
- 2026-10-21: PRD v1.7 applied the architecture review (replan, token-based batches, repair limits, restart and expiry states, drain, reviewer roles). Architecture v1.3 added repair limits and the drain design.
- 2026-10-21: architecture v1.1 and v1.2 added the open-source reference section and fixed eight review defects.
- 2026-10-21: architecture v1.0 written. PRD v1.0 to v1.6.1 revised through repeated reviews.

## 9. Next-Session Handoff

1. Read rules.md, then this file, then tracker.md "Immediate next tasks".
2. The build is done up to what code alone can do. The next steps need the user: owners and reviewers (M0-01), git (M0-03), and running the supervised probe with their own NVIDIA and Tavily keys (M0-09, `uv run python -m eval.provider_probe --yes-call-live-providers`).
3. Then build the fixtures and dev set (they need human labels) and run the PoC checkpoint (M1-21).
4. Update this file and tracker.md before ending the session.
