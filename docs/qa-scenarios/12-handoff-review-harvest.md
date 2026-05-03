# QA Scenario 12 — Hand-off review harvest (Reviews-tab attribution)

**Release validated:** v0.24.0 ([caretaker#617](https://github.com/ianlintner/caretaker/pull/617))

**Setup:** caretaker-qa pinned to `v0.24.0` (see [caretaker-qa#58](https://github.com/ianlintner/caretaker-qa/pull/58)). The Claude Code workflow (`.github/workflows/claude.yml`) is installed; `CLAUDE_CODE_OAUTH_TOKEN` secret is set. The PR opening this scenario is itself the test case — its routing score must exceed the default `40` threshold so caretaker dispatches via the `claude_code` hand-off path rather than the inline LLM path.

**Expected caretaker behavior:**
1. **Cycle 1 (dispatch).** Caretaker scores the PR ≥ 40 (sensitive paths: `.github/workflows/security-audit.yml` + `src/qa_agent/feeds/auth.py`; LOC ~360; file count > 5). The PR routes to `claude_code`. Caretaker labels the PR `claude-code` and posts a hand-off invitation comment with the new schema instructions:
   ```
   <!-- caretaker:pr-reviewer-handoff -->
   @claude caretaker is requesting a full code review for this PR.
   ...
   To have your review surface in the GitHub Reviews tab ... end your reply with the marker line `<!-- caretaker:review-result -->` followed by a fenced JSON block tagged `caretaker-review`.
   ```
2. **Upstream action runs.** `anthropics/claude-code-action@v1` picks up the `@claude` mention, performs the review, and replies in a regular issue comment that includes the response marker + a fenced `caretaker-review` JSON payload (verdict, summary, optional inline comments).
3. **Cycle 2 (harvest).** On the next caretaker run (5-min cron or webhook), `pr_reviewer.handoff_review_consumer` finds the agent's reply with the marker, parses the payload, and calls the GitHub Reviews API. A formal PR review appears under the **Reviews** tab attributed to `the-care-taker[bot]`, with inline comments anchored on the diff. The review body credits the originating agent (`@claude[bot]`).
4. **Cycle 3+ (idempotency).** The agent's reply comment ID is recorded in `TrackedPR.consumed_handoff_review_comment_ids`. Subsequent webhook deliveries / polling cycles do not re-post the formal review.

**Failure modes the scenario catches:**
- The hand-off invitation doesn't include the new schema instructions (template/code path didn't pick up v0.24.0).
- The agent reply is parsed but the formal review is posted on the wrong commit SHA (regression in head-SHA threading).
- The same agent reply is harvested twice (idempotency regression).
- The formal review only lands as an issue comment, not via the Reviews API (regression in `post_review` wiring or fallback path).
- Caretaker's own hand-off invitation gets harvested as if it were the response (`_is_caretaker_authored` regression — the `Reviews` tab would show a self-reply).

**How to verify:**
```bash
# 1. Confirm the hand-off invitation went out (Cycle 1):
gh issue view <pr-number> -R ianlintner/caretaker-qa --comments | \
  grep -A3 "caretaker:pr-reviewer-handoff"

# 2. Wait for the upstream Claude Code workflow to complete:
gh run list -R ianlintner/caretaker-qa --workflow=claude.yml --limit 5

# 3. After the next maintainer cron tick (≤ 5 min), check Reviews:
gh api /repos/ianlintner/caretaker-qa/pulls/<pr-number>/reviews \
  --jq '.[] | {user: .user.login, state, body: (.body | .[0:120])}'

# 4. Idempotency: trigger a second maintainer run manually and confirm
# no second formal review is posted:
gh workflow run maintainer.yml -R ianlintner/caretaker-qa
gh api /repos/ianlintner/caretaker-qa/pulls/<pr-number>/reviews | \
  jq 'map(select(.user.login == "the-care-taker[bot]")) | length'
# → must equal 1
```

<!-- caretaker:qa-scenario -->
<!-- scenario-12: handoff-review-harvest -->
