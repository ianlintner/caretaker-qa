#!/usr/bin/env bash
#
# Interactive setup for caretaker-qa secrets + variables.
#
# Idempotent: `gh secret set` overwrites existing values. Skip any prompt
# with Ctrl-D to leave the current value in place.

set -euo pipefail

REPO="ianlintner/caretaker-qa"

echo "Setting up secrets on ${REPO}. You'll be prompted for each value."
echo "Press Ctrl-D to skip a secret and leave it as-is."
echo

set_secret() {
  local name="$1" description="$2"
  echo "=== ${name} ==="
  echo "${description}"
  if read -rs -p "Value (input hidden): " value && [[ -n "${value}" ]]; then
    echo
    printf '%s' "${value}" | gh secret set "${name}" --repo "${REPO}"
    echo "  -> set"
  else
    echo
    echo "  -> skipped"
  fi
  echo
}

set_variable() {
  local name="$1" value="$2"
  gh variable set "${name}" --body "${value}" --repo "${REPO}"
  echo "variable ${name} -> ${value}"
}

# Required.
set_secret AZURE_AI_API_BASE "Azure AI Foundry endpoint URL (ends with /openai/v1)"
set_secret AZURE_AI_API_KEY  "Azure AI Foundry API key"
set_secret AZURE_API_BASE    "Azure OpenAI endpoint URL (same account, non-Foundry)"
set_secret AZURE_API_KEY     "Azure OpenAI API key"
set_secret COPILOT_PAT       "GitHub fine-grained PAT for non-bot author actions"

# Optional — skip with Ctrl-D if you don't have it.
set_secret ANTHROPIC_API_KEY "Anthropic API key (optional; unlocks claude_enabled: auto)"
set_secret GHSA_TOKEN        "GitHub token with read:public_advisories scope (optional; higher rate limit)"

# Optional — only if roauth2.cat-herding.net is healthy.
set_secret CARETAKER_MCP_CLIENT_ID     "OAuth2 client_id for caretaker MCP backend (optional)"
set_secret CARETAKER_MCP_CLIENT_SECRET "OAuth2 client_secret for caretaker MCP backend (optional)"

# Non-secret repo variables.
set_variable LITELLM_MODEL "azure_ai/gpt-4o"

echo "Done. Verify with:  gh secret list --repo ${REPO}"
echo "Trigger a dry-run:  gh workflow run maintainer.yml --repo ${REPO}"
