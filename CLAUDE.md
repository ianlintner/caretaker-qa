# CLAUDE.md — project norms for AI assistants

## What this repo is

`caretaker-qa` is a live QA harness for [`ianlintner/caretaker`](https://github.com/ianlintner/caretaker). It ships a small security-relevance agent that fetches vuln feeds + security RSS, matches against a watchlist of public repos, and emits an actionable Markdown brief.

Two audiences depend on how you treat changes here:

1. **Human operators** running the agent to get useful briefs. The agent has a real job.
2. **Caretaker itself**, which maintains this repo and reads our code to learn patterns. Any antipattern we introduce here will be propagated.

## Engineering standards

- **Python 3.12**, pydantic v2, type hints everywhere (`mypy --strict` is gating).
- **Deterministic-first**: regex and semver ranges cover the match stage. The LLM is only invoked when the deterministic matcher says "ambiguous." Never fan-out to the LLM for every feed item.
- **Structured output**: every LLM call uses `structured_complete[T: BaseModel]` with a pydantic output schema. No parsing free-form text.
- **Provider-agnostic**: LLM access goes through LiteLLM; model name is config-driven. The default is Azure AI.
- **Bounded cardinality**: every metric / log label is a closed enum. Repo name is low-cardinality; don't make it high.
- **Tests**: pytest. Every feed fetcher has a `respx`-mocked fixture. LLM calls in tests go through a fake client.
- **CI**: ruff format + ruff check + mypy + pytest (80% branch coverage) + CodeQL. All four gates are required.
- **Commits**: Conventional Commits. `feat:`, `fix:`, `chore:`, `test:`, `docs:`. Scope optional.

## What AI assistants should do

- Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src && uv run pytest` **locally** before declaring work done.
- Match the existing patterns — when adding a new feed, follow `feeds/nvd.py` as the reference implementation.
- Keep the LangGraph graph small. Each node has one job and typed I/O.
- Add a test for every new behaviour. Bug fixes get a regression test.
- Do not introduce a new framework without asking. LangGraph + pydantic + LiteLLM + click is enough.
- Do not commit secrets. `.env.example` is the template; real secrets live in GitHub Actions secrets only.

## What AI assistants should not do

- Do not silently widen lint / mypy config. If a rule is wrong for this repo, argue for it in the PR.
- Do not add a retry loop around the LLM — LiteLLM already retries. Stacking retries drives cost up.
- Do not over-fetch. Each feed has a `since` window; respect it. The NVD and OSV APIs are rate-limited.
- Do not edit `reports/` by hand. The nightly workflow owns that directory.

## Caretaker integration

Caretaker v0.19.4 is pinned in `.github/workflows/maintainer.yml`. It maintains dependency freshness, triages PRs + issues, runs the deterministic-first fix ladder on CI failures, and applies guardrails to its own output. If caretaker opens a PR on this repo, treat it like any other contributor's — review, approve, merge.

## Shadow decisions

This repo is a shadow-mode site for caretaker. Decisions about what to do with new feed items (apply a dependency bump? escalate as advisory?) may run under `@shadow_decision` in caretaker; disagreements land as `:ShadowDecision` nodes. See caretaker's enforce-gate CI for how they get promoted.
