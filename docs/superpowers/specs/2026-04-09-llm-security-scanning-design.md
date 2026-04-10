# LLM-Driven Adaptive Security Scanning Framework

**Date:** 2026-04-09
**Status:** Approved
**Scope:** Comprehensive security scanning of the OAuth2 server running in KinD, with LLM-generated synthetic data, matrix-based config testing, and adaptive feedback loops.

---

## 1. Overview

An agent-driven security scanning system that:

1. Deploys the OAuth2 server to KinD under multiple security configurations
2. Uses an LLM (Claude) to generate synthetic test data and attack scenarios per config
3. Runs application, infrastructure, and runtime security scanners in parallel
4. Feeds findings back to the LLM for hypothesis generation and targeted follow-up tests
5. Produces a prioritized security report with evidence and remediation suggestions

### Design Principles

- **Agent-driven with modularity**: LLM orchestrates the loop, but each phase produces versioned artifacts (YAML/JSON) for reproducibility
- **Matrix-based**: multiple server configs tested in parallel conceptually, deployed sequentially to conserve resources
- **Feedback loop on security findings only**: non-security failures are logged but don't trigger LLM analysis
- **Budget-bounded**: max follow-up rounds and wall-clock limits prevent runaway costs

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  LLM Orchestrator (Claude API Agent)                        │
│  - Coordinates all phases                                   │
│  - Generates test scenarios & follow-up tests               │
│  - Analyzes findings & patterns                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
    ┌────────────┐   ┌────────────┐   ┌─────────────┐
    │ Config Gen │   │  K8s Mgr   │   │  Scanners   │
    │ (LLM input)│   │ (Deploy)   │   │ (Parallel)  │
    └────────────┘   └────────────┘   └─────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────▼───────┐
                    │ Results DB   │
                    │ (Findings,   │
                    │  Artifacts)  │
                    └──────────────┘
```

### Components

- **LLM Orchestrator**: Claude Agent (via API or Claude Code) running the full loop
- **Config Generator**: Produces kustomize overlays and server env configs, guided by LLM
- **K8s Manager**: Deploy/tear down configs to KinD, health checks, readiness gates
- **Scanners**: Pluggable security test runners (containerized where possible)
- **Results DB**: JSON files on disk, organized by config and timestamp

---

## 3. Config Matrix

Each config is a full server deployment with a distinct security posture.

| Config           | JWT Secret       | CORS                  | Admin Auth                 | DB       | Purpose                          |
| ---------------- | ---------------- | --------------------- | -------------------------- | -------- | -------------------------------- |
| `prod-hardened`  | 64-char random   | explicit origins only | required                   | Postgres | Baseline secure config           |
| `dev-relaxed`    | short ("dev123") | permissive            | disabled                   | SQLite   | Catch relaxed-mode failures      |
| `misconfig-cors` | strong           | wildcard `*`          | required                   | Postgres | Validate CORS enforcement        |
| `misconfig-auth` | strong           | strict                | username-bypass re-enabled | SQLite   | Validate admin guard regressions |
| `edge-empty`     | empty string     | no origins set        | required                   | Postgres | Startup validation / fail-closed |

Each config maps to a kustomize overlay under `tests/security-scan/configs/<config-name>/`.

---

## 4. LLM-Generated Synthetic Data

For each config, Claude generates test data as JSON fixtures:

```
tests/security-scan/scenarios/<config-name>/
  users.json          # synthetic users (admin, normal, attacker personas)
  clients.json        # OAuth2 client registrations (valid, expired, malicious redirect_uris)
  flows.json          # ordered request sequences (auth code flow, implicit, PKCE)
  attacks.json        # attack payloads (SQLi, XSS in redirect_uri, CSRF tokens)
  timing_probes.json  # requests designed to detect timing leaks
```

### Scenario Types

- **Realistic user flows**: login, consent, token refresh, session management
- **Attack scenarios**: injection, open redirect, CSRF, privilege escalation
- **Edge cases**: malformed requests, boundary conditions, encoding tricks

### Example Attack Scenario

```json
{
  "id": "open-redirect-via-return_to",
  "config_target": ["dev-relaxed", "misconfig-auth"],
  "description": "Attempt open redirect through return_to parameter",
  "requests": [
    {
      "method": "GET",
      "path": "/auth/login",
      "query": { "return_to": "https://evil.com/steal" }
    },
    {
      "method": "GET",
      "path": "/auth/login",
      "query": { "return_to": "//evil.com" }
    },
    {
      "method": "GET",
      "path": "/auth/login",
      "query": { "return_to": "javascript:alert(1)" }
    }
  ],
  "expected": "all should redirect to / or reject, never follow attacker URL",
  "severity_if_fail": "high"
}
```

---

## 5. Scanner Suite

Three categories run in parallel against each deployed config.

### 5a. Application Security Scanners

| Scanner              | What it does                                               | Implementation                                            |
| -------------------- | ---------------------------------------------------------- | --------------------------------------------------------- |
| OWASP ZAP            | Automated web vuln scan (XSS, SQLi, CSRF, headers)         | ZAP Docker image, runs in KinD as a Job                   |
| OAuth2 Flow Tester   | Exercises all grant types with valid + malicious inputs    | Script using LLM-generated `flows.json` + `attacks.json`  |
| Redirect Validator   | Tests `return_to` and `redirect_uri` against allowlists    | Replays `attacks.json` open-redirect scenarios            |
| Auth Boundary Tester | Hits admin endpoints as unauthenticated/normal/admin users | Tests `AdminGuard` 302 behavior, client registration auth |

### 5b. Infrastructure Scanners

| Scanner                  | What it does                                            | Implementation                         |
| ------------------------ | ------------------------------------------------------- | -------------------------------------- |
| kubeaudit                | K8s security audit (capabilities, seccomp, run-as-root) | Runs against deployed manifests        |
| kube-bench               | CIS Kubernetes Benchmark checks                         | Runs as Job in KinD                    |
| Network Policy Validator | Verifies pod-to-pod isolation                           | Attempts cross-namespace calls         |
| Secret Exposure Check    | Ensures secrets aren't in env vars, logs, or responses  | Grep manifests + check response bodies |

### 5c. Runtime Behavior Scanners

| Scanner                  | What it does                                                       | Implementation                                     |
| ------------------------ | ------------------------------------------------------------------ | -------------------------------------------------- |
| Timing Analyzer          | Measures response times to detect timing leaks                     | Replays `timing_probes.json`, statistical analysis |
| Error Leakage Detector   | Checks error responses for stack traces, DB schema, internal paths | Sends malformed requests, inspects responses       |
| Token Entropy Validator  | Verifies tokens/codes have sufficient randomness                   | Collects N tokens, runs entropy + uniqueness tests |
| Observability Leak Check | Ensures metrics/logs don't expose PII or secrets                   | Scrapes `/metrics`, checks pod log output          |

### Unified Finding Format

All scanners output findings in a common JSON format:

```json
{
  "scanner": "timing-analyzer",
  "config": "prod-hardened",
  "timestamp": "2026-04-09T12:00:00Z",
  "findings": [
    {
      "id": "TIMING-001",
      "severity": "medium",
      "category": "runtime",
      "title": "Password comparison timing variance > 5ms across inputs",
      "evidence": {
        "endpoint": "/auth/login",
        "measurements": [
          { "input": "valid_user", "avg_ms": 42 },
          { "input": "invalid_user", "avg_ms": 37 }
        ],
        "variance_ms": 5.2
      },
      "reproducible": null,
      "follow_up_suggested": true
    }
  ]
}
```

---

## 6. LLM Feedback Loop

### Trigger Criteria

The LLM engages for security-relevant findings only:

- Any finding with `severity >= medium`
- Timing variance with statistical significance (p-value < 0.05)
- Response bodies containing stack traces, SQL fragments, internal paths
- Cross-config inconsistencies (passes on one config, fails on another)

### Analysis Flow

1. Claude receives all findings across all configs
2. For each security finding, Claude produces a **hypothesis document**:

```yaml
hypothesis:
  id: "HYPO-2026-04-09-001"
  finding_refs: ["TIMING-001"]
  statement: "Password comparison uses early-return on invalid username, leaking user existence via timing"
  confidence: medium

follow_up_tests:
  - id: "FU-001"
    description: "Repeat timing test with 100 samples per input category"
    requests:
      - {
          method: POST,
          path: "/auth/login",
          body: { username: "known_valid", password: "wrong" },
          repeat: 100,
        }
      - {
          method: POST,
          path: "/auth/login",
          body: { username: "definitely_nonexistent", password: "wrong" },
          repeat: 100,
        }
    analysis: "Compare mean response times with Welch's t-test, p < 0.01 confirms leak"
```

3. Follow-up tests run against the **same still-running KinD instance**
4. Claude renders a **verdict**:

```yaml
verdict:
  hypothesis_id: "HYPO-2026-04-09-001"
  status: confirmed # confirmed | refuted | inconclusive
  evidence_summary: "FU-001 shows 4.8ms mean difference (p=0.003)."
  conclusion: "Timing leak isolated to /auth/login password path."
  severity: high
  remediation: "Ensure username lookup is constant-time."
```

### Loop Termination

- All hypotheses resolved (confirmed or refuted, no inconclusive remaining)
- Max 3 follow-up rounds per finding
- Total scan budget exceeded (configurable wall-clock or API cost limit)

---

## 7. Orchestration

### CLI Entrypoint

```bash
# Full matrix scan with feedback loop
./scripts/security-scan.sh --matrix all --feedback-loops 3 --budget 30m

# Single config for quick iteration
./scripts/security-scan.sh --config prod-hardened --feedback-loops 1

# Regenerate test data only (no scan)
./scripts/security-scan.sh --generate-only --config dev-relaxed
```

### Execution Flow

```
1. Pre-flight checks
   ├── KinD cluster exists or create
   ├── Docker images built (oauth2-server:test, scanner images)
   └── Claude API key available

2. For each config in matrix (sequential deployment):
   ├── LLM: generate scenarios/<config>/ (if not cached)
   ├── Deploy config to KinD via kustomize overlay
   ├── Wait for readiness (health check)
   ├── Seed database with synthetic data
   ├── Run all scanners in parallel
   ├── Collect findings → results/<config>/<timestamp>/
   ├── Tear down config
   └── Next config

3. LLM analysis phase
   ├── Feed all findings across all configs to Claude
   ├── For each hypothesis with follow_up_tests:
   │   ├── Re-deploy relevant config
   │   ├── Run follow-up tests
   │   ├── Collect evidence
   │   └── LLM renders verdict
   └── Loop until termination criteria met

4. Report generation
   └── LLM produces final report
```

---

## 8. Report Output

```
reports/
  2026-04-09-security-scan/
    summary.md              # Human-readable executive summary
    findings.json           # Machine-readable, all findings with evidence
    configs-tested.yaml     # What configs were deployed
    hypotheses.yaml         # All hypotheses + verdicts
    remediation.md          # Prioritized fix suggestions with code examples
    raw/                    # Raw scanner output per config
```

Reports directory is gitignored. Generated scenarios are committed to `tests/security-scan/scenarios/` for reproducibility.

---

## 9. File Structure

```
tests/security-scan/
  configs/
    prod-hardened/          # kustomize overlay + env
    dev-relaxed/
    misconfig-cors/
    misconfig-auth/
    edge-empty/
  scenarios/                # LLM-generated, committed to git
    prod-hardened/
      users.json
      clients.json
      flows.json
      attacks.json
      timing_probes.json
    dev-relaxed/
      ...
  scanners/
    zap/                    # ZAP config + K8s Job manifest
    flow-tester/            # OAuth2 flow test script
    timing-analyzer/        # Timing analysis script
    kubeaudit/              # kubeaudit config
    ...
  scripts/
    security-scan.sh        # Main entrypoint
    deploy-config.sh        # Deploy a single config to KinD
    run-scanners.sh         # Run all scanners against current deployment
    seed-data.sh            # Seed database from scenario JSON
    llm-analyze.sh          # Call Claude API for analysis
reports/                    # gitignored
  ...
```

---

## 10. Dependencies

- **KinD**: local K8s cluster
- **kustomize**: config overlay management (already in use)
- **OWASP ZAP**: Docker image `ghcr.io/zaproxy/zaproxy`
- **kubeaudit**: `ghcr.io/shopify/kubeaudit`
- **kube-bench**: `docker.io/aquasec/kube-bench`
- **Claude API**: for scenario generation, analysis, and follow-up test generation
- **jq / yq**: JSON/YAML processing in scripts
- **Python 3**: required for statistical analysis in timing scanner (Welch's t-test, entropy checks)

---

## 11. Future Extensions

- CI integration: run reduced matrix on every PR, full matrix nightly
- Historical trend tracking: compare findings across scan runs over time
- Custom scanner plugins: add project-specific checks as the codebase evolves
- Multi-LLM comparison: run analysis with multiple models, compare findings
