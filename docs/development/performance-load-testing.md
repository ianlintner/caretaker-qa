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

---

## Scaling to 100K req/min

This section documents the configuration and architecture changes for handling
100,000 requests per minute (~1,667 req/s sustained) with spike traffic.

### Current baseline

| Metric                            | Value                                |
| --------------------------------- | ------------------------------------ |
| Throughput per instance           | ~272 req/s (~16.3K req/min)          |
| client-credentials avg latency    | 2.50 ms (p95: 4.41 ms, p99: 9.25 ms) |
| token introspection avg latency   | 2.18 ms (p95: 5.84 ms)               |
| DB queries per client-credentials | 2 (1 client lookup + 1 token save)   |
| Error rate                        | 0% at measured load                  |

### How many instances?

| Utilization target   | Instances needed | Notes                           |
| -------------------- | ---------------- | ------------------------------- |
| 100% (theoretical)   | ~7               | 1,667 ÷ 272, no headroom        |
| 60% (recommended)    | 10–12            | Leaves room for GC, spikes      |
| With Phase 2 caching | 4–7              | Cached reads reduce DB pressure |

### Environment variables

All pool and scaling settings are configurable at runtime via env vars:

| Variable                               | Default     | Description                                                                                                                   |
| -------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `OAUTH2_DATABASE_MAX_CONNECTIONS`      | `50`        | Max DB pool connections per instance                                                                                          |
| `OAUTH2_DATABASE_MIN_CONNECTIONS`      | `1`         | Min idle pool connections                                                                                                     |
| `OAUTH2_DATABASE_ACQUIRE_TIMEOUT_SECS` | `30`        | Timeout waiting for a connection                                                                                              |
| `OAUTH2_DATABASE_IDLE_TIMEOUT_SECS`    | `600`       | Idle connection lifetime                                                                                                      |
| `OAUTH2_SESSION_KEY`                   | _(random)_  | **Set in production** — hex string, 128 chars (`openssl rand -hex 64`). Without a fixed value, sessions reset on pod restart. |
| `OAUTH2_RATE_LIMIT_ENABLED`            | `false`     | Enable rate limiting                                                                                                          |
| `OAUTH2_RATE_LIMIT_BACKEND`            | `in_memory` | `in_memory` or `redis`                                                                                                        |
| `OAUTH2_RATE_LIMIT_REDIS_URL`          | _(none)_    | Redis URL for shared rate limiting                                                                                            |
| `OAUTH2_RATE_LIMIT_MAX_REQUESTS`       | `100`       | Requests per window                                                                                                           |
| `OAUTH2_RATE_LIMIT_WINDOW_SECS`        | `60`        | Rate limit window                                                                                                             |

### In-process caching

Two LRU caches reduce DB pressure on the hottest read paths:

| Cache            | Max entries | TTL   | Invalidation                |
| ---------------- | ----------- | ----- | --------------------------- |
| Token validation | 10,000      | 60 s  | Evicted on `RevokeToken`    |
| Client lookup    | 10,000      | 5 min | Evicted on LRU + TTL expiry |

These caches are per-instance. At 10 instances with 10K entries each,
worst-case memory overhead is ~100K entries × ~1 KB ≈ 100 MB total.

### Actor mailbox sizing

All three singleton actors (Token, Client, Auth) have a mailbox capacity
of **256 messages** (up from the Actix default of 16). This prevents
backpressure at the HTTP layer when bursts of requests arrive faster
than the actor can process them.

### HTTP server timeouts

| Setting                     | Value | Purpose                               |
| --------------------------- | ----- | ------------------------------------- |
| `keep_alive`                | 75 s  | Matches typical LB idle timeout       |
| `client_request_timeout`    | 30 s  | Caps header wait time                 |
| `client_disconnect_timeout` | 5 s   | Quick cleanup of dropped connections  |
| `backlog`                   | 2,048 | TCP listen queue for spike absorption |

### Kubernetes components

Three optional Kustomize components are available under `k8s/components/`:

#### Redis (distributed rate limiting)

Enables shared rate limiting across all instances instead of per-process
in-memory counters.

```bash
# Add to your kustomization.yaml:
components:
  - ../../components/redis
```

#### PgBouncer (connection pooling)

Interposes a PgBouncer proxy between the app and PostgreSQL, using
transaction-level pooling with a default pool of 25 server connections.

```bash
components:
  - ../../components/pgbouncer
```

#### PostgreSQL tuning

Applies production-oriented settings: `max_connections=300`,
`shared_buffers=1GB`, `work_mem=8MB`, `effective_cache_size=3GB`.

```bash
components:
  - ../../components/postgres-tuning
```

### Production checklist

1. **Set `OAUTH2_SESSION_KEY`** to a stable hex value in the K8s secret
2. **Set `OAUTH2_DATABASE_MAX_CONNECTIONS=50`** (already default, confirm in ConfigMap)
3. **Enable PgBouncer** component if running >4 instances
4. **Enable Redis rate limiter** component for multi-instance consistency
5. **Apply PostgreSQL tuning** component and size the Pod to ≥2 GB RAM
6. **Set HPA** `maxReplicas` to 15–20 (currently 20)
7. **Pre-scale** `minReplicas` to 4–5 if spikes are predictable

- `raw.json` — raw k6 point stream (if enabled via environment)

### Phase 3 — Architecture changes

These higher-effort changes further reduce latency and improve resilience
at scale.

#### Redis L2 cache (feature flag)

Behind the `redis-cache` feature flag the TokenActor writes validated
tokens to Redis after an L1 LRU miss. On subsequent requests the lookup
order is L1 → L2 (Redis) → DB, cutting database reads dramatically:

```bash
# Enable at build time
cargo build --features redis-cache

# Point at your Redis instance
OAUTH2_REDIS_URL=redis://redis:6379
```

Keys are stored as `token:{hash}` with the same 60 s TTL used by the
in-process L1 cache. Revocations delete from both L1 and L2.

#### Read-replica routing

When `DATABASE_READ_URL` is set, `SqlxStorage` maintains a second
connection pool for read-only queries. Eight read methods
(`find_token`, `get_client`, `find_auth_code`, etc.) are routed to
the replica while writes continue against the primary:

| Variable            | Default  | Description                            |
| ------------------- | -------- | -------------------------------------- |
| `DATABASE_READ_URL` | _(none)_ | Connection string for the read replica |

Pool sizing (`max_connections`, `min_connections`, timeouts) is shared
between primary and replica pools.

#### TokenActor sharding

A `TokenActorPool` distributes token operations across multiple actor
instances. Each message is routed to a deterministic shard via a hash
of the relevant key (`client_id` for creation, token value for
validation/revocation):

| Variable                    | Default | Description                    |
| --------------------------- | ------- | ------------------------------ |
| `OAUTH2_TOKEN_ACTOR_SHARDS` | `4`     | Number of TokenActor instances |

Increasing the shard count reduces contention on the per-actor LRU
cache lock and distributes mailbox pressure.

#### Circuit breaker for social login

Each external identity provider (Google, Microsoft, GitHub) is
protected by a lightweight circuit breaker. When consecutive failures
exceed the threshold the breaker opens and rejects requests immediately
until the cooldown elapses:

| Parameter         | Value                             |
| ----------------- | --------------------------------- |
| Failure threshold | 5                                 |
| Cooldown          | 30 s                              |
| States            | Closed → Open → HalfOpen → Closed |

A shared `reqwest::Client` with a 10 s timeout is reused across all
provider calls, eliminating per-request TLS handshake overhead.

#### JWT-only stateless validation

When `OAUTH2_JWT_STATELESS_VALIDATION=true`, the token introspection
endpoint validates access tokens by decoding the JWT signature and
reading claims directly — no database or cache lookup is required:

| Variable                          | Default | Description                    |
| --------------------------------- | ------- | ------------------------------ |
| `OAUTH2_JWT_STATELESS_VALIDATION` | `false` | Enable stateless introspection |

This mode is ideal when revocation latency (up to TTL of the token)
is acceptable and maximum throughput is required. Revoked tokens will
remain valid until they expire naturally.

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
