# Changelog

All notable changes to this project will be documented in this file.

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

## [0.1.4] — 2026-04-28

### Changed

- Caretaker pin upgraded from v0.25.0 to v0.26.1 (deploy-mcp uses replace --force for the agent-worker Job, pre-dispatch comment gate for self-echo + @caretaker triggers, drop pip cache from thin maintainer workflow).

## [0.1.3] — 2026-04-27

### Changed

- Caretaker pin upgraded from v0.24.0 to v0.25.0 (PR-head CI failures routed to PR comment, PR readiness finalization on escalation, GitHub API 403 rate-limit graceful handling, OIDC audience fallback, durable eventing + auto-bootstrap for fleet workflow, pr-reviewer harvest-consumer bug fixes, dogfood config consolidation).

## [0.1.2] — 2026-04-24

### Changed

- Caretaker pin upgraded from v0.18.0 to v0.19.2 (fleet lag regression harness — fleet.yml, weekly cron, caretaker fleet lag CLI).

## [0.1.1] — 2026-04-23

### Changed

- Caretaker pin upgraded from v0.16.0 to v0.17.0 (QA-scenario dispatch suppression, empty-PR-body close, Copilot action_required escalation suppression).
