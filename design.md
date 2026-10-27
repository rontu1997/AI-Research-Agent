# Design System and UX Specification: AI Research Agent

| Field | Value |
|---|---|
| Document | design.md |
| Version | 1.0 — proposed, for design review |
| Aligned with | prd.md v1.7, architecture.md v1.4 |
| Status | Proposed. Nothing here is approved or implemented |
| Updated | 2026-10-21 |
| Owner | Product owner and lead developer (names TBD at PRD milestone M0) |

**Scope.** This file specifies the user-facing experience of the access-restricted pilot: layout, navigation, components, states, visual tokens and accessibility behavior. It does not restate product requirements, copy text or architecture.

**Precedence.** The PRD owns requirements and the exact user-facing copy (PRD §7.3). The architecture owns structure and contracts. When this file disagrees with either, the PRD wins, then the architecture, and this file is corrected. Section references written "PRD §n" or "ARCH §n" point to those documents, and the prefix covers the comma-separated sections that follow it; a bare "§n" elsewhere points here. In the traceability table (§14), the column heading names the document.

**Platform constraint.** The UI is a Streamlit app (ARCH §4.2). Streamlit controls much of the rendered markup, so every claim in this file about assistive-technology behavior, focus handling, theming and responsive collapse is a **test target, not an assumption**. Items to confirm are collected in §15.

---

## 1. Design Principles

| ID | Principle | What it means on screen |
|---|---|---|
| DP-1 | Evidence is one step away | Every supported claim has a labeled toggle that shows its quote, source link and evidence mode. Nothing needs a second page |
| DP-2 | Honest status, never decoration | Completed, Partial and Failed look and read differently. A Partial result is never styled like a success, and "Completed" is never described as comprehensive |
| DP-3 | Meaning never rests on color alone | Every status and evidence mode has a text label and a glyph in addition to color |
| DP-4 | Calm and stable | No auto-dismissing messages, no custom animation, no layout jumps when a run finishes. Content appears in a fixed order |
| DP-5 | Say what happened and what to do next | Every non-success state has a plain message and one next step. No provider text, stack traces or jargon |
| DP-6 | Plain language | Design-owned text uses plain words ("claim", "search snippet", "extracted page text") and avoids internal terms such as "ledger" and "verifier". PRD copy is used exactly as written, including its words "claims", "snippets" and "passages" |
| DP-7 | Keyboard and touch first | All controls are reachable in a logical order, with a visible focus indicator, and touch targets that aim for 44 CSS px and never fall below 24 px |
| DP-8 | One source for look and words | Visual values come from tokens (§12). Every user-facing string comes from `ui/copy.py` |
| DP-9 | Honest density | Terse, list-like reports are a known tradeoff (PRD §6.3). The design makes them scannable instead of pretending they are prose |

---

## 2. Information Architecture and Navigation

### 2.1 Structure

One page with three top-level tabs. There are no routes, so there are no deep links to a result (a reload ends a run, PRD §8.4).

```
AI Research Agent  (header: title and one-line purpose, above the tabs)
├── Research (default tab)
│   ├── Input: topic, depth, [Research], [Clear session]
│   ├── Run area (only when a run is active or finished)
│   │   ├── Progress (while running)
│   │   ├── Status banner and scorecard (when finished)
│   │   ├── Report
│   │   │   ├── Executive summary
│   │   │   ├── Scope and questions researched (facet coverage)
│   │   │   ├── Key findings, each claim with its Evidence toggle
│   │   │   ├── Data and examples (only when supported)
│   │   │   ├── Conflicting or competing evidence
│   │   │   ├── Limitations
│   │   │   ├── Conclusion
│   │   │   └── References
│   │   └── Actions: [Download Markdown], feedback
│   └── Footer: standing notice (reload and result lifetime)
├── About / Privacy
└── FAQ
```

### 2.2 Navigation rules

1. Tabs are always visible, including during a run and in every error state (PRD §7.5: always reachable).
2. Switching tabs never cancels a run. Tab content is client-side, and the run lives in the server (ARCH §4.3).
3. The same tab order is used everywhere. The contact link for reporting questionable citations sits in the same place on About / Privacy and FAQ (WCAG 3.2.6 Consistent Help).
4. There is no page-level back button, breadcrumbs or search. The product has one task.
5. Within the report, order follows PRD §6.3 and never changes between modes.
6. A new run replaces the displayed result. Controls re-enable when a run ends, and the previous result stays visible until the next submission or Clear session.

### 2.3 Content hierarchy of a finished report

1. **Result header:** status banner, then the scorecard (what was found and how well it is supported).
2. **Report body:** summary first, then findings.
3. **References:** numbered, with evidence mode.
4. **Actions:** download and feedback, placed after the report heading and again after the references so that neither floats over content (PRD §7.2).

---

## 3. User Journeys and Screen Flows

### 3.1 Journeys

| ID | Journey | Steps | States passed through | Done when |
|---|---|---|---|---|
| J1 | Run a Quick research and read it | Enter topic; choose Quick; press Research; watch progress; read report; open a citation | Idle, Running, Completed | The report is visible with status, scorecard and references |
| J2 | Receive a Partial report | As J1; the result is Partial | Idle, Running, Partial | The banner names every unmet threshold in plain words, and the report is still usable and exportable |
| J3 | Run ends with no safe report | As J1; fewer than two supported claims | Idle, Running, Failed | The user sees why in plain words, the form keeps the topic, and one retry action is offered |
| J4 | Fix an invalid topic | Submit empty, over-long or non-English text | Idle, Invalid input | Focus returns to the error, the topic is kept, no provider call is made |
| J5 | Find the service busy | Submit while 5 runs are active | Idle, Busy | A clear "try again" message and an unchanged form |
| J6 | Inspect evidence | Toggle "Show evidence" on a claim; read the quote; follow the source link | Completed or Partial | The quote, source title, URL, passage ID and evidence mode are visible, and the link opens the source |
| J7 | Export | Press Download Markdown | Completed or Partial | A `.md` file is saved, Partial files are marked PARTIAL |
| J8 | Give feedback | Press Useful or Not useful | Completed, Partial, Failed | Inline confirmation appears and the buttons are replaced; a second vote is not possible for the same run |
| J9 | Reload or restart mid-run | Reload the page, or the server restarts | Running, then Idle | The form is idle with the standing notice. The user starts again |
| J10 | Return after the result expired | Open the page again within the session after 30 minutes, or after Clear session | Idle with expiry notice | The "result expired" message and the form |
| J11 | Clear the session | Press Clear session when no run is active | Completed, then Idle | The report, evidence and download are gone and the confirmation text is shown |
| J12 | Read privacy and FAQ | Open the tabs at any time | Any | Content is readable without starting a run |

### 3.2 Main flow

```
                 ┌──────────┐ invalid ┌────────────────────┐
   open app ───► │   Idle   │────────►│    Invalid input   │──┐ (topic kept, focus on error)
                 └────┬─────┘         └────────────────────┘  │
                      │ Research                               │
              ┌───────┴────────┬─────────────┬────────────┐    │
              ▼                ▼             ▼            ▼    │
         ┌────────┐       ┌──────────┐  ┌──────────┐  ┌────────────┐
         │  Busy  │       │ Service  │  │   Mode   │  │  Running   │
         └───┬────┘       │  paused  │  │unavailable│ └─────┬──────┘
             │ retry      └────┬─────┘  └────┬─────┘        │
             └─────────────────┴──────────────┴──► Idle     ├─────────► Failed ──► Idle (retry)
                                                             ├─────────► Partial ─┐
                                                             └─────────► Completed┤
                                                                                  ▼
                                        Evidence · Download · Feedback · Clear session ──► Idle
   Reload or restart during Running ──► Idle with the standing notice
   Held run ID no longer resolves   ──► Idle with "result expired"
```

Failure causes inside the run (provider failure, semantic mismatch, budget or timeout) appear as a Failed or Partial result with the message for that cause, not as separate screens.

### 3.3 Mapping to PRD states and architecture codes

| UI state | PRD §7.3 state | Triggered by (ARCH §6.4 and §5.3) |
|---|---|---|
| `idle` | Idle | No run |
| `invalid_input` | Invalid / unsupported language | `INPUT_INVALID`, `LANGUAGE_UNSUPPORTED` |
| `busy` | Busy | `BUSY` |
| `service_paused` | Service paused | `SERVICE_PAUSED` |
| `mode_unavailable` | Mode unavailable | `CONFIG_INVALID` found at startup for one mode, so the mode is disabled |
| `running` | Running | Run state not terminal. `SESSION_ACTIVE` also lands here, because the button was already disabled |
| (no state) | None | `ABANDONED` (the user has gone) and `NOT_FOUND` for an ID the UI never held |
| `completed` | Completed | Status `completed` |
| `partial` | Partial | Status `partial` |
| `failed` | Failed / no evidence | `PLAN_TOO_NARROW`, `NO_EVIDENCE`, fewer than two supported claims |
| `provider_failure` | Provider failure | `SEARCH_FAILED`, `MODEL_FAILED`, or `CONFIG_INVALID` raised during a run |
| `semantic_mismatch` | Semantic mismatch | `VERIFIER_FAILED`, `INTEGRITY_FAILED`, or removed claims in a Partial result |
| `budget_or_timeout` | Budget/timeout | `BUDGET_STOP`, `TIMEOUT` |
| `reloaded` | Page reloaded or server restarted mid-run | New session, no run ID |
| `expired` | Result expired | `NOT_FOUND` for a held run ID |
| `feedback_recorded` | Feedback recorded | Vote accepted |
| `cleared` | Clear session | `clear_session` done |

---

## 4. Page Layouts and Wireframe Specifications

Wireframes are informational, not pixel-exact, and their text is illustrative: final strings come from `ui/copy.py`, and the PRD §7.3 messages are used as written. Widths: the content column is centered and about 46 rem wide on wide screens (Streamlit's centered layout; confirm at M0), and fills the viewport minus a 16 px side gutter on narrow screens.

### 4.1 Idle (desktop)

```
┌──────────────────────────────────────────────────────────────┐
│ AI Research Agent                                            │
│ Research a topic across public websites. Every claim         │
│ links to the text that supports it.                          │
├──────────────────────────────────────────────────────────────┤
│ [ Research ]  [ About / Privacy ]  [ FAQ ]                   │  tabs
├──────────────────────────────────────────────────────────────┤
│ Topic (English, 1–500 characters)                            │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Impact of AI on the Indian job market                    │ │
│ │                                                          │ │
│ └──────────────────────────────────────────────────────────┘ │
│ Try:  [Heat islands] [EV charging] [AI in education]         │
│                                                              │
│ Depth:  (●) Quick   ( ) Deep                                 │
│ Quick: up to 8 sources, stops after 2 minutes.               │
│                                                              │
│ [ Research ]   [ Clear session ]                             │
│                                                              │
│ Third-party search and AI providers process your topic.      │
│ Reloading the page ends a running search.   About / Privacy  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Running

```
│ Depth: Quick   [ Research ] (disabled)  [ Clear session ] (disabled)
├──────────────────────────────────────────────────────────────┤
│ Researching… Elapsed 0:42 (maximum 2:00)                     │
│                                                              │
│  ✓ Planning   ✓ Searching   ● Screening sources              │
│  ○ Drafting   ○ Verifying claims   ○ Finalizing              │
│                                                              │
│ Current step: Screening sources                              │
│ Please don't reload this page while research is running.     │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Completed

```
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ✓ COMPLETED                                              │ │
│ │ 6 usable sources · 4 domains · 8 supported claims        │ │
│ │ Minimum evidence thresholds were met. Coverage is not    │ │
│ │ exhaustive.                                              │ │
│ └──────────────────────────────────────────────────────────┘ │
│ Quick · researched 2026-10-21 · search snippets: 50% of      │
│ claims · questions covered: 3 of 4                           │
│                                                              │
│ [ Download Markdown (.md) ]                                  │
│                                                              │
│ ## Executive summary                                         │
│ C1  Claim text. [1]                   [ ] Show evidence (C1) │
│ ## Scope and questions researched                            │
│ • Background — 3 supported claims                            │
│ • Impacts and risks — 2 supported claims                     │
│ • Current state — not covered                                │
│ ## Key findings                                              │
│ C2  Claim text. [2] [3]               [ ] Show evidence (C2) │
│   ┌ Evidence ──────────────────────────────────────────────┐ │
│   │ Source [2] · Extracted page text                       │ │
│   │ "Quoted passage in plain text…"                        │ │
│   │ Title — example.org   ↗ link (opens in a new tab)      │ │
│   │ Passage 2:p3 · Claim C2                                │ │
│   └────────────────────────────────────────────────────────┘ │
│ ## Competing views … ## Limitations … ## Conclusion …        │
│ ## References                                                │
│ [1] Title — example.org — 2026-03-04 — retrieved 2026-10-21  │
│     Extracted page text · https://example.org/report         │
│                                                              │
│ Was this useful?  [ Useful ]  [ Not useful ]                 │
└──────────────────────────────────────────────────────────────┘
```

### 4.4 Partial

Same layout as Completed with these differences:
- The banner reads "PARTIAL" with a warning glyph and uses the warning tokens.
- Below the headline sits a bulleted list of every unmet threshold in plain words (§9.3).
- The exported file and the report title begin with "PARTIAL —".

```
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ! PARTIAL                                                │ │
│ │ Partial: 100% of supported claims rely on snippets. More │ │
│ │ complete text was not available.                         │ │
│ │ Why this is partial:                                     │ │
│ │  • Most claims rely on search snippets                   │ │
│ │  • Fewer independent websites than the target            │ │
│ └──────────────────────────────────────────────────────────┘ │
```

### 4.5 Failed

```
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ✕ FAILED                                                 │ │
│ │ No report was produced because the available evidence    │ │
│ │ could not support two factual findings.                  │ │
│ │ Try a narrower or clearer topic, or run it again later.  │ │
│ └──────────────────────────────────────────────────────────┘ │
│ [ Try again ]                                                │
│ Your topic is kept above.                                    │
```

If candidate sources exist, they may be listed under the banner as "Sources found but not used" with no synthesized text (PRD §9.4).

### 4.6 About / Privacy and FAQ

Both tabs are plain, single-column, heading-led documents. Content is specified in PRD §7.5. Layout rules:
- A level-2 heading per question or topic, so screen-reader users can jump by heading.
- Short paragraphs of no more than about 5 lines. Lists instead of dense paragraphs.
- The reporting contact is a visible link at the end of both tabs.
- No accordions or expanders (they cannot be reliably tested for keyboard and announcement behavior in Streamlit).

### 4.7 Mobile (320 CSS px)

```
┌────────────────────────┐
│ AI Research Agent      │
│ Research a topic…      │
│ [Research][About][FAQ] │
│ Topic (English, 1–500) │
│ ┌────────────────────┐ │
│ │                    │ │
│ └────────────────────┘ │
│ Depth                  │
│ (●) Quick              │
│ ( ) Deep               │
│ Quick: up to 8 sources │
│ [   Research        ]  │
│ [   Clear session   ]  │
│ Reloading ends a run.  │
└────────────────────────┘
```

Buttons are full width and aim for 44 px tall (never below 24 px). The progress list stacks one stage per line. Source URLs wrap and never force horizontal scrolling (§10).

---

## 5. Color Palette and Typography

### 5.1 Palette (light theme, shipped in the pilot)

Every pair below was computed with the WCAG 2.x contrast formula. "Need" is the success criterion threshold.

| Role | Hex | Used for |
|---|---|---|
| `bg` | `#FFFFFF` | Page background |
| `surface` | `#F3F5F8` | Cards, banners, evidence panel background |
| `text` | `#1B2330` | Body text and headings |
| `text-2` | `#475467` | Secondary text, captions, metadata |
| `primary` | `#0B5CAD` | Primary buttons, links, focus ring |
| `primary-text` | `#FFFFFF` | Text on primary buttons |
| `primary-hover` / `primary-active` | `#094C8F` / `#073D73` | Primary button hover and pressed fills |
| `surface-hover` | `#E6EAF0` | Hover fill for secondary buttons and toggles |
| `border` | `#667085` | Boundaries of controls (inputs, buttons, toggles) |
| `divider` | `#D5DAE1` | Decorative rules only, never a control boundary |
| `ok-fg` / `ok-bg` / `ok-bd` | `#0B5D2A` / `#E7F5EC` / `#2E7D4F` | Completed, extracted evidence |
| `warn-fg` / `warn-bg` / `warn-bd` | `#7A4300` / `#FFF3DC` / `#B26A00` | Partial, cautions |
| `err-fg` / `err-bg` / `err-bd` | `#9B1C1C` / `#FDECEC` / `#C62828` | Failed, validation errors |
| `info-fg` / `info-bg` / `info-bd` | `#0B4A7A` / `#E8F1FA` / `#2F6FA8` | Neutral notices, search-snippet badge |

### 5.2 Verified contrast (light)

| Pair | Ratio | Need | Result |
|---|---|---|---|
| `text` on `bg` | 15.79 | 4.5 | Pass |
| `text` on `surface` | 14.46 | 4.5 | Pass |
| `text-2` on `bg` | 7.69 | 4.5 | Pass |
| `text-2` on `surface` | 7.04 | 4.5 | Pass |
| `primary` (links) on `bg` | 6.67 | 4.5 | Pass |
| `primary` (links) on `surface` | 6.11 | 4.5 | Pass |
| `primary-text` on `primary` | 6.67 | 4.5 | Pass |
| `primary-text` on `primary-hover` / `primary-active` | 8.60 / 10.91 | 4.5 | Pass |
| `text` / `text-2` on `surface-hover` | 13.08 / 6.37 | 4.5 | Pass |
| `border` vs `surface-hover` | 4.12 | 3.0 | Pass |
| `primary` (links) on `surface-hover` | 5.52 | 4.5 | Pass |
| `border` vs `bg` | 4.97 | 3.0 | Pass |
| `border` vs `surface` | 4.55 | 3.0 | Pass |
| Focus ring (`primary`) vs `bg` | 6.67 | 3.0 | Pass |
| Focus ring (`primary`) vs `surface` | 6.11 | 3.0 | Pass |
| `ok-fg` on `ok-bg` | 7.14 | 4.5 | Pass |
| `warn-fg` on `warn-bg` | 7.26 | 4.5 | Pass |
| `err-fg` on `err-bg` | 7.14 | 4.5 | Pass |
| `info-fg` on `info-bg` | 8.09 | 4.5 | Pass |
| `ok-bd` / `warn-bd` / `err-bd` / `info-bd` vs `bg` | 5.05 / 4.24 / 5.62 / 5.30 | 3.0 | Pass |

### 5.3 Dark theme (P1, not shipped in the pilot)

Streamlit follows the browser's color scheme only when a theme is configured for it, and support for separate light and dark theme sections depends on the pinned version (§15). The dark palette is specified now so the tokens are complete. Every pair below also passes.

| Role | Hex | Contrast notes |
|---|---|---|
| `bg` / `surface` | `#0F141A` / `#1A222C` | |
| `text` | `#E9EDF2` | 15.73 on `bg`, 13.64 on `surface` |
| `text-2` | `#A8B3C2` | 8.71 on `bg`, 7.56 on `surface` |
| `primary` / `primary-text` | `#6DB3FF` / `#06101C` | 8.41 on `bg`; 8.69 text on primary |
| `primary-hover` / `primary-active` | `#8EC5FF` / `#A9D4FF` | 10.54 / 12.33 with `primary-text` |
| `surface-hover` | `#243040` | `text` 11.36, `text-2` 6.29, `border` 3.82 |
| `border` | `#7C8AA0` | 5.29 vs `bg`, 4.58 vs `surface` |
| `ok` fg/bg/bd | `#8FD9A8` / `#12301F` / `#4CAF73` | 8.62 text; 6.77 border |
| `warn` fg/bg/bd | `#F2C06B` / `#33260F` / `#D69A2D` | 8.79 text; 7.50 border |
| `err` fg/bg/bd | `#FF9E9E` / `#3A1618` / `#E05A5A` | 8.13 text; 5.09 border |
| `info` fg/bg/bd | `#8CC4F5` / `#14283C` / `#4C8FD0` | 8.10 text; 5.41 border |

A contrast script in `eval/` recomputes all of these from the tokens in CI (§12.3), so this table cannot drift from the code.

### 5.4 Meaning without color

| Meaning | Color role | Glyph | Text label |
|---|---|---|---|
| Completed | `ok` | ✓ | "COMPLETED" |
| Partial | `warn` | ! | "PARTIAL" |
| Failed | `err` | ✕ | "FAILED" |
| Notice | `info` | i | none beyond the message |
| Search snippet | `info` | none | "Search snippet" |
| Extracted page text | `ok` | none | "Extracted page text" |
| Not inspected (metadata-only) | `text-2` on `surface` | none | "Not inspected (title only)" |

Glyphs are text characters inside the banner and never the only cue. Their accessible text comes from the label that follows them.

**Iconography.** The only glyphs are the Unicode characters ✓ ! ✕ i ● ○ ↗. There is no icon font, no image and no extra network request. Each glyph sits next to its text, so a missing glyph on some platform costs nothing. Where Streamlit allows, the glyph is hidden from assistive technology so the text is not announced twice.

### 5.5 Typography

| Item | Spec |
|---|---|
| Typeface | Streamlit's built-in sans-serif, bundled with Streamlit. No external font requests (privacy and speed). Confirm at M0 that no font is fetched from a third party |
| Base size | 16 px (1 rem) body, line height 1.5 |
| Small | 14 px, line height 1.45: captions, metadata, badges. Nothing renders below 14 px |
| H1 | 28 px, line height 1.25, weight 700: product title only |
| H2 | 22 px, line height 1.3, weight 700: report sections |
| H3 | 18 px, line height 1.35, weight 600: sub-sections such as one facet |
| Measure | At most about 75 characters per line (the centered layout width) |
| Text size controls | Sizes are relative (rem), so browser zoom and text-size settings work to 200% |
| Case | Sentence case. Status labels in capitals only for COMPLETED, PARTIAL and FAILED |
| Numbers | Counts as integers, percentages as integers, dates as `YYYY-MM-DD` (UTC date) |
| Quotes | Evidence quotes are plain text in a distinct block (left border `divider`, text `text`), never in italics for long runs |

Heading levels are real heading elements in order (H1 once, H2 for sections, H3 below), because Streamlit's `st.title`, `st.header` and `st.subheader` render real headings.

---

## 6. Spacing, Grids, and Breakpoints

### 6.1 Spacing scale

Base unit 4 px.

| Token | Value | Typical use |
|---|---|---|
| `space-1` | 4 px | Icon and text gap |
| `space-2` | 8 px | Inside badges, between inline controls |
| `space-3` | 12 px | Inside panels (padding), between list items |
| `space-4` | 16 px | Page side gutter on narrow screens, between blocks |
| `space-5` | 24 px | Between report sections |
| `space-6` | 32 px | Between major areas (input, status, report) |
| `space-7` | 48 px | Above the footer notice |

Radius: `radius-1` 6 px (controls, badges), `radius-2` 10 px (banners, panels). Elevation: none; separation uses borders and `surface` fills, so nothing relies on shadows.

### 6.2 Grid and breakpoints

| Class | Width (CSS px) | Layout |
|---|---|---|
| Narrow | below 480 (includes the 320 px requirement) | One column. Depth options stack. Buttons full width. Scorecard items one per line |
| Standard | 480 to 1023 | One centered column. Depth options in a row. Scorecard in two columns |
| Wide | 1024 and above | Same centered column as Standard. Extra width is empty margin |

Streamlit's centered layout caps content width, so Standard and Wide look the same by design. A single reading column also matches the PRD (one task, one report). Streamlit columns collapse to a stack on narrow viewports at a width set by Streamlit, which may differ slightly from 480 px. Verify at M2 and prefer layouts that stay readable either way.

---

## 7. Reusable Component Specifications

Each component is a function in `ui/components.py` (ARCH §4.1) that takes plain data, returns nothing, and calls no provider. Widget keys follow `component:id`, for example `evidence:c003`. The component list follows the product areas in the PRD example: dashboard, question input, source inspection, progress, citations, report viewer.

| Component | Purpose | Content and behavior | Notes |
|---|---|---|---|
| **TopicInput** | Question input | Multi-line text area (about 3 lines high), visible label "Topic (English, 1–500 characters)", example buttons beneath. Validation runs on button press. The topic is kept after any error | No browser-side length cap, so the PRD message "Topics must be 500 characters or fewer." can appear |
| **ExampleChips** | Fill the topic quickly | Three buttons from the PRD personas. Pressing one fills the text area and does not start a run | Keyboard-operable buttons, not links |
| **DepthSelector** | Quick or Deep | Radio group labeled "Depth". Caption under it shows the source limit and maximum time for the chosen depth (from the mode limits, PRD §6.1) | Horizontal at Standard width, stacked at Narrow |
| **ResearchButton** | Start a run | Primary button "Research". Disabled while a run is active or the chosen mode is unavailable (the UI reads availability from `RunManager.get_service_state`, ARCH §6.3), with a caption explaining why | The disabled state is cosmetic; `RunManager` holds the real lock |
| **ClearSessionButton** | Remove the report | Secondary button. Enabled only when there is a topic or a result to clear. Disabled while a run is active, with a caption. On press: `clear_session`, delete UI keys, show the cleared confirmation | See ARCH §4.2 |
| **ProgressStages** | Progress indicator | Six stages in order (§8.4). Each shows a glyph (✓ done, ● current, ○ later) and its name. A text line names the current step. Elapsed time and the maximum time are shown as text | No percentage bar: stage progress is not a measure of time left |
| **StatusBanner** | State of the result | One of three variants (Completed, Partial, Failed) with glyph, label, PRD §7.3 message and, for Partial, the reason list. A "Try again" button sits directly under the Failed variant. It is a native Streamlit button, because a widget cannot live inside the banner's HTML, and it submits the kept topic and depth as a new run with a new idempotency token | App-owned markup with literal templates (§12.4) |
| **Scorecard** | What the evidence looks like | Mode, research date, usable sources, distinct domains, supported claims, snippet-only share, facets covered of planned. Plain text list at Narrow width | Numbers come from the result, never from model text |
| **ReportView** | Report viewer | Renders the report sections in the PRD §6.3 order. Headings are real headings: the status banner label and each report section are H2 under the page's single H1, and sub-sections such as one facet are H3. The report is built on screen from the structured result, one section and one ClaimItem at a time, so every claim can carry its own toggle. The escaped Markdown from the export module is used only for the download. Both use the same escaping function (ARCH §9.4) | HTML is off for this block |
| **ClaimItem** | One supported claim | A visible claim number (C1, C2, … in report order, in `text-2`), the claim text (escaped), its citation markers `[n]`, then the EvidenceToggle on the same row at Standard width and on the next line at Narrow width | Markers are plain text; the references list and the evidence panel give the links. Claim numbers are distinct from citation markers |
| **EvidenceToggle** | Source inspection | Native toggle labeled "Show evidence (C1)", with the claim number in the label so each toggle has a distinct name for screen-reader and speech-control users (WCAG 2.4.6, 2.5.3). First activation records the `evidence_opened` event (ARCH ADR-012) | Native control, so Enter and Space work |
| **EvidencePanel** | Source inspection | Bordered block (`surface`, `border`) showing: source number and evidence-mode badge; the quote in plain text; source title and domain; the source link (opens in a new tab, labeled as such); passage ID; claim number. Content is plain text only | Quote is at most 300 characters (PRD FR-20) |
| **EvidenceModeBadge** | Evidence mode | Text badge from the table in §5.4 | Never color-only |
| **FacetCoverageList** | Scope and questions researched | One line per planned question with its count of supported claims, or "not covered" | Code-generated (PRD §6.3 item 3) |
| **ReferenceItem** | Citations | `[n]` Title — domain — published date if known — retrieved date; then mode badge and the full URL as a link. Long titles and URLs wrap | Link text is the title, not "click here" |
| **Notice** | Inline message | Info, warning or error variant with glyph and text. Never auto-dismisses | Used for validation, busy, paused, unavailable, reload, expiry |
| **FeedbackBar** | Usefulness feedback | "Was this useful?" with two buttons. After a vote: inline confirmation text and no buttons | One vote per run |
| **DownloadButton** | Export | Button "Download Markdown (.md)". File name `ai-research-YYYYMMDD-HHMM.md`, or `ai-research-PARTIAL-YYYYMMDD-HHMM.md` for Partial results. The file name never contains the topic | Placed after the report heading and after the references |
| **StandingNotice** | Reload and result-lifetime notice | One caption in the footer of the Research tab | Always visible |
| **PrivacyTab / FaqTab** | Trust content | Heading-led documents (§4.6) | Content per PRD §7.5. The Privacy tab names the configured providers and models, and for the NVIDIA free prototype API says its terms and limits can change, and says verification runs on this computer when the verifier is local; a one-line caption repeats that on the Research tab |
| **ExpiredNotice** | Result gone | Info notice with the PRD "Result expired" copy and the form below | |

**Reuse rules.** A new visual need is first met by a variant of an existing component. A new component is added to this table before it is built. Components never hard-code colors or spacing (§12).

---

## 8. Interactive States and Animation

### 8.1 Control states

| State | Treatment |
|---|---|
| Default | Token colors, `border` outline on inputs and secondary buttons |
| Hover | Primary button fill becomes `primary-hover`; secondary buttons and toggles fill with `surface-hover`. The cursor is the pointer. No layout change |
| Focus-visible | Target: a 3 px solid `primary` ring with a 2 px offset on every interactive element, never removed and not hidden by sticky headers (WCAG 2.4.11). If a native control's default indicator in the pinned Streamlit version is visible and passes 3:1 against its surroundings, keep it. Override only where it fails, in `ui/theme.py`, with selectors verified for that Streamlit version (§15 item 11) |
| Active (pressed) | Primary button fill becomes `primary-active`. No movement |
| Disabled | Reduced emphasis (text `text-2`, a lighter border where Streamlit allows), plus a caption stating why. Disabled controls are not the only explanation of a state |
| Error | `err-bd` border and an adjacent error message with a glyph and text |
| Loading | See §8.3 |

Disabled text and decorative disabled controls are exempt from the contrast minimum, but the caption explaining the state meets it.

### 8.2 Motion

1. No custom animation. Streamlit's built-in spinner is the only moving element.
2. Nothing auto-dismisses. Status and feedback appear as inline text, not toasts, because timed messages can vanish before they are read.
3. If any transition is ever added, it must be under 200 ms and respect `prefers-reduced-motion`.
4. No auto-playing media and no flashing content.

### 8.3 Loading behavior

- On submit, the Research button disables immediately and the progress area appears in the same render (PRD NFR-01: acknowledged within 1 second).
- While running, the stage line and elapsed time update once per second from the polling fragment (ARCH §4.2). Only the stage change is meant to be announced to assistive technology; the elapsed time is visual.
- The page never shows a spinner with no text. A spinner, if used, sits beside the current-step text.

### 8.4 Progress stages

Six stages, named as in PRD §5.1. The architecture states map to them as follows.

| Stage (shown) | Architecture states (ARCH §5.3) |
|---|---|
| Planning | `PLANNING` |
| Searching | `SEARCHING` |
| Screening sources | `SCREENING` |
| Drafting | `DRAFTING` |
| Verifying claims | `CHECKING`, `VERIFYING`, `ASSEMBLING`, `SCANNING`, `EVALUATING`, `REPAIRING` |
| Finalizing | `FINALIZING` |

The architecture's `RunView.stage_index` carries the index (0 to 5) so the UI needs no knowledge of internal states. The current-step line is the stage name followed by an ellipsis. During "Verifying claims" it uses the PRD sentence "Verifying which claims are supported by retrieved passages…".

---

## 9. Loading, Empty, Error, and Success States

### 9.1 State catalog

The message text in every row is the PRD §7.3 copy, used verbatim from `ui/copy.py`. The "next step" line is design-owned and is a proposal to confirm with the product owner.

| State | Component | Visual | Next step shown | Focus after render |
|---|---|---|---|---|
| Idle (empty) | Form, ExampleChips | No banner. Example topics visible | "Enter a topic, or try an example." | None (normal page order) |
| Invalid input | Notice (error) under the field | Error variant with glyph | "Edit the topic and press Research again." | The error message |
| Running (loading) | ProgressStages, Notice (info) | Stage list and elapsed time | "Please don't reload this page while research is running." (part of the PRD copy) | Unchanged |
| Busy | Notice (warning) | Warning variant | "Try again in a minute." | The notice |
| Service paused | Notice (warning) | Warning variant | "Try again later." | The notice |
| Mode unavailable | Notice (warning) near DepthSelector; the unavailable option is disabled | Warning variant | "Choose the other depth." | The notice |
| Reloaded or restarted | StandingNotice | Footer caption; idle form | "Start your search again." | None |
| Expired | ExpiredNotice | Info variant | "Run it again to get a new result." | The notice |
| Completed (success) | StatusBanner | Success variant | Download, inspect evidence, give feedback | The banner heading |
| Partial | StatusBanner | Warning variant with reason list | Same as Completed, with the limits clearly stated | The banner heading |
| Failed / no evidence | StatusBanner, Try again | Error variant | "Try a narrower or clearer topic, or run it again later." | The banner heading |
| Provider failure | StatusBanner (Failed variant) | Error variant | "Try again in a moment." | The banner heading |
| Semantic mismatch | Notice above the report | Warning variant | "The claims that remain are all matched to their sources." | The notice |
| Budget or timeout | StatusBanner or Notice | Warning variant (Partial) or error variant (Failed) | "You can still read and download what was verified." | The banner heading |
| Feedback recorded | FeedbackBar | Inline text, buttons removed | None | The confirmation text |
| Cleared | Notice (info) | Info variant, form empty | "Start a new search whenever you are ready." | Topic field |

### 9.2 Success is not celebration

A Completed result uses the success tokens but no confetti, no large celebratory wording and no wording such as "comprehensive" or "verified true". The banner states what was met ("Minimum evidence thresholds were met. Coverage is not exhaustive.") per PRD §6.4.

### 9.3 Partial reasons in plain words

The banner lists one plain sentence per reason code. The sentences are design-owned proposals in `ui/copy.py`. Codes come from ARCH §5.4.

| Reason code | Sentence shown |
|---|---|
| `LOW_EVIDENCE_GROUPS` | "Fewer distinct sources than the target." |
| `LOW_DOMAINS` | "Fewer independent websites than the target." |
| `INSUFFICIENT_CLAIMS` | "Fewer supported claims than the target." |
| `INCOMPLETE_FACETS` | "Some planned questions were not covered." |
| `SNIPPET_HEAVY` | "Most claims rely on search snippets, not full page text." |
| `TIMEOUT` | "The search stopped at the time limit." |
| `BUDGET_STOP` | "The search stopped at the cost limit." |

### 9.4 Empty parts inside a result

| Empty part | What is shown |
|---|---|
| No conflicting evidence | "No material disagreement identified in selected evidence." (PRD FR-18) |
| A planned question with no supported claim | "Not covered" in the facet list |
| No publication date | "Date unknown", never a guessed date |
| No sources found but not used | The "Sources found but not used" block is omitted |

### 9.5 Not controlled by this design

Streamlit's own "connecting" and connection-lost overlays cannot be restyled or reworded. The FAQ explains that reloading the page, a lost connection or a server restart can end a run. The design adds no separate state for them.

---

## 10. Responsive Behavior

| Concern | Rule |
|---|---|
| Reflow | No horizontal scrolling at 320 CSS px for the form, the report or the references (WCAG 1.4.10). Only code blocks may scroll, and the product has none |
| Zoom | Usable at 200% zoom and 200% text size with no loss of content or controls (WCAG 1.4.4) |
| Touch targets | Design goal 44 × 44 CSS px for buttons and toggles. The required minimum is 24 × 24 CSS px (WCAG 2.5.8). Streamlit's native radio and toggle sizes are measured at M2 and enlarged with app-owned spacing only where they fall below 24 px |
| Long strings | Titles, domains and URLs wrap using `overflow-wrap: anywhere`. The real link target is never shortened |
| Buttons | Full width at Narrow, natural width at Standard |
| Scorecard | Two columns at Standard, one line per item at Narrow |
| Evidence panel | Full column width. The quote wraps; the source link sits on its own line |
| Progress | Stages wrap onto multiple lines or stack, each with its glyph |
| Download and feedback | After the report heading, not floating (PRD §7.2) |
| Orientation | Works in portrait and landscape |
| Input | Text area grows with content up to a limit, then scrolls inside itself |

---

## 11. Accessibility Requirements

The target is WCAG 2.2 AA (PRD §7.4), tested rather than assumed. The table maps the criteria that apply to this UI.

| Criterion | Requirement in this design | How it is checked |
|---|---|---|
| 1.1.1 Non-text content | Glyphs are decorative beside text labels. No informational images | Review |
| 1.3.1 Info and relationships | Real headings, lists and labels; tabs are native tab controls | axe scan, screen-reader spot check |
| 1.3.2 Meaningful sequence | DOM order matches the visual order in §2.1 | Keyboard walkthrough |
| 1.4.1 Use of color | Status and evidence mode use text and glyph as well as color (§5.4) | Review, grayscale screenshot |
| 1.4.3 Contrast (minimum) | All text pairs at least 4.5:1 (§5.2) | Contrast script in CI |
| 1.4.4 Resize text | Works to 200% | Browser test at 200% |
| 1.4.10 Reflow | No horizontal scroll at 320 px | Browser test at 320 px |
| 1.4.11 Non-text contrast | Control boundaries and the focus ring at least 3:1 (§5.2) | Contrast script, review |
| 1.4.12 Text spacing | No loss of content when user text spacing is increased | Browser test with a spacing override |
| 1.4.13 Content on hover or focus | No hover-only or focus-only content. Streamlit `help` tooltips are not used; explanations are visible captions | Review |
| 2.1.1 Keyboard | Every action is reachable and operable by keyboard, including the Evidence toggle | Keyboard-only walkthrough |
| 2.1.2 No keyboard trap | Focus moves freely through all controls and tabs | Walkthrough |
| 2.2.1 Timing adjustable | No auto-dismissing messages; the run has fixed server limits shown as text | Review |
| 2.4.2 Page titled | The browser tab title is "AI Research Agent". It never contains the topic | Review |
| 2.4.3 Focus order | Logical order: tabs, topic, examples, depth, buttons, then the result in order | Walkthrough |
| 2.4.6 Headings and labels | Descriptive headings and field labels | Review |
| 2.4.7 Focus visible | 3 px ring on every interactive element | Visual check, browser test |
| 2.4.11 Focus not obscured | The focused control is never hidden by other content | Browser test |
| 2.5.8 Target size (minimum) | At least 24 × 24 px, design goal 44 px | Browser test |
| 3.1.1 Language of page | English, with the page language attribute set to English (Streamlit default, verify) | Browser inspection |
| 3.2.2 On input | Typing in the topic or changing depth never starts a run, moves focus or changes context | Test case |
| 3.2.6 Consistent help | The contact link is in the same place on About / Privacy and FAQ | Review |
| 3.3.1 Error identification | Validation errors are named in text next to the field | Test cases for PRD test 1 |
| 3.3.2 Labels or instructions | Every field has a visible label and format hint | Review |
| 3.3.3 Error suggestion | Each error says how to fix it | Review |
| 3.3.7 Redundant entry | The topic is kept after errors and failures | Test case |
| 4.1.2 Name, role, value | Native controls only | axe scan |
| 4.1.3 Status messages | Stage changes and errors are announced where Streamlit allows | Screen-reader spot check; documented limitation if not |

Not applicable: 2.5.7 Dragging movements (no dragging), 3.3.8 Accessible authentication (no sign-in in the pilot).

### 11.1 Streamlit-specific risks to confirm

1. **Focus after a rerun.** Streamlit reruns can drop keyboard focus. The design needs focus to land on the error after a validation failure and on the banner heading after a result. If this cannot be done with native Streamlit, a very small embedded component may be needed. If that also fails, record it as a framework limitation per PRD §7.4 and treat any blocker to primary use as release-blocking.
2. **Live announcements.** Whether `st.status`, alerts or plain text are announced as polite or assertive live regions must be tested with at least one screen reader. If none are, the stage line still updates visibly and the limitation is documented.
3. **Error association.** Streamlit text areas do not link custom error text to the field. The label includes the format hint, and the error sits directly under the field.
4. **Keyboard operation of tabs and toggles.** Verify arrow-key and Enter behavior.
5. **Default widget contrast.** Streamlit's own placeholder text, borders and disabled states may fall below the minimums. They are checked at M2, and any shortfall is fixed with theme values or the app-owned CSS.
6. **No skip link.** Streamlit does not provide a "skip to content" link (WCAG 2.4.1). Because the tabs and the form sit at the top, the impact is low. Confirm with the keyboard walkthrough and note it if it becomes a problem.

### 11.2 Test plan

The accessibility checks map to PRD test 26 and the browser layer of ARCH §13.1: keyboard-only walkthrough of J1 to J12, axe-core scan of each state, 320 px and 200% zoom, screen-reader spot check on Completed, Partial and Failed, and the contrast script. Defects are logged with severity. A defect that blocks starting a run or reading a report is release-blocking.

---

## 12. Design Tokens and Visual Consistency Rules

### 12.1 Token source

Tokens live in `ui/theme.py` (a small module of constants). `.streamlit/config.toml` carries the subset Streamlit reads (primary color, background, secondary background, text color, font). A test asserts that the two agree, so a value cannot be changed in one place only.

### 12.2 Token table

| Token | Light value | Maps to |
|---|---|---|
| `--ar-color-bg` | `#FFFFFF` | Streamlit `backgroundColor` |
| `--ar-color-surface` | `#F3F5F8` | Streamlit `secondaryBackgroundColor` |
| `--ar-color-text` | `#1B2330` | Streamlit `textColor` |
| `--ar-color-text-2` | `#475467` | App CSS |
| `--ar-color-primary` | `#0B5CAD` | Streamlit `primaryColor`; links; focus ring |
| `--ar-color-primary-text` | `#FFFFFF` | App CSS |
| `--ar-color-border` | `#667085` | App CSS |
| `--ar-color-divider` | `#D5DAE1` | App CSS |
| `--ar-ok-fg`, `-bg`, `-bd` | `#0B5D2A`, `#E7F5EC`, `#2E7D4F` | StatusBanner, badges |
| `--ar-warn-fg`, `-bg`, `-bd` | `#7A4300`, `#FFF3DC`, `#B26A00` | StatusBanner, notices |
| `--ar-err-fg`, `-bg`, `-bd` | `#9B1C1C`, `#FDECEC`, `#C62828` | StatusBanner, errors |
| `--ar-info-fg`, `-bg`, `-bd` | `#0B4A7A`, `#E8F1FA`, `#2F6FA8` | Notices, search-snippet badge |
| `--ar-color-primary-hover`, `-active` | `#094C8F`, `#073D73` | Primary button hover and pressed fills |
| `--ar-color-surface-hover` | `#E6EAF0` | Hover fill for secondary buttons and toggles |
| `--ar-space-1` to `-7` | 4, 8, 12, 16, 24, 32, 48 px | Layout |
| `--ar-radius-1`, `-2` | 6 px, 10 px | Controls, panels |
| `--ar-font-size-base` | 1 rem | Body |
| `--ar-font-size-small` | 0.875 rem | Captions, badges |
| `--ar-focus-ring` | 3 px solid `--ar-color-primary`, offset 2 px | All interactive elements |

Dark values are in §5.3 and use the same token names under a dark scope.

### 12.3 Consistency rules

| ID | Rule |
|---|---|
| DR-1 | No hard-coded color, spacing or font size outside `ui/theme.py` |
| DR-2 | Status and evidence mode always show text and a glyph, never color alone |
| DR-3 | All user-facing strings come from `ui/copy.py`, so copy review happens in one file. Keys are `state.<ui state>` (§3.3), `next.<ui state>` (§9.1), `reason.<code>` (§9.3) and `label.<name>` |
| DR-4 | UI labels for evidence modes: snippet is "Search snippet", extracted is "Extracted page text", metadata-only is "Not inspected (title only)" |
| DR-5 | Dates are `YYYY-MM-DD` in UTC; unknown dates read "Date unknown" |
| DR-6 | External links show the source domain and are labeled "(opens in a new tab)" |
| DR-7 | A Partial result always shows its reasons, and a Completed result never uses the words "comprehensive", "exhaustive" or "verified true" |
| DR-8 | Messages never auto-dismiss |
| DR-9 | Third-party text (claims, quotes, titles) is always rendered as escaped plain text |
| DR-10 | Components are reused before new ones are added (§7) |
| DR-11 | Widget keys follow `component:id`, so state is predictable and testable |
| DR-12 | The contrast script runs in CI against `ui/theme.py` and fails the build on any pair below its threshold |

### 12.4 Where HTML is allowed

Streamlit needs `unsafe_allow_html=True` for a few app-owned elements (the status banner and the badges, which need custom colors). The rule is narrow and enforceable:

1. `unsafe_allow_html=True` appears only in `ui/theme.py` and in the StatusBanner and badge helpers.
2. Those helpers build markup from literal templates. Only integers, the fixed state names and strings from `ui/copy.py` are inserted.
3. Third-party text never goes through them (DR-9).
4. A fitness test (ARCH §13.3) fails if the flag appears anywhere else.

This keeps the PRD rule "no executable HTML if HTML rendering is enabled" (PRD §12.1) true by construction.

---

## 13. Design QA Checklist

Run before each release candidate. Every item has an owner and a recorded result.

- [ ] Every state in §9.1 was rendered and screenshotted at 320 px and at desktop width.
- [ ] J1 to J12 were walked with the keyboard only.
- [ ] Contrast script passes for all token pairs in §5.2 and §5.3.
- [ ] Browser zoom at 200% and text spacing overrides cause no content loss.
- [ ] Screen-reader spot check done on Completed, Partial, Failed and the Evidence toggle.
- [ ] Grayscale screenshot of Completed, Partial and Failed still distinguishes them.
- [ ] Every string in the UI comes from `ui/copy.py`, and the PRD §7.3 messages match verbatim.
- [ ] No `unsafe_allow_html=True` outside the allowed helpers.
- [ ] No external font or asset request on page load.
- [ ] The standing notice and the contact link are present in every state where specified.
- [ ] Download file names contain no topic text.

---

## 14. Traceability

| Design area | PRD | Architecture |
|---|---|---|
| Principles | Product principle, §6.3, §7 | AP-1, AP-3, AP-8 |
| IA and navigation | §5.1, §7.5 | §4.2 |
| Journeys and flows | §5, §7.3, §8.4 | §5.3, §6.4 |
| Wireframes | §7.1, §7.2 | §4.2 |
| Palette and typography | §7.4 | §4.2 |
| Components | FR-10, FR-12, FR-20, FR-26 to FR-29, FR-39, FR-44 | §4.1, §4.2 |
| States | §7.3, §6.4 | §6.4 |
| Responsive | §7.2 | — |
| Accessibility | §7.4, NFR-15, test 26 | §13.1 |
| Tokens and rules | FR-14, §12.1 | ADR-012, ADR-019, §13.3 |

---

## 15. Open Items and Assumptions to Confirm

| # | Item | Confirm at |
|---|---|---|
| 1 | Streamlit's built-in sans-serif font is bundled and triggers no external request | M0 |
| 2 | The pinned Streamlit version's theme options: separate light and dark sections, link and border colors, base font size | M0 |
| 3 | The centered layout width and the point where columns collapse to a stack | M0 |
| 4 | Focus management after a rerun, and whether a small embedded component is needed | M2 |
| 5 | Whether status text is announced to screen readers, and how | M2 |
| 6 | Default widget contrast (placeholder, disabled, borders) | M2 |
| 7 | The design-owned "next step" lines and the plain-language reason sentences (§9) need product-owner approval. They are not in the PRD | M0 |
| 8 | PLAN_TOO_NARROW and NO_EVIDENCE share the "Failed / no evidence" message. A more specific message for a plan failure would need a PRD §7.3 addition | PRD change control |
| 9 | Dark theme is P1. It needs the Streamlit option in item 2 and its own accessibility pass | Post-pilot |
| 10 | A master "Show all evidence" toggle for Deep reports with many claims is a P1 idea. It is not specified here | Post-pilot |
| 11 | Whether native focus indicators pass 2.4.7 and 1.4.11, and which CSS selectors an override would need for the pinned Streamlit version | M2 |
| 12 | Native radio and toggle target sizes against the 24 px minimum | M2 |
