# Changelog

All notable changes to this project will be documented in this file.

## [2026-W18] — 2026-04-27

- enforce triage deduplication and suppress caretaker-triggered issues:labeled re-runs (#14)
- filter_output guardrail for deceptive Markdown links (#15)
- sanitize_input guardrail strips HTML before LLM ingestion (#16)
- fetch_nvd retries on HTTP 429 with targeted exponential backoff (#17)
- qa(scenario-11): pin ci_log_analysis to azure_ai/claude-sonnet-4 for prompt-cache validation (#22)
- upgrade caretaker pin from v0.16.0 to v0.17.0 (#26)
- upgrade caretaker pin from v0.18.0 to v0.19.2 (#31)
- handle string-format references in GHSA advisory parser (#32)
- bump pinned caretaker version to 0.19.3 (#34)
- bump caretaker pin to 0.19.4 (#37)
- enable fleet registry heartbeats (#40)
- adopt v0.20.0 fleet workflow (OAuth2 envs) (#45)
- adopt OAuth2 fleet_registry config (v0.20) (#46)
- fast-forward pin v0.19.4 → v0.22.3 + disable fleet_registry (closes #43, subsumes #44) (#50)
- widen GITHUB_TOKEN scopes — checks:write + security-events:read (closes #53) (#54)
- fast-forward pin to v0.24.0 for harvest QA cycle (#58)
- install Claude Code workflow (unblocks v0.24.0 hand-off review QA) (#62)
- upgrade caretaker pin from v0.24.0 to v0.25.0 (#69)

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

## [0.1.3] — 2026-04-27

### Changed

- Caretaker pin upgraded from v0.24.0 to v0.25.0 (PR-head CI failures routed to PR comment, PR readiness finalization on escalation, GitHub API 403 rate-limit graceful handling, OIDC audience fallback, durable eventing + auto-bootstrap for fleet workflow, pr-reviewer harvest-consumer bug fixes, dogfood config consolidation).

## [0.1.2] — 2026-04-24

### Changed

- Caretaker pin upgraded from v0.18.0 to v0.19.2 (fleet lag regression harness — fleet.yml, weekly cron, caretaker fleet lag CLI).

## [0.1.1] — 2026-04-23

### Changed

- Caretaker pin upgraded from v0.16.0 to v0.17.0 (QA-scenario dispatch suppression, empty-PR-body close, Copilot action_required escalation suppression).
