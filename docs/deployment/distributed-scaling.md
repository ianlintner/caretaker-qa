# Distributed Scaling, Clustering, and Regional Shards

This guide describes the production topology for scaling the OAuth2 server beyond a single node or single cluster.

The implementation shipped in this repository now supports the following scale-out building blocks:

- **TokenActor sharding per instance** via `OAUTH2_TOKEN_ACTOR_SHARDS`
- **Redis L2 cache** behind the in-process LRU caches via `OAUTH2_CACHE_REDIS_URL`
- **Redis-backed shared rate limiting** via `OAUTH2_RATE_LIMIT_BACKEND=redis`
- **Read-replica routing** via `OAUTH2_DATABASE_READ_URL`
- **Kubernetes distributed-HA profile** via `k8s/components/distributed-ha` and `k8s/overlays/production-distributed`

## Rollout plan

Use this sequence when promoting the auth plane from a single cluster into a distributed topology:

1. **Build the distributed runtime image** with the `distributed` feature set.
1. **Deploy the distributed Kustomize profile** (Redis + PgBouncer + Postgres tuning + HA scheduling).
1. **Scale each regional shard independently** using local primaries and local read replicas.
1. **Route traffic by tenant, issuer, or geography** at the global edge.
1. **Keep writes inside a shard** and use events for cross-region analytics or async propagation.
1. **Exercise failure modes**: pod eviction, node loss, replica lag, Redis outage, and regional failover.

## Reference topology

```mermaid
graph TB
    Client[Clients / Apps] --> GSLB[Global DNS / GSLB / Anycast]

    GSLB --> USEast[Regional shard: us-east]
    GSLB --> EUWest[Regional shard: eu-west]

    subgraph USEast[Regional shard: us-east]
        USELB[Regional load balancer]
        USELB --> USEPod1[oauth2-server pod]
        USELB --> USEPod2[oauth2-server pod]
        USELB --> USEPod3[oauth2-server pod]

        USEPod1 --> USEPgBouncer[PgBouncer]
        USEPod2 --> USEPgBouncer
        USEPod3 --> USEPgBouncer

        USEPgBouncer --> USEPrimary[(Postgres primary)]
        USEPod1 --> USEReplica[(Postgres read replica)]
        USEPod2 --> USEReplica
        USEPod3 --> USEReplica

        USEPod1 --> USERedis[(Redis)]
        USEPod2 --> USERedis
        USEPod3 --> USERedis
    end

    subgraph EUWest[Regional shard: eu-west]
        EULB[Regional load balancer]
        EULB --> EUPod1[oauth2-server pod]
        EULB --> EUPod2[oauth2-server pod]
        EULB --> EUPod3[oauth2-server pod]

        EUPod1 --> EUPgBouncer[PgBouncer]
        EUPod2 --> EUPgBouncer
        EUPod3 --> EUPgBouncer

        EUPgBouncer --> EUPrimary[(Postgres primary)]
        EUPod1 --> EUReplica[(Postgres read replica)]
        EUPod2 --> EUReplica
        EUPod3 --> EUReplica

        EUPod1 --> EURedis[(Redis)]
        EUPod2 --> EURedis
        EUPod3 --> EURedis
    end

    USEPrimary -. async events / analytics .-> EUPrimary
```

## Build the distributed runtime

The default binary stays lean. For clustered deployments, build the runtime with the distributed feature bundle:

```bash
cargo build --release --features distributed
```

Docker builds can do the same with build args:

```bash
docker build \
  --build-arg CARGO_FEATURES="distributed" \
  -t rust-oauth2-server:distributed .
```

The `distributed` feature enables:

| Feature            | Purpose                                              |
| ------------------ | ---------------------------------------------------- |
| `redis-cache`      | Shared Redis L2 cache for TokenActor and ClientActor |
| `redis-rate-limit` | Cross-pod/shared request throttling                  |
| `events-redis`     | Redis Streams event transport                        |

## Pattern 1: local or single-region HA cluster

Use this when you need one highly-available control plane in a single region.

Start with:

- `k8s/overlays/production-distributed`

This profile composes:

- `k8s/components/distributed-ha`
- `k8s/components/redis`
- `k8s/components/pgbouncer`
- `k8s/components/postgres-tuning`

What it adds on top of the base deployment:

- pod disruption budget
- topology spread across hosts/zones
- safer rolling updates (`maxUnavailable: 0`)
- higher HPA floor (`minReplicas: 3`, `maxReplicas: 30`)
- token actor sharding (`OAUTH2_TOKEN_ACTOR_SHARDS=4`)
- Redis L2 cache wiring (`OAUTH2_CACHE_REDIS_URL=redis://redis:6379`)

## Pattern 2: regional shard / cell

Use this when latency, blast-radius isolation, or data residency require each region to run an autonomous auth shard.

A **shard** in this repository should be treated as a full deployment cell:

- one regional load balancer / ingress
- one writable Postgres primary
- optional local read replicas
- one Redis deployment per shard
- one OAuth2 server replica set per shard
- one session key + JWT secret set shared only inside that shard

### Recommended routing boundaries

Choose **one** primary sharding key and keep it stable:

- `tenant_id`
- issuer hostname (`auth.us.example.com`, `auth.eu.example.com`)
- customer region / residency bucket
- internal customer segment (enterprise vs self-serve)

Avoid cross-shard synchronous lookups. If a request arrives in the wrong
region, route it at the edge instead of forwarding it hop-by-hop between
shards.

### Regional override example

For each region, duplicate the distributed overlay and apply region-specific patches.

```yaml
patches:
  - target:
      kind: ConfigMap
      name: oauth2-server-config
    patch: |
      - op: add
        path: /data/OAUTH2_SERVER_PUBLIC_BASE_URL
        value: "https://auth.us.example.com"
      - op: add
        path: /data/OAUTH2_TOKEN_ACTOR_SHARDS
        value: "8"

  - target:
      kind: Secret
      name: oauth2-server-secret
    patch: |
      stringData:
        OAUTH2_DATABASE_READ_URL: "postgresql://oauth2_user:REDACTED@postgres-read:5432/oauth2"
        OAUTH2_CACHE_REDIS_URL: "redis://redis:6379"
```

Because the deployment now loads optional values from both the ConfigMap and
Secret via `envFrom`, you can inject secure per-region DSNs without editing the
base deployment.

## Pattern 3: global multi-region active/active

Use this when the product needs a worldwide control plane but you still want clear failure domains.

### Recommended model

Treat each region as an independent shard and put a global router in front:

- **Global DNS / GSLB** routes users to the correct regional issuer
- **Each shard owns its own writes**
- **Read replicas stay local to the shard**
- **Redis stays local to the shard**
- **Cross-region replication is asynchronous**, never on the request path

### Avoid these anti-patterns

- one global Postgres primary stretched across regions
- one global Redis instance shared across continents
- forwarding auth requests from one shard to another inside the service mesh
- cross-region synchronous writes during `/oauth/token` or introspection

For auth platforms, boring isolation wins. A cell-based model is easier to
reason about, easier to fail over, and much kinder to latency.

## Runtime knobs

| Variable                               | Use                                                                   |
| -------------------------------------- | --------------------------------------------------------------------- |
| `OAUTH2_DATABASE_READ_URL`             | Route read-heavy lookups to a replica                                 |
| `OAUTH2_DATABASE_MAX_CONNECTIONS`      | Size primary + replica pools per pod                                  |
| `OAUTH2_CACHE_REDIS_URL`               | Shared Redis L2 cache for hot token/client reads                      |
| `OAUTH2_TOKEN_ACTOR_SHARDS`            | Per-process token actor parallelism                                   |
| `OAUTH2_RATE_LIMIT_BACKEND=redis`      | Shared throttling across replicas                                     |
| `OAUTH2_RATE_LIMIT_REDIS_URL`          | Redis endpoint for shared rate limiting                               |
| `OAUTH2_JWT_STATELESS_VALIDATION=true` | Maximum introspection throughput with eventual revocation consistency |

## Operational checklist

Before calling a shard production-ready:

- [ ] Build the image with `--features distributed`
- [ ] Set a stable `OAUTH2_SESSION_KEY` in the secret
- [ ] Confirm JWT secret rotation policy per shard
- [ ] Configure one Postgres primary per shard
- [ ] Configure local read replica(s) if using `OAUTH2_DATABASE_READ_URL`
- [ ] Confirm Redis sizing and eviction policy per shard
- [ ] Validate HPA behavior under spike traffic
- [ ] Validate pod eviction + node drain with the PDB in place
- [ ] Measure replica lag and fail closed if it exceeds your SLA
- [ ] Verify global routing sends a tenant to exactly one shard

## Related files

- `k8s/components/distributed-ha`
- `k8s/overlays/production-distributed`
- `docs/development/performance-load-testing.md`
- `docs/getting-started/configuration.md`
