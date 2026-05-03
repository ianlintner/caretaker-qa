# Security audit

Weekly automated audit of qa_agent's declared dependencies and the
testbed's watchlist coverage.

## What runs

Two jobs in [`.github/workflows/security-audit.yml`](../.github/workflows/security-audit.yml):

1. **pip-audit** — runs against this repo's declared deps. Failures
   are surfaced as a `[Security]` issue (not a CI failure), so the
   scheduled cycle never blocks merges on transient advisory noise.
2. **watchlist-scan** — runs the qa_agent matcher against the last 7
   days of NVD / OSV / GHSA advisories. Uses `NVD_API_KEY` and
   `GITHUB_TOKEN` (via the new
   [`qa_agent.feeds.auth`](../src/qa_agent/feeds/auth.py) helper) so
   the scan stays under the authenticated rate-limit ceiling.

## Schedule

Tuesdays 14:00 UTC, intentionally an hour after caretaker's nightly
scan so the deduper has flushed the prior cycle's signature set.

## Why this is QA-relevant

The audit produces real-shaped activity (failed advisory, opened
issue, applied label) that exercises caretaker's
`SecurityAgent` + `IssueAgent` paths. The matcher's authenticated
fetch is the first time qa_agent has needed credential management,
which is why the new auth helper is its own module rather than inline
in each feed fetcher.

## Disabling

Set `if: false` on the `pip-audit` job to mute the artifact, or remove
the cron line to disable the scheduled trigger entirely. The
`pull_request` trigger only fires when `pyproject.toml` or
`src/qa_agent/feeds/auth.py` change, so the workflow stays cheap on
unrelated PRs.
