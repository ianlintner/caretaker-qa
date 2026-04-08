# OAuth2 Server Load Test Comparison

Compares the performance of **rust-oauth2-server** against the top 4 open-source
OAuth2 servers using [k6](https://k6.io) load testing.

## Servers Tested

| Server                 | Language | Image                                  |
| ---------------------- | -------- | -------------------------------------- |
| rust-oauth2-server     | **Rust** | Built from this repo                   |
| Keycloak 24.0          | Java     | `quay.io/keycloak/keycloak:24.0`       |
| Ory Hydra 2.2          | Go       | `oryd/hydra:v2.2`                      |
| Authentik 2024.2       | Python   | `ghcr.io/goauthentik/server:2024.2`    |
| node-oidc-provider 8.x | Node.js  | Custom (built from `setup/node-oidc/`) |

## Prerequisites

- Docker with Compose v2
- ~4GB free RAM (servers are resource-limited)
- ~10GB free disk (Docker images)
- `jq` for result analysis (`brew install jq`)

## Quick Start

```bash
# Run all benchmarks with light load
./run-benchmarks.sh

# Run specific servers with medium load
./run-benchmarks.sh --servers rust,hydra --profile medium

# Run only the client-credentials test with heavy load
./run-benchmarks.sh --scenarios client-credentials --profile heavy --iterations 5

# Analyze results
./analyze-results.sh
```

## GitHub Actions weekly benchmark run

The repository now includes a scheduled GitHub Actions workflow for overnight benchmark runs.

- **Schedule:** every Monday at **03:17 UTC**
- **Auto-selection window:** looks at commits merged to `main` in the last 7 days
- **First-party servers:** reruns `rust` and `rust-mongo` when first-party
  runtime/build inputs or benchmark harness files change
- **Third-party servers:** reruns `keycloak`, `hydra`, `authentik`, and
  `node-oidc` **only** when their pinned benchmark versions change
- **Version bump follow-up:** when a third-party version changes, the workflow
  also opens a GitHub issue assigned to `copilot` so the checked-in benchmark
  baselines and docs can be reconciled
- **Manual partial runs:** `workflow_dispatch` supports selecting a
  comma-separated server list plus scenarios, profile, iterations, and a
  `force` flag

### Manual run button

You can trigger the workflow manually from GitHub:

1. Open **Actions**
2. Select **Weekly Benchmarks**
3. Click **Run workflow**
4. Optionally choose servers, scenarios, profile, iterations, or `force`

If you provide a server list, the workflow runs exactly those servers.

### How partial CI runs work

For unchanged servers, the workflow reuses the checked-in baseline files already
present in `benchmarks/results/` and overwrites only the selected
server/profile outputs before generating the report artifact.

That keeps weekly runs shorter while still producing a merged comparison artifact.

### Uploaded artifacts

Every benchmark execution uploads a GitHub Actions artifact named
`benchmark-results-<run_number>`.

The artifact includes any generated benchmark JSON, CSV, Markdown reports, and
the CI manifest file from `benchmarks/results/`. The upload step runs even if
the benchmark job fails, so partial results are still available for debugging.

### CI limitations

- GitHub-hosted runners are fine for **directional trend checks**, but they are
  not a substitute for a dedicated, quiet benchmark machine
- Scheduled workflows are **best-effort** and can start late
- If you need a fully refreshed cross-server comparison after a
  benchmark-harness change, trigger the workflow manually with all servers
  selected

## Test Scenarios

| Scenario             | Endpoint                                | What It Tests                               |
| -------------------- | --------------------------------------- | ------------------------------------------- |
| `client-credentials` | `POST /oauth/token`                     | JWT signing, client auth, token persistence |
| `token-introspect`   | `POST /oauth/introspect`                | Token validation, DB lookup                 |
| `discovery`          | `GET /.well-known/openid-configuration` | JSON serialization, HTTP response           |
| `health`             | `GET /health`                           | Baseline HTTP performance                   |

## Load Profiles

| Profile  | Virtual Users | Duration |
| -------- | ------------: | -------- |
| `light`  |       10 → 50 | ~70s     |
| `medium` |      50 → 200 | ~90s     |
| `heavy`  |     100 → 500 | ~130s    |

## Fair Comparison Controls

- **Identical resource limits**: 2 CPU cores, 512MB RAM per server
- **Same database**: PostgreSQL 16 (separate databases, same instance)
- **Same network**: Docker bridge network (no network variance)
- **Sequential testing**: Only one server runs at a time
- **Multiple iterations**: Each test runs 3 times; results are averaged
- **JVM warmup**: Java servers get warmup requests before measurement
- **Same client**: Identical OAuth2 client configuration across all servers

## Output

Results are saved to `results/`:

- `{server}_{scenario}_{profile}_{iteration}_summary.json` — k6 summary per run
- `comparison-report.md` — polished Markdown report with executive summary,
  visual bar charts, and Mermaid throughput-share graphs
- `comparison-data.csv` — CSV for further analysis

## Architecture

```text
┌─────────────┐     ┌──────────────────────┐
│   k6 load   │────▶│  OAuth2 Server       │
│   generator  │     │  (one at a time)     │
└─────────────┘     └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  PostgreSQL 16       │
                    │  (shared instance)   │
                    └─────────────────────┘
```
