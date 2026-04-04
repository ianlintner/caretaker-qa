# Wave 3 Security Features — Design Spec

**Date**: 2026-04-03
**Status**: Approved
**Scope**: Rate limiting, JWT key rotation, cleanup items

## Overview

Wave 3 adds two major security features — rate limiting and JWT key rotation — plus two cleanup items carried from prior waves. These fill the two biggest remaining gaps in production readiness identified in TODO.md and SECURITY.md.

## 1. Rate Limiting

### Algorithm

Token bucket. Each IP address gets a bucket of `max_requests` tokens. Tokens refill at a constant rate of `max_requests / window_secs` per second. A request consumes one token. When the bucket is empty, the request is rejected with `429 Too Many Requests`.

Token bucket naturally allows short bursts (page loads trigger multiple requests) while enforcing sustained rate limits.

### Architecture

**New crate: `oauth2-ratelimit`** (added to workspace `Cargo.toml`)

```
oauth2-ratelimit/
  Cargo.toml          # deps: dashmap, tokio, redis (optional feature)
  src/
    lib.rs            # RateLimiter trait, RateLimitResult, RateLimitError
    token_bucket.rs   # TokenBucket algorithm (reusable, storage-agnostic)
    in_memory.rs      # InMemoryRateLimiter (DashMap-based)
    redis.rs          # RedisRateLimiter (behind `redis` feature flag)
```

**Trait**:

```rust
pub trait RateLimiter: Send + Sync {
    async fn check(&self, key: &str) -> Result<RateLimitResult, RateLimitError>;
}

pub struct RateLimitResult {
    pub allowed: bool,
    pub remaining: u32,
    pub limit: u32,
    pub reset_at: SystemTime,
    pub retry_after: Option<Duration>,
}
```

**InMemoryRateLimiter**:

- Uses `DashMap<String, TokenBucket>` for lock-free concurrent access
- Background tokio task runs every 60s to evict expired entries (IPs not seen for > 2 \* window_secs)
- `TokenBucket` struct: `tokens: f64`, `last_refill: Instant`, `max_tokens: u32`, `refill_rate: f64`

**RedisRateLimiter** (behind `redis` feature flag):

- Atomic Lua script: `MULTI` / `INCR` / `EXPIRE` / `EXEC` pattern
- Key format: `ratelimit:{ip}`, TTL = `window_secs`
- Uses `redis` crate with connection pooling

### Actix Middleware

**File**: `crates/oauth2-actix/src/middleware/rate_limit.rs`

- Follows the existing `Transform`/`Service` pattern (same as `AdminGuard`)
- Uses `EitherBody<B>` to short-circuit with 429 or pass through
- Extracts client IP: reads `X-Forwarded-For` if `trust_proxy_headers` is true in config, otherwise uses `peer_addr()`
- On every response (allowed or rejected), sets standard headers:
  - `X-RateLimit-Limit: {max_requests}`
  - `X-RateLimit-Remaining: {remaining}`
  - `X-RateLimit-Reset: {unix_timestamp}`
- On rejection, additionally sets `Retry-After: {seconds}`
- Registered as outermost global middleware (before session, tracing, etc.)
- Exempt paths: `/health`, `/ready`, `/metrics` — these are internal/monitoring endpoints that should not be rate-limited

### Configuration

**Config struct** (in `oauth2-config/src/lib.rs`):

```rust
pub struct RateLimitConfig {
    pub enabled: bool,          // default: true
    pub max_requests: u32,      // default: 100
    pub window_secs: u64,       // default: 60
    pub backend: String,        // default: "in_memory", also "redis"
    pub redis_url: Option<String>,
}
```

Added to `Config` as `pub rate_limit: Option<RateLimitConfig>` with `#[serde(default)]`.

**HOCON**:

```hocon
rate_limit {
  enabled = true
  max_requests = 100
  window_secs = 60
  backend = "in_memory"
  redis_url = "redis://127.0.0.1:6379"
}
```

**Env vars**: `OAUTH2_RATE_LIMIT_ENABLED`, `OAUTH2_RATE_LIMIT_MAX_REQUESTS`, `OAUTH2_RATE_LIMIT_WINDOW_SECS`, `OAUTH2_RATE_LIMIT_BACKEND`, `OAUTH2_RATE_LIMIT_REDIS_URL`

### Metrics

Two new Prometheus metrics (registered in `oauth2-observability`):

- `oauth2_server_rate_limit_rejected_total` (counter) — total rejected requests, labeled by IP prefix (first 3 octets for privacy)
- `oauth2_server_rate_limit_remaining` (histogram) — distribution of remaining tokens when requests are allowed

## 2. JWT Key Rotation

### KeySet Type

**File**: `crates/oauth2-core/src/models/key_set.rs` (new)

```rust
pub struct SigningKey {
    pub kid: String,
    pub algorithm: Algorithm,     // HS256 or RS256
    pub key_material: Vec<u8>,    // raw secret bytes (HS256) or PEM bytes (RS256)
    pub is_current: bool,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
}

pub struct KeySet {
    keys: Vec<SigningKey>,
}
```

**Methods**:

- `KeySet::current() -> Option<&SigningKey>` — the key marked `is_current`
- `KeySet::current_for_alg(alg: Algorithm) -> Option<&SigningKey>` — current key for a specific algorithm
- `KeySet::find(kid: &str) -> Option<&SigningKey>` — look up by `kid`
- `KeySet::active_keys() -> Vec<&SigningKey>` — all non-expired keys
- `KeySet::rotate(new_key: SigningKey, grace_period: Duration)` — marks old current key(s) of the same algorithm as non-current, sets their `expires_at`, inserts new key as current
- `KeySet::prune_expired()` — removes keys past their `expires_at`

The `KeySet` is stored as `Arc<RwLock<KeySet>>` in Actix app data, shared between the token signing handlers and the JWKS endpoint.

### Token Signing Changes

**File**: `crates/oauth2-core/src/models/token.rs`

**`Claims::encode()`**:

- Takes `&SigningKey` instead of `&str` secret
- Sets `kid` in the JWT header
- Signs with `EncodingKey::from_secret()` for HS256 or `EncodingKey::from_rsa_pem()` for RS256

**`Claims::decode()`**:

- Takes `&KeySet` instead of `&str` secret
- Reads `kid` from the unverified token header
- If `kid` is present: finds the matching key in `KeySet`, validates with that key
- If `kid` is absent: tries all active keys of the expected algorithm (backward compat with pre-rotation tokens that have no `kid`)
- Returns an error if no key successfully validates

**`IdTokenClaims`**: same changes, removing the separate `encode_rs256()` method in favor of the unified `encode(&SigningKey)` path.

### JWKS Endpoint Changes

**File**: `crates/oauth2-actix/src/handlers/wellknown.rs`

- Reads from `Arc<RwLock<KeySet>>` instead of `OidcConfig`
- Returns all active RS256 keys as JWK entries (with `kid`, `kty`, `use`, `alg`, `n`, `e`)
- HS256 keys are NOT included in JWKS (shared secrets must not be published)
- Caches the parsed RSA public key components in the `SigningKey` (current code re-parses PEM on every request)
- `Cache-Control: public, max-age=3600` (unchanged)

### Admin Rotation Endpoint

**Route**: `POST /admin/api/keys/rotate`
**Protected by**: AdminGuard (same as all `/admin/*` routes)

**Request body**:

```json
{
  "algorithm": "RS256",
  "grace_period_hours": 24
}
```

Both fields optional. `algorithm` defaults to the current key's algorithm. `grace_period_hours` defaults to config value.

**Behavior**:

1. Generate new key material (48-byte random for HS256, 2048-bit RSA for RS256)
2. Create `SigningKey` with generated `kid` (format: `{alg}-{timestamp}`, e.g. `rs256-1712150400`)
3. Call `KeySet::rotate(new_key, grace_period)`
4. Persist new key to DB, update old key's `expires_at` in DB
5. Call `KeySet::prune_expired()` and delete pruned keys from DB
6. Return `{ "kid": "rs256-1712150400", "algorithm": "RS256", "created_at": "..." }`

### Key Persistence

**New migration**: `V{next}__add_signing_keys_table.sql`

```sql
CREATE TABLE signing_keys (
    id TEXT PRIMARY KEY,
    kid TEXT NOT NULL UNIQUE,
    algorithm TEXT NOT NULL,
    key_material BLOB NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);
```

`key_material` is encrypted at rest using AES-256-GCM with the JWT secret as the key-encryption-key (KEK). This means the JWT secret still protects everything, but rotated keys are independently stored.

**Startup behavior**:

1. Load all non-expired keys from `signing_keys` table
2. If no keys exist (fresh install or pre-rotation migration):
   - Create HS256 `SigningKey` from `OAUTH2_JWT_SECRET`, `kid` = `hs256-initial`, `is_current` = true
   - If `OAUTH2_ID_TOKEN_PRIVATE_KEY_PEM` is set: create RS256 `SigningKey` from it, `kid` from `OAUTH2_ID_TOKEN_KID` or `rs256-initial`, `is_current` = true
   - Persist these seed keys to DB

### Configuration

Added to `JwtConfig` in `oauth2-config`:

```rust
pub struct JwtConfig {
    pub secret: String,
    pub key_rotation_grace_hours: u64,  // default: 24
}
```

**Env var**: `OAUTH2_JWT_KEY_ROTATION_GRACE_HOURS`

## 3. Cleanup Items

### 3a. Error Propagation in login.rs

**File**: `crates/oauth2-actix/src/handlers/login.rs`, line 143

**Before**: `session.get("return_to").unwrap_or(None)`
**After**: `session.get("return_to")?`

This propagates session deserialization errors as 500s with a log entry rather than silently dropping the return-to URL.

### 3b. E2E Admin Auth

**Files**: E2E scripts in `e2e/` that call `/admin/clients/register`

Update scripts to:

1. `POST /auth/login` with seed admin credentials (`OAUTH2_SEED_USERNAME` / `OAUTH2_SEED_PASSWORD`)
2. Capture session cookie from response
3. Pass cookie with the client registration request

No server code changes — script-only fix.

## Task Ordering

1. **Cleanup** (3a, 3b) — quick wins, < 1 hour
2. **Rate Limiting** — highest security value, estimated 3-4 tasks
3. **JWT Key Rotation** — builds on stabilized codebase, estimated 4-5 tasks

## Out of Scope

- Automatic scheduled key rotation (follow-up wave)
- Per-endpoint or per-client rate limits (upgrade path from per-IP global)
- Rate limit allowlists/bypass rules beyond health/ready/metrics
- Key rotation for social login provider secrets
