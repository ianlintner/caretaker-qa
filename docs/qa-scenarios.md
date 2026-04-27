# QA Scenarios

This file is a lightweight index of the `qa(scenario-NN: <slug>)` issues
filed against caretaker-qa to exercise specific caretaker behaviors.

The authoritative list lives as GitHub issues with the
`<!-- caretaker:qa-scenario -->` HTML-comment marker. Use:

```bash
gh issue list --repo ianlintner/caretaker-qa \
  --search '"<!-- caretaker:qa-scenario -->"' --state all --limit 50
```

to enumerate them. This file exists so a new contributor browsing the
repo can find the convention without first knowing the marker grep.

## Convention

| Slot | Format | Example |
|------|--------|---------|
| Issue title | `qa(scenario-NN): <one-line title>` | `qa(scenario-16): PR flow through event-bus dispatch` |
| Body marker | `<!-- caretaker:qa-scenario -->` | (machine-readable grep key) |
| Slug marker | `<!-- scenario-NN: <slug> -->` | `<!-- scenario-16: pr-flow-event-bus -->` |
| Branch (when a PR is needed) | `caretaker/qa-scenario-NN-<slug>` | `caretaker/qa-scenario-16-pr-flow-event-bus` |
| Closing label | `caretaker:qa-passed` | (set when the cycle records the scenario as passed) |

The `caretaker/*` head-ref convention is what enables caretaker's
auto-approval policy on QA-author PRs.

## Cycle skill

The full QA cycle is documented in
[`.github/skills/caretaker-qa-cycle.md`](https://github.com/ianlintner/caretaker/blob/main/.github/skills/caretaker-qa-cycle.md)
in the upstream caretaker repo.
