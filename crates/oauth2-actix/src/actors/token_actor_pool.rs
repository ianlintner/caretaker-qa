use actix::Addr;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use super::token_actor::TokenActor;

/// A pool of `TokenActor` shards that routes messages by a hash key.
///
/// When `shards == 1` this degenerates to a single actor with no overhead.
/// For `shards > 1` the caller picks the shard via [`route`] which hashes the
/// supplied key and selects the corresponding actor.
#[derive(Clone)]
pub struct TokenActorPool {
    shards: Vec<Addr<TokenActor>>,
}

impl TokenActorPool {
    /// Wrap one or more actor addresses into a pool.
    ///
    /// # Panics
    /// Panics if `shards` is empty.
    pub fn new(shards: Vec<Addr<TokenActor>>) -> Self {
        assert!(!shards.is_empty(), "TokenActorPool requires at least one shard");
        Self { shards }
    }

    /// Select the shard for the given routing key (e.g. client_id or token).
    pub fn route(&self, key: &str) -> &Addr<TokenActor> {
        if self.shards.len() == 1 {
            return &self.shards[0];
        }
        let mut hasher = DefaultHasher::new();
        key.hash(&mut hasher);
        let idx = (hasher.finish() as usize) % self.shards.len();
        &self.shards[idx]
    }

    /// Number of shards in the pool.
    pub fn len(&self) -> usize {
        self.shards.len()
    }

    /// Whether the pool is empty (always false after construction).
    pub fn is_empty(&self) -> bool {
        self.shards.is_empty()
    }
}
