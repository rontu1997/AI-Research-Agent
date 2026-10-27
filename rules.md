# AI Coding Rules: AI Research Agent

| Field | Value |
|---|---|
| Document | rules.md |
| Version | 1.0 — proposed; applies once the user approves it |
| Applies to | AI coding agents working in this project (humans may follow it too) |
| Aligned with | prd.md v1.7, architecture.md v1.4, design.md v1.0 |
| Updated | 2026-10-21 |

**Status of these rules.** They enforce engineering behavior. They do not create, change or relax product requirements. If a rule here conflicts with the PRD, the PRD wins, work stops, and §13 applies. Section references written "PRD §n", "ARCH §n" and "DESIGN §n" point to those files, and the prefix covers the comma-separated sections that follow it; a bare "§n" elsewhere points here.

---

## 1. Agent Role and Responsibilities

**Role.** Implement and maintain the AI Research Agent as specified, verify the work, keep the documents and tracker current, and raise ambiguity instead of guessing.

**Responsible for:**
- Matching the PRD's requirements, hard invariants (Appendix A) and gates.
- Writing tests first for logic, running them, and reporting results as they are. A failing test is reported with its output. A step that was skipped is reported as skipped.
- Keeping secrets, user data and logs safe (§7).
- Updating tracker.md, memory.md and any affected document in the same piece of work (§9).

**Not allowed to:**
- Change, relax or reinterpret a requirement without an approved change (§13).
- Approve a decision (D-01 to D-13), name an owner or reviewer, or mark a gate passed.
- Spend money on live provider calls beyond a cap the user approved.
- Build anything (product code, scaffolding, installed dependencies, a new project) before the user approves the documents. Reading and exploring are fine.
- Publish, deploy, commit or push unless the user asks (§10).

**Working loop for every task:** read the task and its acceptance references; write a failing test; implement the smallest change that passes; run the full required checks (§8); update the documents (§9); report with evidence.

**Workflow skills.** If the harness offers workflow skills (design before building, test-driven development, systematic debugging, verification before completion), follow them. They do not override this file or the PRD.

**Chat versus files.** The terse chat style is a conversation setting. Files written to disk use normal prose.

---

## 2. File-Reading Order and Source-of-Truth Hierarchy

### 2.1 Reading order at the start of a session

1. rules.md (this file).
2. memory.md (state, decisions, lessons, handoff).
3. tracker.md: "Immediate next tasks", then the chosen task and its acceptance references.
4. The PRD sections the task names.
5. The architecture sections the task names.
6. design.md, for any UI work.
7. Existing code and tests for the area.

Do not read the whole PRD every time. Read what the task needs, and read it fully.

### 2.2 Hierarchy (highest first)

1. **prd.md** owns requirements, user-facing copy (PRD §7.3), metrics, gates and change control.
2. **architecture.md** owns structure, contracts, the cost model and ADRs.
3. **design.md** owns layout, components, tokens and accessibility rules.
4. **rules.md** owns process.
5. **tracker.md** owns status and the task list. It never defines requirements.
6. **memory.md** is a summary. It loses to every other file.
7. **Code and comments** show current behavior. They never define a requirement.

When two sources disagree, the higher one wins, the disagreement is recorded, and §13 applies. Never edit a higher-level document to match lower-level code without an approved change.

---

## 3. Approved Technologies and Dependencies

### 3.1 Approved (ARCH §2)

| Area | Approved |
|---|---|
| Language | Python 3.11 or newer |
| UI | Streamlit, version pinned at M0 |
| Schemas | Pydantic v2 |
| HTTP | `httpx` |
| Model SDKs | The writer provider's SDK and the verifier provider's SDK, with built-in retries disabled |
| Search | OpenAI web search through the `SearchProvider` adapter in the shipped live configuration; Tavily remains available for legacy configurations |
| Model providers | The shipped live configuration uses GPT-6 Luna through the OpenAI adapter for writing and review. Because both roles use the same model, describe the review as non-independent. Legacy provider adapters remain for existing tests and configurations. No other provider SDK without approval |
| Domains | `tldextract` from its bundled snapshot with network fetch disabled |
| Testing | `pytest`, `hypothesis`, `pytest-cov`, Streamlit `AppTest`, Playwright with axe-core |
| Quality | `ruff`, `mypy`, `import-linter`, `pip-audit`, a secret scanner |
| Evaluation | `numpy` in `eval/` only |
| Packaging | Docker, with a hashed lockfile |

### 3.2 Not approved

The twelve repositories in ARCH §16 (GPT Researcher, STORM, Trafilatura, Instructor, DeepEval, Promptfoo, Crawl4AI, Arize Phoenix, Ragas, Docling, LangGraph, SearXNG) are references or candidates. None may be added until it passes the adoption review in ARCH §16.3 and has an ADR. Crawl4AI, Docling and Trafilatura's fetching also need PRD change control first.

### 3.3 Adding any dependency

State in the change: what it does, why the standard library or an approved package is not enough, its license, maintenance health, what data it sends or stores, and its footprint. Then pin it with a hash, run `pip-audit`, and update ARCH §2 if it enters the runtime. A dependency is rejected if it fetches pages, sends telemetry by default, stores prompts, or retries model calls outside the guarded call (ARCH §10.2).

### 3.4 Models and providers

Model IDs come only from configuration. No new provider is added without PRD change control. Keys are never hard-coded.

---

## 4. Coding Standards and Naming Conventions

### 4.1 Standards

- Type hints on every public function. `mypy` strict on `core/` and `pipeline/`. `ruff` for lint and format. Line length 100 (proposed).
- Pydantic models use `extra="forbid"`. No `Any` in domain code. No bare `except`. No `print`; use typed telemetry events (ARCH §11.2).
- Checks in `pipeline/` are pure functions. Side effects live only in adapters, telemetry and the run manager.
- Deadlines use a monotonic clock, injected so tests can control it.
- Sorting must be deterministic. Ties break by canonical URL (PRD §6.2).
- Errors use the taxonomy in ARCH §6.4. Exception text never reaches the UI or a log.
- No user-facing string outside `ui/copy.py`. No color, spacing or font value outside `ui/theme.py` (DESIGN DR-1, DR-3).
- Comments explain why, not what. No commented-out code. Match the style of the surrounding code.
- Changing a prompt bumps its version and triggers the fixture scorecard on the dev halves (§8).

### 4.2 Naming

| Item | Convention |
|---|---|
| Modules and functions | `snake_case`; module names match ARCH §4.1 |
| Classes | `PascalCase` |
| Constants | `UPPER_SNAKE_CASE` |
| Enum values | Lowercase strings that match the PRD (`snippet`, `extracted`, `metadata-only`, `completed`, `partial`, `failed`) |
| Error codes and reason codes | `UPPER_SNAKE_CASE` as in ARCH §6.4 and ARCH §5.4 |
| Telemetry events | `domain.event`, for example `run.finished` |
| Widget keys | `component:id` (DESIGN DR-11) |
| Prompt files | `prompts/<role>.v<N>.md` |
| Fixture files | JSONL with a `schema_version` field |
| Tests | `tests/<package>/test_<module>.py` |
| Task IDs in commits | The tracker ID, for example `M1-10` |

---

## 5. Repository and Folder Structure Rules

1. Follow ARCH §4.1. Add no top-level folder or module without updating ARCH §4.1 in the same change, and add an ADR if the change affects layering.
2. The five import rules in ARCH §4.3 are enforced by `import-linter`. Never disable, loosen or bypass them.
3. Sealed evaluation data lives outside the application image and outside code paths that tuning can read (ARCH §7.4, PRD §11.1).
4. `.env`, `logs/`, `state/` and `eval-data/` are git-ignored. `.env.example` holds placeholders only.
5. No generated files, secrets or large binaries in the repository.

---

## 6. Component Reuse Principles

- **UI.** Use the components in DESIGN §7. A new visual need is first met by a variant. A new component is added to DESIGN §7 before or with the code. `app.py` contains layout only.
- **Single implementations.** These exist once and are extended, never duplicated: `status_rules.evaluate`, the escaping function, `normalize_for_match`, the token estimator, the guarded call and the budget ledger.
- **Search first.** Before writing a helper, search the repository for an existing one.
- **Copy and tokens.** Reuse existing `ui/copy.py` keys and `ui/theme.py` tokens.

---

## 7. Security and Secrets-Handling Rules

1. Secrets come only from the environment or the host's secret store. Load them once into `SecretStr`. Never log, print, commit, export or display them. Never put them in `session_state`, prompts, error text, fixtures or screenshots.
2. If a secret is exposed, stop, tell the user and recommend rotating it. Do not rewrite history without permission.
3. Never fetch a URL chosen by a model or a user. Only the configured search adapter makes outbound requests, plus the model providers. Unit tests have no network access.
4. Treat the topic and all retrieved text as untrusted data. Pass them in delimited blocks. Writer and verifier models get no tools and never emit URLs. The OpenAI search adapter may use the hosted web search tool; only URLs and snippets from search results enter the registry.
5. Render third-party text as escaped plain text everywhere, including the export. `unsafe_allow_html=True` is allowed only in the helpers named in ARCH ADR-019.
6. Log only typed allowlisted events. Never log topics, queries, passages, quotes, claim or report text, full URLs, IP addresses or session IDs (ARCH §11.1).
7. **Never fabricate** research citations, sources, URLs, quotes, test results or metrics.
8. Never weaken a trust check (quote match, numeric guard, verifier gate, sentence rules, status thresholds) to make a test or metric pass. Changing one needs PRD change control and, where PRD §11.1 says so, a fresh holdout.
9. Live provider calls go only through the measurement harness under a spend cap the user approved. Ask before the first live call. CI makes no live calls except the nightly canary with a tiny cap.
10. Downloaded files and archives are untrusted. Put each in its own new empty directory, keep scripts elsewhere, and run Python that reads them with `-I`.
11. No real user topics in tests, fixtures, logs or documents.

---

## 8. Testing Requirements and Quality Gates

### 8.1 Rules

- Write the failing test first for any logic change. Watch it fail for the expected reason, then implement.
- Never claim a test passes without running it and reading the output.
- Fix or remove flaky tests. Do not retry them silently.
- Never run tuning against a sealed fixture half or the holdout, and never read sealed files during development. If a sealed set is exposed, record it in the burn history (PRD §11.1).

### 8.2 What to run, by change

| Change | Required tests |
|---|---|
| Planner, source processing, checks, ledger, sentence rules, status rules | Unit and property tests, component tests, boundary tests (PRD tests 3–15, 27, 34, 37, 39) |
| Capacity, budgets, retries, rate limits, provider-fault handling | Unit tests, pool-accounting and startup-check tests, scripted provider faults and outage simulation (PRD tests 2, 16, 20, 21, 32, 38, 42) |
| Adapters | Contract tests against recorded fixtures, error-translation tests |
| Run manager, watchdog, drain | Concurrency tests (PRD tests 17–19, 40) |
| UI | `AppTest`, `poll_once()` tests, contrast and token tests, KPI counter tests; browser tests before a release candidate (PRD tests 1, 18, 22–24, 26, 28–30, 36, 41) |
| Prompts, models, verifier, scan | Fixture scorecards on the dev halves, and a PoC re-run before any new holdout |
| Export or escaping | Golden-file tests in at least two Markdown renderers (PRD tests 22, 35) |
| Prompt-injection and secret-handling paths | Attack fixtures and security tests (PRD tests 25, 35) |
| Measurement harness and evaluation tooling | Hand-computed fixtures (PRD tests 31, 33) |
| Settings, price sheet | Startup call-graph check against the shipped files (PRD test 21) |
| Documents only | The cross-reference check (task M0-13) |

### 8.3 Required commands

These are the canonical commands. They become real in tasks M0-04 and M0-12. Until then, state plainly that they cannot run yet.

```
python -m ruff check .
python -m ruff format --check .
python -m mypy core pipeline
lint-imports                      # runs the import-linter contracts (confirm the command at M0-04)
python -m pytest -q
python -m pip_audit
<secret scanner>                  # chosen in M0-12
```

All must pass before a task can be Done. Coverage targets are in ARCH §13.4.

### 8.4 Release gates

The coding agent does not run the sealed holdout, grade claims or declare a gate passed. Benchmark runs follow PRD §11 with the user's approval and named reviewers.

---

## 9. Documentation Update Requirements

| When this happens | Update in the same piece of work |
|---|---|
| A requirement changes | PRD first (version bump, changelog row, change control), then ARCH and DESIGN |
| A contract, structure or cost figure changes | ARCH (and an ADR if it is a decision), and the PRD if the change is visible in a requirement |
| A UI component, state, token or copy changes | DESIGN (and `ui/copy.py` keys) |
| A task finishes or its status changes | tracker.md status and verification result |
| A decision is made | The decision log and the matching ADR |
| A prompt changes | The prompt file version and a note in the task |
| A session ends | memory.md (and tracker.md "Immediate next tasks") |

Rules:
- Documents are written in normal prose. The terse chat style is for conversation only.
- After any edit that moves or renames a section, run the cross-reference check (task M0-13).
- Keep memory.md short: it summarizes decisions and links to the other files instead of copying them. Remove entries that stop being true.
- Never edit the PRD to match code without an approved change.

---

## 10. Git and Change-Management Conventions

- **Repository state.** The folder is not a git repository yet (task M0-03). Do not run `git init` without the user's approval.
- **Commits and pushes** happen only when the user asks. Do not push, force-push, amend or rewrite shared history without permission. Never skip hooks.
- **Commit style.** One purpose per commit. Imperative subject of at most 72 characters, a body that explains why, and the task ID. End the message with the attribution line the harness or the user specifies.
- **Branches** (proposed): `task/<ID>-<short-slug>`, one task per branch.
- **Change description** (commit body or pull request): task ID, acceptance references, commands run with results, documents updated, risks.
- **Never commit** secrets, `.env`, logs, state files, evaluation data or large binaries.
- **Requirement changes** follow PRD §19 change control, need the user's explicit approval, and are recorded in the decision log and the PRD changelog.
- **ADRs are append-only.** Supersede an ADR with a new one instead of rewriting it.

---

## 11. Prohibited Actions and Unsafe Shortcuts

1. Fabricating a citation, source, URL, quote, metric or test result.
2. Printing, logging, committing or exposing a provider key or any secret.
3. Adding an outbound request path other than the configured adapters, or fetching model- or user-chosen URLs.
4. Weakening or bypassing the quote match, numeric guard, verifier, sentence rules, coverage scan or status thresholds.
5. Marking a claim supported, a status Completed, or a gate passed without the required checks.
6. Running pipeline work in the Streamlit script thread.
7. Putting a result copy in `session_state`, or any content in logs.
8. Using `unsafe_allow_html=True` outside the allowed helpers, or rendering third-party text unescaped.
9. Adding a dependency without the justification in §3.3, or one that is on the unapproved list.
10. Disabling `import-linter`, type checks, lint rules or tests to get a green build.
11. Tuning prompts, thresholds or the verifier against the sealed halves or the holdout.
12. Changing a requirement, threshold, cap or decision without the change process.
13. Retrying model calls outside the guarded call, or enabling SDK-level retries.
14. Making live provider calls without an approved spend cap.
15. Committing, pushing, initializing a repository, deploying or publishing without being asked.
16. Deleting or overwriting files you have not looked at.
17. Using real user topics in tests, fixtures or documents.
18. Describing unimplemented behavior as working.
19. Leaving a TODO that has no tracker entry.
20. Silently choosing between conflicting requirements (§13).
21. Building before the user approves the documents (§1).

---

## 12. Definition of Done

### 12.1 Every task

- [ ] The task's acceptance references in tracker.md are met, with evidence recorded in tracker.md §9.1 as the date, the command or check, and the result.
- [ ] Tests were written first, now pass, and the commands and results are recorded (§8).
- [ ] Lint, types and import rules pass.
- [ ] The PRD hard invariants (Appendix A) still hold.
- [ ] No secret, content or URL appears in code, logs, fixtures or output.
- [ ] Affected documents and tracker.md are updated (§9).
- [ ] No TODO exists without a tracker entry.

### 12.2 Extra checks by type

| Type | Also required |
|---|---|
| Pipeline | Dev-half fixture scorecard re-run if a check or prompt changed; call-graph check still passes; events are typed |
| Capacity or cost | Startup check passes with the shipped price sheet; worst-case figures recomputed if a bound changed |
| UI | All states in DESIGN §9.1 render; keyboard walkthrough; contrast test passes; copy comes from `ui/copy.py` |
| Export | Escaping golden files pass in two renderers; Partial files are marked |
| Documents | Cross-reference check passes; version and changelog updated |
| Release candidate | The PRD §16 checklist, with evidence and the user's sign-off |

"Done" means verified, not just written. Run the commands and read the output before saying so.

---

## 13. When Requirements Are Ambiguous or Contradictory

1. **Stop** work that depends on the unclear point. Other independent work may continue.
2. **Classify** it: missing detail, conflict between documents, conflict between a document and code, or a requirement that cannot be met.
3. **Apply the hierarchy** (§2.2). If a higher document settles it, follow that document and note the resolution in the task.
4. **Otherwise ask the user.** Ask one question, give a recommended option, and say what each option changes.
5. **Record it** in the decision log, in tracker.md "Bugs, blockers and risks", and in memory.md "Unresolved questions".
6. **After an answer that changes a requirement,** follow PRD §19 change control and update the documents (§9).
7. **Small choices** that do not change user-visible behavior or any contract may be made by the agent. Mark them "agent's call" in the commit or ADR note so a reviewer can check them.

Never pick silently, implement both readings, or change an expected result to make a test pass.

---

## Appendix A. PRD Hard Invariants (quick reference)

These are PRD §9.5. Each one must hold after every change.

1. Every displayed material factual sentence is a ledger claim with valid citations, a quote that passed the checks, and a `supported` verdict.
2. Every cited URL comes from the current-run registry. No model-created URLs.
3. Metadata-only sources and unattributed syndicated copies never count as corroborating evidence.
4. No unsupported or uncertain material claim is shown as fact.
5. Counts, statuses and thresholds are computed by deterministic code, never chosen by the writer.
6. Every external call is admitted by a bounded reservation, with retries and wall-time enforced.
7. No third-party content can change instructions, secret access, tools or fetch targets.
8. Partial and Failed never appear as Completed, and only verified content is exported.
9. The pipeline never runs in the Streamlit script thread, and reruns within a session cannot start, duplicate or end a run.
