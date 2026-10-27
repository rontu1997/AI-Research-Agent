# AI Research Agent GitHub Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the AI Research Agent as a clean, secret-free, independently publishable GitHub repository.

**Architecture:** Preserve application source, tests, documentation, dependency manifests, and the safe environment template. Remove only reproducible local environments/caches and generated runtime data; blank the API credential in the ignored local environment file.

**Tech Stack:** Python 3.11, uv, Streamlit, Git

**Spec:** User-approved three-private-repository cleanup arrangement from 2026-10-27.

## Global Constraints

- Never expose or print secret values.
- Preserve `.env.example`; keep `.env` ignored.
- Preserve source, tests, documentation, and `uv.lock`.
- Do not change application behavior.

## Review Focus

- `OPENAI_API_KEY` must have an empty value after cleanup.
- Generated directories must not appear in the Git index.
- The repository must contain all files needed for `uv sync --locked`.
- The existing test suite must still run after recreating dependencies.
- No credential-shaped file may be staged.

---

### Task 1: Sanitize and clean the project

**Files:**
- Modify: `.env`
- Delete: `.venv/`, `.hypothesis/`, `.import_linter_cache/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `logs/`, `state/`, and nested Python cache directories

**Interfaces:**
- Consumes: existing `.gitignore` cleanup rules
- Produces: a source-only project tree with no local credential value

- [ ] Blank `OPENAI_API_KEY` without displaying its prior value.
- [ ] Delete the listed reproducible/generated directories.
- [ ] Confirm `.env` remains ignored and contains an empty API-key assignment.

### Task 2: Initialize and verify Git metadata

**Files:**
- Create: `.git/`

**Interfaces:**
- Consumes: the cleaned project tree
- Produces: an initial local Git repository ready for a private GitHub remote

- [ ] Initialize Git with branch `main`.
- [ ] Stage the source tree and verify `.env` and generated artifacts are absent.
- [ ] Run available tests/lint checks after recreating the locked environment if necessary.
- [ ] Create the initial commit.
