# OAuth2 Server Load Test Comparison Plan

## Objective

Compare the performance of our Rust OAuth2 server against the top 4 open-source OAuth2 servers to demonstrate the benefits of Rust for OAuth2 workloads.

## Servers Under Test

| Server                 | Language      | Version     | Why Chosen                                |
| ---------------------- | ------------- | ----------- | ----------------------------------------- |
| **rust-oauth2-server** | Rust          | (this repo) | Our server                                |
| **Keycloak**           | Java          | 24.0        | Industry standard, most widely deployed   |
| **Ory Hydra**          | Go            | 2.2         | Performance-focused, purpose-built OAuth2 |
| **Authentik**          | Python/Django | 2024.2      | Popular Python-based alternative          |
| **node-oidc-provider** | Node.js       | 8.x         | Leading Node.js OIDC implementation       |

### Language Diversity

Rust vs Java vs Go vs Python vs Node.js — covers the most common server-side languages.

## Load Testing Framework: k6

**Why k6:**

- Written in Go, extremely efficient load generator
- JavaScript-based test scripts (easy to write/maintain)
- Built-in metrics, thresholds, and reporting
- Supports HTTP/2, TLS, and custom protocols
- Outputs structured JSON for analysis
- Runs in containers (consistent results)
- No JVM warmup artifacts in the test tool itself

## Test Scenarios

### Primary Test: Client Credentials Grant (`/oauth/token`)

The **client_credentials** grant is the ideal apples-to-apples comparison because:

- No browser interaction required
- Pure server-side performance (CPU, memory, I/O)
- Single HTTP POST request per token
- All servers implement this identically per RFC 6749
- Tests JWT signing, client authentication, and token storage

### Secondary Tests:

1. **Token Introspection** (`/oauth/introspect`) — validate a previously issued token
2. **Discovery Endpoint** (`/.well-known/openid-configuration`) — cold/warm cache performance
3. **Health Check** (`/health` or equivalent) — baseline HTTP performance

### Test Phases:

1. **Warmup**: 30s ramp-up to baseline VUs
2. **Steady State**: 60s at target load
3. **Ramp Up**: 30s ramp to peak load
4. **Peak**: 60s at peak load
5. **Cooldown**: 30s ramp-down

### Load Profiles:

- **Light**: 10 → 50 VUs
- **Medium**: 50 → 200 VUs
- **Heavy**: 200 → 500 VUs

## Apples-to-Apples Controls

### Infrastructure Controls:

- All servers run in Docker containers with **identical resource limits** (2 CPU, 512MB RAM)
- All use **PostgreSQL 16** as the backend database (same instance, separate databases)
- All run on the **same Docker network** (no network variance)
- k6 runs in its own container on the same network
- Each server is tested **independently** (others stopped during test)

### Test Controls:

- Same pre-registered OAuth2 client (client_id/client_secret)
- Same requested scopes
- Same TLS configuration (disabled — test HTTP only for pure compute comparison)
- JVM-based servers get a **warmup period** before measurement begins
- Each test run is repeated **3 times** and results are averaged
- 30-second pause between test runs for GC/cleanup

### Metrics Captured:

- **Requests/second** (throughput)
- **p50, p95, p99 latency** (response time distribution)
- **Error rate** (%)
- **Memory usage** (container stats)
- **CPU usage** (container stats)

## Directory Structure

```
benchmarks/
├── PLAN.md                          # This file
├── docker-compose.yml               # All servers + PostgreSQL + k6
├── run-benchmarks.sh                # Main orchestration script
├── analyze-results.sh               # Results analysis & comparison
├── k6/
│   ├── scenarios/
│   │   ├── client-credentials.js    # Primary test
│   │   ├── token-introspect.js      # Introspection test
│   │   ├── discovery.js             # Discovery endpoint test
│   │   └── health.js                # Baseline HTTP test
│   └── lib/
│       └── helpers.js               # Shared utilities
├── setup/
│   ├── keycloak/
│   │   └── realm-export.json        # Pre-configured realm
│   ├── hydra/
│   │   └── hydra.yml                # Hydra configuration
│   ├── node-oidc/
│   │   ├── Dockerfile               # Custom node-oidc-provider server
│   │   ├── package.json
│   │   └── server.js
│   └── init-db.sql                  # Create separate databases
└── results/                         # Output directory (gitignored)
```

## Execution Flow

1. `docker compose up -d postgres` — Start shared PostgreSQL
2. Initialize databases via `init-db.sql`
3. For each server:
   a. Start the server container
   b. Wait for health check
   c. Run setup (register client, etc.)
   d. Run warmup phase
   e. Execute k6 test suite (3 iterations)
   f. Collect container resource metrics
   g. Stop the server container
4. Aggregate results and generate comparison report

## Expected Output

- JSON results per server per test
- Summary table comparing all servers
- CSV export for further analysis
