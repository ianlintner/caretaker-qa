# Caretaker setup on `caretaker-qa`

This repo is maintained by [`ianlintner/caretaker`](https://github.com/ianlintner/caretaker) pinned at `.github/maintainer/.version` (currently **v0.16.0**). The maintainer workflow runs on every PR + a daily 08:00 UTC schedule.

## Secrets

The nightly agent and the caretaker workflow both need secrets. Set them via `gh` (you'll be prompted for each value):

```bash
# LLM provider — Azure AI via LiteLLM. Matches caretaker's own config.
gh secret set AZURE_AI_API_BASE --repo ianlintner/caretaker-qa
gh secret set AZURE_AI_API_KEY  --repo ianlintner/caretaker-qa
gh secret set AZURE_API_BASE    --repo ianlintner/caretaker-qa
gh secret set AZURE_API_KEY     --repo ianlintner/caretaker-qa

# Caretaker — a fine-grained PAT that can open PRs / issues / review
# as a non-bot identity (for Copilot assignment etc.).
gh secret set COPILOT_PAT       --repo ianlintner/caretaker-qa

# Optional — an Anthropic API key unlocks the ``llm.claude_enabled: auto``
# path in caretaker's own config. Skip if you're running Azure-only.
gh secret set ANTHROPIC_API_KEY --repo ianlintner/caretaker-qa

# Optional — lets GHSA fetcher use the higher rate-limit tier.
# If unset, the fetcher uses anonymous limits.
gh secret set GHSA_TOKEN        --repo ianlintner/caretaker-qa
```

Values are encrypted at rest; you cannot read them back via `gh`. If you rotate them, re-run the `set` commands above.

## Repo variables (non-secret)

```bash
gh variable set LITELLM_MODEL --body "azure_ai/gpt-4o" --repo ianlintner/caretaker-qa
```

## OAuth2 client (MCP backend)

`roauth2.cat-herding.net` is **not required** for the caretaker maintainer workflow — that path uses the GitHub App installation token (`GITHUB_TOKEN`) plus `COPILOT_PAT`, not OAuth2.

The OAuth2 client only matters when you want this repo to talk to the caretaker MCP backend (admin dashboard, cross-run memory reads). Today, as of 2026-04-22, the server is down (postgres `Service` has zero endpoints; tracked as a cluster-ops issue separate from caretaker). When it's back, register a client with:

```bash
# Run from a machine with OAUTH2_CLIENT_ID / OAUTH2_CLIENT_SECRET set
# for an admin client, or via the roauth2 MCP server.
curl -s -X POST https://roauth2.cat-herding.net/admin/clients \
  -u "$OAUTH2_CLIENT_ID:$OAUTH2_CLIENT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
        "client_name": "caretaker-qa",
        "redirect_uris": ["https://caretaker.cat-herding.net/oauth/callback"],
        "grant_types": ["client_credentials"],
        "scope": "mcp:read mcp:write"
      }'
```

Then:

```bash
gh secret set CARETAKER_MCP_CLIENT_ID     --repo ianlintner/caretaker-qa
gh secret set CARETAKER_MCP_CLIENT_SECRET --repo ianlintner/caretaker-qa
```

## Verifying

After setting secrets:

```bash
# Confirm secrets landed (values obscured).
gh secret list --repo ianlintner/caretaker-qa

# Trigger a run to smoke-test the chain.
gh workflow run maintainer.yml --repo ianlintner/caretaker-qa
gh run watch --repo ianlintner/caretaker-qa
```

The first job (`dispatch-guard`) should pass in < 10 s. The `maintain` job runs `caretaker doctor --bootstrap-check` first; if any required secret is missing it fails with an actionable row.

## What caretaker does on this repo

- **Triage** — closes empty PRs, dedupes duplicate security/upgrade PRs, cascades PR merges to linked issues.
- **Self-heal** — the Wave A3 deterministic-first fix ladder runs ruff-format, ruff-check --fix, mypy install-types, pip-compile upgrade, pytest --lf on CI failures before escalating to an LLM patch.
- **Guardrails** — every external input (issue body, PR review comment, webhook payload) passes through `sanitize_input`; every outbound GitHub write passes through `filter_output`.
- **Attribution telemetry** — every PR / issue carries `caretaker_touched` / `caretaker_merged` / `operator_intervened` booleans. Read them from the admin endpoint.
- **Shadow decisions** — readiness, CI triage, issue triage, and dispatch-guard run under `@shadow_decision` with `mode: shadow`. Disagreements are persisted as `:ShadowDecision` nodes; the caretaker enforce-gate CI gates `shadow → enforce` flips.

## Rollback

If caretaker misbehaves, disable the workflow:

```bash
gh workflow disable maintainer.yml --repo ianlintner/caretaker-qa
```

Re-enable when the fix lands:

```bash
gh workflow enable maintainer.yml --repo ianlintner/caretaker-qa
```
