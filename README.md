# AI Research Agent

An evidence-checked web research app. It searches public sources, drafts a report, checks quotes
against stored passages, and reviews each claim before publishing it. Reports can be completed,
partial, or failed.

## Get the repository

This project is published at
[github.com/rontu1997/AI-Research-Agent](https://github.com/rontu1997/AI-Research-Agent).

```powershell
git clone https://github.com/rontu1997/AI-Research-Agent.git
cd AI-Research-Agent
```

## Run with GPT-6 Luna

Install [uv](https://docs.astral.sh/uv/), then:

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY to your key.
uv sync
uv run streamlit run app.py
```

The shipped `.env.example` is configured for live OpenAI web search and `gpt-6-luna` for
planning, writing, and review. **Only `OPENAI_API_KEY` needs editing.** The OpenAI key also pays
for web search tool calls. The [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists the API model ID; the [web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
describes the Responses API search tool. `.env` is ignored by Git.

The app uses search result snippets as evidence and does not fetch source URLs itself. Sources
without usable text are discarded. This can yield a partial or failed report when search returns
too little source text. The writer and reviewer use the **same model**, so the review is a second
check but is not an independent model-family verification. Deterministic quote and numeric checks
still run before a claim can appear in the report.

The price sheet at `core/price_sheet_openai.json` uses current standard GPT-6 Luna text rates
and reserves an estimated $0.02 per web search call for the tool fee and content tokens.
Per-run and daily limits remain in force, but estimates may differ from actual billing. Check
your OpenAI usage dashboard when testing.

## Offline checks

```powershell
uv run pytest
uv run ruff check .
uv run mypy .
```

The scripted providers in `adapters/fakes.py` support tests and the optional `demo.py` offline
example. No real providers are called by the test suite. The live provider probe sends paid API
requests and should be run only with an approved spend cap:

```powershell
uv run python -m eval.provider_probe --yes-call-live-providers
```

See `prd.md`, `architecture.md`, and `design.md` for the original product design. Their
multi-provider examples describe earlier development configurations; this README and
`.env.example` describe the current OpenAI test setup.
