# Product Requirements Document (PRD): AI Research Agent

| Field | Value |
|---|---|
| Product | AI Research Agent |
| Artifact | prd.md |
| Version | 1.8 — v1.7 plus approved provider changes: NVIDIA Build and a local Ollama verifier are supported (2026-10-22) |
| Status | Implementation-review candidate; M0 decisions and release gates remain unapproved |
| Updated | 2026-10-22 |
| Accountable product owner | Project sponsor — individual to be named before Milestone 1 |
| Engineering owner | Lead developer — individual to be named before Milestone 1 |
| Proposed MVP audience | Single-user/local or access-restricted internal pilot |
| Proposed initial platform | Python + Streamlit web application |
| Decision status | Defaults below are proposals, subject to owner sign-off (§4 and §19) |

**Product principle:** Traceable evidence and honest uncertainty take priority over polished but unsupported claims. Runtime passage-support checks reduce unsupported claims but do not guarantee factual truth.

---

## 1. Executive Summary

The AI Research Agent accepts a user-supplied topic, searches multiple public websites, assesses relevant evidence, compares potentially contradictory material, and produces a structured report with numbered clickable citations and a bibliography. Users can choose Quick or Deep research and download the result as Markdown.

The differentiator is **auditable, passage-checked evidence**. Every factual sentence in the report is a *ledger claim*: an atomic assertion tied to a verbatim quoted span inside a specific retrieved passage. Before publication, each claim passes deterministic checks (the quote exists in the stored passage; every number and date in the claim appears in the quote) and an independent semantic support check. Cited URLs must originate from the current research run. This is evidence-support checking, not independent confirmation of real-world truth. Users can open an Evidence Details panel to see, for each claim, the exact quoted passage the checks used. The product discloses snippet-only support, conflicts, abstentions, and partial coverage, and a Completed status means minimum evidence thresholds were met, not that the topic is exhaustively covered.

**MVP release:** locally runnable and optionally deployed behind access controls. Public multi-user launch is a later, separate gate requiring the controls in §17.

---

## 2. Problem, Users, and Success

### 2.1 Problem

Manual web research involves searching diverse sources, separating authoritative evidence from commentary, resolving duplication and contradictory findings, and maintaining citations. A generic LLM answer can be persuasive while including fabricated references or claims not backed by the linked text.

### 2.2 Primary user job

When I enter a topic I am unfamiliar with, help me understand the most important findings and disagreements, and give me references I can inspect.

| Persona | Research need | Example input |
|---|---|---|
| Student | Accessible overview with sources | "What causes urban heat islands?" |
| Analyst | Industry or market scan | "EV charging infrastructure trends in India" |
| Content researcher | Evidence-backed brief | "Generative AI in education: benefits and risks" |
| General professional | Fast orientation | "Current challenges of green hydrogen" |

### 2.3 Goals

1. Complete the topic-to-cited-report workflow with minimal user input.
2. Cover materially different aspects of the topic and multiple independent domains where sources exist.
3. Make important claims inspectable and separate fact, interpretation, uncertainty, and disagreement.
4. Support Quick and Deep modes with transparent retrieval limits and costs.
5. Export the report with functioning Markdown reference links.
6. Fail safely and transparently when retrieval, model, or citation validation fails.

### 2.4 Non-goals for the MVP

- Guaranteeing truth of all internet content or professional-grade fact checking.
- Bypassing paywalls, website restrictions, or publisher terms.
- Persistent research history, collaborative workspaces, recurring monitoring, or follow-up chat.
- PDF/DOCX exports or custom source filters.
- Public anonymous, unlimited, multi-tenant access.
- Searching private user accounts, documents, or paywalled repositories.
- Fluent, free-form synthesis prose. The pilot deliberately trades reading polish for verifiability (see §6.3).

### 2.5 Alternatives and differentiation (qualitative, not a market study)

| Approach | Benefit | Limitation relevant to this product | MVP response |
|---|---|---|---|
| Manual web search | Reader directly inspects original sources | Slow to consolidate, compare and cite | Organize sources and claims into one report |
| Generic AI chat answer | Convenient narrative | References or apparent support may not reflect actual source passages | Enforce source registry, quoted-span matching and runtime passage verification |
| AI search / deep-research products | Broad retrieval and synthesized findings | Source visibility, cost, and inspectability differ by product/version | Explicit evidence modes, bounded budgets, download, abstentions |

No claim of superior quality over a named competitor is authorized without a controlled side-by-side evaluation.

### 2.6 Metrics and release evidence

Metrics are grouped by what they actually measure. *Integrity* metrics confirm that code-enforced rules hold. *Screening* metrics measure the verifier and scan components in isolation on labeled fixtures. *Quality* metrics measure shipped output through human review on a sealed holdout.

| Metric | Class | Proposed pilot decision threshold | Measurement and caveats |
|---|---|---|---|
| URL/ID referential integrity | Integrity | 100% of generated outputs | Deterministic tests against the current-run registry |
| Ledger integrity | Integrity | 100% of displayed material factual claims have a ledger record that passes the quote-match and numeric-guard checks (§8.3) | Deterministic. This confirms the pipeline ran; it is **not** a quality measure |
| Verifier screening | Screening | On the sealed fixture test half (§11.2): ≤2 false accepts among ≥60 negative pairs (≥20 adversarial); zero false accepts on injection-bearing pairs; ≤6 false rejects among ≥30 supported pairs | Report counts and Wilson intervals (the upper bound at 2/60 is about 11%). A screening gate, not a guarantee |
| Coverage-scan accuracy | Screening | ≥29 of ≥30 planted unledgered factual sentences detected, and ≤10% of ≥200 clean interpretation/transition sentences falsely flagged | Fixture reports with planted sentences plus clean reports (§11.2) |
| Human-reviewed grounding | Quality | ≥92% observed fully supported over ≥160 sampled claims from ≥50 holdout reports; cluster-bootstrap 95% lower bound ≥85% | Report-level cluster bootstrap (§11.3). Not proof of universal correctness |
| Eligible-topic completion | Quality | ≥95% observed (≥48 of 50) among ≥50 mode-eligible holdout topics per mode | Eligibility defined per mode and sealed before the run (§11.1); audited provider-outage rule in §11.3 |
| Terminal-state correctness | Quality | ≥95% on Partial/Failed fixtures and all hard-case holdout topics; zero source-poor items labeled Completed | Thresholds in §6.4; fixture adjudication |
| Domain diversity | Quality | ≥80% of eligible-topic runs include ≥3 registrable domains | Eligibility inventory plus retrieval-date evidence |
| Essential-question coverage | Quality | Mean coverage ≥0.60 (Quick) / ≥0.70 (Deep) over Completed holdout reports; ≤10% of Completed reports below 0.40 | Reviewers score blind-authored essential questions against displayed supported claims (§11.6). Provisional until the D-13 checkpoint |
| Readability | Quality | Holdout median overall readability ≥3.5/5 and ≥70% of reports ≥3.0; the dev-set median at the PoC triggers a review if <3.0 | Reviewer rubric (§11.7). Provisional until the D-13 checkpoint; a product-quality target, not a safety gate |
| Spurious budget stops | Quality | ≤2% of healthy-provider benchmark runs end in a budget-stop status | Guards against reservation rules starving healthy runs (§10.1) |
| Report / export completeness | Integrity | 100% of Completed outputs contain required headings, verifiable references and valid UTF-8 Markdown | Automated checks |
| User feedback | Informational | Feedback control present; event recorded without raw report storage; no usefulness target initially | Optional useful / not useful action |

Benchmark results and methodology must be published in the internal release checklist. No unmeasured quality claim may be used in marketing.

### 2.7 Product KPIs (informational in the pilot)

KPIs show whether the product is useful. They do not gate release. Targets are set after a 4-week pilot baseline. Data comes from aggregate counters only (D-08, FR-44) and never from topics, reports, passages or user identifiers.

The pilot's main learning question is: **do users open the evidence, and do they find the verified, terse report useful?**

| KPI | Definition | Source | Initial target |
|---|---|---|---|
| Activation | Share of invited pilot users who start at least one run in their first week | Pilot roster, or host access logs if the host provides them; not app telemetry | Baseline first |
| Run outcome mix | Share of runs ending Completed, Partial and Failed, with reason codes | Status telemetry | Baseline first. Differs from the gated eligible-topic completion rate, which is measured on the benchmark |
| Evidence engagement | Share of Completed and Partial reports where Evidence Details was opened at least once | `evidence_opened` counter | Baseline first |
| Export rate | Share of reports downloaded | `export_downloaded` counter | Baseline first |
| Useful ratio | Useful ÷ (Useful + Not useful) votes | Feedback votes (FR-26) | Baseline first; do not interpret below 30 votes |
| Time to report | p50 and p95 end-to-end seconds per mode | Stage timings | NFR-02 targets |
| Cost per run | Median and p95 estimated actual cost per mode | Cost telemetry | §6.1 targets |
| Repeat use | Share of pilot users with at least two runs in a week | Pilot roster or host-level aggregates | Baseline first |

---

## 3. Scope and Release Phases

| Capability | Pilot MVP (P0) | Public launch | Later |
|---|---|---|---|
| Topic submission, Quick/Deep mode, stage status, cited report, Markdown export | Required | Required | — |
| Search/provider evidence registry and deterministic ranking | Required | Required | — |
| Citation ID/URL provenance, quoted-span match, numeric guard, runtime claim-to-passage verifier | Required, fail closed | Required + strengthened evaluation | Inspectable evidence view |
| Sentence typing and coverage scan | Required | Required | — |
| Objective completed/partial/failed thresholds | Required | Required | — |
| Verifier fixture scorecard; dev/holdout benchmark split; annotator protocol | Required | Expanded samples and independent review | Ongoing regression monitoring |
| Background run manager (survives Streamlit reruns; full page reload is not recoverable) | Required | Replaced by shared job queue with reconnect | Reload-recovery token (FR-38) |
| Evidence Details panel (claim, matched quote, source link, evidence mode) | Required | Required | Highlighting and filtering |
| Essential-question coverage evaluation | Required (measured, provisional thresholds) | Expanded sample | — |
| M1 proof-of-concept checkpoint (cost, latency, grounding feasibility) | Required before committing to M2 | — | — |
| Session-only retention, clear-session, About/Privacy, pilot FAQ, feedback | Required | Public notice, support procedures | Opt-in history |
| English-only pilot input policy | Required | Explicit supported-language policy | Multilingual mode |
| Local or access-restricted single-process deployment with in-process caps | Required | Shared distributed quotas/auth and billing controls | Team plans |
| PDF/DOCX, saved research, source filters, follow-up Q&A, scheduling | — | Optional, separately scoped | Planned |

The pilot is not described as producing fully fact-checked or universally accurate research. It checks whether assertions are entailed by retrieved text, whose underlying truth may remain uncertain.

---

## 4. Proposed Decisions and Lean Governance

All entries remain proposals, not project-owner approvals. The smallest decision set needed to start coding is D-01 to D-05, D-10 and D-11. The rest can be finalized before hosting or evaluation as specified.

| ID | Decision | Proposed default | Approver / due | Blocks |
|---|---|---|---|---|
| D-01 | Language | English pilot only; non-English script detection and rejection per §6.7; English output | Product owner / M0 | Pilot |
| D-02 | Evidence retrieval | Search snippets plus provider-permitted extracted passages; label modes; no arbitrary crawling | Tech lead / M0 | Pilot |
| D-03 | Storage | No persistent topic/report/excerpt storage; in-process session memory only. Feedback votes, a small daily spend counter and drain marker files are operational metadata (see D-08) | Product owner / M0 | Pilot |
| D-04 | Hosting | Local or authenticated/access-restricted **single-process** pilot | Product owner / M0 | Hosted pilot |
| D-05 | Trust policy | P0 atomic-claim ledger, quoted-span match, numeric guard, independent semantic support check, sentence typing, fail closed | Product + QA / M0 | Pilot |
| D-06 | Freshness | Show retrieval date; prioritize fresh material for time-sensitive topics | Product / M2 | Pilot |
| D-07 | Budgets | Server-side pre-call admission using worst-case configured prices/token caps and a startup call-graph check; no asserted exact external billing hard stop | Eng + product / M2 | Pilot |
| D-08 | Logs and feedback | Redacted operational metadata, including feedback votes keyed by `run_id`, retained ≤7 days where the host permits; counters may be kept longer only without `run_id`; documented provider retention | Eng + privacy / M3 | Hosted pilot |
| D-09 | Public access | No anonymous public launch before §17 gates and distributed rate limiting | Sponsor / public gate | Public only |
| D-10 | Status rules | Fixed source/claim/domain/snippet thresholds in §6.4, **frozen before holdout runs** (revisable once, at the D-13 checkpoint, using dev-set data only); later changes require a new PRD version and a fresh holdout | Product + QA / M0 | Pilot |
| D-11 | Verifier independence | Verifier uses a different model family from the writer where available. Family is the model's own family, not its vendor prefix or hosting platform: Nemotron with Gemma on NVIDIA Build qualifies, while `nvidia/llama-3.1-nemotron-70b-instruct` with `meta/llama-3.1-70b-instruct` does not (both Llama), and a second provider serving the same family does not satisfy it; if not, the correlated-error risk is disclosed and the §11.2 fixture gate is mandatory | Eng + QA / M0 | Pilot |
| D-12 | Annotation staffing | Gate claims are labeled by two reviewers independent of the engineer who wrote the writer/verifier prompts (§11.2, §15.1), named at M0 with a written availability schedule (§15); fallback is single-annotator labeling with an "evaluation-only" label | Product owner / M0 | Pilot grounding sign-off |
| D-13 | PoC checkpoint and provisional targets | Cost caps (including whether to raise Quick's admitted cap, §10.3), latency, status-threshold (§6.4), coverage and readability targets are provisional until the M1 proof-of-concept checkpoint (§15); revised once from dev-set data, then frozen together with the core requirements | Product + eng / M1 exit | Pilot |

**Governance minimum:** one named accountable product/release owner and one engineering owner (may be the same person for a solo project), plus **two reviewers independent of the engineer** for grounding sign-off (D-12). Record role, chosen default or deviation, approver, and date in a one-page decision log. Privacy, legal and security review (one reviewer may cover all three) is required for hosting, not for local coding. An unresolved M0 blocker prevents labeling the pilot approved, but does not prevent prototyping with clearly marked assumptions.

---

## 5. User Journey and User Stories

### 5.1 Happy path

1. Open the app; review the short evidence/privacy notice if desired.
2. Enter an English research topic (1–500 characters) and choose Quick or Deep.
3. Submit. The server validates the topic and language policy, then the run manager checks the active-session lock, global capacity, and budget admission.
4. Read stage updates: Planning → Searching → Screening sources → Drafting → Verifying claims → Finalizing. Widget interactions and in-page reruns do not interrupt the run; reloading the page ends it and is not recoverable in the pilot (§8.4).
5. Read a report labeled Completed or Partial with actual source/domain counts, snippet-only-claim share, citations, disagreements and limitations.
6. Open a citation, inspect the matched quote for any claim in Evidence Details, download Markdown, optionally mark Useful / Not useful, or Clear session. About / Privacy and the pilot FAQ explain supported languages, retention, evidence limits, and why partial reports happen.

### 5.2 User stories

| ID | Story | Outcome |
|---|---|---|
| US-01 | Submit a topic | Invalid/non-English inputs show inline errors and make no provider call |
| US-02 | Choose depth | Query/source/token budgets and status thresholds follow mode |
| US-03 | Inspect a finding | Every material factual claim links to evidence-supported source IDs; references remain clickable |
| US-04 | Interpret uncertainty | Unsupported claims are removed; conflicting views have attributed citations; mode/limitations visible |
| US-05 | See an honest status | Completed, Partial, Failed selected by explicit rules (§6.4), never a subjective "usable" judgment |
| US-06 | Recover from failures | Provider/budget errors use redacted copy and an actionable retry path |
| US-07 | Export | Downloaded .md contains displayed verified content and links |
| US-08 | Control session data | Clear-session empties report, topic, excerpts and feedback UI state in server session |
| US-09 | Understand privacy/capabilities | About/Privacy + FAQ are reachable and state retention, external processing and limits |
| US-10 | Give lightweight feedback | Click Useful / Not useful and receive confirmation; duplicate clicks for the same run are idempotent |
| US-11 | Keep my run when the page reruns | Widget interactions and in-page reruns re-attach to the in-flight run instead of duplicating or killing it; a full page reload is not recoverable in the pilot and is disclosed in the UI and FAQ |
| US-12 | See the evidence behind a claim | Evidence Details shows the claim, matched quote, source link, passage ID and evidence mode |

---

## 6. Functional Requirements and Acceptance Criteria

P0 = required before internal pilot. P1 = optional improvement/hardening. P2 = future. "Verified" always means *supported by the supplied passage*, not independently proven true.

| ID | Pri. | Requirement | Measurable acceptance criteria |
|---|---|---|---|
| FR-01 | P0 | Validate topic | Trim, reject empty and >500 Unicode characters without a provider call |
| FR-02 | P0 | Research mode | Quick/Deep selectable; actual call/query/source/token counts respect server settings |
| FR-03 | P0 | Query plan | ≥2 non-duplicate queries. Each planned facet carries a category from a fixed enum (`background`, `drivers_mechanisms`, `evidence_trends`, `impacts_risks`, `perspectives_disputes`, `current_state`, `context_regional`, `other`). A viable plan has ≥3 (Quick) or ≥4 (Deep) facets in distinct categories, with `other` counting at most once. This leaves at least one facet of margin over the Completed requirement of ≥2 (Quick) or ≥3 (Deep) supported facets. A short plan gets one replan before any search call; if still short, return Failed with reason `PLAN_TOO_NARROW` and no search spend |
| FR-04 | P0 | Search adapter | Save provider request status, query, time, returned IDs, and evidence modes (redacted telemetry) |
| FR-05 | P0 | Source diversity | Count distinct registrable domains; attempt domain-balanced selection without inventing coverage |
| FR-06 | P0 | Deterministic source ranking | Same normalized source set/settings produce identical registry order using the §6.2 algorithm |
| FR-07 | P0 | Source registry | IDs, URLs, canonical URLs, title, registrable domain, date, passages, mode, truncation, provider provenance |
| FR-08 | P0 | Evidence-constrained claim drafting | Writer emits a structured ledger of atomic claims, each with `citation_id`, `passage_id`, a verbatim `quote`, `facet_id` and `section` (`summary`, `findings`, `data`, `competing` or `conclusion`). No factual text exists outside the ledger (see FR-34) |
| FR-09 | P0 | Referential citation validity | 100% in-text IDs exist in the current-run registry; cited URL matches the stored URL; failures never publish |
| FR-10 | P0 | Reference presentation | Clickable sources with publication date if available, retrieved date, evidence-mode label, and nearby markers |
| FR-11 | P0 | Report format | Required sections in §6.3; conflict discussion only when evidence warrants, otherwise "none identified" |
| FR-12 | P0 | Markdown export | UTF-8 .md exactly reflects the displayed verified report, with the same references and the Evidence appendix (§6.3). Third-party text (claim text, quotes, titles) is escaped so it renders as inert text: no raw HTML, no active link or image syntax, no code-fence breakout. Only registry URLs become links (§12.1) |
| FR-13 | P0 | Stage and error UX | Named progress stages, specific Completed/Partial/Failed messages per §7 |
| FR-14 | P0 | Secrets and provider scope | Credentials server-only; raw third-party content untrusted; no arbitrary web fetch |
| FR-15 | P0 | Bounded execution | Enforce caps on queries, source count, claim count, writer and verifier input tokens (§6.1, §6.2 step 7, §8.3 step 3), wall-time and max 2 retries per call |
| FR-16 | P0 | Evidence-mode labeling | `snippet`, `extracted`, `metadata-only`; metadata-only forbidden as support |
| FR-17 | P0 | One bounded repair | Only one constrained rewrite after validator/verifier failures, and only when the first-pass status is not Completed. The pass repairs at most 6 (Quick) or 12 (Deep) failed claims, in drafted order, using only the passages they cite within a repair input cap of 5,000 or 8,000 tokens (§6.1). Then rerun all checks on the repaired items, or return Partial/Failed |
| FR-18 | P0 | Contradiction behavior | When selected sources present materially incompatible claims about the same proposition and scope, report both positions with citations, what differs (date/definition/method), and unresolved uncertainty; never assert consensus. If none is detected, say "No material disagreement identified in selected evidence", never "all sources agree" |
| FR-19 | P0 | Passage-support verifier | For every material factual claim, an independent verifier returns `supported` / `uncertain` / `unsupported` using only the claim and its quoted passages; non-`supported` claims are removed or explicitly demoted to non-factual questions (§8.3) |
| FR-20 | P0 | Evidence Details panel | For every displayed claim, a read-only panel opened by a labeled toggle widget (not a browser-only expander, which cannot report opens for FR-44) shows the claim text, the matched quote (≤300 characters, escaped plain text), citation ID, source title and clickable registry URL, passage ID, and evidence mode. It is keyboard operable, mirrors the export's Evidence appendix, and renders no third-party HTML |
| FR-21 | P1 | Opt-in history | Authenticated storage with deletion/retention policy after privacy review |
| FR-22 | P1 | PDF export | Headings and verified clickable references preserved |
| FR-23 | P1 | Source/date filtering | Explicit allow/block and date controls with source provenance |
| FR-24 | P2 | Follow-up Q&A | Reuses a persisted, authorized corpus; independently verifies new claims |
| FR-25 | P2 | Recurring research | Schedules, opt-in notifications and spend controls |
| FR-26 | P0 | Optional usefulness feedback | At most one Useful/Not useful event per (`run_id`, session); stored event contains only run_id, mode, status, reason codes, vote, timestamp (D-08); no topic/report text; keyboard accessible |
| FR-27 | P0 | Clear session | Button removes report, topic, excerpts, source registry and the previous feedback selection from app session and hides export; makes no claim of deletion from third-party processors; disabled while a run is active |
| FR-28 | P0 | About / Privacy | In-app panel identifying providers, data sent, retention boundaries, language restrictions, excerpt limits, and a reporting mechanism via the `CONTACT_URL` setting (startup check fails for hosted deployments if unset) |
| FR-29 | P0 | Pilot FAQ | Accessible explanations of sources, partial/failed status, retrieval modes, cost estimates and cancellation limitations |
| FR-30 | P0 | Language handling | §6.7 policy; tests for English, non-Latin long queries, short proper names, and transliterated text |
| FR-31 | P0 | Deterministic status | One centralized status evaluator enforces §6.4 and emits machine-readable reason codes |
| FR-32 | P0 | Pre-call cost admission | Before every external call, compute a conservative spend ceiling from configured token/call maxima; reject unsafe/unpriced calls; log modeled ceilings and provider usage separately (§10.1) |
| FR-33 | P0 | Quoted-span match and numeric guard | Each claim's `quote` (25–300 characters) must lie entirely within one stored passage after the defined normalization, and every number, percentage, currency amount and date in the claim text must appear in its quotes. Computed or derived figures are not permitted in claims |
| FR-34 | P0 | Sentence typing and coverage scan | Report body is assembled from typed sentences (§8.3 step 5). Claim sentences are the verified ledger text verbatim; other types obey deterministic token rules; a model coverage scan runs as a second layer |
| FR-35 | P0 | Verifier and scan fixtures | Labeled fixture sets with a sealed test half, scorecard produced by a repeatable script, and gate thresholds from §2.6 |
| FR-36 | P0 | Background run manager | Runs execute in a bounded worker pool outside the Streamlit script thread; the UI re-attaches by `run_id` within the same Streamlit session; abandoned runs (closed or reloaded page) stop issuing new calls (§8.4). Recovery after a full page reload is out of scope for the pilot (FR-38) |
| FR-37 | P0 | Call-graph startup check | At startup, for each mode and at maximum token settings, validate (i) that the sum of per-stage base reservations fits the admitted cap, and (ii) that base reservations plus the worst-case demand on the shared contingency pool (two further attempts of every first-pass call, one planner replan (FR-03), and the repair branch within its FR-17 limits, each with its own retries, all times the safety factor) also fit the cap (§10.1). Verifier batch counts come from token sizes, not fixed numbers. Otherwise refuse to serve that mode |
| FR-38 | P1 | Reload recovery | The UI places an opaque random reconnect token (≥128 bits) in a URL query parameter; the server maps the token to `run_id` with a TTL no longer than the result TTL; when hosted, the token is honored only for the same authenticated principal. The URL is a bearer secret, so the token is never logged or sent to providers, and the feature needs privacy review before enabling. Re-attaching restores progress or the finished result |
| FR-39 | P0 | Coverage disclosure | The report lists each planned facet with its count of displayed supported claims; facets with none are marked "not covered" (code-generated). Neither the UI nor the export describes a Completed report as comprehensive or exhaustive, and the status badge explains what Completed means |
| FR-40 | P0 | Coverage and readability evaluation tooling | An eval script computes essential-question coverage scores, the hollow-completion rate, readability rubric scores and bootstrap intervals from reviewer labels (§11.6, §11.7) |
| FR-41 | P1 | Two-verifier agreement | Claims containing numbers, dates or source attributions must be judged `supported` by two independent verifier passes (different prompt, and a different model where available); disagreement removes the claim. Enable if fixture false-accept results or the §10.3 simulation warrant it |
| FR-42 | P0 | Feasibility measurement harness | Records per-call input/output tokens, modeled and actual cost, retry counts, stage timings and removed-claim counts; compares them with the §10.3 simulation; produces the PoC report (§15) |
| FR-43 | P1 | Verified aggregation (composite claims) | A sentence combining ≥2 supported claims of the same facet is itself a ledger claim that carries every quote and passes FR-33 and the verifier. Merging unverified text in the renderer is prohibited. Enabled only through the §11.7 readability trigger or a later roadmap decision, after re-evaluation against the verifier and grounding gates |
| FR-44 | P0 | KPI event counters | Per-run values `evidence_opened`, `export_downloaded` and `feedback_vote` are recorded as separate append-only events keyed by run ID and joined to the run record in reporting (D-08). They contain no topic, report, passage or user identifier and are reported only as aggregates (§2.7) |
| FR-45 | P0 | Daily spend guard | A configurable daily alert threshold and stop threshold on committed spend. Reaching the alert threshold logs an alert event. At the stop threshold new runs are rejected as "Service paused" (§7.3). The day's total survives a process restart (D-03). Events carry no content |

### 6.1 Mode configuration and budgets (proposed)

| Parameter | Quick | Deep |
|---|---|---|
| Planned queries | 3 | 8 |
| Required planned facets (distinct categories, FR-03) | ≥3 | ≥4 |
| Search query cap | 4 | 10 |
| Maximum selected sources | 8 | 20 |
| Maximum passages stored per source | 6 | 8 |
| Maximum ledger claims drafted | 14 | 36 |
| Max passages (quotes) per claim | 3 | 4 |
| Maximum failed claims repaired (FR-17) | 6 | 12 |
| Maximum repair input tokens | 5,000 | 8,000 |
| Maximum writer input tokens (passages plus prompt) | 9,000 | 24,000 |
| Claims per verifier call (batch) | ≤8 and within the input cap below | ≤8 and within the input cap below |
| Maximum verifier input tokens per batch | 7,000 | 9,000 |
| Concurrent verifier calls | ≤4 | ≤4 |
| Typical report length, evidence permitting | ~400–800 words | ~1,000–2,000 words |
| Wall-clock ceiling | 120 seconds | 360 seconds |
| Target measured p50 / p95 | ≤45 / ≤90 seconds | ≤120 / ≤240 seconds |
| Target modeled cost per completed run | ≤$0.30 | ≤$1.50 |
| Pre-call admitted modeled upper bound per run | $0.75 | $3.00 |

Report lengths are shorter than in v1.2 because factual prose is rendered from atomic ledger claims (§6.3). All mode parameters, thresholds and targets in §6 and §10 are provisional until the D-13 proof-of-concept checkpoint (§15), when they are revised once using dev-set measurements and then frozen. Cost caps are on modeled admissible spend using versioned pricing assumptions, not provider invoices (§10.1). If provider throttles make targets infeasible, benchmark and adjust by signed change request rather than quietly violating caps.

**Stage time budgets (design targets, not guarantees; they sum to the p50 targets):**

| Stage | Quick (s) | Deep (s) |
|---|---|---|
| Planning | 4 | 6 |
| Searching (queries in parallel) | 10 | 25 |
| Screening | 1 | 2 |
| Drafting ledger | 14 | 40 |
| Verifying (batched, parallel) | 9 | 25 |
| Coverage scan | 4 | 10 |
| Finalizing | 1 | 2 |
| **Total** | **43** | **110** |

The single repair pass (plus re-verification and re-scan) is the main driver of the gap between p50 and p95.

### 6.2 Deterministic source selection and ranking

1. **Eligibility:** accept only HTTP(S) canonical URLs returned by the current-run provider, with a non-empty evidence passage of ≥30 non-whitespace characters. Metadata-only results may be listed as "not inspected" but are not usable.
2. **Deduplicate:** normalize host/canonical URL and known tracking parameters; remove exact and excerpt-hash syndicated duplicates and keep provenance of merged results. Group clearly syndicated text as one evidentiary group even across domains.
3. **Source category:** if a manually versioned, documented domain/metadata allowlist positively identifies an original publisher or primary evidence, assign `primary=1`; otherwise `primary=0` (unknown, not automatically "secondary"). No model-guessed authority badge.
4. **Deterministic score:** `4 × provider_relevance_0_to_1 + 2 × extracted_mode + 1 × primary + 1 × recency_match`. `recency_match=1` only for an explicitly time-sensitive topic with a known publication date within the freshness window. Missing scores and dates contribute 0. Scores are frozen per run with the config version; provider rank is converted reproducibly when numeric relevance is absent.
5. **Diversity:** sort by descending score, then ascending canonical URL as tie-breaker; select in round-robin passes by distinct registrable domain before taking additional sources per domain. No more than 2 selected from one domain while unused eligible domains remain. Respect the source cap.
6. **Passage selection:** from each selected source, keep the top passages by a deterministic lexical-overlap score against the planned queries, up to the per-source cap in §6.1; ties broken by passage order.
7. **Token-budget trim:** estimate writer input tokens as `ceil(characters ÷ 3.5)` over all selected passages, plus a fixed prompt allowance (1,500 tokens Quick, 2,000 Deep) that includes the output schema. If the estimate exceeds the mode's writer input cap (§6.1), drop passages in this deterministic order until it fits: lowest-scoring sources first; within a source, lowest lexical-overlap passages first, always keeping each remaining source's top passage; if the estimate is still over, drop whole sources from the lowest score upward. Record dropped passage and source counts in redacted metrics. The 3.5 characters-per-token ratio is deliberately conservative for English text. The PoC harness compares the estimator with provider-reported token counts, and the ratio may be changed once at the D-13 checkpoint. This step makes the §10.3 worst case a bound, not an assumption.
8. **Audit:** unit fixtures assert exact ordering, duplicate handling, primary flags, domain diversity and the trim order; export counts and selected ranks in redacted metrics.

"Prefer original studies" is a bounded score preference where metadata has verified provenance, not a claim that the algorithm recognizes scientific quality.

### 6.3 Report template and prose model

1. Title, research date, mode, status and coverage metrics (code-generated)
2. Executive summary
3. Scope and questions researched (code-generated: each planned facet with its number of displayed supported claims; facets with none are marked "not covered")
4. Key findings (ledger claims with adjacent citation IDs)
5. Data/examples (only if evidence supports exact figures and context)
6. Conflicting/competing evidence, or "No material disagreement identified in selected evidence"
7. Limitations, snippet-only claim percentage, missing facets and uncertainty (code-generated)
8. Conclusion
9. References: `[n] title — domain — published date when known — retrieved date — URL — mode`
10. Evidence appendix: for each displayed claim, the claim ID, matched quote (≤300 characters), citation ID, passage ID and evidence mode. It mirrors the Evidence Details panel

**Prose model (known tradeoff):** every factual sentence is a verified ledger claim printed verbatim with its `[n]` markers. Interpretation and transition sentences are tightly constrained (§8.3 step 5). The result reads as a structured list of checked statements rather than flowing narrative. A verified-aggregation step that merges claims into fluent prose is a Phase 2 item (§18) and must not weaken the checks.

**Claim placement and counting:** the writer assigns each claim a `section` (`summary`, `findings`, `data`, `competing` or `conclusion`). The renderer prints each `claim_id` once, in its assigned section. The summary holds at most 3 claims in Quick and 5 in Deep, and the conclusion at most 2 and 3. All counts in §6.4 and the snippet-only share use distinct `claim_id`s across the whole report.

### 6.4 Deterministic terminal status rules (normative)

Definitions:

- **Usable source:** registry source with permitted snippet or extracted text ≥30 non-whitespace characters, a non-empty valid URL, and a unique evidence-group identifier. A metadata-only result is never usable.
- **Supported material claim:** atomic factual proposition with one or more citation IDs, verbatim quote(s) that pass the FR-33 checks, a `supported` verifier verdict, and no contrary higher-priority validation error.
- **Snippet-only share:** (displayed supported material claims whose supporting passages are all snippet-mode) ÷ (displayed supported material claims). All-extracted gives 0%; all-snippet gives 100%. Not computed from source count. No denominator ⇒ Failed.
- **Coverage facet:** distinct question in the generated plan mapped to ≥1 displayed supported claim; the ledger stores `facet_id`. Contradictory facts require attributable discussion, not silent averaging.
- **Counting rule:** every count in this section (supported claims, facets, snippet-only share) uses distinct `claim_id`s. A claim is never counted twice, because it is printed once (§6.3).

| Condition | Quick threshold | Deep threshold |
|---|---|---|
| Completed: usable evidence groups | ≥3 | ≥6 |
| Completed: distinct registrable domains | ≥2 | ≥3 |
| Completed: displayed supported material claims | ≥4 | ≥8 |
| Completed: supported plan facets | ≥2 | ≥3 |
| Completed: snippet-only claim share | ≤80% | ≤70% |
| Completed: integrity / semantic requirements | All claims and references pass | All claims and references pass |
| Completed: execution | No unresolved required-stage error, timeout, or budget stop | Same |
| Partial: minimum safe report | ≥2 supported material claims from ≥1 usable evidence group, all displayed claims valid | Same |
| Failed: no safe report | Fewer than 2 supported claims, or verification/integrity cannot be made clean | Same |

**Decision order:**

1. Reject unsafe input or unavailable configuration ⇒ Failed (a validation error before the run may be UI-only). A plan that is still too narrow after one replan (`PLAN_TOO_NARROW`, FR-03) and a search that returns no usable evidence also end as Failed, each with its reason code.
2. Remove every claim or sentence that failed a check. If the first-pass status is not Completed, run one repair within the FR-17 limits and re-evaluate. If a displayed claim still lacks support after that, remove it or fail.
3. If fewer than two safe claims remain ⇒ Failed with no synthesized report.
4. If all Completed conditions are satisfied ⇒ Completed.
5. Otherwise ⇒ Partial, listing every unmet threshold as a reason code (`LOW_DOMAINS`, `SNIPPET_HEAVY`, `INSUFFICIENT_CLAIMS`, `BUDGET_STOP`, `INCOMPLETE_FACETS`, and so on).

A Partial report is not a completed report for reliability and quality denominators. The user can still export a safe Partial report, marked prominently `PARTIAL — ...`. Provider outages, source poverty, topical nuance, and short excerpts never excuse an unverified claim. The all-snippet path will normally be Partial by design; improving extracted-evidence coverage is part of pilot feasibility testing, not a reason to relax status labels invisibly. **The thresholds above are provisional until the D-13 checkpoint and frozen before the holdout runs (D-10).** Completed means the minimum evidence thresholds were met. It does not mean the topic is comprehensively covered, and the UI must never say so. Coverage adequacy is measured separately (§11.6).

### 6.5 Contradiction and inferential-claim rules

- When two selected pieces of evidence disagree on comparable scope/metric/date, include both cited positions and the source/method difference if present; otherwise say why unresolved.
- Do not treat a disagreement in time period, definition, or population as a direct contradiction without stating the mismatch.
- Interpretation sentences must be labeled "Interpretation:" and must cite the supported claims they build on (§8.3 step 5). Uncited material factual premises remain prohibited.
- Claims with uncertain evidence cannot be emitted as supported factual assertions merely by adding "may" or a citation. They may appear as an explicit unverified question in Limitations without implying confirmation.

### 6.6 Resource-limit semantics

Budget exhaustion never triggers another external request; the latest validated safe snapshot may be emitted as Partial if it passes §6.4. Search calls, retry attempts, writer tokens, verifier tokens, scan tokens, and repair usage all draw down one per-run budget. There is one drafting pass and at most one constrained repair pass, which is itself re-verified and re-scanned.

### 6.7 Language support policy (D-01)

English UI/reports only. Reject topics with ≥20 alphabetic characters where >70% of alphabetic characters are outside Latin Unicode script, before external calls, with the copy: "This pilot accepts English-language topics only. Please rewrite your topic in English." Accept short proper nouns in other scripts (<20 alphabetic characters) to avoid over-rejection, but warn that search quality is unvalidated; report output remains English. Latin-script non-English and transliterated topics are accepted with a notice: "English-language research is supported; other languages may be incomplete." This is a cheap script heuristic, not reliable language identification; pilot tests must record false accepts and rejects. Do not claim multilingual support.

### 6.8 Definition: material factual claim (normative)

A **material factual claim** is any statement in report prose that asserts something about the external world that could be true or false and that a reader could rely on. It includes:

- figures, percentages, amounts, dates and durations;
- attributes of named entities;
- causal, comparative, trend and ranking assertions;
- attributions of statements or positions to a source;
- existence or occurrence assertions;
- definitions presented as fact.

It excludes:

- headings;
- code-generated text (scope, coverage, status, limitation templates);
- statements about the report's own evidence limits;
- correctly labeled interpretation sentences that add no new facts (§8.3 step 5);
- short transitions.

Where it is ambiguous whether a sentence is material, treat it as material. Annotators, the coverage scan, and the metrics in §2.6 all use this definition.

---

## 7. UX, Screens, and Accessibility

### 7.1 Desktop informational wireframe

```
+------------------------------------------------------------------------+
| AI Research Agent            [About / Privacy] [Pilot FAQ]              |
+------------------------------------------------------------------------+
| Topic (English for pilot)                                              |
| [ Impact of AI on the Indian job market________________________ ]       |
| Depth: (o) Quick  ( ) Deep              [Research] [Clear session]      |
| Research limits and third-party processing notice                       |
+------------------------------------------------------------------------+
| Stage: Verifying claims ...                                             |
| Planning ✓ Searching ✓ Screening ✓ Drafting ✓ Verifying ● Finalizing ○ |
+------------------------------------------------------------------------+
| Status: PARTIAL   Sources: 5   Domains: 3  Snippet-only claims: 90%    |
| Notice: The evidence is predominantly snippets; some facets are thin.  |
| Research report                                      [Download .md]     |
| Executive summary ... [1] [2]                                           |
| Key findings ... [3]  [Evidence details ▸ per claim]                    |
| Contradictions / limitations / sources ...                              |
| Was this useful?   [Useful] [Not useful]                                 |
+------------------------------------------------------------------------+
```

### 7.2 Mobile behavior

Single-column layout; controls stack below 480px; readable source links wrap; no horizontal document scrolling at 320px; report, download and feedback remain operable by keyboard and touch. Never show a "completed" badge when the status evaluator returns Partial.

### 7.3 States and concrete copy

| State | UI behavior | Example copy |
|---|---|---|
| Idle | Form, mode, source/budget note | "Enter an English topic to research public websites." |
| Invalid / unsupported language | Keep topic, focus error, make no provider call | "This pilot accepts English-language topics only." |
| Running | Disable duplicate submission and Clear session; show stage announcement and a reload warning | "Verifying which claims are supported by retrieved passages… Please don't reload this page while research is running." |
| Busy | No run started; offer retry | "The service is at capacity. Please try again in a minute." |
| Result expired | A held run ID no longer resolves (30-minute result lifetime or Clear session); show the form | "Your earlier result is no longer available. Results are kept for 30 minutes. Please run it again." |
| Service paused | Daily spend stop reached, or the service is shutting down; no run starts | "Research is paused right now. Please try again later." |
| Mode unavailable | A mode failed its startup cost check; disable it with an explanation | "This depth is unavailable right now. Please choose the other depth or try again later." |
| Page reloaded or server restarted mid-run | New session starts idle; the orphaned run stops issuing new calls (§8.4); the idle footer carries a standing notice | "Reloading the page, or a server restart, ends a running search. If that happens, start it again." |
| Completed | Show scorecard, report with Evidence Details, export and feedback | "Completed: 6 usable sources, 4 domains, 8 supported claims. Minimum evidence thresholds were met; coverage is not exhaustive." |
| Partial | Prominent non-dismissible notice, unmet thresholds, export tagged partial | "Partial: 100% of supported claims rely on snippets. More complete text was not available." |
| Failed / no evidence | No synthesized report; preserve form and offer retry | "No report was produced because the available evidence could not support two factual findings." |
| Provider failure | Generic code, safe details only | "Search service unavailable. No unverified report was published." |
| Semantic mismatch | One repair, then block unresolved claims | "Some claims could not be matched to their cited passages; they were omitted." |
| Budget/timeout | No additional calls; Partial only if a safe snapshot exists | "Stopped at the configured limit. Only passage-checked findings are shown." |
| Feedback recorded | Non-intrusive confirmation | "Thanks — your feedback was recorded without storing the report." |
| Clear session | Remove all current research UI state and export | "Session cleared in this app; external provider processing is unchanged." |

**Cancellation:** no Cancel button in the pilot, because an in-flight provider call cannot be reliably aborted. Clear session is disabled while a run is active, with an explanation. Runs abandoned by a closed or reloaded browser page stop issuing new calls at the next stage boundary (§8.4). Explain this in the FAQ.

### 7.4 Accessibility acceptance (WCAG 2.2 AA target)

Keyboard-only happy, partial, error, feedback and clear paths; logical focus and explicit labels; programmatic status/error announcements where Streamlit permits (including the polling stage display); text contrast ≥4.5:1, control boundaries ≥3:1; 200% zoom without lost functionality; screen-reader spot check; no status conveyed by color alone. Log Streamlit framework limitations and treat any blocker to primary research/report access as release-blocking. Verify; do not assume the framework meets WCAG. The Evidence Details toggle must switch with Enter or Space, expose quotes as readable text, and keep a logical focus order.

### 7.5 About/Privacy and FAQ content minimum

**About/Privacy** identifies the configured search and model providers; what topic/evidence is transmitted to them; application session-only retention versus provider-side policies; telemetry and feedback fields and retention; risks of submitting confidential data; source provenance versus factual accuracy; supported languages and report status rules; and the reporting contact. **FAQ** explains Quick/Deep, snippet versus extracted text, why reports are terse lists of checked statements, contradictions, why reports can be Partial/Failed, estimated costs, the missing Cancel control, what Completed does and does not mean, why reloading the page or restarting the server ends a run, how long results are kept (30 minutes), how to read Evidence Details, and how to report questionable citations. Both are always reachable even when no report exists.

---

## 8. Technical Architecture and Verification Pipeline

### 8.1 Modules and trust boundaries

| Component | Candidate implementation | Responsibility |
|---|---|---|
| UI | Streamlit | Input, polling stage display, result, Evidence Details panel, feedback, clear-session, Privacy/FAQ. Never runs pipeline work itself |
| Run manager | Python (`ThreadPoolExecutor`, locks) | Worker pool, per-session lock, capacity permits, idempotency, heartbeat watchdog, result TTL (§8.4) |
| Orchestrator | Python | State machine, budgets, failure/retry orchestration, safe snapshots |
| Planner | OpenAI via bounded adapter | Query/facet generation; output validated and capped |
| Search adapter | Tavily via interface | Retrieve URL, snippet/extracted text, metadata and provenance |
| Source selector | Pure Python | Eligible evidence, URL canonicalization, ranking, diversity, evidence grouping, passage chunking |
| Claim ledger writer | Model + strict schema | Draft atomic claims with citation, passage, quote and facet; typed non-claim sentences |
| Deterministic claim checker | Pure Python | Quote match and numeric guard (FR-33); sentence-type token rules (FR-34) |
| Passage verifier (P0) | Separate model (D-11), strict JSON | Semantic supported/uncertain/unsupported verdicts, batched |
| Coverage scanner | Separate model call | Second-layer scan for factual sentences outside the ledger |
| Finalizer | Pure Python + bounded model repair | Omit invalid claims, render report, compute status |
| Telemetry | Redacted structured metrics | IDs, counters, stage codes, cost-ceiling estimates, feedback votes |
| Settings | Env/secret store + versioned price sheet | Runtime/token limits, provider versions, conservative unit rates |
| Test suite | pytest + mocks + fixtures + human review | Determinism, faults, attack fixtures, scorecards, evaluation |

```
Topic → validate/language policy
      → run manager: idempotency, session lock, capacity permit, cost admission
      → [worker thread from here on]
      → plan queries/facets → search provider → normalize/dedupe/rank/chunk passages
      → evidence registry with immutable source IDs and passage IDs
      → draft ledger: atomic claims + quotes, plus typed non-claim sentences
      → deterministic checks per claim: ID/URL, quote-in-passage, numeric guard
      → batched semantic verifier (separate model call)
      → remove failed claims, ≤1 repair → RE-RUN all checks on affected items
      → typed-sentence rules + coverage scan over the assembled report
      → deterministic status evaluator → report/status/references/export/feedback
```

### 8.2 Files / code boundaries

```
ai-research-agent/
  app.py                 # Streamlit UI, polling fragment, privacy/FAQ, feedback and session controls
  run_manager.py         # Worker pool, session lock, semaphore, idempotency, heartbeat, result TTL
  research_agent.py      # Pipeline state machine and safe snapshots
  search_provider.py     # Bounded provider requests
  source_processing.py   # Deterministic ranking/dedupe, evidence registry, passage chunking
  claim_ledger.py        # Atomic claims, quotes, facet IDs, citation mapping
  claim_checks.py        # Quote normalization/match, numeric guard, sentence-type rules
  passage_verifier.py    # Batched semantic verifier with strict-JSON parsing
  coverage_scan.py       # Second-layer unledgered-sentence scan
  citation_validator.py  # Referential links, URLs, claim coverage checks
  report_generator.py    # Report rendering and ≤1 repair
  status_rules.py        # Central §6.4 status decision and reason codes
  capacity.py            # Cost admission, reservations, call-graph startup check
  telemetry.py           # Redacted metrics, feedback event aggregation
  settings.py            # Versioned price/budget/model assumptions, CONTACT_URL
  eval/                  # Fixture sets, scorecard scripts, bootstrap/Wilson reporting
  tests/
  requirements.txt
  .env.example
  README.md
  prd.md
```

These are target modules. Any pre-existing prototype code is a baseline, not evidence that these controls are implemented.

### 8.3 P0 claim-to-passage verification protocol

1. **Ledger drafting.** The writer outputs a structured ledger of atomic factual propositions. Each has `claim_id`, `text`, `facet_id`, and one or more `{citation_id, passage_id, quote}` entries, plus relevant context (date, geography, units). The writer must **not** supply a support label; labels come only from the verifier.
2. **Deterministic checks (FR-33).**
   - The source exists in the current run, is evidence-eligible, and the `passage_id` belongs to it.
   - The `quote` is 25–300 characters and lies entirely within a single stored passage after `normalize_for_match`: Unicode NFKC, whitespace collapse, typographic quote/dash unification, case-insensitive comparison. No other fuzziness is permitted.
   - Every number, percentage, currency amount, range and date in the claim text appears in the concatenated quotes after number-format normalization (`1,000` = `1000`; `%` = `percent`). Number words are normalized for one through ten and for "million/billion".
   - The claim text contains no arithmetic result that is not stated in a quote (no sums, differences, growth rates). Such claims are rejected as `unsupported`.
   - A failed check marks the claim `unsupported` before any model call.
3. **Independent semantic verification.** Claims that passed step 2 are sent to the verifier, which sees only the claim and its quoted passages (the full stored passage plus the quote), with no web access, secrets or other claims.
   - Passages are wrapped in explicit delimiters and the system prompt states that passage content is untrusted data, not instructions.
   - Output is strict JSON `{"verdict": "supported|uncertain|unsupported", "reason": "<=200 chars"}`. Any parse failure, extra field, or out-of-enum value is treated as `unsupported`.
   - The prompt requests entailment, not topical similarity, and distinguishes an original-study claim from an article merely mentioning it.
   - Calls are batched with at most 8 claims per call and at most the mode's verifier input cap (§6.1) in estimated tokens, using the same estimator as §6.2 step 7. Claims are packed in drafted order and any excess spills into further batches. Temperature 0; up to 4 calls in parallel. Per-claim verdicts are cached within the run by hash of (claim, quote texts, verifier version).
4. **Acceptance.** `supported` requires unambiguous support for the full scope, number, entity, dates and negation. `uncertain` and `unsupported` material claims are removed from the report. An uncertain research question may be listed in Limitations without being asserted.
5. **Sentence typing (FR-34).** The writer assembles each section as a list of typed sentences. The renderer builds the report from them.
   - `claim`: no text of its own. The renderer prints the verified ledger text verbatim with its `[n]` markers. Claims are atomic, so a sentence cites exactly one ledger claim.
   - `interpretation`: must start with "Interpretation:"; must reference ≥1 supported `claim_id`; ≤40 words. A deterministic token check requires every digit-bearing token and every capitalized word (other than the first word) to appear in the cited claims' text, the topic string, or the section headings; otherwise the sentence is dropped.
   - `transition`: ≤15 words; no digits; no capitalized words outside the topic string and headings; no URLs; otherwise dropped.
   - `meta`: renderer-owned templates only; the writer cannot author them.
   - Any sentence of another type, or untyped text, is rejected.
6. **Coverage scan.** A separate model call classifies every `interpretation` and `transition` sentence (and any dropped or rejected text) for embedded material factual assertions per §6.8. Flagged sentences are removed. Recall is measured on planted-sentence fixtures (§11.2). Step 5 is the primary enforcement; the scan is a defense in depth, not the only safeguard.
7. **Repair.** One repair pass may rewrite or delete failed claims and sentences, within the FR-17 limits, but cannot add new URLs or sources. All deterministic checks, verification and the scan re-run on every affected item. If fewer than two safe claims remain, the run is Failed.
8. **Boundary.** The checker confirms that retrieved text supports a claim. It cannot guarantee the text is true, current, non-deceptive, or free of source bias. Runtime checking can still produce false accepts, so §11 human sampling is mandatory and the product must not be labeled "fact checked".

### 8.4 Run model and concurrency (Streamlit execution)

**Problem addressed.** Streamlit re-executes the script on every widget interaction or browser refresh and stops the previous execution. A pipeline running inside the script thread would be interrupted mid-run while provider calls and spend continue untracked. The run model therefore separates the UI from the pipeline.

**Design (single-process pilot):**

1. A `RunManager` singleton is created once as a cached server resource. It owns a bounded `ThreadPoolExecutor(max_workers=5)`, a `BoundedSemaphore(5)`, and a lock-protected dictionary of run records. Each record holds `run_id`, `session_id`, status, stage, `deadline`, `cancel_flag`, `result`, `last_heartbeat` and `created_at`.
2. On submit, the UI generates an **idempotency token** once per form render and consumes it on the first submit. A duplicate token returns the existing `run_id` instead of starting a second run.
3. `submit()` takes a non-blocking semaphore permit. If none is free it returns BUSY immediately and queues nothing. It also enforces one active run per session via the session-to-run map. A disabled button is not a lock.
4. The worker thread executes the pipeline and **never calls any Streamlit API**. It writes stage and result into its record. The semaphore permit is released in a `finally` block.
5. The UI stores `run_id` in session state and shows progress with a polling fragment (`st.fragment` with `run_every`). Widget interactions, in-page reruns, and brief websocket reconnects that keep the same Streamlit session re-attach by `run_id` and do not affect the worker. The pinned Streamlit version must support this; confirm at M0.
   **Pilot guarantee boundary:** a full browser reload, or opening a new tab, creates a new Streamlit session and loses session state, so the new session cannot find its run. The pilot does not recover from this. It warns users not to reload (§7.3), discloses the limitation in the FAQ, and relies on the watchdog below to stop the orphaned run. FR-38 specifies an optional recovery token as a P1 feature.
6. **Heartbeat watchdog.** Each poll updates `last_heartbeat`. If no heartbeat arrives for 90 seconds (page closed or reloaded), the orchestrator sets `cancel_flag` and stops issuing new calls at the next stage boundary. The in-flight call completes and its spend is accounted; the result is discarded. The timeout is configurable. Browsers throttle timers in background tabs, which can slow polling, so the default must exceed the slowest throttled poll interval observed in the browser test (§11.4, test 29); otherwise users who switch tabs would lose their runs.
7. **Result lifecycle.** Records are purged on Clear session, on heartbeat loss plus 10 minutes, or 30 minutes after completion, whichever is first. Everything is in process memory (D-03). A process restart loses in-flight runs. The UI cannot tell this from a fresh visit, because the new session has no run ID, so the user sees the idle form with the standing notice (§7.3).
8. **Limits of this design.** State is per process. Running multiple Streamlit processes, containers or autoscaled replicas is unsupported in the pilot. Public or multi-instance launch requires a shared job queue and distributed per-user quotas with leases/TTLs (for example managed Redis) plus load tests (§17).
9. **Reload recovery.** An opaque reconnect token (FR-38) would let a new session re-attach to a run. It is excluded from the pilot because a token in the URL is a bearer secret that needs privacy review, and because the stored-result lifetime must stay within D-03.
10. **Graceful drain (NFR-19).** The app cannot trap SIGTERM itself. A wrapper process starts Streamlit and traps SIGTERM, then writes a drain marker. The run manager stops admitting runs, and the wrapper waits for active runs to finish or for the drain timeout (default 120 s) before forwarding the signal. See architecture.md §12.2.

---

## 9. Data Contracts and Invariants

### 9.1 ResearchRequest

```json
{ "topic": "Impact of AI on the Indian job market", "depth": "deep", "idempotency_token": "opaque" }
```

Trimmed topic of 1–500 Unicode characters; `depth` in `quick|deep`; language policy §6.7. `run_id` and `session_id` are generated by the server; `session_id` is an app-generated random value, not Streamlit's internal identifier. No user-supplied arbitrary fetch target.

### 9.2 SourceRecord and immutable passages

```json
{
  "citation_id": 1,
  "provider_result_id": "opaque-result-id",
  "title": "Illustrative source title",
  "url": "https://example.org/report",
  "canonical_url": "https://example.org/report",
  "registrable_domain": "example.org",
  "published_at": null,
  "retrieved_at": "2026-10-21T00:00:00Z",
  "evidence_mode": "snippet",
  "passages": [
    { "passage_id": "1:p1", "text": "A hypothetical piece of supporting evidence, not a real claim.", "truncated": false }
  ],
  "evidence_group_id": "hash-of-normalized-text-group",
  "primary_evidence_verified": false,
  "provider_rank": 2,
  "retrieval_warning": null
}
```

All example URLs and text are illustrative, not real facts.

**Passage construction.**
- A `snippet` source yields one passage: the provider-returned snippet, up to 1,500 characters; if longer, truncate and set `truncated: true`.
- An `extracted` source is split at sentence boundaries into non-overlapping chunks of at most 800 characters; keep the top chunks per §6.2 step 6 up to the per-source cap; set `truncated` if content was dropped.
- Passages store provider-returned verbatim text. Only an immutable normalized comparison view is derived from it (`normalize_for_match`, §8.3 step 2).
- Passage IDs are `{citation_id}:p{n}`. A quote must lie within one passage; a claim needing two passages cites two quotes.
- Use a public suffix list for registrable domains. Metadata-only sources have no passages.

### 9.3 ClaimRecord and verifier outcome

```json
{
  "claim_id": "c003",
  "text": "Illustrative factual assertion that must be supported by its quote.",
  "claim_type": "material_fact",
  "facet_id": "f2",
  "section": "findings",
  "evidence": [
    { "citation_id": 1, "passage_id": "1:p1", "quote": "Illustrative verbatim span from the stored passage." }
  ],
  "quote_match_ok": true,
  "numeric_guard_ok": true,
  "verifier_version": "support-v1",
  "support_verdict": "supported",
  "support_reason": "Illustrative only: assess scope and entailment before accepting."
}
```

`support_verdict` is set by the verifier, never by the writer. Accepted values: `supported`, `uncertain`, `unsupported`. An illustrative record does not establish real support.

### 9.4 ResearchResult (status and measurements)

```json
{
  "run_id": "opaque-id",
  "depth": "deep",
  "status": "partial",
  "reason_codes": ["SNIPPET_HEAVY", "LOW_DOMAINS"],
  "report_markdown": "# PARTIAL Research Report\n...",
  "source_ids": [1, 2],
  "validated_claim_ids": ["c003", "c004"],
  "metrics": {
    "query_count": 5,
    "usable_sources": 2,
    "unique_domains": 2,
    "supported_claims": 2,
    "supported_facets": 1,
    "snippet_only_claim_share": 1.0,
    "elapsed_ms": 42500,
    "modeled_spend_ceiling_usd": 0.75,
    "estimated_actual_cost_usd": null
  }
}
```

`status` is `completed|partial|failed`. In a Failed state `report_markdown` is null; a list of source links without synthesized claims may be shown separately. A Partial export includes the Partial status and reason codes. Cost may be null when usage/pricing is unavailable; never display null as zero.

### 9.5 Hard invariants

1. Every displayed material factual sentence is a ledger claim with a ledger record, valid citation IDs, a quote that passed the FR-33 checks, and a `supported` verifier verdict.
2. Every cited URL originates in the current-run registry; no writer-created URLs appear in references or body.
3. Metadata-only results and unattributed copied syndication cannot count as corroborating factual evidence.
4. No unsupported or uncertain material factual assertion is rendered as fact. Deliberately stated uncertainty is a question or gap, not an endorsed conclusion.
5. Source, domain, facet, claim and snippet counts and statuses are computed by deterministic code, never chosen by the writer.
6. Every external call is admitted using configured bounds, token budgets and a modeled spend reservation. Max retries and wall-time are enforced where technically possible.
7. No third-party content can modify privileged instructions, secret access, or allowed tools. This includes content shown to the verifier and the coverage scanner.
8. Partial and Failed never quietly appear as Completed; only verified content can be exported.
9. The pipeline never executes inside the Streamlit script thread; UI reruns within a session cannot start, duplicate, or terminate a run.

---

## 10. Non-Functional Requirements, Cost, and Reliability

These are targets to measure, not claims of proven service levels or provider billing guarantees.

| ID | Dimension | Testable target |
|---|---|---|
| NFR-01 | UI response | Research click acknowledged within 1 second on the specified pilot host |
| NFR-02 | Latency | Quick p50 ≤45s, empirical p95 ≤90s; Deep p50 ≤120s, p95 ≤240s; report 95% bootstrap intervals and sample size (§10.2) |
| NFR-03 | Timeout | Quick 120s; Deep 360s; no infinite spinner; provider cancellation is best-effort only |
| NFR-04 | Budget admission | Versioned worst-case pricing model reserves estimated upper cost for every planned outgoing call, including retries, verifier, scan and repair; reject if reservations cross $0.75 Quick / $3.00 Deep |
| NFR-05 | Invoicing honesty | Cost ceilings are estimates, not exact billing hard stops; disclose unknown tariffs; block unpriced or uncapped provider operations |
| NFR-06 | Completion | Pilot ≥95% observed (≥48/50) on ≥50 mode-eligible holdout attempts per mode, under the frozen §6.4 rules |
| NFR-07 | Data retention | Raw prompts, evidence and reports are session-only; clear removes local session state; external provider retention is disclosed, not claimed deletable |
| NFR-08 | Logs | Only redacted operational metadata; ≤7 days where the host supports this, otherwise hosting requires a sign-off exception |
| NFR-09 | Observability | Every attempted run carries run ID, mode, status/reason codes, stages, source/facet/claim counts, timings, token counts (when available), modeled cost and errors |
| NFR-10 | Access security | No credentials in browser, report, prompts, or logs; prompt-injection tests pass for writer, verifier and scanner |
| NFR-11 | Pilot concurrency | One active run per session and ≤5 active runs per Python process, enforced by the run manager's locks and semaphore |
| NFR-12 | Public concurrency | Redis or equivalent shared quota and distributed leases with bounded TTL before multiple workers or anonymous users |
| NFR-13 | Legal compliance | No paywall/robots/access-bypass; bounded evidence storage and proper attribution |
| NFR-14 | Setup portability | Clean-install env-secret run; hosted secrets injected without code edits |
| NFR-15 | Accessibility | §7 WCAG 2.2 AA target testing; keyboard and screen-reader audit; no severe blocker |
| NFR-16 | Provider resilience | ≤2 transient retries per request; no retry on invalid-key/permission failures; deterministic error codes |
| NFR-17 | Run robustness | Widget interaction, in-page rerun, or double-click during a run never duplicates or terminates it; abandoned (closed or reloaded) runs stop new calls within one stage boundary after 90s (configurable) without heartbeat; background-tab throttling does not cause false abandonment |
| NFR-18 | Stage budgets | Stage durations tracked against §6.1 stage budgets; report per-stage p50/p95 in the benchmark |
| NFR-19 | Graceful shutdown | On SIGTERM the service stops admitting runs and lets active runs finish for up to a drain timeout (default 120 s) before exit; a deploy during a longer run may still cut it |

### 10.1 Modeled spend ceiling vs. real invoices

1. Store versioned provider/model input-token and output-token unit prices plus per-search-call costs; include a safety factor (proposed 1.25×) and maximal configured token allotments.
2. **Budget structure: base reservations plus a shared contingency pool.** For each mode, a stage's *base reservation* is the worst single-attempt cost of its planned calls at maximum configured tokens, times the safety factor. The *shared contingency pool* is the mode's admitted cap minus the sum of all base reservations. Retries (attempts 2 and 3), the planner replan (FR-03) and the repair branch (repair, re-verification, re-scan, within the FR-17 limits) draw on the pool, first come first served. Stages have no fixed percentage allowances: a fixed split can reject a viable configuration. The v1.4 split (planner 5%, search 15%, writer 30%, verifier 25%, repair 15%, scan 10%) would have failed the startup check in four places even though both modes fit their global caps (§10.3). Provider calls that cannot be bounded or priced are disabled until configured.
3. Before each external call, reserve `max_possible_call_cost × safety_factor` first against the stage's base reservation (first attempt) and then against the pool (retries and repair). If the reservation fails, do not call. After a call returns, reconcile against reported usage and release the unused part of the reservation to where it came from.
4. **Startup call-graph check (FR-37):** at maximum token settings, require (i) the sum of base reservations ≤ the cap, and (ii) the sum of base reservations plus the worst-case pool demand (two further attempts of every first-pass call, one planner replan, and the repair branch within its limits, each with its own retries, all times the safety factor) ≤ the cap. If either fails, refuse to serve that mode. Condition (ii) guarantees that no sequence of retries within the configured limits can exhaust the pool before the pipeline finishes, so an early stage's retries cannot starve a later stage. The measured spurious budget-stop rate must still be ≤2% (§2.6).
5. Never assume absent billing data equals zero. Log an `unknown_cost` state, alert, and block further calls if accounting becomes untrustworthy.
6. This model prevents knowingly exceeding a configured modeled upper bound. Provider rounding, tariff changes, retries outside the app, taxes and delayed metering mean it cannot promise an exact real-money hard stop. Provider-side budget limits and billing alerts remain required wherever supported.
7. The one-process pilot may use in-memory counters. Public launch needs durable distributed counters, per-user quotas and tested stop switches.

### 10.2 Measurement conditions

Log model/provider versions, host type, concurrency, search date and content modes. Run the holdout benchmark of §11.1 in both modes. Report medians and empirical 95th percentiles with percentile-bootstrap 95% intervals (10,000 resamples); these remain approximate for curated and correlated samples. State any provider outages and whether they were excluded; always show the full-rate denominator. A change of model, pricing, verifier, thresholds or major search behavior triggers re-baselining (§11.1).

### 10.3 Worked budget and latency simulation (illustrative)

This simulation shows how the call-graph check (FR-37) is evaluated and which calls dominate cost. **Every price and token count below is an illustrative placeholder, not a current provider price or a measured value.** The M1 harness (FR-42) replaces them with measurements, and the D-13 checkpoint decides whether any target changes.

Assumed unit prices: writer and planner model $2.50 per million input tokens and $10 per million output tokens; verifier and scan model $0.30 and $1.20; search $0.016 per call with extraction enabled. Writer and verifier input maxima come from the §6.1 caps (9,000 and 24,000 tokens for the writer; 7,000 and 9,000 per verifier batch). The §6.2 trim and §8.3 batching enforce them, so the worst case below is a bound, not an assumption. Verifier batch counts come from token sizes: with 1,500-character snippet passages and 3 or 4 quotes per claim, a batch holds about 4 claims, so the worst case is 4 batches in Quick (14 claims) and 9 in Deep (36 claims). The repair pass is limited by §6.1 (6 or 12 claims, 5,000 or 8,000 input tokens), which gives at most 2 or 3 re-verify batches. The worst case also includes the planner replan that FR-03 allows. Figures are rounded; totals are computed from unrounded values.

**Typical run (no repair):**

| Call | Quick | Deep |
|---|---|---|
| Planner (1 call) | 1,000 in / 500 out — $0.0075 | 1,000 in / 500 out — $0.0075 |
| Search | 3 calls — $0.048 | 8 calls — $0.128 |
| Writer (1 call) | 7,500 in / 2,400 out — $0.043 | 16,500 in / 5,500 out — $0.096 |
| Verifier (batches of ≤8 claims) | 2 batches, 7,200 in / 1,200 out — $0.004 | 5 batches, 18,000 in / 3,000 out — $0.009 |
| Coverage scan (1 call) | 1,500 in / 300 out — $0.001 | 3,000 in / 500 out — $0.002 |
| **Total** | **≈ $0.10** (target ≤ $0.30) | **≈ $0.24** (target ≤ $1.50) |

**Worst-case admission by stage, Quick** (maximum-token calls; base reservation = one attempt × 1.25; worst case = three attempts × 1.25):

| Stage | Worst single attempt | Base reservation | Worst case with 2 retries |
|---|---|---|---|
| Planner | $0.0118 | $0.015 | $0.044 |
| Search (4 calls) | $0.0640 | $0.080 | $0.240 |
| Writer (9,000 in / 3,000 out) | $0.0525 | $0.066 | $0.197 |
| Verifier (4 batches, ≤7,000 in / 800 out each) | $0.0122 | $0.015 | $0.046 |
| Coverage scan | $0.0011 | $0.001 | $0.004 |
| **First-pass subtotal** | **$0.142** | **$0.177** | **$0.531** |
| Planner replan (pool-funded) | $0.0118 | — | $0.044 |
| Repair branch, ≤6 claims: repair writer $0.0325 (5,000 in / 2,000 out), re-verify 2 batches $0.0061, re-scan $0.0011 | $0.040 | — | $0.149 |
| **Worst-case total** | | | **$0.724** |

**Worst-case admission by stage, Deep:**

| Stage | Worst single attempt | Base reservation | Worst case with 2 retries |
|---|---|---|---|
| Planner | $0.0118 | $0.015 | $0.044 |
| Search (10 calls) | $0.1600 | $0.200 | $0.600 |
| Writer (24,000 in / 7,000 out) | $0.1300 | $0.163 | $0.488 |
| Verifier (9 batches, ≤9,000 in / 800 out each) | $0.0329 | $0.041 | $0.123 |
| Coverage scan | $0.0022 | $0.003 | $0.008 |
| **First-pass subtotal** | **$0.337** | **$0.421** | **$1.263** |
| Planner replan (pool-funded) | $0.0118 | — | $0.044 |
| Repair branch, ≤12 claims: repair writer $0.050 (8,000 in / 3,000 out), re-verify 3 batches $0.0110, re-scan $0.0022 | $0.063 | — | $0.237 |
| **Worst-case total** | | | **$1.544** |

**Startup check (FR-37):**

| | Quick | Deep |
|---|---|---|
| Admitted cap | $0.75 | $3.00 |
| Sum of base reservations — condition (i) | $0.177 | $0.421 |
| Shared contingency pool (cap − base) | $0.573 | $2.579 |
| Worst-case pool demand (retries, replan, repair branch) | $0.547 | $1.123 |
| Pool spare | $0.026 | $1.456 |
| Base + worst-case pool demand — condition (ii) | $0.724 ✓ | $1.544 ✓ |
| Share of cap used in the worst case | ≈ 97% | ≈ 51% |

**What the simulation shows (under the placeholders):**

1. Search calls dominate typical cost, about 47% of a Quick run and 53% of a Deep run.
2. **A fixed percentage split fails where a shared pool passes.** Under the v1.4 split, the worst case exceeds the stage allowance in four places: Quick planner ($0.044 against 5% of $0.75 = $0.0375), Quick search ($0.240 against $0.1125), Quick repair branch ($0.149 against $0.1125) and Deep search ($0.600 against $0.450). Both modes still fit their global caps, so the split would have refused to serve viable configurations. The base-plus-pool structure removes that failure mode while keeping the total bound.
3. Both modes pass conditions (i) and (ii), but Quick has only about $0.03 of spare pool (3.5% of its cap). That leaves almost no room for a price change, so the D-13 checkpoint must decide whether to raise Quick's admitted cap, lower its claim cap or repair limit, or use a cheaper writer. A writer model priced 2× higher adds about $0.32 to Quick's worst case (writer plus repair $0.085 × 3.75), reaching about $1.04 against the $0.75 cap. Condition (ii) would then fail and the startup check would refuse to serve Quick. The check does real work, and the model choice at M0 matters. Without the FR-17 repair limits, repairing and re-verifying every claim with the full writer input would put Quick at about $0.78, above its cap.
4. Deep has large headroom. At the D-13 checkpoint, either lower the Deep cap or spend the headroom on two-verifier agreement (FR-41).
5. Typical costs sit well below the targets, so targets may be tightened at the checkpoint. The harness records actual retry rates (FR-42) to check how conservative the three-attempt assumption is; the admission model stays worst-case regardless.
6. **Latency risk found before building:** at an assumed 150 output tokens per second, a 2,400-token Quick ledger takes about 16 s against a 14 s drafting budget, and a 5,500-token Deep ledger takes about 37 s against a 40 s budget. Output length, not search or verification, is the likely latency driver. If measurement confirms it, options are a lower Quick claim cap, shorter ledger fields (for example shorter quotes), or parallel per-facet drafting calls.

---

## 11. Evaluation, Annotation Protocol, and Release Gates

### 11.1 Benchmark design: development set, sealed holdout, per-mode eligibility

**Two sets, strictly separated.**

- **Development set:** ≥20 topics, used freely to tune prompts, the verifier, scan, thresholds and eligibility procedures. It is labeled for per-mode eligibility and essential questions during M1, because the PoC checkpoint needs those labels. It is also the source of the verifier-fixture dev half.
- **Holdout set:** ≥80 distinct topics, frozen and **sealed**: not run through the system, and not used to tune anything, before the gate runs. It spans science, health (non-personal), economy, technology, history, policy and regional subjects, and contains ≥10 designed hard cases (source-poor, conflicting, non-English, adversarial or time-sensitive).
- **Burn rule:** if prompts, models, verifier, scan or the §6.4 thresholds are changed after any holdout result has been seen, the inspected holdout topics are burned. Re-qualify on a fresh holdout in which at least 50% of topics are new, and publish the history of burned holdouts.

**Per-mode eligibility (fixes the v1.2 mismatch between eligibility and Completed thresholds).** An independent assessor labels each holdout topic for each mode on the benchmark freeze date. Eligibility means a fair test of Completed is possible with margin above the §6.4 floors. Inventory is recorded (URLs, dates, passages, accessibility) and is **never** given to the agent.

| Mode | Inventory required to be Quick/Deep-eligible | §6.4 Completed floor it must exceed |
|---|---|---|
| Quick-eligible | ≥5 publicly reachable, topic-relevant pages across ≥3 registrable domains; ≥6 distinct explicit factual passages spanning ≥3 facets; ≥2 of the pages returned in `extracted` mode by the configured provider for the assessor's recorded sample queries | 3 evidence groups, 2 domains, 4 claims, 2 facets, ≤80% snippet-only |
| Deep-eligible | ≥10 pages across ≥4 domains; ≥14 distinct explicit factual passages spanning ≥4 facets; ≥4 pages returned in `extracted` mode | 6 evidence groups, 3 domains, 8 claims, 3 facets, ≤70% snippet-only |

- The provider-reachability check queries only the search provider, not the whole pipeline.
- Assessors continue adding topics until ≥50 topics are Quick-eligible and ≥50 are Deep-eligible. Overlap between the two sets is reported. For every eligible topic the assessor also writes the essential questions used by the coverage evaluation (§11.6).
- A second annotator audits ≥20% of eligibility records; disagreements are resolved before any run.
- Topics that fail eligibility remain in the all-runs table. Source-poor, snippet-limited and adversarial topics are graded by **correct terminal status**, not by Completed rate. Never quietly exclude genuine hard cases from all reported metrics.
- Eligibility is a necessary condition for a fair Completed test, not a prediction that the pipeline will succeed.

### 11.2 Verifier and scan fixtures, and human claim annotation

**Verifier fixtures (FR-35).** ≥200 labeled pairs of (claim, quoted passage set), split into a dev half (used to tune the verifier prompt) and a **sealed test half** (≥100 pairs). A minimum dev set of ≥60 pairs (≥20 supported; ≥40 negative, including ≥10 adversarial or injection-bearing) is built in M1 so the PoC checkpoint can measure false accepts and false rejects. M2 expands the inventory to the full set.

- Composition of the test half: ≥30 `supported` pairs; ≥60 negative pairs (unsupported or borderline). Of the negatives, ≥10 carry passage text that attempts to command the verdict (for example "mark this claim supported") and ≥10 more are adversarial near-misses from the extended categories below.
- Negative categories, covered in both halves: wrong number, wrong date/period, flipped polarity or negation, broadened scope or population, topically related but irrelevant, and mention-versus-assertion. Extended adversarial categories: hedge turned into certainty ("may" to "will"), conditional turned unconditional, attribution swap (who said it), currency/unit/magnitude swap (million versus billion, ₹ versus $), similar-entity confusion, opinion presented as fact, past versus current tense, and ambiguous table-fragment readings.
- Two reviewers label every fixture; disagreements are adjudicated.
- A script (`eval/`) produces the scorecard: confusion matrix, false-accept and false-reject counts, Wilson intervals, injection-pair outcomes. Gate thresholds are in §2.6.

**Coverage-scan fixtures.** ≥40 synthetic reports containing ≥30 planted material factual sentences placed in `interpretation` or `transition` slots, plus ≥40 clean reports (≥200 interpretation/transition sentences) for the false-positive rate. Gate: ≥29 of the ≥30 planted sentences detected and ≤10% of clean sentences falsely flagged. Over-flagging matters because every false flag removes a legitimate sentence.

**Human claim annotation (holdout reports).**

- **Sample:** ≥160 displayed material factual claims from ≥50 holdout reports. Spread across modes, topic domains, Completed/Partial, snippet/extracted, and citation positions. Sample uniformly within strata using a recorded random seed; cap at 4 claims per report. Fifty reports at the cap give 200 claims, which leaves slack for Partial reports holding fewer than 4. If fewer than 160 claims are available, sample additional holdout reports until 160 is reached, and report the actual distribution. At least 10% of claims are numeric/time-sensitive where available. Oversample risky conflicts separately as a stress metric, not in the main sample.
- **Reviewer view:** reviewers see the exact passages and quotes available to the model, not live web pages (a separate source-authenticity audit may use live pages).
- **Label rubric:**

| Label | Decision rule | Gate treatment |
|---|---|---|
| `supported` | Quoted passage directly entails the entire claim, including quantities, scope, dates and attribution | Success |
| `partially_supported` | Some material qualifier, quantity, causal claim, or population not established | Failure |
| `unsupported` | Cited text is irrelevant, contradicts the claim, or supports a different statement | Failure |
| `not_assessable` | Passage unavailable/truncated, citation cannot be inspected, or ambiguity prevents a decision | Failure |

- **Staffing (D-12):** two reviewers independent of the engineer who wrote the writer/verifier prompts. Reviewer A labels all claims; reviewer B independently labels ≥50% (≥80). Pre-calibrate on 20 non-scored claims. Adjudicate all disagreements by documented joint decision with the product owner as tie-breaker. The engineer may not label or adjudicate gate claims. Record instructions, reviewer identities, evidence mode, inter-annotator agreement, and anonymized failure examples.
- **Fallback:** if only one independent reviewer is available, the pilot may proceed with single-annotator labeling, and the result is labeled **"evaluation-only; double-label requirement unmet"** under the §11.5 waiver policy. It is not a release pass.

### 11.3 Statistical decision rules

- **Human grounding gate (pilot):** ≥160 annotated claims from ≥50 reports; observed `supported` / reviewed ≥92%; **report-level cluster-bootstrap** 95% lower bound ≥85% (resample reports with replacement, 10,000 resamples, recompute the pooled rate). Report the Wilson interval alongside for reference. Claims within a report are correlated, so plain Wilson understates uncertainty; the cluster bootstrap is the binding interval. No known fabricated URL and no knowingly published confirmed unsupported material claim. This is a controlled benchmark gate, not a guarantee of 92% accuracy in arbitrary use.
- **Completion gate (pilot):** on ≥50 mode-eligible holdout attempts per mode, observed Completed rate ≥95% (≥48 of 50). The Wilson 95% lower bound is reported for transparency; at n=50 the observed-rate criterion is the binding one. Other attempts remain in the all-runs table. No retroactive recategorization of eligibility after poor results without a signed re-annotation reason. **Provider outages:** a run that fails or degrades during a provider-wide outage, shown by the provider's status record or by a failed health probe logged by the harness within the run window, is rerun once after recovery. The original attempt stays in the all-runs table and leaves the gate denominator only with that audit evidence. Publish both the gate rate and the all-attempts rate.
- **Status correctness:** on ≥20 fixed Partial/Failed fixtures plus all hard-case and source-poor holdout topics, ≥95% of automatic statuses match the rubric expectation; zero source-poor fixtures marked Completed. The rubric derives from §6.4 counts, not subjective readability.
- **Provenance safety:** 100% of deterministic reference and provenance tests pass; zero fabricated URLs or IDs in the published sample. A single violation is a blocker regardless of aggregate percentage.
- **Public launch expanded gate:** ≥150 mode-eligible attempts per mode with ≥97% observed Completed and Wilson lower bound ≥93% (for example 146/150); ≥400 reviewed claims across ≥100 reports with ≥95% observed supported and cluster-bootstrap lower bound ≥90%, with ≥50% double-labeled and fully adjudicated. Revalidate after provider or model revisions.
- **Stratum reporting:** per-stratum rates (mode, status, evidence mode, topic domain) are descriptive only. Do not draw inferential conclusions from strata with fewer than 20 claims.
- **Caveat:** all intervals assume the sampled topics and claims are representative. Curated benchmarks and repeated-provider effects mean the intervals may understate real deployment uncertainty. Never present them as production guarantees. Publish point estimates, numerator/denominator, intervals, sampling design, seeds and exclusions.

### 11.4 Minimum executable tests

1. Empty, excessive-length and unsupported-script topics → no provider call.
2. Quick/Deep caps (queries, sources, claims, tokens) include verifier, scan, repair, and retries.
3. Duplicate/canonical/syndicated handling and exact deterministic ranking order and passage selection.
4. Snippet vs extracted vs metadata-only treatment; passage chunking boundaries; truncation flags.
5. Cited `[99]`, a model-created URL, or a source ID from an old run → blocked.
6. A real registered source cited for an irrelevant claim → verifier returns `unsupported`; claim does not publish.
7. Paraphrase with wrong quantity, timeframe, subject or polarity → not supported.
8. A quote absent from the stored passage (even if the topic is similar) → blocked before any model call.
9. A claim whose number or date is not in its quote → blocked by the numeric guard; a computed figure (sum, growth rate) → blocked.
10. One repair only; repaired claims and sentences are fully re-checked; failed repair ⇒ Partial/Failed.
11. Typed-sentence rules: an `interpretation` sentence with a new number or entity, a `transition` containing digits, untyped text, and writer-authored `meta` are all rejected.
12. A planted unledgered factual sentence is caught by the coverage scan fixtures (§11.2).
13. Same-scope contradictory evidence cited both ways, no false consensus.
14. An all-snippet but otherwise rich run yields `SNIPPET_HEAVY` Partial per the numeric threshold.
15. Threshold boundaries for sources, domains, claims, facets and snippet share tested at N−1, N and N+1 for both modes.
16. Failure, timeout, budget stop, and invalid key: safe status, no secret, no fabricated report.
17. Run manager: semaphore max 5, one-per-session lock and idempotency token under concurrent requests, including release on exception.
18. A Streamlit rerun (widget interaction or fragment poll), a websocket reconnect within one session, and a double-click during a run neither duplicate nor terminate the run; the UI re-attaches by `run_id`.
19. The heartbeat watchdog stops new calls within one stage boundary after 90 seconds (configurable) without a poll, and the result is discarded and purged.
20. Unknown provider pricing or an unbounded token request blocks the call; the maximum modeled reservation is never exceeded.
21. Startup call-graph check refuses a mode whose worst-case reservation exceeds its cap.
22. Markdown download and the Partial banner match rendered verified content.
23. Feedback event is idempotent, redacted (no topic/report text), and keyboard-activatable.
24. Clear-session erases report and evidence and disables the stale download; About/Privacy/FAQ are accessible.
25. Prompt-injection text inside snippets and rendered Markdown cannot exfiltrate secrets or alter instructions, including content shown to the verifier and the scanner; verifier injection fixtures produce zero false accepts.
26. Accessibility: keyboard-only flow, screen reader, 320px/200% zoom and alert announcements, including the polling stage display and the Evidence Details panel.
27. Planner output with too few facets or too few distinct categories triggers one replan; a second shortfall returns `PLAN_TOO_NARROW` with zero search spend (Quick ≥3 facets, Deep ≥4).
28. Evidence Details shows the claim, matched quote, URL, passage ID and evidence mode for every displayed claim as escaped plain text; the export's Evidence appendix matches the panel.
29. After a full page reload the new session shows the idle form and the orphaned run stops through the watchdog without publishing a result. Polling throttled by a background tab does not cause a false abandonment at the configured timeout (measure the slowest throttled poll interval in the supported browsers).
30. The facet coverage list marks unsupported planned facets "not covered"; a Completed report is never called comprehensive in the UI or the export.
31. The measurement harness reproduces per-call tokens, cost, retry counts and stage timings for a dev-set run and flags any call-graph or stage-budget violation against §10.3.
32. Pool accounting: retries, the planner replan and the repair branch draw on the shared contingency pool; conditions (i) and (ii) are both enforced; a configuration whose worst-case pool demand exceeds the pool is refused at startup (including a configuration shaped like the v1.4 percentage split); a simulated worst-case run (every call retried twice, plus one planner replan and one repair) finishes without a budget stop.
33. The evaluation tooling computes readability and coverage scores, medians and bootstrap intervals from reviewer label files, and reproduces the numbers in a hand-computed fixture.
34. Token caps: a passage set above the writer input cap is trimmed in the specified deterministic order and never exceeds the cap under the estimator; verifier batches never exceed 8 claims or the verifier input cap, with excess claims spilling into extra batches; the harness reports estimator error against provider-reported token counts.
35. Export safety: hostile snippet and claim text (HTML and script tags, image and link syntax, code-fence breakouts, Markdown control characters) renders as inert text in at least two common Markdown renderers, and only registry URLs are clickable.
36. KPI counters: `evidence_opened`, `export_downloaded` and `feedback_vote` are recorded once per run, contain no topic, report, passage or user identifier, and aggregate correctly.
37. Claim placement: each `claim_id` is printed once, in its assigned section; the summary and conclusion respect their per-mode limits; the §6.4 counts use distinct claim IDs.
38. Outage rule: a simulated provider-wide outage during a benchmark run triggers one audited rerun, and the report shows both the gate rate and the all-attempts rate.
39. A plan that stays too narrow after one replan, and a search with no usable evidence, both end Failed with the correct reason code and no unnecessary spend.
40. Graceful drain: after the wrapper sees SIGTERM, new submissions are rejected as "Service paused", active runs finish, and the process exits when the count reaches zero or the drain timeout passes.
41. The result-expired, service-paused and mode-unavailable states show the right copy, and Clear session removes every session key except the session ID. The daily spend stop rejects new runs as "Service paused" and survives a restart (FR-45).
42. Repair limits: a run with more failed claims than the limit repairs only the first 6 (Quick) or 12 (Deep), within the repair input cap; the worst-case run in test 32 still finishes without a budget stop.

### 11.5 Pilot release gates (hard vs. configurable)

| Category | Gate | Waiver policy |
|---|---|---|
| Hard safety | Citation/URL validity, FR-33 checks, sentence-typing rules, claim support check and repair coverage, no known fabricated reference, no credential exposure | No waiver |
| Hard status | §6.4 centralized numeric rules, frozen before holdout; Partial/Failed fixtures; zero source-poor items Completed | No waiver |
| Screening | Verifier and coverage-scan scorecards on the sealed fixture test halves (§2.6) | Re-run after fixes on a fresh fixture half; no waiver of the injection-pair criterion |
| Measured quality | §11.3 grounding and eligible-topic completion targets, §11.6 coverage targets and §11.7 readability targets, on the sealed holdout | Re-run on a fresh holdout (burn rule). An exception requires sponsor + evaluator sign-off and the pilot is labeled evaluation-only, not release-passed |
| Performance/cost | Targets in §10, recorded p50/p95 with bootstrap intervals, modeled pre-call admission, no unpriced outgoing calls, spurious budget stops ≤2% | Latency/cost deviations may be approved for an access-restricted pilot with disclosed limits; admission safety cannot be waived |
| UX/privacy | Core flows, run robustness (NFR-17), feedback/clear/FAQ, retention, WCAG blocker review, accurate provider disclosures | No waiver for secret leaks or an inaccessible primary flow |
| Public | All §17 controls and expanded evaluation benchmarks | No soft approval from pilot evidence |

### 11.6 Essential-question coverage evaluation

The §6.4 thresholds are deterministic minimums. They show that a report has some supported claims across some facets, not that it answers what a reader needs. Coverage adequacy is therefore measured separately, and independently of whether individual claims are supported.

1. **Essential questions.** While labeling eligibility (§11.1), the assessor writes the questions a competent briefing on the topic must answer: ≥5 for Quick-eligible topics and ≥8 for Deep-eligible topics, each one sentence with a pointer to the inventory pages that answer it. They are written blind to any system output. A second annotator audits ≥20% of them.
2. **Scoring.** After the holdout runs, the independent reviewers (D-12) score each essential question against the displayed supported claims in the report, using ledger text only and not model-written interpretation: `covered` (1.0), `partial` (0.5) or `missing` (0). A report's coverage score is the mean over its questions. Score every Completed holdout report plus ≥20 Partial reports sampled across reason codes, and double-label ≥50%.
3. **Gate (provisional until D-13):** mean coverage over Completed holdout reports ≥0.60 for Quick and ≥0.70 for Deep, and no more than 10% of Completed reports below 0.40 ("hollow completions"). Report the distribution and per-topic scores with a topic-level bootstrap interval (10,000 resamples).
4. **Use of results.** Coverage is measured offline. No gold questions exist at runtime, so a Completed report is never downgraded automatically. If hollow completions exceed the limit, revise the §6.4 thresholds or the planner facet rules, then qualify on a fresh holdout (burn rule). Do not adjust the rubric after seeing scores.
5. **Runtime proxies.** Planner breadth rules (FR-03) and per-facet coverage disclosure (FR-39) reduce narrow plans and make gaps visible to the reader; they do not replace this evaluation.

### 11.7 Readability and usefulness evaluation

The trust-first prose model (§6.3) trades fluency for verifiability. Whether that trade is acceptable is a measured product outcome, not an assumption.

1. **Rubric.** Reviewers rate each report 1–5 on four items: *clarity* (each statement is understandable on its own), *organization* (findings are grouped so a reader can follow them), *takeaway* (a reader could state the main findings after one read), and *reading effort* (absence of choppiness and repetition). The overall readability score is the mean of the four. The annotator guide defines anchors for 1, 3 and 5, and reviewers calibrate on 5 non-scored reports.
2. **Sample.** At the PoC: all dev reports (≥20), one reviewer. On the holdout: ≥50 reports, the same reports used for claim review (about 3 minutes each), double-labeled on ≥50%.
3. **Targets (provisional until D-13):** holdout median overall score ≥3.5, and ≥70% of reports ≥3.0. These are product-quality targets, not safety gates, and follow the measured-quality waiver policy in §11.5.
4. **Readability trigger.** If the PoC median overall score is below 3.0, the D-13 Adjust outcome may pull verified aggregation (FR-43) into pilot scope through change control. Allowed levers, none of which may weaken §8.3: ordering and grouping claims by facet; code-generated section headings; constrained transitions; and composite claims, meaning a sentence that combines two or more supported claims of the same facet is itself a ledger claim carrying all of its quotes and passing FR-33 and the verifier. Any lever is re-evaluated against the verifier-fixture and grounding gates before use.
5. **Usefulness signal.** Feedback votes (FR-26) are reported alongside these scores but gate nothing in the pilot.

---

## 12. Security, Privacy, and Abuse Prevention

### 12.1 Trust boundaries

- User topic input and third-party search content are untrusted. This includes passages shown to the writer, the verifier and the coverage scanner.
- Retrieved text is passed as delimited data, never as privileged instructions. Models must not execute webpage-embedded commands or disclose credentials. Verifier and scanner outputs are parsed as strict JSON; anything else is treated as failure.
- Do not construct arbitrary server-side fetch requests from model-generated URLs. Use only the configured search/retrieval provider and approved extraction behavior.
- Render Markdown using framework-safe behavior; prohibit executable HTML/script injection if HTML rendering is enabled.
- Quotes and claim text derived from third-party passages are rendered as escaped plain text in Evidence Details. Links are rendered only from registry URLs.
- The Markdown export applies the same rule to everything third-party: claim text, quotes and source titles are escaped so that HTML, link and image syntax, and code fences inside them stay inert when the file is opened in any Markdown viewer. Titles used as link labels have their brackets escaped. The export contains no raw HTML or scripts.
- Restrict secret visibility to the server process; avoid verbose external-provider error serialization.
- Enforce topic size, query count, source count, claim count, retries, output size and maximum execution time.
- The worker threads of the run manager have no access to Streamlit session secrets beyond the run's own inputs.

### 12.2 Pilot data lifecycle (D-03, D-08)

| Data | Where used | Proposed retention | Notes |
|---|---|---|---|
| Topic and generated report | App process memory, session | Session only; erased on explicit clear, TTL purge (§8.4), or session expiry | No persistent product database |
| Selected evidence passages and ledger | App process memory during and after the run | Same as above | No full-page cache for the MVP |
| Metrics (run_id, durations, counts, status/reason codes, error code, cost estimate) | Restricted operational logs | ≤7 days | No raw topics, passages, report bodies, or secrets |
| Feedback votes (run_id, mode, status, reason codes, vote, timestamp) | Restricted operational logs | ≤7 days; counters without `run_id` may be kept longer | No topic or report text |
| Authentication/rate-limit tokens (only if hosted) | Access gateway/host | Minimize; host policy documented | Public launch may require a separate notice |
| Content sent to model/search providers | Third-party services | Subject to provider contracts and settings | Document requests, subprocessors, retention, regional controls; deletion cannot be guaranteed |

Explicitly document in a privacy notice that submitted topics and retrieved passages may be transmitted to the search and model providers (including the verifier and scanner calls). Before any public launch, obtain a security/privacy review of provider data processing, international transfers where relevant, and the hosting platform. If required retention controls cannot be honored by the chosen host, revise the policy rather than claiming compliance.

### 12.3 Abuse and cost controls

For the access-restricted pilot: one in-flight run per session, ≤5 concurrent runs per process, and configurable daily application spend alert/stop budgets. Make host and network rate limits part of the deployment configuration. Use server-side key storage only.

For public launch: an identity-aware rate limiter backed by shared storage (not in-process counters), for example a proposed starting quota of 10 runs/account/day plus 1 concurrent run/account; IP/network abuse protections with privacy review; CAPTCHA or challenge when appropriate; billing alerts; per-user caps; and an emergency kill switch. Tune values after load testing; they are not approved pricing policy.

### 12.4 Compliance and regulatory requirements (pilot)

This section lists obligations to check before the pilot handles real users' topics. It is not legal advice and makes no claim that the product complies with any law or provider term. What applies depends on who the users are and where the service is hosted.

| Area | Pilot requirement | Owner | Evidence |
|---|---|---|---|
| Data-protection law | Before hosting, identify the laws that apply to the pilot's users and hosting location (for example India's Digital Personal Data Protection Act, 2023, or the EU GDPR). Treat topics as potentially personal data. The privacy notice (FR-28) states purposes, recipients (search and model providers), retention (D-03, D-08) and a contact | Product owner + privacy reviewer | Written applicability note in the decision log |
| Provider terms and data processing | Read and record each provider's current terms on retention, use of inputs for training, regional processing, subprocessors and permitted use of returned content. This covers the verifier provider if D-11 adds a second vendor. Configure the available no-training and retention settings; record any gap | Engineering + privacy reviewer | Dated provider-terms checklist |
| Website content and copyright | Use only provider-returned results; no access-control bypass (NFR-13). Keep excerpts bounded (snippets ≤1,500 characters, quotes ≤300 characters), attribute with source links, and store nothing beyond the session | Product owner + privacy/legal reviewer | Excerpt-limit tests; privacy/legal review note |
| AI transparency | Label output as AI-generated and evidence-checked, not fact-checked (§8.3 step 8); disclose limits in the FAQ (§7.5) | Product owner | UI and FAQ review |
| Accessibility | WCAG 2.2 AA is a testing target (§7.4). No conformance claim is made without an audit | Product owner + QA | Audit record (PL-08 for public) |
| Security baseline | Server-side secrets, dependency audit, injection fixtures (NFR-10; PL-05 for public) | Engineering | Test and audit records |
| Sensitive and personal topics | The UI tells users not to enter personal, confidential or sensitive data; pilot guidance excludes research about private individuals | Product owner | Notice text and FAQ |
| Records | Keep the decision log, provider-terms checklist and applicability note for the life of the pilot | Product owner | Records exist and are current |

---

## 13. Deployment and Failure Behavior

### 13.1 Pilot deployment

1. **Local:** Python environment, `.env.example` copied to `.env`, provider keys stored outside version control; start via `streamlit run app.py`.
2. **Hosted internal:** managed Python deployment as a **single process** with server-side secret injection, access restriction, TLS via the hosting platform, health checks, fixed caps, and redacted logs. Do not run replicas or multiple workers (§8.4).
3. **Configuration:** `SEARCH_API_KEY`, `OPENAI_API_KEY`, writer and verifier model/provider settings, query/source/claim/token/runtime limits, price sheet version, operational log retention, spend thresholds, `CONTACT_URL`, allowed deployment origins as applicable.
4. **Startup checks:** validate required config without logging secret values and run the call-graph check (FR-37). If required configuration is missing, or neither mode passes, exit non-zero so the platform does not route traffic. If only one mode fails, start with that mode disabled ("Mode unavailable") and raise an alert.
5. **Rollback:** retain the previously tested build/version and deployment configuration; roll back for systemic failures or a citation-integrity regression.

### 13.2 Provider failure policy

| Failure | Retry behavior | User-facing result |
|---|---|---|
| Bad/missing key, invalid request | No retry | Setup/actionable error; never reveal the key |
| Provider rate limit | Up to 2 bounded retries if Retry-After/budget allows | Partial result or graceful failure |
| Temporary network/5xx | Up to 2 backoff retries | Partial if verified evidence exists; else failure |
| Search returns no usable evidence | Optional distinct-query attempt within cap | Explain no sources; do not synthesize an unsupported answer |
| Some sources blocked or snippet-only | Continue with remaining evidence | Prominent source limitations and mode labels |
| Model timeout or spend ceiling | Stop further model/search calls | Safe Partial if previously validated; else failure |
| Verifier unavailable or malformed output | No retry beyond the 2 transient retries; unparseable output counts as `unsupported` | Claims are omitted; Partial or Failed per §6.4 |
| Invalid citation IDs, quote/numeric mismatch or unsupported claims | One constrained repair, then rerun checks | Never show an unsupported claim as completed; only safe Partial or Failed |
| Process restart during a run | None | The user sees the idle form with the standing notice (§7.3); there is no separate state |

### 13.3 Telemetry schema (redacted)

```json
{
  "run_id": "opaque-id",
  "mode": "quick",
  "stage": "verification",
  "result": "completed",
  "reason_codes": [],
  "elapsed_ms": 38900,
  "stage_elapsed_ms": { "planning": 3800, "searching": 9100, "drafting": 13000, "verifying": 8400 },
  "search_requests": 3,
  "source_count": 7,
  "unique_domain_count": 5,
  "model_input_tokens": 12400,
  "model_output_tokens": 1600,
  "modeled_spend_ceiling_usd": 0.75,
  "estimated_actual_cost_usd": 0.22,
  "supported_claim_count": 6,
  "removed_claim_count": 2,
  "snippet_only_claim_share": 0.5,
  "evidence_opened": false,
  "export_downloaded": false,
  "feedback_vote": null,
  "error_code": null
}
```

Avoid raw prompts, document text, full URLs (which may contain identifiers), API responses, IP addresses, and provider credentials in application telemetry by default. Diagnostic detail may be held transiently during a local debug session and must not be uploaded to production logs without approval. `removed_claim_count` supports measuring verifier over-removal.

---

## 14. Assumptions, Dependencies, and Risks

### 14.1 Assumptions

Each assumption names what breaks if it is false and where it gets checked. Record a validation outcome for every row by the end of the stated milestone.

| ID | Assumption | If false | Validated by |
|---|---|---|---|
| A-01 | The search provider returns usable snippets and, for a meaningful share of results, provider-permitted extracted passages | Most runs end Partial with `SNIPPET_HEAVY`; Completed is rarely reachable | Extracted-mode check in eligibility labeling; PoC (M1) |
| A-02 | Writer and verifier models follow the strict JSON and ledger schemas reliably within 2 retries | Completion drops; repair is overused | PoC (M1) |
| A-03 | The verifier meets the fixture screening gate (§2.6) | Unsupported claims reach readers; FR-41 or a different model is needed | Fixture scorecard (M2) |
| A-04 | Model output speed is about 150 output tokens per second or better | Drafting stage budgets (§6.1) are missed; claim caps or per-facet parallel drafting are needed | Measurement harness (M1) |
| A-05 | Provider unit prices are obtainable and stable enough to keep a versioned price sheet | Cost admission blocks calls or is wrong | Price sheet at M0; re-check at D-13 |
| A-06 | Pilot load stays at or below 5 concurrent runs on one process, and in-memory run records fit host memory | Busy responses; memory pressure | Load test (M3) |
| A-07 | The pinned Streamlit version supports `st.fragment` polling and same-session reconnect, and background-tab throttling is manageable | The run model (§8.4) needs a different UI approach | M0 check; test 29 (M2) |
| A-08 | Pilot users write English topics of 500 characters or fewer | Rejections frustrate users | D-01; pilot feedback |
| A-09 | Two independent reviewers are available on the §15 schedule | Evaluation-only fallback (D-12) | M0 |
| A-10 | Public web content and provider results stay stable across the holdout window (proposed ≤14 days from the freeze date) | Eligibility inventories go stale; re-inventory is needed | Freeze date and run window recorded (M3) |
| A-11 | The host provides access control, TLS, secret injection and log-retention control for a single process | Hosted pilot is blocked (D-04) | M0 and before the hosted run |
| A-12 | Users accept terse, verified reports in place of fluent prose | Low usefulness; FR-43 trigger | Readability scores (§11.7) and KPIs (§2.7) |
| A-13 | A wrapper process can drain the app on SIGTERM, because the app cannot trap the signal itself | Deploys cut active runs | M0 check (NFR-19) |

### 14.2 Dependencies

| Dependency | Used for | Constraint or risk | Mitigation | Owner |
|---|---|---|---|---|
| Search provider (Tavily, behind an adapter) | Retrieval of URLs, snippets and extracted passages | Outage, rate limits, price or terms changes, extraction availability | Adapter interface keeps a swap feasible; bounded retries; re-baseline on change (§19) | Engineering |
| Writer and planner model provider (OpenAI) | Query planning, ledger drafting, repair | Model deprecation or behavior change, price changes, data terms | Pin model versions; versioned price sheet; re-baseline on change | Engineering |
| Verifier and scan model (different family where available, D-11) | Semantic verification and coverage scan | A second vendor adds another key, terms review and failure mode | Record in the provider-terms checklist (§12.4); fixture gate | Engineering + QA |
| Streamlit (pinned version) | UI, polling fragment, session state | Accessibility limits; version-specific behavior | Pin the version; accessibility audit; M0 check | Engineering |
| Python libraries (public suffix list, URL canonicalization, statistics for bootstrap) | Registrable domains, deduplication, evaluation tooling | Stale suffix data; vulnerable packages | Pin versions; refresh the suffix list; dependency audit (PL-05 for public) | Engineering |
| Hosting platform | Single-process hosting, TLS, secrets, logs | No access control or log-retention control | A-11 check; D-04 | Engineering + product |
| People: product owner, engineer, two independent reviewers | Decisions, build, grounding and coverage evaluation | Availability | M0 named roles and schedule (D-12) | Product owner |
| Benchmark assets (dev and holdout sets, eligibility inventories, fixtures) | Evaluation and gates | Content drift; leakage | Freeze date; sealed holdout; burn rule (§11.1) | QA |
| Privacy and legal review | Hosted pilot sign-off | Delays | Schedule at M0; §12.4 checklist | Product owner |

A change to any provider, model, extraction depth, retention or hosting setup triggers the change-control rule in §19.

**Candidate open-source tools (not dependencies).** Twelve projects are tracked as references or dev tools in `architecture.md` §16: GPT Researcher, STORM, Trafilatura, Instructor, DeepEval, Promptfoo, Crawl4AI, Arize Phoenix, Ragas, Docling, LangGraph and SearXNG. None is a dependency, and each needs the adoption review in that section before it enters the runtime or CI. A tool that fetches pages (Crawl4AI, Docling, Trafilatura's fetching), sends content to a new third party, or changes the search provider needs PRD change control first (D-02, D-03, §12.4, §19).

### 14.3 Risks and mitigations

| Risk | Impact | Mitigation / owner |
|---|---|---|
| Hallucinated citation / unsupported claim | Trust damage | ID/URL checks, quote match, numeric guard, semantic verifier, sentence typing, plus independent human sampling; engineering + QA |
| Verifier false accepts or correlated errors with the writer | Unsupported claims shipped | Different model family where available (D-11); sealed fixture gate; injection fixtures; human sampling; engineering + QA |
| Verifier over-removal lowers completion and report value | Poor product value, failed completion gate | Track `removed_claim_count`; measure false-reject rate on supported fixtures (§2.6); tune on dev set only; engineering |
| Benchmark overfitting / holdout leakage | Inflated release evidence | Dev/holdout split, sealed holdout, burn rule, published holdout history; QA |
| Snippet scarcity makes Completed unattainable | Low completion; pressure to relax thresholds | Per-mode eligibility with extracted-mode check; thresholds frozen (D-10); feasibility review at M2; product + QA |
| Snippet mistaken for full-text evidence | False confidence | Source-mode labels, explicit excerpt scope, extraction only when allowed; engineering |
| Writer smuggles facts into interpretation or transition sentences | Unverified assertions | Typed sentences, deterministic token rules, coverage scan with recall gate; engineering |
| Website prompt injection (writer, verifier, scanner) | Content or secret compromise | Data/instruction separation, strict JSON outputs, no tool scope, injection fixtures; security + engineering |
| Streamlit rerun interrupts a run; spend continues untracked | Wasted cost, lost results, duplicate runs | Background run manager, idempotency token, heartbeat watchdog (§8.4); engineering |
| Full page reload orphans a run (new Streamlit session) | Lost report, wasted spend until the next stage boundary | Explicitly out of pilot guarantee; reload warning, FAQ, 90 s watchdog; optional recovery token (FR-38); engineering + product |
| Completed reports that are technically valid but shallow ("hollow completions") | Users over-trust a thin report | Facet breadth rules, per-facet coverage disclosure, "Completed" wording, essential-question coverage gate (§11.6); product + QA |
| Cost or latency targets infeasible with the chosen models | Pilot slips or targets quietly relaxed | §10.3 simulation, M1 PoC checkpoint with Go/Adjust/Stop (D-13), measurement harness; engineering + product |
| Search provider outage / rate limit | Poor completion | Retries, hard limits, graceful partial/failure; engineering |
| Poor domain diversity / syndicated duplicates | False consensus | Registrable-domain logic, evidence groups, coverage notices; QA |
| Reservation rules starve healthy runs | Spurious Partial results | Base reservations plus a shared contingency pool, startup conditions (i) and (ii), ≤2% spurious-stop metric (§10.1); engineering |
| Independent annotators unavailable, or a failed first holdout forces rework | Grounding sign-off delayed; schedule slips | Reviewers named at M0 with a written availability schedule (D-12); explicit rework contingency (§15); decide the evaluation-only fallback before M3; product owner |
| User enters confidential topic | Privacy exposure | Clear notice, no persistent storage, provider processing review; product + security |
| Spend spike / anonymous abuse | Unexpected bills | Access restriction, per-mode budgets, alerts, later per-user rate limits; ops |
| Cost and latency vary by model/provider | Bad UX/economics | Benchmark under pinned configuration, stage budgets, re-baseline on change; engineering |
| Accessibility failures (including the polling UI) | Excluded users | Keyboard/mobile/screen-reader checks; product + QA |
| Copyright/access terms | Legal exposure | Link/attribution, bounded excerpts, no bypassing controls; product/security |
| Rapidly changing subject | Staleness | Research timestamp; distinguish event, publication and retrieval dates; product |
| Terse list-style reports reduce perceived quality | Low user satisfaction | Disclose in FAQ; readability rubric measured at the PoC and on the holdout (§11.7); readability trigger can pull verified aggregation (FR-43) into the pilot; product |

---

## 15. Delivery Plan, Resourcing, and Estimates

**Assumptions:** one experienced Python/Streamlit developer, one search API and one model API (plus a verifier model per D-11), no public authentication or database in the pilot. Estimates are person-hours, not elapsed time or promises. They include the added P0 work: quoted-span and numeric guard, sentence typing, coverage scan, verifier fixtures, run manager, and the dev/holdout benchmark with per-mode eligibility. API/vendor uncertainty and verifier tuning can expand them.

| Milestone | Scope | Engineering | Independent QA / annotation | Product / ops / privacy | Exit criteria |
|---|---|---|---|---|---|
| M0 — Decisions & foundation | Name owner and two independent reviewers and agree their availability schedule; approve D-01–D-05, D-10–D-12; pick models, pricing assumptions, repo; confirm Streamlit fragment support | 8–12 h | 1–3 h | 4–6 h | Signed one-page decision log including reviewer availability; booting local app |
| M1 — Proof-of-concept slice | Thin vertical slice for both modes: UI shell, planner/provider, deterministic ranking, registry, passage chunking, ledger drafting, quote/numeric checks, verifier, rendering; measurement harness (FR-42) and PoC report. QA side: dev-set eligibility labels and essential questions (≥20 topics), minimum verifier dev fixture (≥60 pairs), dev readability scoring, review of dev outputs | 32–52 h | 23–36 h | 2–4 h | PoC checkpoint decision recorded: Go, Adjust or Stop (D-13) |
| M2 — Trust core + failure handling | Full ledger, sentence typing, coverage scan, repair, status engine, run manager, graceful drain wrapper, budgets/call-graph check, Evidence Details panel, facet taxonomy and replan, coverage disclosure, writer/verifier token caps with trim and token-based batching, export escaping, KPI counters, privacy/FAQ/feedback; expand verifier fixtures to ≥200 pairs including adversarial, build scan fixtures and attack fixtures | 63–99 h | 12–20 h | 2–4 h | Fixture, adversarial and boundary tests pass |
| M3 — Evaluation + private pilot | Instrumentation, benchmark runner, sealed holdout runs, scorecard/bootstrap/coverage/readability tooling, hosting, accessibility fixes, compliance checklist (§12.4), release docs | 40–68 h | 100–138 h | 12–20 h | §11 evidence, §12.4 compliance checklist and §16 checklist signed |
| **Pilot total** | M0–M3 | **143–231 h** | **136–197 h** | **20–34 h** | **299–462 person-hours combined** |

**M1 proof-of-concept checkpoint (D-13).** Before committing to M2, run the M1 slice on the ≥20-topic dev set in both modes and produce a PoC report covering:

- per-call token counts and cost against the §10.3 simulation;
- per-stage latency against the §6.1 budgets, including ledger drafting time;
- verifier false-accept and false-reject counts on the dev fixtures, and the share of drafted claims removed;
- the Completed/Partial/Failed distribution with reason codes;
- grounding on a dev sample of ≥40 claims (labeled by anyone; not a gate);
- essential-question coverage and readability scores (§11.7) on dev reports;
- measured retry rates, to check the worst-case attempt assumption in §10.3.

The checkpoint ends in one of three recorded outcomes. **Go:** continue to M2 unchanged. **Adjust:** revise the cost, latency, status-threshold and coverage targets once, using dev-set data only, record the revisions in the decision log, then freeze them with the core requirements. If the median dev readability score is below 3.0, Adjust may pull verified aggregation (FR-43) into pilot scope through change control (§11.7). **Stop and redesign:** for example if dev-sample grounding is below 75%, if fewer than half of the eligible dev topic-mode runs (roughly 20–30 runs, reported as counts because the dev set is small and the result is directional) reach Completed after one tuning round, or if the §10.3 call-graph check cannot be satisfied with any affordable model pair. These stop criteria are proposals to confirm at M0.

**Annotation labor breakdown (M3 QA, estimate):** eligibility inventory plus essential questions for ≥80 topics across both modes ≈ 46–58 h; second-annotator audit of eligibility records and essential questions ≈ 9–12 h; claim labeling for ≥160 claims ≈ 12–16 h; double labeling of ≥80 claims ≈ 7–9 h; calibration and adjudication ≈ 5–8 h; essential-question coverage scoring of Completed reports and ≥20 Partial reports ≈ 4–7 h; reviewing holdout runs, status fixtures and hard cases ≈ 8–13 h; readability scoring of ≥50 holdout reports ≈ 3–5 h; accessibility audit ≈ 6–10 h. These sum to 100–138 h. The minimum dev verifier fixture (≥60 pairs) and the dev-set eligibility labels with essential questions are budgeted in M1 QA. The rest of the fixture construction (expansion to ≥200 pairs, 40 synthetic reports with planted sentences, and 40 clean reports) is budgeted in M2 QA.

**Evaluator commitment (M0 exit criterion).** At M0, name the two independent reviewers and record a written availability schedule covering their combined time: roughly 23–36 h during M1 (dev labeling), 12–20 h during M2 (fixtures), and 100–138 h concentrated in a 3–4 week M3 window, plus the rework window below if needed. If that schedule cannot be met, choose the D-12 fallback (single annotator, evaluation-only) before M3 starts, not after the holdout has run.

**Rework contingency (not in the totals).** If the first sealed holdout fails any measured gate, the burn rule (§11.1) requires re-qualifying on a fresh holdout with ≥50% new topics. Plan for at least one such cycle: about 57–79 h of QA and annotation (new eligibility inventories and essential questions ≈ 23–29 h, audit ≈ 4–6 h, claim labeling ≈ 12–16 h, double labeling ≈ 7–9 h, calibration and adjudication ≈ 3–5 h, coverage and readability scoring ≈ 4–7 h, run review ≈ 4–7 h), about 16–40 h of engineering for tuning and reruns, another holdout pass of API spend, and 2–4 further working weeks. Separately, a failed sealed verifier or scan fixture test half needs a fresh test half (§11.5): about 8–14 h of QA to build ≥100 verifier pairs or the scan fixtures anew, plus the tuning time above.

**Benchmark API spend (planning estimate from this PRD's own targets, not provider quotes):** one sealed holdout pass is about 80 Quick runs at ≤$0.30 plus 80 Deep runs at ≤$1.50, around $144 at targets and up to $300 at admission ceilings. With dev-set iteration, fixture runs, re-runs and a possible fresh holdout, reserve roughly $600–$800 (including PoC checkpoint runs) pending real unit prices. The §10.3 placeholders suggest typical per-run costs well below the caps, so this reserve is conservative and should be revised at the D-13 checkpoint. Hosting costs are additional.

**Schedule planning envelope:** approximately 9–13 working weeks, before the rework contingency, with one engineer and part-time independent reviewers, depending on availability and provider rates. This is not a committed delivery date. Reserve 15–25% contingency for verifier calibration and provider variability; it is not included in the table totals.

If real report density cannot supply enough claims for the sample, additional holdout runs and cost are added explicitly. Public-launch hardening (distributed quotas, auth, policy/security reviews, larger samples) is not included.

### 15.1 Lean RACI and gate ownership

| Workstream | Accountable | Implementer | Independent verifier |
|---|---|---|---|
| Scope, status thresholds, MVP approval | Named product owner at M0 | Lead developer (same person allowed for a solo team) | Independent reviewers |
| Search/LLM integration, budgets, run manager | Lead developer | Lead developer | QA reviewer |
| Trust-core tests, fixtures, evaluation and claim-label protocol | Product owner | Lead developer builds tooling; **reviewers label** | Two independent reviewers (D-12) |
| Hosted privacy, legal and security configuration | Product owner | Lead developer / host ops | Privacy, legal and security reviewer (one person may hold all three roles) before hosting |
| Public release authorization | Named sponsor | Ops + engineering | Independent security/privacy sign-off |

M0 is a real blocker: until an accountable owner, an implementer, and two independent reviewers are named, the PRD remains an implementation-review candidate, not an approved pilot or public launch. One person may fill product and engineering roles, but may not label, adjudicate or sign off gate claims. If only one independent reviewer exists, or the availability schedule in §15 cannot be met, use the evaluation-only fallback in §11.2, and decide that at M0 rather than after the holdout.

---

## 16. Definition of Done: Access-Restricted Pilot

- [ ] Named owner, implementer and two independent reviewers with a written availability schedule; M0 decisions D-01–D-05 and D-10–D-12 recorded.
- [ ] English topic validation, Quick/Deep, progress, status, feedback, clear-session, About/Privacy and FAQ usable.
- [ ] Run manager keeps runs alive across Streamlit reruns; idempotency, session lock, capacity limit and heartbeat watchdog tested, including background-tab throttling (NFR-17).
- [ ] The full-page-reload limitation is disclosed in the UI and FAQ.
- [ ] Evidence Details panel and the export's Evidence appendix show the claim, matched quote, source link and evidence mode for every displayed claim.
- [ ] M1 proof-of-concept checkpoint (D-13) report recorded, with any one-time target revisions logged before the holdout is run.
- [ ] Essential-question coverage and hollow-completion rate measured on the holdout (§11.6).
- [ ] Readability scored on dev reports at the PoC and on holdout reports (§11.7); any use of the readability trigger is recorded.
- [ ] Startup call-graph check enforces both conditions (i) and (ii) for each mode, with the shared contingency pool (§10.1).
- [ ] Search provider respects source restrictions; deterministic source ranks, passage chunking and a current-run registry in place.
- [ ] Ledger claims carry verbatim quotes; quote match and numeric guard pass for every displayed claim.
- [ ] An independent semantic verifier operates at runtime for all material factual claims; sealed verifier and coverage-scan fixture scorecards meet §2.6.
- [ ] Sentence typing enforced; unsupported/uncertain claims removed; one repair at most; zero fabricated URLs.
- [ ] Completed/Partial/Failed assigned per §6.4 with frozen thresholds and reason codes.
- [ ] Conflicts attributed fairly; insufficient evidence never hidden behind a Completed label.
- [ ] Safe Partial export and Completed export preserve the same verified Markdown, clickable references and Evidence appendix.
- [ ] Provider faults, prompt injection (writer, verifier, scanner), wrong-source citations, quantity/date mismatch, concurrency races, budget admission and call-graph check pass §11.4.
- [ ] Provider-facing data notice, session-only clearing and redacted logs tested; no secret disclosure.
- [ ] Graceful drain and the result-expired, service-paused and mode-unavailable states are tested (NFR-19; tests 40 and 41).
- [ ] Compliance checklist (§12.4) completed and filed; every assumption in §14.1 has a recorded validation outcome; dependency versions are pinned (§14.2).
- [ ] KPI counters (FR-44) emit aggregate-only data, and baselines are recorded over the pilot period (§2.7).
- [ ] Writer and verifier input caps are enforced by the trim and batching rules, and the estimator error is reported (§6.2 step 7, §8.3 step 3).
- [ ] The Markdown export is escaped against hostile third-party text and tested in at least two renderers (FR-12).
- [ ] Sealed holdout results recorded: eligibility labels, annotator protocol, sample sizes, cluster-bootstrap and Wilson intervals, latency bootstrap intervals, burn history, release gates (§11).
- [ ] Any permissible measured-target exception explicitly signed; the product stays labeled evaluation-only and is never silently marked release-passed.
- [ ] Local setup and deployment runbook, tested rollback, and access-restricted configuration available.
- [ ] Pilot not open to unrestricted anonymous public access.

---

## 17. Public Launch: Mandatory Independent Gate

Access-restricted pilot approval does not authorize public or multi-tenant launch. Public release needs a newly signed review of each item below.

| ID | Requirement | Evidence / pass rule |
|---|---|---|
| PL-01 | Owner and response process | Named release owner, incident contact, rollback runbook and verified emergency shutdown |
| PL-02 | Shared admission | Auth or reviewed equivalent anti-abuse protections; shared job queue, distributed quotas/leases, per-user limits and bounded queues verified in load tests |
| PL-03 | Spend protection | Provider-side billing alerts plus shared modeled-budget counters, tested kill switch and invoice reconciliation |
| PL-04 | Privacy | Provider flow/retention disclosures, legal/privacy sign-off, notices, support contact and data-processing review |
| PL-05 | Security | No open critical/high issues; injection, URL, secret, dependency and auth review passed |
| PL-06 | Run reliability | ≥150 mode-eligible attempts per mode; ≥97% observed Completed with Wilson lower bound ≥93%; all-run status outcomes published |
| PL-07 | Grounding / claims | ≥400 independently sampled claims across ≥100 reports; ≥95% observed support with cluster-bootstrap lower bound ≥90%; ≥50% double-annotated; 100% citation provenance |
| PL-08 | Accessibility | WCAG 2.2 AA targeted audit, documented supported browsers, no severe core-flow blocker |
| PL-09 | Monitoring | Error, status-reason, latency, modeled cost, unusual spend and provider alerts tested in staging |
| PL-10 | User guidance | Public English-language limitation, evidence modes, Partial/Failed meanings, attributions and terms published |
| PL-11 | Coverage adequacy and reload recovery | Essential-question coverage gate (§11.6) re-run on an expanded sample with ≥150 mode-eligible attempts per mode; reconnect or shared job-queue recovery of runs verified under load (PL-02) |

Public-launch sample sizes and interval rules follow §11.3. Provider, model or retention architecture changes require targeted re-evaluation; an outdated pilot pass is not inherited automatically.

---

## 18. Roadmap Beyond Pilot

**Phase 2:** verified aggregation into more fluent prose (FR-43, without weakening §8.3; may be pulled into the pilot by the §11.7 readability trigger), an enhanced evidence view (passage highlighting and filtering), reload recovery (FR-38), two-verifier agreement for high-risk claims (FR-41), improved cross-source corroboration, richer primary-source metadata, PDF/DOCX export, opt-in authenticated history, source/date filters and measured multilingual exploration.

**Phase 3:** follow-up research Q&A over retained authorized evidence, scheduled updates, report comparisons, group workflows and reusable trusted-source collections. These depend on additional access control, retention, evaluation and budget policies.

---

## 19. Decision Register and Closure Rules

**Closure rule:** a decision is APPROVED only when the explicit choice, named approver, date and evidence/link appear in a decision log. An unapproved default is PROPOSED, not a decision; disputed or unknown choices are BLOCKED. The owner may be the solo builder, but two independent reviewers must be named for trust sign-off.

| Decision | Proposed baseline | Approver | Required by | State |
|---|---|---|---|---|
| D-01 English pilot | §6.7 script heuristic, English reports | Product owner TBD | M0 | PROPOSED |
| D-02 Snippets + allowed extracts | Evidence labels and no arbitrary crawler | Tech lead TBD | M0 | PROPOSED |
| D-03 Session-only retention | Explicit provider-processing notice | Product owner TBD | M0 | PROPOSED |
| D-04 Single-process internal hosting | Access restricted, TLS if hosted | Product owner TBD | Before hosted run | PROPOSED |
| D-05 P0 trust policy | §8.3 ledger, quote match, numeric guard, verifier, sentence typing | Product + QA TBD | M0 | PROPOSED |
| D-06 Freshness | Search date and contextual recency | Product owner TBD | M2 | PROPOSED |
| D-07 Pre-call spend policy | §10.1 worst-case modeled admissions + call-graph check | Tech lead TBD | M2 | PROPOSED |
| D-08 Redacted logging and feedback | ≤7-day retention where the host permits | Privacy/ops TBD | M3 hosted | PROPOSED |
| D-09 Public access | Disallowed until §17 approvals | Sponsor TBD | Public gate | PROPOSED |
| D-10 Status thresholds | §6.4 mode-specific criteria, frozen before holdout | Product + QA TBD | M0 | PROPOSED |
| D-11 Verifier independence | Different model family from writer where available | Eng + QA TBD | M0 | PROPOSED |
| D-12 Annotation staffing | Two independent reviewers; evaluation-only fallback | Product owner TBD | M0 | PROPOSED |
| D-13 PoC checkpoint and provisional targets | §15 Go/Adjust/Stop; one-time revision of targets from dev-set data, then freeze | Product + eng TBD | M1 exit | PROPOSED |

No named approvers are invented. Before M1, the project sponsor must record the individuals filling the product, engineering and two reviewer roles. Revisions to the verifier definition, status thresholds, pricing assumptions, provider, retrieval depth, audience, hosting or retention require versioned change review and targeted tests. Changing P0 pass rules solely to improve scores is prohibited without transparent re-baselining and a fresh holdout (§11.1 burn rule). **Requirements freeze:** the core requirements (§6, §8.3, §8.4, §9) are frozen at the D-13 checkpoint; later changes follow the change-control rule above.

---

## 20. Document Notes and Change Log

This is a proposed product/engineering specification, not an external-provider service commitment. API terms, price schedules, privacy and retention claims, hosting limits, data-processing permissions and model capabilities require verification during implementation. Quantified quality metrics are release targets, not measured product results. Any pre-existing prototype is a baseline; it is not evidence that the P0 trust verifier, UI controls, run manager or benchmarks are implemented.

| Version | Date | What changed |
|---|---|---|
| 1.0 | 2026-10-21 | Initial traceable multi-site research MVP proposal |
| 1.1 | 2026-10-21 | Scope decisions, evidence modes, NFRs, UX, deployment and evaluation gates |
| 1.2 | 2026-10-21 | Promoted semantic support verification to P0; deterministic status thresholds and source scoring; Wilson/annotation methodology; feedback, clear-session, privacy and FAQ requirements; language, concurrency and cost-admission specs; expanded estimates; simplified governance |
| 1.3 | 2026-10-21 | Closed the v1.2 review findings (first findings table below) |
| 1.4 | 2026-10-21 | Closed the v1.3 review findings (second findings table below) |
| 1.5 | 2026-10-21 | Closed the v1.4 review findings (third findings table below) |
| 1.6 | 2026-10-21 | Closed the v1.5 review findings and added the missing standard sections (fourth findings table below) |
| 1.6.1 | 2026-10-21 | Added a pointer to the candidate open-source tools tracked in architecture.md §16, with the change-control rule for tools that fetch pages or add data flows (§14.2) |
| 1.7 | 2026-10-21 | Applied the architecture review findings: corrected worst-case cost model, repair limits, restart and expiry states, graceful drain, reviewer roles; then a scoring pass added FR-45, fixed the decision-order contradiction with FR-17, updated estimates and test 32 (fifth findings table below) |

**v1.3 review findings and where they were addressed**

| Finding in v1.2 review | Resolution | Section |
|---|---|---|
| Completion gate conflicted with Completed thresholds (eligibility floor below Completed floor; shared topic list) | Per-mode eligibility with margin above the floors, plus an extracted-mode provider check; thresholds frozen | §11.1, §6.4, D-10 |
| Verbatim passage check could be vacuous; passage chunking undefined | Writer emits a verbatim `quote`; defined normalization and match; numeric guard; chunking rules | FR-33, §8.3, §9.2–9.3 |
| "Material factual claim" undefined; coverage scan unspecified | Normative definition; sentence typing with deterministic token rules; scan as a second layer with a recall gate | §6.8, FR-34, §8.3 steps 5–6 |
| Verifier never measured on its own; correlated errors | Labeled fixture sets with sealed test half, scorecard script, injection pairs, false-accept and false-reject gates; verifier independence decision | FR-35, §2.6, §11.2, D-11 |
| Tuning leakage; undercounted annotation labor | Dev set vs sealed holdout with burn rule; re-estimated labor, schedule and API spend | §11.1, §15 |
| Streamlit rerun semantics unspecified | Background run manager with idempotency, heartbeat watchdog, result TTL | FR-36, §8.4, NFR-17 |
| Feedback storage conflicted with session-only retention | Feedback votes are 7-day operational metadata, no content | FR-26, D-03, D-08, §12.2 |
| Annotation staffing unrealistic for a solo project | Two reviewers independent of the engineer; evaluation-only fallback | D-12, §11.2, §15.1 |
| Reservation rule could cause spurious budget stops; verifier batching and latency unspecified | Stage allocations, reservation reconciliation, startup call-graph check, batching and stage time budgets | §10.1, §6.1, FR-37 |
| Risk table stale | Added verifier error, over-removal, overfitting, snippet scarcity, rerun interruption, reservation starvation, annotator availability, and prose-quality risks | §14 |
| Statistics: redundant interval clause; clustered claims; thin strata | Cluster bootstrap by report is the binding interval; sample raised to ≥160 claims from ≥40 reports; observed-rate criterion stated as binding for completion; strata descriptive only | §11.3 |
| Dangling "starter ZIP" reference; metric table conflated integrity and quality | Reference removed; metrics grouped as integrity, screening and quality | §20, §2.6 |

**v1.4 review findings and where they were addressed**

| Finding in v1.3 review | Resolution | Section |
|---|---|---|
| A full browser reload creates a new Streamlit session, so a run could be orphaned | Pilot guarantee limited to in-page reruns and same-session reconnects; full reload explicitly excluded, warned about and disclosed; orphaned runs stop via the watchdog (90 s, tuned for background-tab throttling); a recovery token is specified as P1 | FR-36, FR-38, §8.4, §7.3 |
| Evidence was checked internally but not inspectable by users in the pilot | Evidence Details panel and the export's Evidence appendix promoted to P0 | FR-20, FR-12, §6.3, §7 |
| A Deep plan with two facets could never reach Completed | Planner must return ≥3 (Quick) or ≥4 (Deep) facets in distinct categories; one replan; `PLAN_TOO_NARROW` before any search spend | FR-03, §6.1 |
| Completeness and coverage weakly measured | Per-facet coverage disclosure; blind-authored essential-question coverage evaluation with a hollow-completion limit; "Completed" never means comprehensive | FR-39, FR-40, §11.6, §6.4 |
| Cost and verifier feasibility unproven | Worked call-graph simulation with sensitivity and a latency finding; M1 proof-of-concept checkpoint with Go/Adjust/Stop; measurement harness; larger adversarial fixture set; scan false-positive gate; optional two-verifier agreement | §10.3, §15, FR-42, FR-41, §11.2 |
| Housekeeping: v1.3's M3 QA subtotal (76 h low) did not match its own breakdown (86 h low) | Estimates recomputed from the itemized breakdown | §15 |

**v1.5 review findings and where they were addressed**

| Finding in v1.4 review | Resolution | Section |
|---|---|---|
| The fixed per-stage percentage split contradicted the global-cap simulation | Replaced the split with per-stage base reservations plus a shared contingency pool; the startup check now has conditions (i) and (ii); §10.3 is recomputed by stage and shows the old split would have failed in four places (Quick planner, Quick search, Quick repair branch, Deep search) | §10.1, §10.3, FR-37 |
| M1 depended on fixtures budgeted in M2 | A minimum dev verifier set (≥60 pairs) and dev-set eligibility and essential-question labels moved into M1; M2 expands the inventory | §11.1, §11.2, §15 |
| Evaluation is operationally heavy and a failed holdout was unplanned | Reviewers named at M0 with a written availability schedule (exit criterion); per-milestone hours; explicit rework contingency; estimates raised to 286–439 person-hours | §15, §15.1, D-12 |
| Terse claim-by-claim prose may not satisfy readers | Readability is a measured outcome at the PoC and on the holdout; a trigger can pull verified aggregation (FR-43) into the pilot through D-13 | §11.7, FR-40, FR-43, §15 |

**v1.6 review findings and where they were addressed**

| Finding in v1.5 review, or request | Resolution | Section |
|---|---|---|
| Writer input cap undefined, so the worst case was not enforced. The same gap existed for verifier batch input | Added writer and verifier input caps, a deterministic trim, and token-based batching. §10.3 recomputed: Quick worst case $0.645 (about 86% of cap), Deep $1.431 (about 48%) | §6.1, §6.2 step 7, §8.3 step 3, §10.3, FR-15 |
| Grounding sample arithmetic (160 claims from 40 reports at a cap of 4 left no slack) | ≥160 claims from ≥50 reports, with a rule for shortages | §2.6, §11.2, §11.3, §11.7 |
| Claim counting and reuse undefined | `section` field; each claim printed once; counts use distinct `claim_id`s; summary and conclusion limits | FR-08, §6.3, §6.4, §9.3 |
| Markdown export not escaped | Escaping rules, an export test, and a DoD item | FR-12, §12.1, §11.4 |
| Outage treatment in the completion gate | Audited rerun and exclusion rule; both rates published | §11.3, §2.6 |
| `PLAN_TOO_NARROW` and no-evidence missing from the decision order | Added to step 1 | §6.4 |
| Fixture rework unbudgeted | Added to the rework contingency | §15 |
| Noisy PoC Stop criterion | Reported as counts and marked directional | §15 |
| Missing standard sections | Added §2.7 Product KPIs, §12.4 Compliance, §14.1 Assumptions, §14.2 Dependencies (§14 renamed), and FR-44 | §2.7, §12.4, §14, FR-44 |
| Estimates | Re-estimated to 294–453 person-hours | §15 |

**v1.7 findings (from the architecture review) and where they were addressed**

| Finding | Resolution | Section |
|---|---|---|
| The worst-case cost omitted the planner replan, assumed 2 and 5 verifier batches, and left repair unbounded | Replan included; batch counts from token sizes (4 and 9); repair limited to 6 or 12 claims and 5,000 or 8,000 input tokens; §10.3 recomputed: Quick $0.724 (about 97% of cap, $0.03 spare), Deep $1.544 (about 51%); D-13 decides whether to raise Quick's cap | §6.1, FR-17, FR-37, §10.1, §10.3, D-13 |
| `evidence_opened` cannot come from a browser-only expander; post-run events cannot be written onto a finished log line | Toggle widget for Evidence Details; counters recorded as separate events and joined by run ID | FR-20, FR-44, §7.4 |
| "Run lost" state is unreachable after a restart or reload | State removed; the idle form with the standing notice covers it. Added "Result expired", "Service paused" and "Mode unavailable" | §7.3, §7.5, §8.4, §13.2 |
| Daily spend stop needs a counter that survives restart | Counter and drain markers declared operational metadata | D-03 |
| Repair trigger and session ID unspecified | Repair only when the first-pass status is not Completed; app-generated session ID | FR-17, §9.1 |
| Readiness mechanism unspecified | Exit non-zero if nothing is servable; disable a single failing mode | §13.1 |
| No graceful shutdown | Wrapper-based drain, NFR-19, A-13, test 40 | §8.4, §10, §14.1, §11.4 |
| Legal reviewer role unnamed | One privacy, legal and security reviewer role before hosting | §4, §12.4, §15.1 |
| v1.7 changes add work not yet in the estimates | M2 engineering raised by 5–9 h for the drain wrapper, replan accounting, repair limits and the new states: 63–99 h; pilot total 299–462 person-hours | §15 |
| The daily spend stop had a state, a decision and a section but no requirement | FR-45 added; test 41 extended | FR-45, §7.3, D-03, §12.3 |
| A verifier could only be a hosted model | **Approved change, 2026-10-22, requested by the project user.** A local Ollama model is a supported verifier, reached through the OpenAI-compatible endpoint on this computer with schema-constrained JSON and strict validation of every reply. It gets no real credential, is never replaced by another provider when it fails (the run fails closed), and detects when Ollama silently cut a prompt short (`ContextTruncated`). The PRD's verification, citation, cost and time limits are unchanged. A 45-pair synthetic development set and `eval/verifier_eval.py` measure accuracy, time and memory; they cannot certify the §2.6 gate. On the development laptop the 8B model is accurate on that small set but is not shown to meet the gate's false-accept rate and is too slow for either mode's time limit | §8.1, D-11, §2.6, §11.2, NFR-03, ARCH ADR-021 |
| Only paid OpenAI and Anthropic keys were a supported way to run live | **Approved change, 2026-10-22, requested by the project user.** NVIDIA Build's OpenAI-compatible hosted API is a supported provider for both roles. Development default: `nvidia/nemotron-3-ultra-550b-a55b` as planner and writer, `openai/gpt-oss-20b` (hosted by NVIDIA) as verifier; `google/gemma-4-31b-it` was the first choice but its hosted endpoint timed out on every request in a live probe on 2026-10-22. Independence under D-11 is judged by model family (vendor of the model), never by hosting platform, and startup refuses a same-family pair. Original providers stay configurable. Verification, citation checks and fail-closed behavior are unchanged; JSON is validated strictly on our side even where an endpoint offers no structured-output mode. A free-prototype price sheet carries budgeting rates (not charges) with a review date; live mode refuses it after that date. NVIDIA describes this hosted API as a trial for prototyping, so it is a development setting, not a pilot-hosting decision | §8.1, D-11, §10.1, NFR-04, NFR-05, ARCH ADR-020 |

**Non-negotiable product rule:** If a material claim is not supported by an identified passage from a registered current-run source and cannot pass runtime verification, do not publish it as factual research. Return an explicitly limited Partial result when safe evidence exists; otherwise return Failed. A verified citation checks source support, not the truth of the internet source.
