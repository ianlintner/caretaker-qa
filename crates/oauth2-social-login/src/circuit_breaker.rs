//! Lightweight circuit breaker for external provider HTTP calls.
//!
//! States:
//!   Closed  → requests flow normally; consecutive failures tracked.
//!   Open    → requests are rejected immediately; transitions to HalfOpen
//!             after a cooldown period.
//!   HalfOpen → a single probe request is allowed; success → Closed,
//!              failure → Open (resets cooldown).

use std::sync::Mutex;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum State {
    Closed,
    Open { since: Instant },
    HalfOpen,
}

/// A per-provider circuit breaker.
pub struct CircuitBreaker {
    inner: Mutex<Inner>,
    /// Number of consecutive failures before opening the circuit.
    failure_threshold: u32,
    /// How long the circuit stays open before allowing a probe.
    cooldown: Duration,
}

struct Inner {
    state: State,
    consecutive_failures: u32,
}

impl CircuitBreaker {
    /// Create a new circuit breaker.
    ///
    /// * `failure_threshold` – open after this many consecutive failures.
    /// * `cooldown` – duration the circuit stays open before half-opening.
    pub fn new(failure_threshold: u32, cooldown: Duration) -> Self {
        Self {
            inner: Mutex::new(Inner {
                state: State::Closed,
                consecutive_failures: 0,
            }),
            failure_threshold,
            cooldown,
        }
    }

    /// Check whether a request is allowed.
    ///
    /// Returns `true` if the circuit is closed or half-open (probe allowed).
    /// Returns `false` if open and cooldown has not elapsed.
    pub fn allow_request(&self) -> bool {
        let mut inner = self.inner.lock().unwrap();
        match inner.state {
            State::Closed => true,
            State::Open { since } => {
                if since.elapsed() >= self.cooldown {
                    inner.state = State::HalfOpen;
                    true
                } else {
                    false
                }
            }
            State::HalfOpen => {
                // Only one probe at a time; subsequent callers are rejected
                // until the probe completes (on_success / on_failure).
                false
            }
        }
    }

    /// Record a successful request. Resets the circuit to Closed.
    pub fn on_success(&self) {
        let mut inner = self.inner.lock().unwrap();
        inner.consecutive_failures = 0;
        inner.state = State::Closed;
    }

    /// Record a failed request. May open the circuit.
    pub fn on_failure(&self) {
        let mut inner = self.inner.lock().unwrap();
        inner.consecutive_failures += 1;
        if inner.consecutive_failures >= self.failure_threshold
            || inner.state == State::HalfOpen
        {
            inner.state = State::Open {
                since: Instant::now(),
            };
        }
    }
}
