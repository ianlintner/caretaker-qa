# caretaker-qa

A small security-relevance agent used as a live QA environment for [`ianlintner/caretaker`](https://github.com/ianlintner/caretaker).

The agent itself has a real job: fetch recent security advisories (NVD, OSV, GHSA) and security-news RSS, match them against a watchlist of public repos (the caretaker fleet plus a few widely-used open-source projects), and emit a short Markdown brief of items an operator should act on. Running the agent on a schedule produces realistic PRs, issues, CI failures, and dependency drift for caretaker to exercise.

## Why this repo exists

Caretaker is an autonomous GitHub repo maintainer. Validating its behaviour requires a repo whose maintenance signal is non-synthetic: a repo that fails CI sometimes, receives dependency bumps, accumulates comments, and has real code to review. This repo provides that surface while doing something small and useful on its own.

Think of it as the caretaker fleet's always-on QA harness — the noise it generates is exactly the noise caretaker is supposed to triage, and the patches it accepts are the patches caretaker is supposed to produce.

## What the agent does

```
                      ┌─────────────┐
NVD / OSV / GHSA  ──▶ │             │
                      │   fetcher   │
BleepingComputer  ──▶ │    stage    │─┐
Hacker News /sec  ──▶ │             │ │
                      └─────────────┘ │
                                      ▼
                              ┌──────────────┐
                              │  matcher     │  (deterministic CPE /
                              │  (regex +    │   package / repo topic)
                              │   semver)    │
                              └──────┬───────┘
                                     │  only ambiguous items
                                     ▼
                              ┌──────────────┐
                              │   judge      │  (Azure AI via LiteLLM,
                              │   (LangGraph │   structured_complete
                              │    node)     │   with Pydantic)
                              └──────┬───────┘
                                     ▼
                              ┌──────────────┐
                              │   report     │  Markdown + JSON
                              └──────────────┘
```

Deterministic-first by design: regex and semver-range matching cover the obvious cases for free, and the LLM is only invoked when the match is genuinely ambiguous (e.g. the advisory names a package but the watchlist repo depends on a fork, or the severity depends on whether a feature flag is on).

## Usage

```bash
uv sync --extra dev
uv run qa-agent scan --since 24h --watchlist watchlist.yml --out out/brief.md
```

Or one-shot with uv:

```bash
uv run qa-agent scan --dry-run
```

## Structure

```
src/qa_agent/
├── cli.py                 # click CLI entry
├── feeds/                 # feed fetchers (NVD, OSV, GHSA, RSS)
├── watchlist.py           # parse watchlist.yml
├── manifest.py            # pull dependency manifests from each watched repo
├── matcher.py             # deterministic CPE / package / topic matching
├── relevance_graph.py     # LangGraph: fetch → match → judge → report
├── relevance_llm.py       # structured_complete for ambiguous-case judgement
└── report.py              # JSON + Markdown digest writers
tests/                     # pytest suite, fixtures for each feed
watchlist.yml              # list of repos to monitor
```

## Development

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv run pytest --cov
```

CI runs all four in `.github/workflows/ci.yml` and fails on any one.

## Scheduled operation

`.github/workflows/nightly.yml` runs the agent at 02:00 UTC, writes the brief into `reports/YYYY-MM-DD.md`, and opens a PR if anything changed. That PR is caretaker's responsibility to triage.

## Caretaker wiring

`.github/maintainer/config.yml` is pinned to v0.23.0 with Wave A features on. See `docs/caretaker-setup.md` for the full configuration.

## License

MIT.
