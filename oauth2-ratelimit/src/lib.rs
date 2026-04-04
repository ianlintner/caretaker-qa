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
