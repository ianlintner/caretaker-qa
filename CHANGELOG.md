# Changelog

All notable changes to this project will be documented in this file.

## [2026-W17] — 2026-04-24

- enforce triage deduplication and suppress caretaker-triggered issues:labeled re-runs (#14)
- filter_output guardrail for deceptive Markdown links (#15)
- sanitize_input guardrail strips HTML before LLM ingestion (#16)
- fetch_nvd retries on HTTP 429 with targeted exponential backoff (#17)
- qa(scenario-11): pin ci_log_analysis to azure_ai/claude-sonnet-4 for prompt-cache validation (#22)
- upgrade caretaker pin from v0.16.0 to v0.17.0 (#26)
- upgrade caretaker pin from v0.18.0 to v0.19.2 (#31)
- handle string-format references in GHSA advisory parser (#32)

## [0.1.0] — 2026-04-22

Initial release. Ships the scaffolding for a live QA harness for `ianlintner/caretaker`.

### Added

- `qa-agent scan` CLI — fetches NVD / OSV / GHSA advisories + security RSS, matches them against a watchlist, emits a Markdown brief.
- LangGraph-based relevance pipeline: `fetch → match → judge → report`.
- Deterministic matcher with CPE + package + repo-topic matching; LLM judge only invoked on ambiguous items.
- `watchlist.yml` seeded with the caretaker fleet (audio_engineer, python_dsa, kubernetes-apply-vscode, flashcards, Example-React-AI-Chat-App) plus three popular OSS projects (langchain, fastapi, axios).
- CI workflow: ruff format + ruff check + mypy --strict + pytest (80% coverage floor) + CodeQL.
- Nightly workflow: runs the agent at 02:00 UTC, commits the brief into `reports/`, opens a PR.
- Caretaker maintainer.yml pinned to v0.16.0 with Wave A features on (fix-ladder, guardrails, attribution telemetry).

## [0.1.2] — 2026-04-24

### Changed

- Caretaker pin upgraded from v0.18.0 to v0.19.2 (fleet lag regression harness — fleet.yml, weekly cron, caretaker fleet lag CLI).

## [0.1.1] — 2026-04-23

### Changed

- Caretaker pin upgraded from v0.16.0 to v0.17.0 (QA-scenario dispatch suppression, empty-PR-body close, Copilot action_required escalation suppression).
