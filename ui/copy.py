"""Every user-facing string (design.md DR-3). PRD §7.3 messages are used as written."""

from __future__ import annotations

COPY: dict[str, str] = {
    "app.title": "AI Research Agent",
    "app.tagline": "Research a topic across public websites. Every claim links to the text that supports it.",
    "state.idle": "Enter an English topic to research public websites.",
    "next.idle": "Enter a topic, or try an example.",
    "state.invalid_empty": "Please enter a topic to research.",
    "state.invalid_long": "Topics can be up to 500 characters long. Please shorten it.",
    "state.invalid_language": "This pilot accepts English-language topics only.",
    "next.invalid": "Edit the topic and press Research again.",
    "state.running": (
        "Verifying which claims are supported by retrieved passages… "
        "Please don't reload this page while research is running."
    ),
    "state.busy": "The service is at capacity. Please try again in a minute.",
    "state.session_active": "A search is already running in this session.",
    "state.expired": (
        "Your earlier result is no longer available. Results are kept for 30 minutes. Please run it again."
    ),
    "state.paused": "Research is paused right now. Please try again later.",
    "state.mode_unavailable": (
        "This depth is unavailable right now. Please choose the other depth or try again later."
    ),
    "state.config_invalid": "The service is not configured correctly. Please contact the maintainers.",
    "state.reload_notice": (
        "Reloading the page, or a server restart, ends a running search. If that happens, start it again."
    ),
    "state.completed": "Minimum evidence thresholds were met. Coverage is not exhaustive.",
    "state.partial": "Some thresholds were not met. Read the limits below before relying on this report.",
    "state.failed": (
        "No report was produced because the available evidence could not support two factual findings."
    ),
    "next.failed": "Try a narrower or clearer topic, or run it again later.",
    "state.provider_failure": "Search service unavailable. No unverified report was published.",
    "state.semantic_mismatch": "Some claims could not be matched to their cited passages; they were omitted.",
    "state.budget_stop": "Stopped at the configured limit. Only passage-checked findings are shown.",
    "state.feedback": "Thanks — your feedback was recorded without storing the report.",
    "state.cleared": "Session cleared in this app; external provider processing is unchanged.",
    "next.cleared": "Start a new search whenever you are ready.",
    "state.abandoned": "This search stopped because the page was closed or reloaded. Start it again.",
    "state.demo_offtopic": (
        "Demo mode only has data about the Harborview bike-share pilot, so other topics find no sources. "
        "Use the demo topic, or configure live mode for real research."
    ),
    "state.demo": "Demo mode: scripted providers and synthetic data. This is not real research.",
    "label.topic": "Topic (English, 1–500 characters)",
    "label.depth": "Depth",
    "label.research": "Research",
    "label.clear": "Clear session",
    "label.try_again": "Try again",
    "label.download": "Download Markdown (.md)",
    "label.useful": "Useful",
    "label.not_useful": "Not useful",
    "label.feedback_prompt": "Was this useful?",
    "label.tab_research": "Research",
    "label.tab_about": "About / Privacy",
    "label.tab_faq": "FAQ",
    "label.not_covered": "Not covered",
    "label.date_unknown": "Date unknown",
    "label.no_disagreement": "No material disagreement identified in selected evidence.",
    "label.link_new_tab": "(opens in a new tab)",
    "label.standing": (
        "Third-party search and AI providers process your topic. "
        "Reloading the page ends a running search. Results are kept for 30 minutes."
    ),
    "label.clear_disabled": "Clear session is unavailable while a search is running.",
    "label.research_disabled": "A search is running, or this depth is unavailable.",
}

EXAMPLES: tuple[str, ...] = ("Urban heat islands", "EV charging infrastructure", "AI in education")

REASONS: dict[str, str] = {
    "LOW_EVIDENCE_GROUPS": "Fewer distinct sources than the target.",
    "LOW_DOMAINS": "Fewer independent websites than the target.",
    "INSUFFICIENT_CLAIMS": "Fewer supported claims than the target.",
    "INCOMPLETE_FACETS": "Some planned questions were not covered.",
    "SNIPPET_HEAVY": "Most claims rely on search snippets, not full page text.",
    "TIMEOUT": "The search stopped at the time limit.",
    "BUDGET_STOP": "The search stopped at the cost limit.",
}

_FAILURES: dict[str, str] = {
    "SEARCH_FAILED": COPY["state.provider_failure"],
    "MODEL_FAILED": "The writing service failed. No unverified report was published. Try again in a moment.",
    "VERIFIER_FAILED": "The checking service failed. No unverified report was published. Try again in a moment.",
    "INTEGRITY_FAILED": "Something went wrong while checking the evidence. No unverified report was published.",
    "NO_EVIDENCE": COPY["state.failed"],
    "INSUFFICIENT_CLAIMS": COPY["state.failed"],
    "LOW_EVIDENCE_GROUPS": COPY["state.failed"],
    "PLAN_TOO_NARROW": "The topic could not be split into enough distinct questions. Try a broader or clearer topic.",
    "BUDGET_STOP": "The search stopped at the cost limit before enough claims were checked. No report was produced.",
    "TIMEOUT": "The search stopped at the time limit before enough claims were checked. No report was produced.",
    "ABANDONED": COPY["state.abandoned"],
    "INPUT_INVALID": COPY["state.invalid_empty"],
    "LANGUAGE_UNSUPPORTED": COPY["state.invalid_language"],
}

_EVIDENCE_LABELS = {
    "snippet": "Search snippet",
    "extracted": "Extracted page text",
    "metadata-only": "Not inspected (title only)",
}

PRIVACY_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "What this tool does",
        (
            "It searches public websites for your topic, drafts short statements, and keeps only the "
            "statements that a separate checking step finds supported by a quoted passage.",
            "Verified means supported by the supplied passage. It does not mean independently proven true.",
        ),
    ),
    (
        "Who processes your topic",
        (
            "Your topic is sent to a third-party search provider and to AI model providers (a writing "
            "model and a separate checking model). Selected passages from public web pages are also sent "
            "to the models. Their own retention and privacy policies apply to that processing.",
            "Do not enter confidential, personal or sensitive information.",
        ),
    ),
    (
        "What this app keeps",
        (
            "The app keeps no database and no user accounts. Your topic and report live in memory for "
            "your session and are removed 30 minutes after a run finishes, or when you clear the session.",
            "Operational logs contain run IDs, stage names, counts, durations and cost estimates. They never "
            "contain your topic, source text, claims or credentials, and are deleted after 7 days.",
            "Feedback records only a useful or not useful vote, without the report.",
        ),
    ),
    (
        "Languages and report status",
        (
            "This pilot accepts English-language topics only.",
            "A report is Completed when minimum evidence thresholds are met, Partial when some are not "
            "(the reasons are listed), and Failed when fewer than two statements could be supported.",
        ),
    ),
)

FAQ_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "What is the difference between Quick and Deep?",
        (
            "Quick reads up to 8 sources and stops after 2 minutes. Deep reads up to 20 sources, plans more "
            "questions and stops after 6 minutes. Deep costs more to run.",
        ),
    ),
    (
        "What is a search snippet, and what is extracted page text?",
        (
            "A snippet is the short excerpt a search engine shows. Extracted text is the body of the page. "
            "Claims based only on snippets are weaker, and a report that leans on them is marked Partial.",
        ),
    ),
    (
        "Why is the report a list of short statements?",
        (
            "Each statement has to be checkable against a quoted passage. Free-form prose cannot be checked "
            "that way, so the report keeps to checked statements with citations.",
        ),
    ),
    (
        "What happens when sources disagree?",
        (
            "Both positions are shown with their citations. If no disagreement was found in the selected "
            "evidence, the report says so. It never claims that all sources agree.",
        ),
    ),
    (
        "Why can a report be Partial or Failed?",
        (
            "The tool prefers saying less to saying something unsupported. Too few sources, too few "
            "supported statements, a time or cost limit, or a weak evidence base all lower the status.",
        ),
    ),
    (
        "What does Completed mean, and what does it not mean?",
        (
            "It means minimum thresholds for sources, domains, statements and questions were met and every "
            "shown statement matched its passage. It does not mean the topic was covered exhaustively or "
            "that the sources are right.",
        ),
    ),
    (
        "Why is there no Cancel button?",
        (
            "A call already sent to a provider cannot be reliably aborted. If you close or reload the page, "
            "the run stops sending new calls after about 90 seconds.",
        ),
    ),
    (
        "Why does reloading the page end my search?",
        (
            "Your session identifies your run. A reload or a server restart starts a new session, so the "
            "earlier run can no longer be reached. Results are kept for 30 minutes within the same session.",
        ),
    ),
    (
        "What does a run cost?",
        (
            "Each depth has a cost ceiling that the service enforces. Estimated costs are not shown per run "
            "in this pilot.",
        ),
    ),
)


def text(key: str) -> str:
    return COPY[key]


def reason(code: str) -> str:
    return REASONS.get(code, "A threshold was not met.")


def evidence_label(mode: str) -> str:
    return _EVIDENCE_LABELS.get(mode, "Unknown evidence type")


def failure_message(code: str | None, detail: str | None = None) -> str:
    if code == "VERIFIER_FAILED" and detail == "ContextTruncated":
        return (
            "The local checking model's context window is too small for this evidence, so nothing was "
            "verified. Raise OLLAMA_CONTEXT_LENGTH on the Ollama server and VERIFIER_CONTEXT_TOKENS in "
            ".env to the same value (for example 8192), then run it again."
        )
    return _FAILURES.get(code or "", "No report was produced. Please try again later.")
