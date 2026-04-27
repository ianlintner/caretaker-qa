# QA Scenario 12b — Hand-off review harvest (fresh repro window)

**Release validated:** [v0.24.0](https://github.com/ianlintner/caretaker/releases/tag/v0.24.0) ([caretaker#617](https://github.com/ianlintner/caretaker/pull/617))

**Why 12b:** Scenario 12 ([#61](https://github.com/ianlintner/caretaker-qa/pull/61)) dispatched the v0.24.0 hand-off invitation correctly, but the [`claude.yml` workflow](../../.github/workflows/claude.yml) wasn't installed on this repo until *after* the invitation was posted. `issue_comment` events don't replay retroactively, so Claude never received the dispatch on #61 even after the workflow landed in [#62](https://github.com/ianlintner/caretaker-qa/pull/62). 12b is a fresh reproduction window — `claude.yml` is now in place, so the brand-new PR fires `pull_request.opened` → caretaker scores → `issue_comment.created` (hand-off invitation) → Claude Code action picks it up cleanly.

**Setup:** caretaker pinned to v0.24.0, `claude.yml` present on default branch, `ANTHROPIC_API_KEY` secret configured, `allowed_bots: github-actions` so caretaker's invitation (posted by `github-actions[bot]`) is trusted.

**Expected caretaker behavior:**
1. **Cycle 1 (dispatch).** caretaker scores this PR ≥ 40 (sensitive paths: `.github/workflows/secret-audit.yml` + `src/qa_agent/secret_tracker.py`). The PR is labeled `claude-code` and a fresh hand-off invitation comment is posted.
2. **Upstream action (cycle 1.5).** `anthropics/claude-code-action@v1` fires on the `issue_comment.created` event (the workflow now exists), reviews the PR, and replies with a regular issue comment. If it follows the v0.24.0 schema, the reply ends with `<!-- caretaker:review-result -->` followed by a fenced `caretaker-review` JSON block.
3. **Cycle 2 (harvest).** On the next caretaker run, `pr_reviewer.handoff_review_consumer` parses the agent reply, calls the GitHub Reviews API, and a formal review appears in the **Reviews** tab attributed to `the-care-taker[bot]`, with inline comments anchored on the diff. The body credits `@claude[bot]`.
4. **Idempotency.** The agent reply's comment ID is recorded in `TrackedPR.consumed_handoff_review_comment_ids`. Subsequent cycles do not re-post.

**Failure modes the scenario catches:**
- Claude Code action filters caretaker's invitation as bot-authored (regression in `allowed_bots: github-actions`).
- The hand-off invitation in the comment thread is parsed as the agent's reply by the consumer (the `_is_caretaker_authored` regression flagged during 12 — see follow-up PR pending in caretaker).
- Two formal reviews are posted on the same agent reply (idempotency regression).
- The formal review is posted on the wrong commit SHA after a force-push (regression in head-SHA threading).

**How to verify:**
```bash
# 1. caretaker dispatched (within 5 min of PR open):
gh pr view <pr-number> -R ianlintner/caretaker-qa --json labels --jq '.labels[].name'
# → must include "claude-code"

# 2. Claude Code action ran:
gh run list -R ianlintner/caretaker-qa --workflow=claude.yml --limit 5

# 3. Claude posted a structured reply:
gh api /repos/ianlintner/caretaker-qa/issues/<pr-number>/comments \
  --jq '.[] | select(.user.login == "claude") | {has_payload: (.body | contains("caretaker:review-result"))}'

# 4. caretaker harvested (≤ 5 min after Claude's reply):
gh api /repos/ianlintner/caretaker-qa/pulls/<pr-number>/reviews \
  --jq '.[] | {user: .user.login, state, body_preview: (.body | .[0:120])}'
# → must include {"user": "github-actions[bot]" or "the-care-taker[bot]", ...}
```

<!-- caretaker:qa-scenario -->
<!-- scenario-12b: handoff-review-harvest-fresh -->
