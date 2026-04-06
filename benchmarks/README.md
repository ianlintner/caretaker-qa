# OAuth2 Server Load Test Comparison

Compares the performance of **rust-oauth2-server** against the top 4 open-source OAuth2 servers using [k6](https://k6.io) load testing.

## Servers Tested

| Server | Language | Image |
|--------|----------|-------|
| rust-oauth2-server | **Rust** | Built from this repo |
| Keycloak 24.0 | Java | `quay.io/keycloak/keycloak:24.0` |
| Ory Hydra 2.2 | Go | `oryd/hydra:v2.2` |
| Authentik 2024.2 | Python | `ghcr.io/goauthentik/server:2024.2` |
| node-oidc-provider 8.x | Node.js | Custom (built from `setup/node-oidc/`) |

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

## Test Scenarios

| Scenario | Endpoint | What It Tests |
|----------|----------|---------------|
| `client-credentials` | `POST /oauth/token` | JWT signing, client auth, token persistence |
| `token-introspect` | `POST /oauth/introspect` | Token validation, DB lookup |
| `discovery` | `GET /.well-known/openid-configuration` | JSON serialization, HTTP response |
| `health` | `GET /health` | Baseline HTTP performance |

## Load Profiles

| Profile | Virtual Users | Duration |
|---------|-------------:|----------|
| `light` | 10 → 50 | ~70s |
| `medium` | 50 → 200 | ~90s |
| `heavy` | 100 → 500 | ~130s |

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
- `comparison-report.md` — polished Markdown report with executive summary, visual bar charts, and Mermaid throughput-share graphs
- `comparison-data.csv` — CSV for further analysis

## Architecture

```
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
