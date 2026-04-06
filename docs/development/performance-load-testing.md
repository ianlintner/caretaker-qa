# Performance & Load Testing

This page documents the benchmark harness in `benchmarks/`, how to run it, and how to read the latest performance results.

## What is being measured?

The harness compares OAuth2 server behavior under identical load against these targets:

- `rust` (Rust OAuth2 + PostgreSQL)
- `rust-mongo` (Rust OAuth2 + MongoDB)
- `keycloak`
- `hydra`
- `authentik`
- `node-oidc`

Primary scenarios:

- `client-credentials` — token issuance hot path
- `token-introspect` — token validation/lookup
- `discovery` — OIDC discovery endpoint
- `health` — baseline HTTP health endpoint

## Latest result snapshot

Source: `benchmarks/results/comparison-report.md` (generated `2026-04-06 01:52:27 UTC`).

### Scenario winners

| Scenario           | Winner              |  Throughput |
| ------------------ | ------------------- | ----------: |
| client-credentials | Rust OAuth2 (Mongo) | 272.5 req/s |
| token-introspect   | Rust OAuth2         | 271.6 req/s |
| discovery          | Rust OAuth2         | 539.3 req/s |
| health             | Rust OAuth2         | 539.7 req/s |

### Client-credentials highlights

| Server              | Req/s | Avg (ms) | p95 (ms) |
| ------------------- | ----: | -------: | -------: |
| Rust OAuth2         | 271.6 |     2.50 |     4.41 |
| Rust OAuth2 (Mongo) | 272.5 |     1.84 |     3.96 |
| Keycloak (Java)     | 270.3 |     2.89 |     4.79 |
| node-oidc (Node.js) | 270.4 |     2.88 |     6.98 |

> [!IMPORTANT]
> These are **relative, local-machine** results.
> Treat ordering and ratios as directional;
> do not treat absolute req/s as universally portable.

## How to run benchmarks

From repository root:

```bash
bash benchmarks/run-benchmarks.sh
```

Run a focused scenario:

```bash
bash benchmarks/run-benchmarks.sh \
  --servers rust,keycloak,hydra,authentik,node-oidc \
  --scenarios client-credentials \
  --profile light \
  --iterations 3
```

Compare Rust storage backends directly:

```bash
bash benchmarks/run-benchmarks.sh \
  --servers rust,rust-mongo \
  --scenarios client-credentials \
  --profile light \
  --iterations 3
```

Regenerate the report:

```bash
bash benchmarks/analyze-results.sh
```

## Load profiles

| Profile  | Pattern       |
| -------- | ------------- |
| `light`  | up to 50 VUs  |
| `medium` | up to 200 VUs |
| `heavy`  | up to 500 VUs |

For stable comparisons, use at least **3 iterations** per scenario.

## Benchmark outputs

Generated files in `benchmarks/results/`:

- `*_summary.json` — raw k6 summary by server/scenario/profile/iteration
- `comparison-report.md` — rendered Markdown report
- `comparison-data.csv` — flat table for spreadsheet/BI analysis
- `raw.json` — raw k6 point stream (if enabled via environment)

## Reproducibility checklist

- Keep test runs on an otherwise idle machine.
- Use the same profile/iterations across compared servers.
- Prefer running all compared servers in one pass of `run-benchmarks.sh`.
- Re-run 3–5 times for confidence before making product decisions.

## Known caveats

- Some third-party servers can report high error rates in specific scenarios
  depending on endpoint compatibility/expectations.
  Use per-scenario validation and logs before drawing conclusions.
- Rust + Mongo benchmark seeding expects RFC3339 timestamps in seeded client docs.

## Related docs

- [Testing](testing.md)
- [Production deployment checklist](../deployment/production.md)
- [Benchmark harness README](https://github.com/ianlintner/rust-oauth2-server/blob/main/benchmarks/README.md)
