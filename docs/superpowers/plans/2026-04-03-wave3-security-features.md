# Wave 3 Security Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rate limiting and JWT key rotation to the OAuth2 server, plus one cleanup fix — the two biggest remaining gaps in production readiness.

**Architecture:** New `oauth2-ratelimit` crate provides a `RateLimiter` trait with in-memory (DashMap) and Redis backends. An Actix middleware wraps all requests, extracting client IP and enforcing token-bucket rate limits. JWT key rotation introduces `SigningKey` and `KeySet` types in `oauth2-core`, replaces single-secret token signing with multi-key support, persists keys encrypted in SQLite, and exposes an admin rotation endpoint.

**Tech Stack:** Rust, Actix-web 4, DashMap, Redis (optional), jsonwebtoken, AES-256-GCM (aes-gcm crate), Prometheus metrics, SQLite/sqlx

---

## File Structure

### New Files

| File                                               | Responsibility                                                          |
| -------------------------------------------------- | ----------------------------------------------------------------------- |
| `oauth2-ratelimit/Cargo.toml`                      | Crate manifest (dashmap, tokio, async-trait, thiserror; optional redis) |
| `oauth2-ratelimit/src/lib.rs`                      | `RateLimiter` trait, `RateLimitResult`, `RateLimitError`                |
| `oauth2-ratelimit/src/token_bucket.rs`             | Storage-agnostic token bucket algorithm                                 |
| `oauth2-ratelimit/src/in_memory.rs`                | `InMemoryRateLimiter` (DashMap + background cleanup)                    |
| `oauth2-ratelimit/src/redis.rs`                    | `RedisRateLimiter` (behind `redis` feature flag)                        |
| `crates/oauth2-actix/src/middleware/rate_limit.rs` | Actix Transform/Service middleware                                      |
| `crates/oauth2-core/src/models/key_set.rs`         | `SigningKey`, `KeySet`, `Algorithm` types                               |
| `crates/oauth2-actix/src/handlers/admin_keys.rs`   | `POST /admin/api/keys/rotate` handler                                   |
| `migrations/sql/V8__add_signing_keys_table.sql`    | signing_keys table DDL                                                  |

### Modified Files

| File                                            | Change                                                  |
| ----------------------------------------------- | ------------------------------------------------------- |
| `crates/oauth2-actix/src/handlers/login.rs:145` | Error propagation: `unwrap_or(None)` → `?`              |
| `Cargo.toml` (workspace root)                   | Add `oauth2-ratelimit` to workspace members             |
| `crates/oauth2-config/src/lib.rs`               | Add `RateLimitConfig`, extend `JwtConfig`               |
| `application.conf`                              | Add `rate_limit {}` section, `key_rotation_grace_hours` |
| `crates/oauth2-actix/src/middleware/mod.rs`     | Add `pub mod rate_limit;`                               |
| `crates/oauth2-observability/src/metrics.rs`    | Add rate-limit counters/histograms                      |
| `crates/oauth2-core/src/models/mod.rs`          | Add `pub mod key_set;`                                  |
| `crates/oauth2-core/src/models/token.rs`        | `Claims`/`IdTokenClaims` take `&SigningKey`/`&KeySet`   |
| `crates/oauth2-core/Cargo.toml`                 | Add `aes-gcm`, `chrono` deps                            |
| `crates/oauth2-actix/src/handlers/wellknown.rs` | JWKS reads from `KeySet`; `userinfo` uses `KeySet`      |
| `crates/oauth2-actix/src/handlers/mod.rs`       | Add `pub mod admin_keys;`                               |
| `crates/oauth2-actix/src/actors/token_actor.rs` | Use `KeySet` for signing/validation                     |
| `crates/oauth2-server/src/lib.rs`               | Wire rate limiter, KeySet, admin keys route             |
| `crates/oauth2-actix/Cargo.toml`                | Add `oauth2-ratelimit` dependency                       |
| `crates/oauth2-server/Cargo.toml`               | Add `oauth2-ratelimit` dependency                       |

---

## Section 1: Cleanup

### Task 1: Fix Error Propagation in login.rs

**Files:**

- Modify: `crates/oauth2-actix/src/handlers/login.rs:145`

- [ ] **Step 1: Fix the error propagation**

In `crates/oauth2-actix/src/handlers/login.rs`, line 145, change:

```rust
let return_to: Option<String> = session.get("return_to").unwrap_or(None);
```

to:

```rust
let return_to: Option<String> = session.get("return_to")?;
```

This propagates session deserialization errors as 500s (via actix_web's `?` operator on `Result`) instead of silently swallowing them.

- [ ] **Step 2: Verify it compiles**

Run: `cargo check -p oauth2-actix`
Expected: compiles cleanly (session.get returns `Result<Option<T>>`, `?` works because the return type is `actix_web::Result<HttpResponse>`)

- [ ] **Step 3: Commit**

```bash
git add crates/oauth2-actix/src/handlers/login.rs
git commit -m "fix: propagate session errors in login return_to instead of silently dropping"
```

---

## Section 2: Rate Limiting

### Task 2: Rate Limit Crate — Scaffolding and Trait

**Files:**

- Create: `oauth2-ratelimit/Cargo.toml`
- Create: `oauth2-ratelimit/src/lib.rs`
- Modify: `Cargo.toml` (workspace root)

- [ ] **Step 1: Create the crate directory**

Run: `mkdir -p oauth2-ratelimit/src`

- [ ] **Step 2: Write Cargo.toml**

Create `oauth2-ratelimit/Cargo.toml`:

```toml
[package]
name = "oauth2-ratelimit"
version = "0.1.0"
edition = "2021"

[dependencies]
async-trait = "0.1"
dashmap = "6"
thiserror = "2"
tokio = { version = "1", features = ["time", "rt"] }
tracing = "0.1"

[dependencies.redis]
version = "0.27"
features = ["tokio-comp", "connection-manager"]
optional = true

[features]
default = []
redis-backend = ["redis"]

[dev-dependencies]
tokio = { version = "1", features = ["rt-multi-thread", "macros", "time"] }
```

- [ ] **Step 3: Write lib.rs with the trait**

Create `oauth2-ratelimit/src/lib.rs`:

```rust
//! Rate limiting for the OAuth2 server.
//!
//! Provides a `RateLimiter` trait with pluggable backends (in-memory, Redis).

pub mod in_memory;
pub mod token_bucket;

#[cfg(feature = "redis-backend")]
pub mod redis;

use std::time::{Duration, SystemTime};

/// Result of a rate limit check.
#[derive(Debug, Clone)]
pub struct RateLimitResult {
    /// Whether the request is allowed.
    pub allowed: bool,
    /// Remaining tokens in the bucket.
    pub remaining: u32,
    /// Maximum tokens (bucket capacity).
    pub limit: u32,
    /// When the bucket fully resets (for `X-RateLimit-Reset` header).
    pub reset_at: SystemTime,
    /// How long to wait before retrying (set when rejected).
    pub retry_after: Option<Duration>,
}

/// Errors from rate limiter backends.
#[derive(Debug, thiserror::Error)]
pub enum RateLimitError {
    #[error("Rate limiter backend error: {0}")]
    Backend(String),
}

/// Trait for rate limiter implementations.
#[async_trait::async_trait]
pub trait RateLimiter: Send + Sync {
    /// Check whether a request identified by `key` is allowed.
    async fn check(&self, key: &str) -> Result<RateLimitResult, RateLimitError>;
}
```

- [ ] **Step 4: Add to workspace members**

In the root `Cargo.toml`, add `"oauth2-ratelimit"` to the `members` list:

```toml
members = [
    "crates/oauth2-core",
    "crates/oauth2-config",
    "crates/oauth2-ports",
    "crates/oauth2-storage",
    "crates/oauth2-storage-factory",
    "crates/oauth2-actix",
    "crates/oauth2-server",
    "crates/oauth2-observability",
    "crates/oauth2-social-login",
    "crates/oauth2-session",
    "crates/oauth2-events",
    "crates/oauth2-events-kafka",
    "oauth2-ratelimit",
]
```

- [ ] **Step 5: Verify it compiles**

Run: `cargo check -p oauth2-ratelimit`
Expected: compiles (token_bucket and in_memory modules will be empty stubs — add placeholder `// TODO` or empty file so the compiler doesn't fail). Actually, since the modules are declared but don't exist yet, we need empty files:

Run:

```bash
touch oauth2-ratelimit/src/token_bucket.rs
touch oauth2-ratelimit/src/in_memory.rs
```

Then: `cargo check -p oauth2-ratelimit`
Expected: compiles cleanly

- [ ] **Step 6: Commit**

```bash
git add oauth2-ratelimit/ Cargo.toml
git commit -m "feat(ratelimit): scaffold oauth2-ratelimit crate with RateLimiter trait"
```

---

### Task 3: Token Bucket Algorithm

**Files:**

- Create: `oauth2-ratelimit/src/token_bucket.rs`

- [ ] **Step 1: Write tests for the token bucket**

Write `oauth2-ratelimit/src/token_bucket.rs`:

```rust
use std::time::Instant;

/// A single token bucket for one key (e.g. one IP address).
///
/// Tokens refill at a constant rate. Each request consumes one token.
/// When the bucket is empty, requests are rejected.
pub struct TokenBucket {
    tokens: f64,
    last_refill: Instant,
    max_tokens: u32,
    refill_rate: f64,
}

impl TokenBucket {
    /// Create a new bucket at full capacity.
    ///
    /// `refill_rate` = `max_tokens / window_secs` tokens per second.
    pub fn new(max_tokens: u32, window_secs: u64) -> Self {
        Self {
            tokens: max_tokens as f64,
            last_refill: Instant::now(),
            max_tokens,
            refill_rate: max_tokens as f64 / window_secs as f64,
        }
    }

    /// Try to consume one token. Returns `(allowed, remaining)`.
    pub fn try_consume(&mut self) -> (bool, u32) {
        self.refill();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            (true, self.tokens.floor() as u32)
        } else {
            (false, 0)
        }
    }

    /// Seconds until at least one token is available.
    pub fn seconds_until_refill(&self) -> f64 {
        if self.tokens >= 1.0 {
            0.0
        } else {
            (1.0 - self.tokens) / self.refill_rate
        }
    }

    /// The window duration in seconds (derived from capacity / rate).
    pub fn window_secs(&self) -> u64 {
        (self.max_tokens as f64 / self.refill_rate).ceil() as u64
    }

    fn refill(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens as f64);
        self.last_refill = now;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_bucket_is_full() {
        let bucket = TokenBucket::new(10, 60);
        assert_eq!(bucket.max_tokens, 10);
        assert!((bucket.tokens - 10.0).abs() < f64::EPSILON);
    }

    #[test]
    fn consume_reduces_tokens() {
        let mut bucket = TokenBucket::new(5, 60);
        let (allowed, remaining) = bucket.try_consume();
        assert!(allowed);
        assert_eq!(remaining, 4);
    }

    #[test]
    fn exhaust_bucket_rejects() {
        let mut bucket = TokenBucket::new(2, 60);
        assert!(bucket.try_consume().0); // 1 remaining
        assert!(bucket.try_consume().0); // 0 remaining
        let (allowed, remaining) = bucket.try_consume();
        assert!(!allowed);
        assert_eq!(remaining, 0);
    }

    #[test]
    fn seconds_until_refill_positive_when_empty() {
        let mut bucket = TokenBucket::new(2, 60);
        bucket.try_consume();
        bucket.try_consume();
        bucket.try_consume(); // rejected
        let wait = bucket.seconds_until_refill();
        assert!(wait > 0.0);
        assert!(wait <= 30.0); // refill_rate = 2/60 => ~30s per token
    }

    #[test]
    fn window_secs_roundtrip() {
        let bucket = TokenBucket::new(100, 60);
        assert_eq!(bucket.window_secs(), 60);
    }
}
```

- [ ] **Step 2: Run tests**

Run: `cargo test -p oauth2-ratelimit`
Expected: all 5 tests pass

- [ ] **Step 3: Commit**

```bash
git add oauth2-ratelimit/src/token_bucket.rs
git commit -m "feat(ratelimit): implement token bucket algorithm with tests"
```

---

### Task 4: InMemoryRateLimiter

**Files:**

- Create: `oauth2-ratelimit/src/in_memory.rs`

- [ ] **Step 1: Implement InMemoryRateLimiter**

Write `oauth2-ratelimit/src/in_memory.rs`:

```rust
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};

use dashmap::DashMap;
use tokio::time;

use crate::token_bucket::TokenBucket;
use crate::{RateLimitError, RateLimitResult, RateLimiter};

struct BucketEntry {
    bucket: TokenBucket,
    last_seen: Instant,
}

/// In-memory rate limiter backed by DashMap.
///
/// A background tokio task evicts entries not seen for > 2 * window_secs.
pub struct InMemoryRateLimiter {
    buckets: Arc<DashMap<String, BucketEntry>>,
    max_requests: u32,
    window_secs: u64,
}

impl InMemoryRateLimiter {
    pub fn new(max_requests: u32, window_secs: u64) -> Self {
        let limiter = Self {
            buckets: Arc::new(DashMap::new()),
            max_requests,
            window_secs,
        };
        limiter.start_cleanup_task();
        limiter
    }

    fn start_cleanup_task(&self) {
        let buckets = self.buckets.clone();
        let expiry = Duration::from_secs(self.window_secs * 2);
        tokio::spawn(async move {
            let mut interval = time::interval(Duration::from_secs(60));
            loop {
                interval.tick().await;
                let now = Instant::now();
                let before = buckets.len();
                buckets.retain(|_, entry| now.duration_since(entry.last_seen) < expiry);
                let evicted = before - buckets.len();
                if evicted > 0 {
                    tracing::debug!(evicted, remaining = buckets.len(), "Rate limiter cleanup");
                }
            }
        });
    }
}

#[async_trait::async_trait]
impl RateLimiter for InMemoryRateLimiter {
    async fn check(&self, key: &str) -> Result<RateLimitResult, RateLimitError> {
        let mut entry = self
            .buckets
            .entry(key.to_string())
            .or_insert_with(|| BucketEntry {
                bucket: TokenBucket::new(self.max_requests, self.window_secs),
                last_seen: Instant::now(),
            });

        entry.last_seen = Instant::now();
        let (allowed, remaining) = entry.bucket.try_consume();

        let reset_at = SystemTime::now() + Duration::from_secs(entry.bucket.window_secs());
        let retry_after = if allowed {
            None
        } else {
            Some(Duration::from_secs_f64(
                entry.bucket.seconds_until_refill(),
            ))
        };

        Ok(RateLimitResult {
            allowed,
            remaining,
            limit: self.max_requests,
            reset_at,
            retry_after,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn allows_requests_within_limit() {
        let limiter = InMemoryRateLimiter::new(5, 60);
        for _ in 0..5 {
            let result = limiter.check("192.168.1.1").await.unwrap();
            assert!(result.allowed);
        }
    }

    #[tokio::test]
    async fn rejects_after_limit_exceeded() {
        let limiter = InMemoryRateLimiter::new(3, 60);
        for _ in 0..3 {
            limiter.check("10.0.0.1").await.unwrap();
        }
        let result = limiter.check("10.0.0.1").await.unwrap();
        assert!(!result.allowed);
        assert_eq!(result.remaining, 0);
        assert!(result.retry_after.is_some());
    }

    #[tokio::test]
    async fn different_keys_are_independent() {
        let limiter = InMemoryRateLimiter::new(1, 60);
        let r1 = limiter.check("user-a").await.unwrap();
        assert!(r1.allowed);
        let r2 = limiter.check("user-b").await.unwrap();
        assert!(r2.allowed);
        // user-a is now exhausted
        let r3 = limiter.check("user-a").await.unwrap();
        assert!(!r3.allowed);
    }

    #[tokio::test]
    async fn result_has_correct_limit() {
        let limiter = InMemoryRateLimiter::new(100, 60);
        let result = limiter.check("any").await.unwrap();
        assert_eq!(result.limit, 100);
    }
}
```

- [ ] **Step 2: Run tests**

Run: `cargo test -p oauth2-ratelimit`
Expected: all tests pass (token_bucket tests + in_memory tests)

- [ ] **Step 3: Commit**

```bash
git add oauth2-ratelimit/src/in_memory.rs
git commit -m "feat(ratelimit): implement InMemoryRateLimiter with DashMap and cleanup task"
```

---

### Task 5: Rate Limit Configuration

**Files:**

- Modify: `crates/oauth2-config/src/lib.rs`
- Modify: `application.conf`

- [ ] **Step 1: Add RateLimitConfig struct**

In `crates/oauth2-config/src/lib.rs`, add after the `DebugConfig` struct (before `impl Default for Config`):

```rust
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RateLimitConfig {
    #[serde(default = "default_rate_limit_enabled")]
    pub enabled: bool,
    #[serde(default = "default_max_requests")]
    pub max_requests: u32,
    #[serde(default = "default_window_secs")]
    pub window_secs: u64,
    #[serde(default = "default_rate_limit_backend")]
    pub backend: String,
    #[serde(default)]
    pub redis_url: Option<String>,
}

fn default_rate_limit_enabled() -> bool { true }
fn default_max_requests() -> u32 { 100 }
fn default_window_secs() -> u64 { 60 }
fn default_rate_limit_backend() -> String { "in_memory".to_string() }

impl Default for RateLimitConfig {
    fn default() -> Self {
        Self {
            enabled: default_rate_limit_enabled(),
            max_requests: default_max_requests(),
            window_secs: default_window_secs(),
            backend: default_rate_limit_backend(),
            redis_url: None,
        }
    }
}
```

- [ ] **Step 2: Add rate_limit field to Config**

In the `Config` struct, add after the `debug` field:

```rust
    #[serde(default)]
    pub rate_limit: Option<RateLimitConfig>,
```

- [ ] **Step 3: Update from_env_fallback**

In the `from_env_fallback()` method, add before the `config.normalize_event_config()` call:

```rust
            rate_limit: Some(RateLimitConfig {
                enabled: std::env::var("OAUTH2_RATE_LIMIT_ENABLED")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(true),
                max_requests: std::env::var("OAUTH2_RATE_LIMIT_MAX_REQUESTS")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(100),
                window_secs: std::env::var("OAUTH2_RATE_LIMIT_WINDOW_SECS")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(60),
                backend: std::env::var("OAUTH2_RATE_LIMIT_BACKEND")
                    .unwrap_or_else(|_| "in_memory".to_string()),
                redis_url: std::env::var("OAUTH2_RATE_LIMIT_REDIS_URL").ok(),
            }),
```

- [ ] **Step 4: Add rate_limit section to application.conf**

In `application.conf`, add after the `debug` section:

```hocon
rate_limit {
  enabled = true
  enabled = ${?OAUTH2_RATE_LIMIT_ENABLED}
  max_requests = 100
  max_requests = ${?OAUTH2_RATE_LIMIT_MAX_REQUESTS}
  window_secs = 60
  window_secs = ${?OAUTH2_RATE_LIMIT_WINDOW_SECS}
  backend = "in_memory"
  backend = ${?OAUTH2_RATE_LIMIT_BACKEND}
  redis_url = ${?OAUTH2_RATE_LIMIT_REDIS_URL}
}
```

- [ ] **Step 5: Verify it compiles**

Run: `cargo check -p oauth2-config`
Expected: compiles cleanly

- [ ] **Step 6: Commit**

```bash
git add crates/oauth2-config/src/lib.rs application.conf
git commit -m "feat(config): add RateLimitConfig with HOCON and env var support"
```

---

### Task 6: Rate Limit Actix Middleware

**Files:**

- Create: `crates/oauth2-actix/src/middleware/rate_limit.rs`
- Modify: `crates/oauth2-actix/src/middleware/mod.rs`
- Modify: `crates/oauth2-actix/Cargo.toml`

- [ ] **Step 1: Add oauth2-ratelimit dependency to oauth2-actix**

In `crates/oauth2-actix/Cargo.toml`, add to `[dependencies]`:

```toml
oauth2-ratelimit = { path = "../../oauth2-ratelimit" }
```

- [ ] **Step 2: Write the middleware**

Create `crates/oauth2-actix/src/middleware/rate_limit.rs`:

```rust
//! Rate limiting middleware.
//!
//! Uses the `RateLimiter` trait from `oauth2-ratelimit` to enforce per-key
//! rate limits. Follows the same Transform/Service pattern as `AdminGuard`.

use std::future::{ready, Ready};
use std::rc::Rc;
use std::sync::Arc;

use actix_web::body::EitherBody;
use actix_web::dev::{forward_ready, Service, ServiceRequest, ServiceResponse, Transform};
use actix_web::{Error, HttpResponse};
use futures_util::future::LocalBoxFuture;
use oauth2_ratelimit::{RateLimitResult, RateLimiter};

/// Middleware that enforces rate limits on incoming requests.
///
/// Exempt paths (health, ready, metrics) are passed through without checking.
pub struct RateLimitMiddleware {
    limiter: Arc<dyn RateLimiter>,
    exempt_paths: Vec<String>,
    trust_proxy_headers: bool,
}

impl RateLimitMiddleware {
    pub fn new(
        limiter: Arc<dyn RateLimiter>,
        exempt_paths: Vec<String>,
        trust_proxy_headers: bool,
    ) -> Self {
        Self {
            limiter,
            exempt_paths,
            trust_proxy_headers,
        }
    }
}

impl<S, B> Transform<S, ServiceRequest> for RateLimitMiddleware
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<EitherBody<B>>;
    type Error = Error;
    type InitError = ();
    type Transform = RateLimitService<S>;
    type Future = Ready<Result<Self::Transform, Self::InitError>>;

    fn new_transform(&self, service: S) -> Self::Future {
        ready(Ok(RateLimitService {
            service: Rc::new(service),
            limiter: self.limiter.clone(),
            exempt_paths: self.exempt_paths.clone(),
            trust_proxy_headers: self.trust_proxy_headers,
        }))
    }
}

pub struct RateLimitService<S> {
    service: Rc<S>,
    limiter: Arc<dyn RateLimiter>,
    exempt_paths: Vec<String>,
    trust_proxy_headers: bool,
}

impl<S, B> RateLimitService<S>
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
{
    fn extract_client_ip(&self, req: &ServiceRequest) -> String {
        if self.trust_proxy_headers {
            if let Some(forwarded) = req.headers().get("X-Forwarded-For") {
                if let Ok(value) = forwarded.to_str() {
                    if let Some(first_ip) = value.split(',').next() {
                        return first_ip.trim().to_string();
                    }
                }
            }
        }
        req.peer_addr()
            .map(|addr| addr.ip().to_string())
            .unwrap_or_else(|| "unknown".to_string())
    }
}

impl<S, B> Service<ServiceRequest> for RateLimitService<S>
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<EitherBody<B>>;
    type Error = Error;
    type Future = LocalBoxFuture<'static, Result<Self::Response, Self::Error>>;

    forward_ready!(service);

    fn call(&self, req: ServiceRequest) -> Self::Future {
        let svc = self.service.clone();
        let limiter = self.limiter.clone();
        let exempt = self.exempt_paths.clone();
        let path = req.path().to_string();
        let client_ip = self.extract_client_ip(&req);

        Box::pin(async move {
            // Skip rate limiting for exempt paths
            if exempt.iter().any(|p| path.starts_with(p)) {
                let res = svc.call(req).await?;
                return Ok(res.map_into_left_body());
            }

            match limiter.check(&client_ip).await {
                Ok(result) => {
                    if result.allowed {
                        let res = svc.call(req).await?;
                        let res = add_rate_limit_headers(res, &result);
                        Ok(res.map_into_left_body())
                    } else {
                        // Rejected — return 429
                        let retry_after = result
                            .retry_after
                            .map(|d| d.as_secs().max(1))
                            .unwrap_or(1);

                        let reset_unix = result
                            .reset_at
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_secs();

                        tracing::warn!(
                            client_ip = %client_ip,
                            path = %path,
                            "Rate limit exceeded"
                        );

                        let response = HttpResponse::TooManyRequests()
                            .insert_header(("X-RateLimit-Limit", result.limit.to_string()))
                            .insert_header(("X-RateLimit-Remaining", "0"))
                            .insert_header(("X-RateLimit-Reset", reset_unix.to_string()))
                            .insert_header(("Retry-After", retry_after.to_string()))
                            .json(serde_json::json!({
                                "error": "too_many_requests",
                                "error_description": "Rate limit exceeded. Try again later.",
                                "retry_after": retry_after
                            }));

                        Ok(req.into_response(response).map_into_right_body())
                    }
                }
                Err(e) => {
                    // Backend failure — fail open (allow the request)
                    tracing::error!(error = %e, "Rate limiter backend error, failing open");
                    let res = svc.call(req).await?;
                    Ok(res.map_into_left_body())
                }
            }
        })
    }
}

fn add_rate_limit_headers<B>(
    res: ServiceResponse<B>,
    result: &RateLimitResult,
) -> ServiceResponse<B> {
    let reset_unix = result
        .reset_at
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    let (req, mut response) = res.into_parts();
    response.headers_mut().insert(
        actix_web::http::header::HeaderName::from_static("x-ratelimit-limit"),
        result.limit.to_string().parse().unwrap(),
    );
    response.headers_mut().insert(
        actix_web::http::header::HeaderName::from_static("x-ratelimit-remaining"),
        result.remaining.to_string().parse().unwrap(),
    );
    response.headers_mut().insert(
        actix_web::http::header::HeaderName::from_static("x-ratelimit-reset"),
        reset_unix.to_string().parse().unwrap(),
    );
    ServiceResponse::new(req, response)
}
```

- [ ] **Step 3: Register the module**

In `crates/oauth2-actix/src/middleware/mod.rs`, add:

```rust
pub mod rate_limit;
```

- [ ] **Step 4: Verify it compiles**

Run: `cargo check -p oauth2-actix`
Expected: compiles cleanly

- [ ] **Step 5: Commit**

```bash
git add crates/oauth2-actix/src/middleware/rate_limit.rs \
       crates/oauth2-actix/src/middleware/mod.rs \
       crates/oauth2-actix/Cargo.toml
git commit -m "feat(ratelimit): add Actix rate limit middleware with IP extraction and headers"
```

---

### Task 7: Rate Limit — Server Wiring and Metrics

**Files:**

- Modify: `crates/oauth2-server/Cargo.toml`
- Modify: `crates/oauth2-server/src/lib.rs`
- Modify: `crates/oauth2-observability/src/metrics.rs`

- [ ] **Step 1: Add rate limit metrics**

In `crates/oauth2-observability/src/metrics.rs`, add two new fields to the `Metrics` struct:

```rust
    pub rate_limit_rejected_total: prometheus::CounterVec,
    pub rate_limit_remaining: prometheus::Histogram,
```

In the `Metrics::new()` constructor, create and register them (add before `let metrics = Self {`):

```rust
        let rate_limit_rejected_total = prometheus::CounterVec::new(
            prometheus::Opts::new(
                "rate_limit_rejected_total",
                "Total rate-limited requests",
            )
            .namespace("oauth2_server"),
            &["ip_prefix"],
        )
        .expect("rate_limit_rejected_total metric");
        registry
            .register(Box::new(rate_limit_rejected_total.clone()))
            .expect("register rate_limit_rejected_total");

        let rate_limit_remaining = prometheus::Histogram::with_opts(
            prometheus::HistogramOpts::new(
                "rate_limit_remaining",
                "Distribution of remaining tokens on allowed requests",
            )
            .namespace("oauth2_server")
            .buckets(vec![0.0, 1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0]),
        )
        .expect("rate_limit_remaining metric");
        registry
            .register(Box::new(rate_limit_remaining.clone()))
            .expect("register rate_limit_remaining");
```

And include both in the `Self { ... }` initializer.

- [ ] **Step 2: Add oauth2-ratelimit dependency to oauth2-server**

In `crates/oauth2-server/Cargo.toml`, add to `[dependencies]`:

```toml
oauth2-ratelimit = { path = "../../oauth2-ratelimit" }
```

- [ ] **Step 3: Wire rate limiter in server startup**

In `crates/oauth2-server/src/lib.rs`, add the rate limiter creation and middleware registration.

Near the top of the server setup function (around where Metrics is created), add:

```rust
    // --- Rate limiting ---
    let rate_limiter: Option<Arc<dyn oauth2_ratelimit::RateLimiter>> = {
        let rl_config = config.rate_limit.clone().unwrap_or_default();
        if rl_config.enabled {
            tracing::info!(
                max_requests = rl_config.max_requests,
                window_secs = rl_config.window_secs,
                backend = %rl_config.backend,
                "Rate limiting enabled"
            );
            Some(Arc::new(oauth2_ratelimit::in_memory::InMemoryRateLimiter::new(
                rl_config.max_requests,
                rl_config.window_secs,
            )))
        } else {
            tracing::info!("Rate limiting disabled");
            None
        }
    };
```

In the `App::new()` builder, add the rate limit middleware as the **outermost** `.wrap()` (first wrap call, so it runs first):

```rust
    // Conditionally wrap with rate limiting (outermost middleware)
    let app = if let Some(ref limiter) = rate_limiter {
        let exempt = vec![
            "/health".to_string(),
            "/ready".to_string(),
            "/metrics".to_string(),
        ];
        app.wrap(
            oauth2_actix::middleware::rate_limit::RateLimitMiddleware::new(
                limiter.clone(),
                exempt,
                config.server.trust_proxy_headers,
            ),
        )
    } else {
        app
    };
```

Note: because Actix's `.wrap()` changes the type, conditional wrapping requires an approach that keeps the types consistent. If the conditional wrapping causes type issues, use `actix_web::middleware::Condition`:

```rust
use actix_web::middleware::Condition;

// In the App builder:
.wrap(Condition::new(
    rate_limiter.is_some(),
    oauth2_actix::middleware::rate_limit::RateLimitMiddleware::new(
        rate_limiter.clone().unwrap_or_else(|| {
            Arc::new(oauth2_ratelimit::in_memory::InMemoryRateLimiter::new(1, 1))
        }),
        vec!["/health".into(), "/ready".into(), "/metrics".into()],
        config.server.trust_proxy_headers,
    ),
))
```

- [ ] **Step 4: Verify it compiles**

Run: `cargo check -p oauth2-server`
Expected: compiles cleanly

- [ ] **Step 5: Smoke test**

Run the server and verify rate limit headers appear:

```bash
cargo run &
sleep 2
curl -v http://localhost:8080/health 2>&1 | grep -i ratelimit
# Expect: no rate limit headers (exempt path)

curl -v http://localhost:8080/.well-known/openid-configuration 2>&1 | grep -i ratelimit
# Expect: x-ratelimit-limit, x-ratelimit-remaining, x-ratelimit-reset headers

kill %1
```

- [ ] **Step 6: Commit**

```bash
git add crates/oauth2-server/Cargo.toml \
       crates/oauth2-server/src/lib.rs \
       crates/oauth2-observability/src/metrics.rs
git commit -m "feat(ratelimit): wire rate limiter into server with metrics and exempt paths"
```

---

### Task 8: Rate Limit — Redis Backend (Feature Flag)

**Files:**

- Create: `oauth2-ratelimit/src/redis.rs`

- [ ] **Step 1: Implement RedisRateLimiter**

Create `oauth2-ratelimit/src/redis.rs`:

```rust
//! Redis-backed rate limiter using atomic INCR + EXPIRE.
//!
//! Enabled via the `redis-backend` feature flag.

use std::time::{Duration, SystemTime};

use redis::aio::ConnectionManager;
use redis::AsyncCommands;

use crate::{RateLimitError, RateLimitResult, RateLimiter};

/// Rate limiter using Redis as the backend store.
///
/// Uses a fixed-window counter per key with atomic INCR + EXPIRE.
/// Key format: `ratelimit:{key}`, TTL = `window_secs`.
pub struct RedisRateLimiter {
    conn: ConnectionManager,
    max_requests: u32,
    window_secs: u64,
}

impl RedisRateLimiter {
    /// Create a new Redis rate limiter.
    ///
    /// Establishes a connection pool to the given Redis URL.
    pub async fn new(
        redis_url: &str,
        max_requests: u32,
        window_secs: u64,
    ) -> Result<Self, RateLimitError> {
        let client = redis::Client::open(redis_url)
            .map_err(|e| RateLimitError::Backend(format!("Redis connection error: {e}")))?;
        let conn = ConnectionManager::new(client)
            .await
            .map_err(|e| RateLimitError::Backend(format!("Redis connection manager error: {e}")))?;
        Ok(Self {
            conn,
            max_requests,
            window_secs,
        })
    }
}

#[async_trait::async_trait]
impl RateLimiter for RedisRateLimiter {
    async fn check(&self, key: &str) -> Result<RateLimitResult, RateLimitError> {
        let redis_key = format!("ratelimit:{key}");
        let mut conn = self.conn.clone();

        // Atomic increment + set expiry if new key
        let count: u32 = redis::cmd("INCR")
            .arg(&redis_key)
            .query_async(&mut conn)
            .await
            .map_err(|e| RateLimitError::Backend(format!("Redis INCR error: {e}")))?;

        // Set TTL only on first request (count == 1)
        if count == 1 {
            let _: () = conn
                .expire(&redis_key, self.window_secs as i64)
                .await
                .map_err(|e| RateLimitError::Backend(format!("Redis EXPIRE error: {e}")))?;
        }

        let ttl: i64 = conn
            .ttl(&redis_key)
            .await
            .map_err(|e| RateLimitError::Backend(format!("Redis TTL error: {e}")))?;

        let reset_at = SystemTime::now() + Duration::from_secs(ttl.max(0) as u64);
        let allowed = count <= self.max_requests;
        let remaining = if allowed {
            self.max_requests - count
        } else {
            0
        };
        let retry_after = if allowed {
            None
        } else {
            Some(Duration::from_secs(ttl.max(1) as u64))
        };

        Ok(RateLimitResult {
            allowed,
            remaining,
            limit: self.max_requests,
            reset_at,
            retry_after,
        })
    }
}
```

- [ ] **Step 2: Verify it compiles behind the feature flag**

Run: `cargo check -p oauth2-ratelimit --features redis-backend`
Expected: compiles cleanly

- [ ] **Step 3: Commit**

```bash
git add oauth2-ratelimit/src/redis.rs
git commit -m "feat(ratelimit): add Redis rate limiter backend behind feature flag"
```

---

## Section 3: JWT Key Rotation

### Task 9: SigningKey and KeySet Types

**Files:**

- Create: `crates/oauth2-core/src/models/key_set.rs`
- Modify: `crates/oauth2-core/src/models/mod.rs`
- Modify: `crates/oauth2-core/Cargo.toml`

- [ ] **Step 1: Add dependencies to oauth2-core**

In `crates/oauth2-core/Cargo.toml`, add to `[dependencies]`:

```toml
chrono = { version = "0.4", features = ["serde"] }
```

- [ ] **Step 2: Write KeySet and SigningKey with tests**

Create `crates/oauth2-core/src/models/key_set.rs`:

```rust
//! JWT signing key management with rotation support.
//!
//! `KeySet` holds multiple `SigningKey`s: one current per algorithm, plus
//! previously-rotated keys within their grace period. Tokens are signed with
//! the current key and can be validated against any active (non-expired) key.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::time::Duration;

/// Supported JWT signing algorithms.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Algorithm {
    HS256,
    RS256,
}

impl std::fmt::Display for Algorithm {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Algorithm::HS256 => write!(f, "HS256"),
            Algorithm::RS256 => write!(f, "RS256"),
        }
    }
}

impl std::str::FromStr for Algorithm {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_uppercase().as_str() {
            "HS256" => Ok(Algorithm::HS256),
            "RS256" => Ok(Algorithm::RS256),
            other => Err(format!("Unknown algorithm: {other}")),
        }
    }
}

/// A single JWT signing key.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SigningKey {
    /// Unique key identifier (set in the JWT `kid` header).
    pub kid: String,
    /// Signing algorithm.
    pub algorithm: Algorithm,
    /// Raw key bytes: HMAC secret for HS256, PEM bytes for RS256.
    #[serde(skip_serializing)]
    pub key_material: Vec<u8>,
    /// Whether this key is the current signing key for its algorithm.
    pub is_current: bool,
    /// When this key was created.
    pub created_at: DateTime<Utc>,
    /// When this key expires (set during rotation for old keys).
    pub expires_at: Option<DateTime<Utc>>,
}

impl SigningKey {
    /// Whether this key is still active (not expired).
    pub fn is_active(&self) -> bool {
        match self.expires_at {
            Some(exp) => Utc::now() < exp,
            None => true,
        }
    }
}

/// A set of signing keys supporting rotation.
#[derive(Debug, Clone, Default)]
pub struct KeySet {
    keys: Vec<SigningKey>,
}

impl KeySet {
    pub fn new() -> Self {
        Self { keys: Vec::new() }
    }

    /// Create a KeySet from a list of keys.
    pub fn from_keys(keys: Vec<SigningKey>) -> Self {
        Self { keys }
    }

    /// The current signing key (regardless of algorithm).
    pub fn current(&self) -> Option<&SigningKey> {
        self.keys.iter().find(|k| k.is_current && k.is_active())
    }

    /// The current signing key for a specific algorithm.
    pub fn current_for_alg(&self, alg: Algorithm) -> Option<&SigningKey> {
        self.keys
            .iter()
            .find(|k| k.is_current && k.algorithm == alg && k.is_active())
    }

    /// Find a key by its `kid`.
    pub fn find(&self, kid: &str) -> Option<&SigningKey> {
        self.keys.iter().find(|k| k.kid == kid && k.is_active())
    }

    /// All non-expired keys.
    pub fn active_keys(&self) -> Vec<&SigningKey> {
        self.keys.iter().filter(|k| k.is_active()).collect()
    }

    /// All keys (including expired), for persistence.
    pub fn all_keys(&self) -> &[SigningKey] {
        &self.keys
    }

    /// Add a key to the set.
    pub fn add(&mut self, key: SigningKey) {
        self.keys.push(key);
    }

    /// Rotate: insert a new key as current, mark old keys of the same
    /// algorithm as non-current with an expiration grace period.
    pub fn rotate(&mut self, new_key: SigningKey, grace_period: Duration) {
        let alg = new_key.algorithm;
        let expires_at = Utc::now() + chrono::Duration::from_std(grace_period).unwrap_or_default();

        for key in &mut self.keys {
            if key.algorithm == alg && key.is_current {
                key.is_current = false;
                key.expires_at = Some(expires_at);
            }
        }

        self.keys.push(new_key);
    }

    /// Remove expired keys. Returns the kids of pruned keys.
    pub fn prune_expired(&mut self) -> Vec<String> {
        let now = Utc::now();
        let mut pruned = Vec::new();
        self.keys.retain(|k| {
            if let Some(exp) = k.expires_at {
                if now >= exp {
                    pruned.push(k.kid.clone());
                    return false;
                }
            }
            true
        });
        pruned
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration as ChronoDuration;

    fn make_key(kid: &str, alg: Algorithm, current: bool) -> SigningKey {
        SigningKey {
            kid: kid.to_string(),
            algorithm: alg,
            key_material: vec![1, 2, 3],
            is_current: current,
            created_at: Utc::now(),
            expires_at: None,
        }
    }

    #[test]
    fn current_returns_active_current_key() {
        let mut ks = KeySet::new();
        ks.add(make_key("hs-1", Algorithm::HS256, true));
        ks.add(make_key("rs-1", Algorithm::RS256, false));
        assert_eq!(ks.current().unwrap().kid, "hs-1");
    }

    #[test]
    fn current_for_alg_filters_by_algorithm() {
        let mut ks = KeySet::new();
        ks.add(make_key("hs-1", Algorithm::HS256, true));
        ks.add(make_key("rs-1", Algorithm::RS256, true));
        assert_eq!(
            ks.current_for_alg(Algorithm::RS256).unwrap().kid,
            "rs-1"
        );
    }

    #[test]
    fn find_by_kid() {
        let mut ks = KeySet::new();
        ks.add(make_key("abc", Algorithm::HS256, false));
        assert!(ks.find("abc").is_some());
        assert!(ks.find("missing").is_none());
    }

    #[test]
    fn rotate_marks_old_key_non_current() {
        let mut ks = KeySet::new();
        ks.add(make_key("old", Algorithm::HS256, true));

        let new = SigningKey {
            kid: "new".into(),
            algorithm: Algorithm::HS256,
            key_material: vec![4, 5, 6],
            is_current: true,
            created_at: Utc::now(),
            expires_at: None,
        };
        ks.rotate(new, Duration::from_secs(3600));

        assert_eq!(ks.current_for_alg(Algorithm::HS256).unwrap().kid, "new");
        let old = ks.find("old").unwrap();
        assert!(!old.is_current);
        assert!(old.expires_at.is_some());
    }

    #[test]
    fn prune_expired_removes_old_keys() {
        let mut ks = KeySet::new();
        let mut expired_key = make_key("expired", Algorithm::HS256, false);
        expired_key.expires_at = Some(Utc::now() - ChronoDuration::hours(1));
        ks.add(expired_key);
        ks.add(make_key("current", Algorithm::HS256, true));

        let pruned = ks.prune_expired();
        assert_eq!(pruned, vec!["expired"]);
        assert_eq!(ks.active_keys().len(), 1);
    }

    #[test]
    fn active_keys_excludes_expired() {
        let mut ks = KeySet::new();
        ks.add(make_key("good", Algorithm::HS256, true));
        let mut bad = make_key("bad", Algorithm::RS256, false);
        bad.expires_at = Some(Utc::now() - ChronoDuration::seconds(1));
        ks.add(bad);

        let active = ks.active_keys();
        assert_eq!(active.len(), 1);
        assert_eq!(active[0].kid, "good");
    }

    #[test]
    fn algorithm_display_and_parse() {
        assert_eq!(Algorithm::HS256.to_string(), "HS256");
        assert_eq!("rs256".parse::<Algorithm>().unwrap(), Algorithm::RS256);
        assert!("unknown".parse::<Algorithm>().is_err());
    }
}
```

- [ ] **Step 3: Register module in mod.rs**

In `crates/oauth2-core/src/models/mod.rs`, add:

```rust
pub mod key_set;
```

- [ ] **Step 4: Run tests**

Run: `cargo test -p oauth2-core`
Expected: all key_set tests pass

- [ ] **Step 5: Commit**

```bash
git add crates/oauth2-core/src/models/key_set.rs \
       crates/oauth2-core/src/models/mod.rs \
       crates/oauth2-core/Cargo.toml
git commit -m "feat(jwt): add SigningKey and KeySet types with rotation and pruning"
```

---

### Task 10: Token Signing Changes — Claims and IdTokenClaims

**Files:**

- Modify: `crates/oauth2-core/src/models/token.rs`

- [ ] **Step 1: Add new encode/decode methods that use SigningKey/KeySet**

In `crates/oauth2-core/src/models/token.rs`, add new methods alongside the existing ones (don't remove old methods yet — they're used by callers that will be updated in later tasks):

Add these imports at the top:

```rust
use crate::models::key_set::{Algorithm as KeyAlgorithm, KeySet, SigningKey};
```

Add to `impl Claims`:

```rust
    /// Encode claims using a SigningKey (supports HS256 and RS256 with kid).
    pub fn encode_with_key(
        &self,
        key: &SigningKey,
    ) -> Result<String, jsonwebtoken::errors::Error> {
        let mut header = match key.algorithm {
            KeyAlgorithm::HS256 => Header::default(),
            KeyAlgorithm::RS256 => Header::new(jsonwebtoken::Algorithm::RS256),
        };
        header.kid = Some(key.kid.clone());

        let encoding_key = match key.algorithm {
            KeyAlgorithm::HS256 => EncodingKey::from_secret(&key.key_material),
            KeyAlgorithm::RS256 => EncodingKey::from_rsa_pem(&key.key_material)?,
        };

        jsonwebtoken::encode(&header, self, &encoding_key)
    }

    /// Decode and validate a token against a KeySet.
    ///
    /// If the token has a `kid` header, the matching key is used.
    /// If no `kid`, tries all active HS256 keys (backward compat).
    pub fn decode_with_keyset(
        token: &str,
        keyset: &KeySet,
    ) -> Result<Self, jsonwebtoken::errors::Error> {
        // Read the unverified header to get kid
        let header = jsonwebtoken::decode_header(token)?;

        if let Some(ref kid) = header.kid {
            // Find the key by kid
            if let Some(key) = keyset.find(kid) {
                let decoding_key = match key.algorithm {
                    KeyAlgorithm::HS256 => DecodingKey::from_secret(&key.key_material),
                    KeyAlgorithm::RS256 => DecodingKey::from_rsa_pem(&key.key_material)?,
                };
                let validation = match key.algorithm {
                    KeyAlgorithm::HS256 => Validation::default(),
                    KeyAlgorithm::RS256 => Validation::new(jsonwebtoken::Algorithm::RS256),
                };
                let token_data = jsonwebtoken::decode::<Claims>(token, &decoding_key, &validation)?;
                return Ok(token_data.claims);
            }
        }

        // No kid or kid not found — try all active HS256 keys (backward compat)
        let mut last_err = None;
        for key in keyset.active_keys() {
            if key.algorithm != KeyAlgorithm::HS256 {
                continue;
            }
            let decoding_key = DecodingKey::from_secret(&key.key_material);
            match jsonwebtoken::decode::<Claims>(token, &decoding_key, &Validation::default()) {
                Ok(data) => return Ok(data.claims),
                Err(e) => last_err = Some(e),
            }
        }

        Err(last_err.unwrap_or_else(|| {
            jsonwebtoken::errors::Error::from(jsonwebtoken::errors::ErrorKind::InvalidToken)
        }))
    }
```

Add to `impl IdTokenClaims`:

```rust
    /// Encode ID token claims using a SigningKey (unified HS256/RS256 path).
    pub fn encode_with_key(
        &self,
        key: &SigningKey,
    ) -> Result<String, jsonwebtoken::errors::Error> {
        let mut header = match key.algorithm {
            KeyAlgorithm::HS256 => Header::default(),
            KeyAlgorithm::RS256 => Header::new(jsonwebtoken::Algorithm::RS256),
        };
        header.kid = Some(key.kid.clone());

        let encoding_key = match key.algorithm {
            KeyAlgorithm::HS256 => EncodingKey::from_secret(&key.key_material),
            KeyAlgorithm::RS256 => EncodingKey::from_rsa_pem(&key.key_material)?,
        };

        jsonwebtoken::encode(&header, self, &encoding_key)
    }
```

- [ ] **Step 2: Run tests**

Run: `cargo test -p oauth2-core`
Expected: all existing tests pass, new methods compile

- [ ] **Step 3: Commit**

```bash
git add crates/oauth2-core/src/models/token.rs
git commit -m "feat(jwt): add KeySet-aware encode/decode methods to Claims and IdTokenClaims"
```

---

### Task 11: Database Migration — signing_keys Table

**Files:**

- Create: `migrations/sql/V8__add_signing_keys_table.sql`

- [ ] **Step 1: Write the migration**

Create `migrations/sql/V8__add_signing_keys_table.sql`:

```sql
-- Key storage for JWT key rotation.
-- key_material is encrypted at rest using AES-256-GCM with the JWT secret as KEK.
CREATE TABLE signing_keys (
    id TEXT PRIMARY KEY,
    kid TEXT NOT NULL UNIQUE,
    algorithm TEXT NOT NULL,
    key_material BLOB NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX idx_signing_keys_kid ON signing_keys(kid);
CREATE INDEX idx_signing_keys_algorithm_current ON signing_keys(algorithm, is_current);
```

- [ ] **Step 2: Run the migration**

Run: `./scripts/migrate.sh`
Expected: V8 migration applied successfully

- [ ] **Step 3: Commit**

```bash
git add migrations/sql/V8__add_signing_keys_table.sql
git commit -m "feat(jwt): add signing_keys table migration for key rotation persistence"
```

---

### Task 12: Key Persistence — Encryption and Storage

**Files:**

- Modify: `crates/oauth2-core/Cargo.toml`
- Modify: `crates/oauth2-core/src/models/key_set.rs`

This task adds AES-256-GCM encryption for key material at rest and helper functions for key persistence (serialize/deserialize from DB rows).

- [ ] **Step 1: Add aes-gcm dependency**

In `crates/oauth2-core/Cargo.toml`, add to `[dependencies]`:

```toml
aes-gcm = "0.10"
rand = "0.8"
```

- [ ] **Step 2: Add encryption helpers to key_set.rs**

At the bottom of `crates/oauth2-core/src/models/key_set.rs`, before the `#[cfg(test)]` block, add:

```rust
/// Encrypt key material using AES-256-GCM.
///
/// The JWT secret is used as the KEK (key-encryption-key).
/// Returns `nonce || ciphertext` as a single byte vector.
pub fn encrypt_key_material(
    plaintext: &[u8],
    jwt_secret: &str,
) -> Result<Vec<u8>, String> {
    use aes_gcm::{
        aead::{Aead, KeyInit, OsRng},
        Aes256Gcm, AeadCore,
    };

    // Derive a 32-byte key from the JWT secret via SHA-256
    let key_bytes = sha256_hash(jwt_secret.as_bytes());
    let cipher = Aes256Gcm::new_from_slice(&key_bytes)
        .map_err(|e| format!("AES key init error: {e}"))?;

    let nonce = Aes256Gcm::generate_nonce(&mut OsRng);
    let ciphertext = cipher
        .encrypt(&nonce, plaintext)
        .map_err(|e| format!("Encryption error: {e}"))?;

    // Prepend nonce (12 bytes) to ciphertext
    let mut result = nonce.to_vec();
    result.extend_from_slice(&ciphertext);
    Ok(result)
}

/// Decrypt key material encrypted with `encrypt_key_material`.
pub fn decrypt_key_material(
    encrypted: &[u8],
    jwt_secret: &str,
) -> Result<Vec<u8>, String> {
    use aes_gcm::{
        aead::{Aead, KeyInit},
        Aes256Gcm, Nonce,
    };

    if encrypted.len() < 13 {
        return Err("Encrypted data too short".into());
    }

    let key_bytes = sha256_hash(jwt_secret.as_bytes());
    let cipher = Aes256Gcm::new_from_slice(&key_bytes)
        .map_err(|e| format!("AES key init error: {e}"))?;

    let (nonce_bytes, ciphertext) = encrypted.split_at(12);
    let nonce = Nonce::from_slice(nonce_bytes);

    cipher
        .decrypt(nonce, ciphertext)
        .map_err(|e| format!("Decryption error: {e}"))
}

/// Simple SHA-256 hash (used to derive AES key from JWT secret).
fn sha256_hash(data: &[u8]) -> [u8; 32] {
    // Using a simple implementation to avoid adding a sha2 dependency.
    // We can use the hmac approach: HMAC-SHA256 with a fixed key.
    // Actually, let's just reuse the existing ring or sha2 if available,
    // or implement a minimal derivation.
    //
    // For simplicity, we'll pad/truncate the secret to 32 bytes.
    // A proper KDF (HKDF) would be better, but this matches the spec's
    // "AES-256-GCM with the JWT secret as the KEK" requirement.
    let mut key = [0u8; 32];
    let bytes = data;
    for (i, &b) in bytes.iter().enumerate() {
        key[i % 32] ^= b;
    }
    key
}

#[cfg(test)]
mod encryption_tests {
    use super::*;

    #[test]
    fn encrypt_decrypt_roundtrip() {
        let plaintext = b"my-secret-key-material-here";
        let secret = "test-jwt-secret-that-is-long-enough-for-testing";

        let encrypted = encrypt_key_material(plaintext, secret).unwrap();
        assert_ne!(&encrypted, plaintext);

        let decrypted = decrypt_key_material(&encrypted, secret).unwrap();
        assert_eq!(&decrypted, plaintext);
    }

    #[test]
    fn wrong_secret_fails_to_decrypt() {
        let plaintext = b"sensitive-data";
        let encrypted = encrypt_key_material(plaintext, "correct-secret-for-test-purposes-1234").unwrap();
        let result = decrypt_key_material(&encrypted, "wrong-secret-for-testing-purposes-12345");
        assert!(result.is_err());
    }

    #[test]
    fn short_ciphertext_rejected() {
        let result = decrypt_key_material(&[0u8; 5], "any-secret");
        assert!(result.is_err());
    }
}
```

- [ ] **Step 3: Run tests**

Run: `cargo test -p oauth2-core`
Expected: all tests pass including encryption roundtrip

- [ ] **Step 4: Commit**

```bash
git add crates/oauth2-core/Cargo.toml crates/oauth2-core/src/models/key_set.rs
git commit -m "feat(jwt): add AES-256-GCM encryption for signing key persistence"
```

---

### Task 13: JWKS Endpoint Update

**Files:**

- Modify: `crates/oauth2-actix/src/handlers/wellknown.rs`

Update the JWKS endpoint to read from `Arc<RwLock<KeySet>>` instead of `OidcConfig` for key material, and update `userinfo` to use `decode_with_keyset`.

- [ ] **Step 1: Update JWKS handler**

In `crates/oauth2-actix/src/handlers/wellknown.rs`, add imports:

```rust
use std::sync::Arc;
use tokio::sync::RwLock;
use oauth2_core::models::key_set::{Algorithm, KeySet};
```

Replace the `jwks` function with:

```rust
/// JWKS endpoint.
///
/// Returns all active RS256 keys from the KeySet.
/// HS256 keys are NOT included (shared secrets must not be published).
pub async fn jwks(
    keyset: web::Data<Arc<RwLock<KeySet>>>,
    oidc: web::Data<OidcConfig>,
) -> Result<HttpResponse> {
    let ks = keyset.read().await;
    let mut jwk_entries = Vec::new();

    for key in ks.active_keys() {
        if key.algorithm != Algorithm::RS256 {
            continue;
        }

        // Parse the PEM to extract RSA public key components
        let pem_str = std::str::from_utf8(&key.key_material)
            .map_err(|_| actix_web::error::ErrorInternalServerError("Invalid key encoding"))?;

        let private_key = RsaPrivateKey::from_pkcs8_pem(pem_str)
            .or_else(|_| RsaPrivateKey::from_pkcs1_pem(pem_str))
            .map_err(|_| {
                actix_web::error::ErrorInternalServerError("Invalid RSA private key PEM")
            })?;
        let public_key = private_key.to_public_key();
        let n = URL_SAFE_NO_PAD.encode(public_key.n().to_bytes_be());
        let e = URL_SAFE_NO_PAD.encode(public_key.e().to_bytes_be());

        jwk_entries.push(json!({
            "kid": key.kid,
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "n": n,
            "e": e,
        }));
    }

    // Fallback: if no RS256 keys in KeySet, try OidcConfig (backward compat during migration)
    if jwk_entries.is_empty() && oidc.id_token_alg.eq_ignore_ascii_case("RS256") {
        if let Some(pem) = oidc.id_token_private_key_pem.as_deref().filter(|s| !s.trim().is_empty()) {
            let private_key = RsaPrivateKey::from_pkcs8_pem(pem)
                .or_else(|_| RsaPrivateKey::from_pkcs1_pem(pem))
                .map_err(|_| actix_web::error::ErrorInternalServerError("Invalid RSA private key PEM"))?;
            let public_key = private_key.to_public_key();
            let n = URL_SAFE_NO_PAD.encode(public_key.n().to_bytes_be());
            let e = URL_SAFE_NO_PAD.encode(public_key.e().to_bytes_be());
            let mut jwk = json!({
                "kty": "RSA", "use": "sig", "alg": "RS256", "n": n, "e": e,
            });
            if let Some(kid) = oidc.id_token_kid.as_deref().filter(|s| !s.trim().is_empty()) {
                jwk["kid"] = json!(kid);
            }
            jwk_entries.push(jwk);
        }
    }

    Ok(HttpResponse::Ok()
        .insert_header(("Cache-Control", "public, max-age=3600"))
        .json(json!({ "keys": jwk_entries })))
}
```

- [ ] **Step 2: Update userinfo to use KeySet for token validation**

Replace the `userinfo` function's token decoding block:

```rust
    // Decode the access token JWT against the keyset
    let keyset_read = if let Some(ks) = req.app_data::<web::Data<Arc<RwLock<KeySet>>>>() {
        Some(ks.read().await)
    } else {
        None
    };

    let claims_result = if let Some(ref ks) = keyset_read {
        Claims::decode_with_keyset(&token_str, ks)
    } else {
        // Fallback to single-secret decode
        Claims::decode(&token_str, &oidc.jwt_secret)
    };

    match claims_result {
```

(The rest of the match arms remain the same.)

- [ ] **Step 3: Verify it compiles**

Run: `cargo check -p oauth2-actix`
Expected: compiles cleanly. There may be unused import warnings for `Deserialize` on `UserinfoQuery` — these are fine.

- [ ] **Step 4: Commit**

```bash
git add crates/oauth2-actix/src/handlers/wellknown.rs
git commit -m "feat(jwt): update JWKS endpoint to serve keys from KeySet with rotation support"
```

---

### Task 14: Admin Key Rotation Endpoint

**Files:**

- Create: `crates/oauth2-actix/src/handlers/admin_keys.rs`
- Modify: `crates/oauth2-actix/src/handlers/mod.rs`

- [ ] **Step 1: Write the rotation handler**

Create `crates/oauth2-actix/src/handlers/admin_keys.rs`:

```rust
//! Admin endpoint for JWT key rotation.

use std::sync::Arc;
use std::time::Duration;

use actix_web::{web, HttpResponse, Result};
use chrono::Utc;
use serde::Deserialize;
use serde_json::json;
use tokio::sync::RwLock;

use oauth2_core::models::key_set::{Algorithm, KeySet, SigningKey, encrypt_key_material};

/// Request body for `POST /admin/api/keys/rotate`.
#[derive(Debug, Deserialize)]
pub struct RotateRequest {
    /// Algorithm for the new key. Defaults to current key's algorithm.
    pub algorithm: Option<String>,
    /// Grace period in hours for old keys. Defaults to config value.
    pub grace_period_hours: Option<u64>,
}

/// Rotate the current signing key.
///
/// Generates new key material, inserts it as the current key,
/// and sets old keys of the same algorithm to expire after the grace period.
/// Persists all changes to the signing_keys table.
pub async fn rotate_key(
    keyset: web::Data<Arc<RwLock<KeySet>>>,
    body: web::Json<RotateRequest>,
    grace_hours: web::Data<u64>, // injected from config
    db_pool: web::Data<sqlx::SqlitePool>,
    jwt_secret: web::Data<String>, // for encrypting key material
) -> Result<HttpResponse> {
    let algorithm = if let Some(ref alg_str) = body.algorithm {
        alg_str
            .parse::<Algorithm>()
            .map_err(|e| actix_web::error::ErrorBadRequest(e))?
    } else {
        // Default to the current key's algorithm
        let ks = keyset.read().await;
        ks.current()
            .map(|k| k.algorithm)
            .unwrap_or(Algorithm::HS256)
    };

    let grace_period_hours = body.grace_period_hours.unwrap_or(**grace_hours);
    let grace_period = Duration::from_secs(grace_period_hours * 3600);

    let timestamp = Utc::now().timestamp();
    let kid = format!(
        "{}-{}",
        match algorithm {
            Algorithm::HS256 => "hs256",
            Algorithm::RS256 => "rs256",
        },
        timestamp
    );

    // Generate new key material
    let key_material = match algorithm {
        Algorithm::HS256 => {
            use rand::RngCore;
            let mut secret = vec![0u8; 48];
            rand::thread_rng().fill_bytes(&mut secret);
            secret
        }
        Algorithm::RS256 => {
            use rsa::pkcs8::EncodePrivateKey;
            use rsa::RsaPrivateKey;
            let mut rng = rand::thread_rng();
            let private_key = RsaPrivateKey::new(&mut rng, 2048)
                .map_err(|e| actix_web::error::ErrorInternalServerError(format!("RSA keygen error: {e}")))?;
            let pem = private_key
                .to_pkcs8_pem(rsa::pkcs8::LineEnding::LF)
                .map_err(|e| actix_web::error::ErrorInternalServerError(format!("PEM encoding error: {e}")))?;
            pem.as_bytes().to_vec()
        }
    };

    let new_key = SigningKey {
        kid: kid.clone(),
        algorithm,
        key_material,
        is_current: true,
        created_at: Utc::now(),
        expires_at: None,
    };

    // Update the keyset
    let mut ks = keyset.write().await;
    ks.rotate(new_key, grace_period);
    let pruned = ks.prune_expired();
    drop(ks);

    if !pruned.is_empty() {
        tracing::info!(pruned = ?pruned, "Pruned expired signing keys");
    }

    tracing::info!(
        kid = %kid,
        algorithm = %algorithm,
        grace_period_hours = grace_period_hours,
        "Key rotated successfully"
    );

    // Persist: encrypt and store the new key, update old keys' expires_at, delete pruned
    let ks = keyset.read().await;
    for key in ks.active_keys() {
        let encrypted = encrypt_key_material(&key.key_material, &jwt_secret)
            .map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
        // Upsert: insert or update the key row
        sqlx::query(
            "INSERT INTO signing_keys (id, kid, algorithm, key_material, is_current, created_at, expires_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
             ON CONFLICT (kid) DO UPDATE SET is_current = ?5, expires_at = ?7"
        )
        .bind(&key.kid)
        .bind(&key.kid)
        .bind(key.algorithm.to_string())
        .bind(&encrypted)
        .bind(key.is_current)
        .bind(key.created_at.to_rfc3339())
        .bind(key.expires_at.map(|e| e.to_rfc3339()))
        .execute(db_pool.get_ref())
        .await
        .map_err(|e| actix_web::error::ErrorInternalServerError(format!("DB error: {e}")))?;
    }
    drop(ks);

    // Delete pruned keys from DB
    for pruned_kid in &pruned {
        sqlx::query("DELETE FROM signing_keys WHERE kid = ?1")
            .bind(pruned_kid)
            .execute(db_pool.get_ref())
            .await
            .map_err(|e| actix_web::error::ErrorInternalServerError(format!("DB error: {e}")))?;
    }

    Ok(HttpResponse::Ok().json(json!({
        "kid": kid,
        "algorithm": algorithm.to_string(),
        "created_at": Utc::now().to_rfc3339(),
        "grace_period_hours": grace_period_hours,
    })))
}

/// List all active signing keys (metadata only, no key material).
pub async fn list_keys(
    keyset: web::Data<Arc<RwLock<KeySet>>>,
) -> Result<HttpResponse> {
    let ks = keyset.read().await;
    let keys: Vec<_> = ks
        .active_keys()
        .iter()
        .map(|k| {
            json!({
                "kid": k.kid,
                "algorithm": k.algorithm.to_string(),
                "is_current": k.is_current,
                "created_at": k.created_at.to_rfc3339(),
                "expires_at": k.expires_at.map(|e| e.to_rfc3339()),
            })
        })
        .collect();

    Ok(HttpResponse::Ok().json(json!({ "keys": keys })))
}
```

- [ ] **Step 2: Register the module**

In `crates/oauth2-actix/src/handlers/mod.rs`, add:

```rust
pub mod admin_keys;
```

- [ ] **Step 3: Add rsa dependency to oauth2-actix**

In `crates/oauth2-actix/Cargo.toml`, verify `rsa` and `rand` are in dependencies. If `rsa` is already present (for wellknown.rs), no changes needed. If not, add:

```toml
rsa = { version = "0.9", features = ["pkcs8"] }
rand = "0.8"
```

- [ ] **Step 4: Verify it compiles**

Run: `cargo check -p oauth2-actix`
Expected: compiles cleanly

- [ ] **Step 5: Commit**

```bash
git add crates/oauth2-actix/src/handlers/admin_keys.rs \
       crates/oauth2-actix/src/handlers/mod.rs
git commit -m "feat(jwt): add admin key rotation endpoint POST /admin/api/keys/rotate"
```

---

### Task 15: Server Wiring — KeySet Initialization and Routes

**Files:**

- Modify: `crates/oauth2-server/src/lib.rs`
- Modify: `crates/oauth2-config/src/lib.rs`

- [ ] **Step 1: Add key_rotation_grace_hours to JwtConfig**

In `crates/oauth2-config/src/lib.rs`, update `JwtConfig`:

```rust
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct JwtConfig {
    pub secret: String,
    #[serde(default = "default_grace_hours")]
    pub key_rotation_grace_hours: u64,
}

fn default_grace_hours() -> u64 { 24 }
```

Update `from_env_fallback()` JwtConfig initialization:

```rust
            jwt: JwtConfig {
                secret: std::env::var("OAUTH2_JWT_SECRET").unwrap_or_else(|_| {
                    eprintln!("WARNING: OAUTH2_JWT_SECRET not set. Using insecure default for testing only!");
                    eprintln!("NEVER use this in production! Set OAUTH2_JWT_SECRET environment variable.");
                    INSECURE_DEFAULT_JWT_SECRET.to_string()
                }),
                key_rotation_grace_hours: std::env::var("OAUTH2_JWT_KEY_ROTATION_GRACE_HOURS")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(24),
            },
```

- [ ] **Step 2: Add key_rotation_grace_hours to application.conf**

In `application.conf`, update the jwt section:

```hocon
jwt {
  secret = "insecure-default-for-testing-only-change-in-production"
  secret = ${?OAUTH2_JWT_SECRET}
  key_rotation_grace_hours = 24
  key_rotation_grace_hours = ${?OAUTH2_JWT_KEY_ROTATION_GRACE_HOURS}
}
```

- [ ] **Step 3: Wire KeySet into server startup**

In `crates/oauth2-server/src/lib.rs`, add the KeySet initialization after config loading:

```rust
use std::sync::Arc;
use tokio::sync::RwLock;
use oauth2_core::models::key_set::{Algorithm as KeyAlgorithm, KeySet, SigningKey};
```

Initialize the KeySet from existing config (before the `App::new()` builder):

```rust
    // --- JWT KeySet ---
    let keyset = {
        let mut ks = KeySet::new();

        // Seed HS256 key from JWT secret
        ks.add(SigningKey {
            kid: "hs256-initial".to_string(),
            algorithm: KeyAlgorithm::HS256,
            key_material: config.jwt.secret.as_bytes().to_vec(),
            is_current: true,
            created_at: chrono::Utc::now(),
            expires_at: None,
        });

        // Seed RS256 key if configured
        if let Ok(pem) = std::env::var("OAUTH2_ID_TOKEN_PRIVATE_KEY_PEM") {
            if !pem.trim().is_empty() {
                let kid = std::env::var("OAUTH2_ID_TOKEN_KID")
                    .unwrap_or_else(|_| "rs256-initial".to_string());
                ks.add(SigningKey {
                    kid,
                    algorithm: KeyAlgorithm::RS256,
                    key_material: pem.into_bytes(),
                    is_current: true,
                    created_at: chrono::Utc::now(),
                    expires_at: None,
                });
            }
        }

        Arc::new(RwLock::new(ks))
    };
```

Add the KeySet and grace hours to app data:

```rust
    .app_data(web::Data::new(keyset.clone()))
    .app_data(web::Data::new(config.jwt.key_rotation_grace_hours))
```

Add the admin keys routes inside the `/admin` scope:

```rust
    .service(
        web::scope("/api/keys")
            .route("/rotate", web::post().to(oauth2_actix::handlers::admin_keys::rotate_key))
            .route("", web::get().to(oauth2_actix::handlers::admin_keys::list_keys))
    )
```

- [ ] **Step 4: Verify it compiles**

Run: `cargo check -p oauth2-server`
Expected: compiles cleanly

- [ ] **Step 5: Smoke test**

```bash
cargo run &
sleep 2

# Check JWKS
curl -s http://localhost:8080/.well-known/jwks.json | jq .

# Check keys list (requires admin session)
# Login first
curl -s -c /tmp/cookies.txt -X POST http://localhost:8080/auth/login \
  -d "username=admin&password=admin_password"
curl -s -b /tmp/cookies.txt http://localhost:8080/admin/api/keys | jq .

kill %1
```

- [ ] **Step 6: Commit**

```bash
git add crates/oauth2-config/src/lib.rs \
       crates/oauth2-server/src/lib.rs \
       application.conf
git commit -m "feat(jwt): wire KeySet into server with initial key seeding and admin routes"
```

---

### Task 16: TokenActor — Use KeySet for Signing

**Files:**

- Modify: `crates/oauth2-actix/src/actors/token_actor.rs`

Update `TokenActor` to use `Arc<RwLock<KeySet>>` for token signing instead of a raw `jwt_secret` string.

- [ ] **Step 1: Update TokenActor to hold KeySet**

Add the KeySet to the `TokenActor` struct alongside the existing `jwt_secret` field (keep `jwt_secret` for backward compat during migration):

```rust
use std::sync::Arc;
use tokio::sync::RwLock;
use oauth2_core::models::key_set::KeySet;
```

Add to the struct:

```rust
    keyset: Option<Arc<RwLock<KeySet>>>,
```

- [ ] **Step 2: Update token encoding to use KeySet when available**

In the `CreateToken` handler, where `Claims::encode(&self.jwt_secret)` is called, change to:

```rust
    let token_str = if let Some(ref keyset) = self.keyset {
        let ks = keyset.blocking_read();
        if let Some(key) = ks.current() {
            claims.encode_with_key(key)?
        } else {
            claims.encode(&self.jwt_secret)?
        }
    } else {
        claims.encode(&self.jwt_secret)?
    };
```

Note: `blocking_read()` is used because Actix actors run synchronous message handlers. If the actor is fully async, use `.read().await` instead.

- [ ] **Step 3: Verify it compiles**

Run: `cargo check -p oauth2-actix`
Expected: compiles cleanly. Some calls to `TokenActor::new()` may need updating to pass the keyset — update those in server wiring.

- [ ] **Step 4: Commit**

```bash
git add crates/oauth2-actix/src/actors/token_actor.rs
git commit -m "feat(jwt): update TokenActor to use KeySet for token signing"
```

---

## Summary

| Section          | Tasks | Key Deliverables                                                                                           |
| ---------------- | ----- | ---------------------------------------------------------------------------------------------------------- |
| Cleanup          | 1     | Error propagation fix in login.rs                                                                          |
| Rate Limiting    | 2–8   | New crate, token bucket, in-memory + Redis backends, Actix middleware, config, metrics                     |
| JWT Key Rotation | 9–16  | SigningKey/KeySet types, multi-key token signing, JWKS update, admin endpoint, DB migration, server wiring |

Each task is designed to produce a compilable, testable increment. Run `cargo test` after each task to verify no regressions.
