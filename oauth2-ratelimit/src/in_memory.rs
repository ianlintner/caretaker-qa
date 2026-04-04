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
