# Build ledger

Record of the build that followed the user's approval of the six documents (2026-10-21). The documents
are the binding spec; there was no separate plan file, so `tracker.md` served as the task list. Every
decision that went beyond or against a document is a ruling here, with what it costs if wrong.

Format: `Ruling: <what> — <why> — <cost if wrong>`.

## Rulings

1. Ruling: the number word "one" is not a numeric-guard token (two to ten are) — "one" is an idiom
   ("one of the", "no one") and would reject correct claims — a claim whose only number is "one" is
   not checked against its quote (the verifier still reads it).
2. Ruling: no `git init`, no commits — rules.md §10 requires the user's approval and the approval to
   build did not mention version control — the work is uncommitted; initialise when approved (M0-03).
3. Ruling: a small `.env` parser in `core/settings.py` instead of `python-dotenv` — rules.md requires
   a justification for each dependency and the parser is 15 lines — an unusual `.env` syntax may parse
   differently.
4. Ruling: the token estimator and the passage/quote size constants live in `core/tokens.py`, not
   `capacity.py` — the registry, checks and capacity module all need them and `pipeline` must not import
   `core.capacity` for a constant — a rename if the documents' tree is preferred.
5. Ruling: ledger normalization is lenient (misplaced claims are moved, unplaced ones appended, unknown
   sentence references dropped) rather than rejecting the draft — a writer that mis-sections a claim
   should not cost the run its budget — a slightly different section order than the writer intended.
6. Ruling: status counts use registry-usable sources (PRD-literal), not only cited ones — matches PRD
   §6.4 — a run may count a usable source no claim cites.
7. Ruling: demo mode serves a synthetic corpus about a fictional topic on reserved domains, and the UI
   and every report carry a demo notice — real-looking fake research would mislead (rules.md: never
   fabricate) — none beyond the labeling.
8. Ruling: `ProviderCircuitOpen` is not retried within a call — an open breaker means fail fast — a
   run during a provider outage fails immediately instead of waiting.
9. Ruling: module placement follows ARCH §4.3, not the tracker's file names: `core/run_manager.py` and
   `core/research_agent.py` (first built under `pipeline/`, moved when import-linter showed the layering
   gap); `pipeline/verifier.py`, `scan.py`, `writer.py`, `repair.py`, `report.py`; one `adapters/live.py`
   for the three live adapters — the layering contracts need the run machinery above `pipeline`, and one
   file keeps the shared parsing in one place — ARCH §4.1 was updated to the built tree; tracker "Files"
   columns still show the planned names.
10. Ruling: `ui/*` may also import `core.settings` (mode limits) and `core.text_safety` (a new pure
    helper for escaping and link safety) — ARCH §4.3 rule 2 lists only run_manager, models and errors
    but its layering sentence lets every layer use settings, and the UI must escape third-party text
    without importing `pipeline` — one more allowed module in `.importlinter`.
11. Ruling: model output is requested in JSON mode and validated with pydantic, not with provider
    strict structured output — strict schemas reject optional fields and defaults used by the models
    — a malformed answer costs a schema retry instead of being prevented.
12. Ruling: no `temperature` is sent to OpenAI (several current models accept only the default) or to
    Anthropic (the installed SDK's `Messages.create` takes none) — sending it would fail or be
    rejected — answers are less deterministic; the `LLMClient` protocol still carries the argument.
13. Ruling: live mode refuses to start on the placeholder price sheet and when the verifier provider is
    OpenAI (the writer's family) — PRD D-11 requires an independent verifier and rules.md forbids live
    spend without real prices — a user cannot try live mode until they supply both.
14. Ruling: the Completed banner uses the PRD §7.3 copy "coverage is not exhaustive" even though design
    DR-7 forbids the word "exhaustive" in Completed copy — the PRD text is verbatim authority and the
    word is negated — the lint test strips that phrase before checking forbidden words.
15. Ruling: a verifier verdict of `uncertain` is treated like `unsupported` (the claim is removed or
    sent to repair) — PRD FR-19 says non-supported claims are removed — fewer claims survive.
16. Ruling: the scan runs once, after repair, over the final claim set. A scan outage drops all
    interpretation and transition sentences with a warning; a budget or time stop inside the scan or
    repair keeps the first-pass claims and marks the run Partial — saves a scan call and never
    publishes unchecked connecting text — a run may lose harmless transitions.
17. Ruling: a search stage with at least one successful query continues; all queries failing is
    `SEARCH_FAILED` — partial results are still real evidence — thinner evidence, reported as Partial.
18. Ruling: "Try again" rotates the idempotency token while "Research" reuses it — a double-click must
    return the same run, a deliberate retry must start a new one — none.
19. Ruling: the telemetry allowlist gained a `ui.feedback` event and a `vote` field — PRD requires
    feedback votes without report content — none.
20. Ruling: ruff ignores E501 for prose-heavy files (copy, theme CSS, synthetic corpus, prompts, tests)
    and UP042 everywhere; mypy is strict for application code and relaxed for tests — wrapping
    sentences mid-string hurts review, and `(str, Enum)` keeps members plain strings for JSON — a
    stricter rule set may surface more findings later.
21. Ruling: the 8 `pillow` advisories reported by `pip-audit` are not fixed — `pillow` is only a
    Streamlit dependency, 1.66.0 pins it below the fixed 13.0.0, and the app renders no user-supplied
    images; overriding the pin is riskier — exposure if Streamlit ever renders attacker-supplied images.
22. Ruling: `entrypoint.py` (the SIGTERM wrapper) has no automated test; the drain handshake it uses
    (`core/drain.py`, run manager integration) is tested — testing real signals and child processes is
    platform-specific — a wrapper bug would show only at deploy time (M2-21 is marked Partial).
23. Ruling: a run whose provider reports no usage is charged its full reservation and flagged
    `unknown_cost` — a conservative bound is safer than a guess — the daily guard may stop early.

24. Ruling: a call that fails with a schema violation or a content refusal is charged its full
    reservation (and flagged `unknown_cost`); timeouts, 5xx and 429 are released — the provider
    produced and billed a response in the first case, and charging every timeout would drain the
    pool on outages — a timed-out call the provider did bill is not counted, so the daily stop can
    under-count slightly.
25. Ruling: a claim longer than 210 characters (`claim_text_allowance` 60 tokens x 3.5) is rejected
    as `CLAIM_TOO_LONG`; passage titles sent to the writer are cut at 120 characters; scan and
    repair prompts are built to their input caps and anything that does not fit is dropped or
    flagged — the cost model assumed these sizes — a long but valid claim is lost.
26. Ruling: the numeric guard now also treats letter-adjacent numbers (FY2023, Q3), leading decimals,
    signs, ISO dates and clock times (as whole tokens), abbreviated magnitudes (k, m, bn), number
    words up to "ninety" and "hundred", quantity words (half, twice, doubled) and ALL-CAPS months as
    tokens — the review showed each could change a figure unnoticed — more false rejects (for
    example "5 m" meaning metres, or "Q3" against "third quarter"); Roman numerals and ordinals
    beyond "third" are still not covered.
27. Ruling: interpretation and transition rules now check the first word too (a short list of
    sentence starters is allowed), reject spelled-out numbers and URLs, and the quote match requires
    word and number boundaries — lowercase new entities ("the mayor cancelled funding") cannot be
    caught by rules and rely on the model scan — one such sentence could pass if the scan misses it.
28. Ruling: the daily spend stop is checked only when a run is admitted, so concurrent runs can
    overshoot it by up to the number of workers times a mode cap — reserving against the daily cap
    would add a second ledger the PRD does not specify — a bad day can overspend the stop; lower
    `DAILY_SPEND_STOP_USD` or `MAX_CONCURRENT_RUNS` if that matters.
29. Ruling: ruling 16 stands (a scan outage drops the non-claim sentences and the run may still be
    Completed) — nothing unchecked is published — PRD §6.4 may intend the scan to be a required
    stage; if so a scan outage should be Partial.
30. Ruling: an interpretation may cite claims shown in any section — the rules only need a valid
    supported claim — none.
31. Ruling: heartbeat behaviour under a throttled background browser tab is untested (needs a real
    browser, M2-25) — the 90 s timeout was chosen to tolerate throttling — a long-backgrounded tab
    could abandon its own run.
32. Ruling: regression tests for the final review live in `tests/test_final_review_fixes.py`, with
    the shared `make_ctx` fixture re-exported from `tests/conftest.py` — one place to see what the
    review changed — none.

## NVIDIA Build support (2026-10-22)

The user asked for NVIDIA Build (free prototype API) as the development default: Nemotron 3 Ultra as
planner and writer, Gemma 4 31B as verifier, Tavily kept, original providers kept. NVIDIA's behavior was
checked against its documentation only: no live call was made (no key, no approved call).

33. Ruling: verifier independence is judged by model family (the model's own name; vendor, hosting prefixes and tags are ignored), not by
    hosting platform or provider; this replaces the earlier rule that refused any OpenAI-compatible
    verifier — the user's pair is two families on one platform and PRD D-11 asks for a different family;
    PRD v1.8 and ADR-020 record it — two models from one vendor under different names (for example two
    Llama models) are refused, and a vendor shipping unrelated families under one name would be accepted.
34. Ruling: for NVIDIA the JSON mode defaults to `none` (schema in the system prompt, strict parse and
    validation) and `response_format` is opt-in — NVIDIA documents Gemma 4 as having no structured-output
    mode and shows none for hosted Nemotron — more malformed answers, each retried and charged; no
    verification step was weakened.
35. Ruling: NVIDIA requests send `max_tokens` and `temperature`; the output-length parameter name is a
    setting (`WRITER_TOKEN_PARAM`, `VERIFIER_TOKEN_PARAM`) — the two model pages disagree
    (`max_tokens` against `max_completion_tokens`) — a wrong default shows up as a 400 in the probe and
    is fixed in `.env`.
36. Ruling: reasoning blocks (`<think>...</think>`, `<|channel>thought...<channel|>`) are removed before
    the JSON is located, and an unfinished block means no answer — reasoning can contain JSON-looking
    text and must never be parsed as the answer — a model that answers inside its reasoning block fails
    closed and is retried.
37. Ruling: the writer is sent `chat_template_kwargs {"enable_thinking": false}` unless
    `WRITER_THINKING=on`; the verifier gets no such field — it is documented for Nemotron and keeps
    output short enough for the token caps; Gemma's switch is a prompt token and is not used — a
    Nemotron deployment that benefits from reasoning needs the setting turned on.
38. Ruling: the free-prototype price sheet holds the PRD section 10.3 rates as budgeting rates, not
    charges, and carries `review_after` (2027-01-20); live mode refuses it after that date — a zero
    price would make every cost cap and the daily stop meaningless, and the user asked not to assume the
    endpoints stay free — displayed costs are notional, and caps would understate if NVIDIA ever charged
    more than the budgeting rates.
39. Ruling: `NVIDIA_MAX_RPM` defaults to 40 and writer and verifier share one rate limiter — no limit is
    published for this API, both roles use one key and endpoint — a lower real limit shows up as 429s
    (retried, honoring Retry-After); a higher one wastes time.
40. Ruling: base URLs must be `https` (or `http` on localhost), checked at startup — a key must not be
    sent in clear text because of a typo in `.env` — a plain-HTTP internal gateway needs the check
    loosened.
41. Ruling: the hosted NVIDIA API is treated as a development setting only — NVIDIA's blog says
    production use is self-hosted NIM under an enterprise license — a pilot on this API would need that
    reviewed first (M0-08); the UI and About page say the terms can change.
42. Ruling: `.env.example` keeps `RESEARCH_PROVIDER_MODE=fake` while naming the NVIDIA models and URLs —
    a copied file must not start calling providers by accident — the user has one extra edit to go live.
43. Ruling: `eval/provider_probe.py` exists for the key owner to run (four tiny calls) and refuses to run
    without `--yes-call-live-providers` — it is the only honest way to confirm the documented behavior,
    and rules.md forbids my making the first live call — until it is run, the NVIDIA notes in ARCH §8.6
    stay documentation-level.
44. Ruling: the About page now names the configured providers and models (PRD §7.5 asks for it) — it
    was generic text before — none.
45. Ruling: providers `openai` and `anthropic` keep their previous defaults (`max_completion_tokens`, JSON
    mode, no temperature for OpenAI) — the original path must not change behavior — none.
46. Ruling: `PriceSheet` and `Settings` gained fields (free_prototype, review_after, checked_on, writer
    and verifier provider, JSON mode, token parameter, base URLs, thinking, rate) — all derived from
    environment variables and covered by tests — none.
47. Ruling: the earlier ruling 13 (live mode refuses an OpenAI verifier) is superseded by ruling 33 —
    kept for the record — none.

## Live probe and verifier change (2026-10-22, later)

At the user's request the probe was run against NVIDIA Build with the user's key, followed by diagnostics
(model listing, tiny calls to several candidate verifiers, a four-way test of reasoning controls): about 14
requests of at most 800 tokens, no search, no keys printed, scripts kept outside the project.

48. Ruling: the verifier is `openai/gpt-oss-20b`, replacing `google/gemma-4-31b-it` — the user chose it after
    Gemma 4 timed out on 4 of 4 requests while Nemotron answered in under 3 s; OpenAI's family differs from
    Nemotron, so D-11 holds — gpt-oss-20b on the free tier stalled past 60 s on about one request in three,
    so runs can end `VERIFIER_FAILED` or `TIMEOUT`.
49. Ruling: per-role timeout factors (`WRITER_TIMEOUT_FACTOR`, `VERIFIER_TIMEOUT_FACTOR`) scale the stage
    timeouts, and `.env.example` sets the verifier's to 2.0 — a real verifier batch can take 30 to 50 s at
    8 tokens per second, longer than the 30 s default — a stall now costs a longer wait before the retry; the
    guard still caps every call at the time left in the run.
50. Ruling: reasoning-effort controls for gpt-oss-20b were measured and not adopted — a system-prompt
    `Reasoning: low` and `chat_template_kwargs` changed completion tokens only from 112 to 151 and latency
    not at all, and the top-level `reasoning_effort` field timed out once — more reasoning tokens than
    necessary on each call.
51. Ruling: I edited only the `VERIFIER_MODEL` line of the user's `.env` (no key was read or printed) —
    the user asked for the model and an unsaved or stale value had already cost one failed probe — the file
    is the user's; they can revert that line.
52. Ruling: `ENV_FILE` selects the env file (default `.env`) and every test now points it at a missing
    file — the suite read the developer's real `.env`, so two demo tests failed the moment live mode was
    configured, and a test must never see live keys — none.
53. Ruling: Gemma 4 31B stays in the price sheet and in the documents as a documented alternative — its
    hosted endpoint may recover and the user may want it back — a stale entry, harmless.

## Live runs against the free endpoint (2026-10-22, latest)

The user ran the app twice (Tavily credits were used, both runs ended "The checking service failed") and
asked why. The app's own telemetry log and three replays of the demo corpus with the real models (no search,
about 20 free-tier model requests) gave the answer; findings are in ARCH §8.6.

54. Ruling: a provider timeout that occurs after the run's deadline has passed is reported as the deadline
    (`TIMEOUT`), not as a provider failure — the first failed app run was mislabeled "checking service
    failed" when the run had simply run out of time — none.
55. Ruling: a failed result carries `detail` (an exception class name, never a message or body) and the
    page shows "Detail: <code> (<class>)" — the user could not tell a stalled verifier from a refused
    request, and the class name is safe to show — none.
56. Ruling: `RUN_TIME_FACTOR` (0.5 to 5, default 1.0) scales only each mode's wall clock, and
    `.env.example` sets 2.0 for the NVIDIA development profile — a Quick run needs about 110 s on this
    endpoint and a single stall pushes it over 120 s; cost, claim, source and token limits are untouched so
    the PRD cost model is unchanged — this relaxes PRD NFR-03 (Quick 120 s, Deep 360 s) for that
    operator's runs only, shown on the page; set 1.0 for the PRD limits.
57. Ruling: `VERIFIER_TIMEOUT_FACTOR` is 1.25 in `.env.example` (it was 2.0 an hour earlier) — measured
    batches take 8 to 21 s when they work and a stalled call never recovers, so giving up at 37 s and
    retrying beats waiting 60 s — a legitimately slow batch above 37 s is retried.
58. Ruling: no `VERIFIER_PARALLEL` setting and no retry-count change were added — one-at-a-time batches
    stalled as often as parallel ones, so neither helps, and more attempts per call would go beyond PRD
    NFR-16 and the cost model; the user decides whether to relax that — until then a stalling provider
    ends a run `VERIFIER_FAILED` or `TIMEOUT`, with nothing unverified published.

## Local Ollama verifier (2026-10-22, evening)

The user asked for Nemotron 3 Ultra as planner and writer, a local Ollama `qwen3-vl:8b-instruct` as the
independent verifier, Tavily for search, PRD verification, citation, cost and timeout limits unchanged, no
fallback to NVIDIA, no downloads, no live Tavily test. Measurements used local Ollama only (about 100 requests,
no cost) plus one replay with the NVIDIA writer (two requests) on the demo corpus.

59. Ruling: a separate `ollama` verifier provider with a placeholder key `ollama` and no
    `VERIFIER_API_KEY` — "keep NVIDIA credentials separate" is then true by construction and a test asserts
    the client key — a user who wants a keyed remote Ollama uses provider `openai` with a base URL.
60. Ruling: Ollama's JSON mode is `json_schema` (the Pydantic schema, strict) — measured: `json_object` and a
    plain request returned valid JSON of the wrong shape, `json_schema` returned schema-valid output — the
    reply is still validated by Pydantic, so a server that ignores the schema fails closed.
61. Ruling: a truncation guard raises `ContextTruncated` (a `ProviderBadRequest`, never retried) when the
    prompt tokens Ollama reports are under 60 percent of our estimate for prompts of 500 tokens or more —
    measured: Ollama processed 2,050 of about 6,500 tokens with no error and ignores a per-request context
    setting on `/v1` — a tokenizer that differs from our estimate by more than 40 percent would raise a
    false alarm and fail a run closed.
62. Ruling: `VERIFIER_PARALLEL` (1 to 8, default 4 = the PRD value; 1 in `.env.example`) — a local Ollama
    serves one request at a time, so queued batches only time out — cost, claim and token limits are not
    touched.
63. Ruling: `RUN_TIME_FACTOR` is 1.0 again in `.env.example` and in the user's `.env`, and
    `VERIFIER_TIMEOUT_FACTOR` is 3.0 — the user required the PRD timeouts unchanged; per-call timeouts are
    capped by the time left in the run, so 3.0 cannot extend a run — this supersedes the 2.0 and 1.25 of
    rulings 56 and 57 for the Ollama setup.
64. Ruling: I changed these lines of the user's `.env` (keys untouched): VERIFIER_PROVIDER nvidia to ollama,
    VERIFIER_MODEL openai/gpt-oss-20b to qwen3-vl:8b-instruct, VERIFIER_BASE_URL to
    http://localhost:11434/v1, VERIFIER_JSON_MODE none to json_schema, VERIFIER_TIMEOUT_FACTOR 1.25 to 3.0,
    RUN_TIME_FACTOR 2.0 to 1.0, and added VERIFIER_PARALLEL=1 — the user asked for this configuration — the
    setup now times out on this machine (B-14); to go back, restore those previous values.
65. Ruling: the evaluation set is 45 hand-written synthetic pairs and is labeled synthetic in every row and
    report — the sealed set needs human labels and cannot be invented — it can show a model failing (the 4B
    model obeyed injections) but cannot certify the PRD §2.6 gate.
66. Ruling: memory is reported as system RAM in use, GPU memory in use and `ollama ps`, not as the Ollama
    process working set — the first run reported 112 MB for a 6.3 GB model because memory-mapped weights are
    not in the working set; that report carries a note saying so — none.
67. Ruling: `qwen3-vl:4b-instruct` was evaluated only as a comparison and is not a default; no model was
    downloaded; the text models named in ARCH §8.7 are untested candidates — a candidate may behave worse
    than the 8B vision model, so none is recommended as better without running the same command.
68. Ruling: the local models are listed in the price sheet at the verifier budgeting rates — they cost
    nothing per call but the budget caps and the call-graph check must still bind — displayed costs are
    notional.
69. Ruling: the time limits were not relaxed to make the local verifier fit — the user asked for PRD limits
    unchanged — every Quick and Deep run on this laptop ends `TIMEOUT` until the hardware, the model or the
    limit changes (the owner's decision, B-14).
70. Ruling: `build_writer` and `build_verifier` are public in `adapters/live.py` — the evaluation harness
    builds the verifier exactly as the service does — none.

## Review of the Ollama change set (2026-10-22, night)

A fresh reviewer (opus, read-only) found no Critical defect and no credential or fallback leak, and several
Important gaps. One fix pass followed, each fix test-first; suite 533 of 533, ruff, mypy and import-linter clean.

- Final: fixed a truncation guard that was a single ratio near its own threshold — `test_a_prompt_that_cannot_fit_the_context_is_refused_before_any_request`, `test_prompt_plus_output_reaching_the_window_means_context_shift_and_fails_closed`, `test_missing_usage_cannot_be_checked_so_it_fails_closed_for_a_large_prompt`, `test_context_length_is_a_validated_setting_that_reaches_the_adapter` RED→GREEN
- Final: fixed no test driving a truncation through the call guard, and a misleading page message — `test_the_failure_is_a_single_attempt_that_ends_the_run_as_verifier_failed`, `test_the_page_tells_the_operator_how_to_fix_a_truncated_context` RED→GREEN (two subclass-only tests that could not fail were removed)
- Final: fixed an `ollama` provider that could point at a remote host while the About page said "not sent to a third party", and wording that ignored what NVIDIA receives — `test_the_ollama_provider_must_point_at_this_computer`, `test_the_about_page_names_what_nvidia_receives_and_what_stays_local` RED→GREEN
- Final: fixed an indicative gate that compared raw counts (2 false accepts "passed" on 26 pairs), a report that hid which negatives the numeric guard already stops, a mean that included a short last batch, and a stress set that repeated one passage — `test_the_indicative_gate_compares_rates_not_raw_counts`, `test_the_report_says_which_negatives_the_deterministic_guard_already_blocks`, `test_full_size_batches_are_timed_separately_from_the_short_last_batch`, `test_stress_mode_cites_three_distinct_passages_per_claim` RED→GREEN
- Final: fixed supported pairs that were all near copies and an injection pair that tested nothing — `test_supported_claims_include_real_paraphrases_not_only_near_copies`, `test_an_injection_row_pressures_the_verifier_to_reject_a_supported_claim` RED→GREEN (8 paraphrase pairs added, I02 replaced)
- Final: fixed overstated and stale documents (README, ARCH §8.6, memory, tracker, price-sheet note, "Aligned with") and the "passes" wording (documents now say the 8B model is not shown to meet the gate)

71. Ruling: the re-run of both models on the expanded 53-pair set from an idle state was stopped by Claude
    Code when the system ran critically low on memory (15.2 of 15.7 GB in use with the 8B model loaded) and was
    not restarted — the user's machine, not the run, was at fault and restarting risks freezing it — the
    reports on disk are the original runs on the 45-pair version 1, kept in `verifier_scripted_v1.jsonl` and
    rescored (no model called) with `--rescore --fixtures`; the 8 paraphrase pairs, the replaced injection
    pair, the distinct-passage stress mode and `--cold-start` are implemented and tested but not run on a model.
72. Ruling: `VERIFIER_CONTEXT_TOKENS` (default 4096) must equal the server's `OLLAMA_CONTEXT_LENGTH`, and
    `.env.example` and the user's `.env` ship 4096 because `ollama ps` reports 4096 on this machine — a value
    larger than the truth would make the guard trust a window that is not there — until both are raised to 8192
    every real Quick run is refused with `ContextTruncated` and a message saying how to fix it.
73. Ruling: the `ollama` provider must point at this computer; a remote Ollama is configured as provider
    `openai` with its own key — evidence must not leave the machine while the page says it stays — a LAN Ollama
    needs that explicit choice and its https URL.
74. Ruling: the indicative gate compares rates and reports false accepts both over all unsupported pairs and
    over the pairs that reach the verifier — the PRD gate is rate-like and the numeric guard stops some pairs
    first in production — the "passes the screening thresholds" statements were withdrawn.
75. Ruling: an 8B false accept of a causal overreach (O02) and the speed shortfall are reported as findings,
    not tuned away — the user asked for measured quality and a recommendation — none.

Deferred minors (Ollama change set):

- Final: minor (deferred): `VERIFIER_PARALLEL` defaults to 4 and `VERIFIER_TIMEOUT_FACTOR` to 1.0 whatever the provider, so an Ollama setup without `.env.example` queues batches and times out; `VERIFIER_PARALLEL=2.9` becomes 2
- Final: minor (deferred): the truncation estimate always uses 3.5 characters per token and ignores `EST_CHARS_PER_TOKEN`
- Final: minor (deferred): `json_schema` is accepted for any provider, and OpenAI's strict mode rejects optional fields, so enabling it for an OpenAI model would likely fail every call (closed); the schema is also repeated in the system prompt
- Final: minor (deferred): `model_family` does not see through uploader-prefixed Hugging Face GGUF names (`hf.co/bartowski/nvidia_Nemotron-H-8B-GGUF` gives "nvidia") or distills (`deepseek-r1:8b`, `qwq:32b`)
- Final: minor (deferred): `UPSTREAM_WORST_S` uses a 53 s writer while the replay saw 68 s, which only strengthens the infeasibility conclusion

## Review of the NVIDIA change set (2026-10-22)

A second fresh subagent (opus, read-only) reviewed this change set. One fix pass followed; each fix was
written test-first and watched fail (`tests/test_nvidia_review_fixes.py`), suite 464 of 464, ruff, mypy
and import-linter clean.

- Final: fixed same-family pairs passing the independence check (vendor prefix used as family) — `test_same_family_pairs_are_refused_whatever_the_hosting_prefix` RED→GREEN
- Final: fixed a key being sendable to the other provider's host after copying `.env.example` — `test_a_key_cannot_be_sent_to_the_other_providers_host`, `test_env_example_keeps_the_alternatives_complete_and_the_load_modest` RED→GREEN
- Final: fixed a free-prototype sheet with no review date or zero rates being accepted forever, a malformed sheet crashing the app, and expiry checked only at startup — `test_free_sheet_without_a_review_date_or_with_zero_rates_is_refused`, `test_a_malformed_or_missing_sheet_is_a_named_problem_not_a_crash`, `test_a_running_service_stops_admitting_runs_once_the_sheet_expires` RED→GREEN
- Final: fixed the UI hiding why live mode refused to start — `test_startup_problems_are_shown_by_name_and_secrets_are_not` RED→GREEN
- Final: fixed the shared limiter (lock held while sleeping, waits ignoring the deadline, one breaker for both roles) and added a concurrency-aware default — `test_waiting_for_the_limiter_never_holds_its_lock`, `test_a_wait_longer_than_the_deadline_is_refused_without_spending_a_slot_or_budget`, `test_nvidia_roles_share_one_rate_limit_but_keep_separate_breakers` RED→GREEN
- Final: a hypothesis health check in `test_capacity.py` failed intermittently when the suite ran in one process (timing only); it now suppresses `too_slow` and the deadline, assertions unchanged

Final: Ruling: whether hosted NVIDIA rejects `temperature=0.0`, accepts `chat_template_kwargs` on non-Nemotron models, or wants `max_completion_tokens` for Gemma is unknown — all are one-line settings or code defaults and `eval/provider_probe.py` exists to find out — a wrong guess is a 400 on the first supervised call.
Final: Ruling: NVIDIA's real trial rate limit is unknown — `NVIDIA_MAX_RPM` and `MAX_CONCURRENT_RUNS` are settings, 429s are retried honoring Retry-After — a lower real limit shows up as throttling or timeouts, not wrong answers.
Final: Ruling: the reviewer asked whether reasoning arrives in `reasoning_content` or inline — either works: a separate field leaves `content` clean and inline blocks are stripped — none.
Final: Ruling: `retry_on_schema` for the verifier predates this change set (it was in the first build); ARCH §8.1 and PRD §13.2 still say a malformed verifier answer is not retried — retries are bounded by the call-graph demand and a verifier that never parses fails the run closed; the documents should be reconciled at the next approved edit — spend on malformed answers is higher than the documents imply.

Deferred minors (NVIDIA change set):

- Final: minor (deferred): nested `<think>` tags expose JSON written inside the outer block; a literal `<think>` in a legitimate answer fails closed and is charged
- Final: minor (deferred): `finish_reason == "length"` is retried at the same output cap, so truncated answers are likely to fail three times, each charged at its reservation
- Final: minor (deferred): provider disclosure follows the provider setting, not the URL called (`WRITER_PROVIDER=nvidia` with another host cannot pass the host check, but `openai` with any URL is named only as "an OpenAI-compatible endpoint"); the free-tier note mentions costs that the FAQ says are not shown; telemetry `cost_usd` carries no notional marker
- Final: minor (deferred): `.env` parsing keeps inline comments (`WRITER_THINKING=on # x` becomes off), `NVIDIA_MAX_RPM=abc` silently falls back to 40, and some settings are ignored without a warning (`WRITER_THINKING` with a non-NVIDIA writer, `VERIFIER_BASE_URL` with an Anthropic verifier); `chat_template_kwargs` is sent to any NVIDIA writer model
- Final: minor (deferred, now obsolete): an Ollama verifier needing a non-empty `VERIFIER_API_KEY` (the `ollama` provider uses a placeholder key and needs none)
- Final: minor (deferred): pydantic validates in lax mode, so a numeric string passes an int field; "strict" means extra keys are forbidden, not strict types
- Final: minor (deferred): `eval/provider_probe.py` probes the writer with the verifier schema and prompt at 400 tokens, cannot test `json_object`, and reports any provider error as "does not parse"
- Final: minor (deferred): ARCH header says "Aligned with prd.md v1.6"; ARCH row for the verifier lists only Claude candidates; with injected providers `startup_problems` checks the settings' model names rather than the injected ones (tests only)

## Final review of the first build

Reviewer: fresh subagent on the most capable available model (opus), read-only, against the whole
tree. One fix pass followed, each fix written test-first (RED seen, then GREEN); suite 357 of 357,
ruff, mypy and import-linter clean.

- Final: fixed billed failed calls not counted (#1) — `test_schema_violations_are_charged_because_the_provider_billed_them`, `test_content_refusals_are_charged_but_plain_server_errors_are_not` RED→GREEN, suite 357/357
- Final: fixed quote match starting inside a number or word (#2) — `test_a_quote_cannot_start_in_the_middle_of_a_number_or_word` RED→GREEN
- Final: fixed numeric-guard evasions (#3) — `test_numeric_guard_rejects_these_substitutions` (11 cases) and `test_numeric_guard_still_accepts_faithful_claims` RED→GREEN
- Final: fixed weak sentence rules (#4) — `test_interpretation_rules_catch_leading_entities_number_words_and_urls`, `test_transition_rules_catch_leading_entities_and_spelled_numbers` RED→GREEN
- Final: fixed second search returning the first report (#5) — `test_second_research_click_starts_a_new_run` RED→GREEN
- Final: fixed unenforced prompt caps (#6) — `test_overlong_claim_text_is_rejected_by_the_ledger`, `test_writer_passages_truncate_long_titles`, `test_scan_never_sends_more_than_its_input_cap_and_flags_the_overflow`, `test_repair_prompt_respects_the_repair_input_cap_and_per_claim_quote_limit` RED→GREEN
- Final: fixed `EST_CHARS_PER_TOKEN` partly ignored and unvalidated (#7) — `test_runtime_batching_uses_the_configured_chars_per_token`, `test_invalid_chars_per_token_is_a_named_startup_problem`, `test_service_passes_the_setting_into_every_context` RED→GREEN
- Final: fixed missing telemetry and startup refusal (#8) — `test_call_guard_reports_provider_calls_and_breaker_trips`, `test_service_emits_startup_checks_and_refuses_when_no_mode_is_servable`, `test_run_manager_emits_stage_rejection_and_cost_events` RED→GREEN
- Final: fixed Partial export not marked (#9) — `test_partial_report_title_starts_with_partial` RED→GREEN
- Final: fixed raw validation codes shown to users (#10) — `test_validation_warning_codes_become_plain_sentences` RED→GREEN
- Final: fixed a reservation left open if cost extraction raises (#13) — `test_a_reservation_is_released_if_cost_extraction_raises` RED→GREEN (a Minor fixed because it shared the guard rewrite)

Deferred minors:

- Final: minor (deferred): `escape_md` leaves bare `https://` and `www.` text and bidi control characters unescaped (#11)
- Final: minor (deferred): an empty `choices` list in the OpenAI reply escapes the adapters as IndexError, and SDK errors ride along as `__cause__` (#12)
- Final: minor (deferred): a `BaseException` in a run worker leaves the run without a result and its slot held; `pool.submit` after shutdown orphans a run; `_tombstones` grows without bound (#14)
- Final: minor (deferred): NFKC turns "10²" into "102" so a quote can match a superscript (#15)
- Final: minor (deferred): `.importlinter` does not cover `app.py` or `service.py` (#16)
- Final: minor (deferred): `unused_sources` docstring says completed runs but also runs for Partial; the "found but not inspected" list is only in the export (#17)
- Final: minor (deferred): `provider.call` and `provider.breaker` events carry no run ID
- Final: minor (deferred): Roman numerals and ordinals beyond "third" are not numeric-guard tokens

## Not built (needs people, money or a decision)

Decision log and owners (M0-01/02/08/11), model choice and real prices (M0-06/07), live wire-format
verification (M0-09), CI configuration (M0-12), dev set, fixtures and sealed holdout (M1-18/19/20,
M2-18/19, M3-01/02), benchmark runs and human grounding labels (M3-03/04/06/07/08/09), hosting
(M3-10), browser and screen-reader audits (M2-25, M3-11), load test (M3-12). None of these can be done
by code alone and none was simulated.
