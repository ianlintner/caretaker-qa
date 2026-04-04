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
