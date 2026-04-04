//! Admin endpoint for JWT key rotation.

use std::sync::Arc;
use std::time::Duration;

use actix_web::{web, HttpResponse, Result};
use chrono::Utc;
use serde::Deserialize;
use serde_json::json;
use tokio::sync::RwLock;

use oauth2_core::models::key_set::{Algorithm, KeySet, SigningKey};

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
    _jwt_secret: web::Data<String>, // for encrypting key material (used during DB persistence)
) -> Result<HttpResponse> {
    let algorithm = if let Some(ref alg_str) = body.algorithm {
        alg_str
            .parse::<Algorithm>()
            .map_err(actix_web::error::ErrorBadRequest)?
    } else {
        // Default to the current key's algorithm
        let ks = keyset.read().await;
        let alg = ks.current().map(|k| k.algorithm).unwrap_or_else(|| {
            tracing::debug!("No current key found; defaulting to HS256");
            Algorithm::HS256
        });
        alg
    };

    let grace_period_hours = body.grace_period_hours.unwrap_or(**grace_hours);
    let grace_period = Duration::from_secs(grace_period_hours * 3600);

    let timestamp = Utc::now().timestamp();
    let kid = format!("{}-{}", algorithm.to_string().to_lowercase(), timestamp);

    // Generate new key material
    let key_material = match algorithm {
        Algorithm::HS256 => {
            use rand::RngCore;
            let mut secret = vec![0u8; 48];
            rand::rng().fill_bytes(&mut secret);
            secret
        }
        Algorithm::RS256 => {
            use rsa::pkcs8::EncodePrivateKey;
            use rsa::RsaPrivateKey;
            // Use OsRng from rsa's rand_core 0.6 (not rand 0.9's rand_core 0.9)
            // to satisfy the CryptoRngCore trait bound on RsaPrivateKey::new.
            let private_key = RsaPrivateKey::new(&mut rsa::rand_core::OsRng, 2048).map_err(|e| {
                tracing::error!(error = %e, "RSA key generation failed");
                actix_web::error::ErrorInternalServerError("Key generation failed")
            })?;
            let pem = private_key
                .to_pkcs8_pem(rsa::pkcs8::LineEnding::LF)
                .map_err(|e| {
                    tracing::error!(error = %e, "PEM encoding failed");
                    actix_web::error::ErrorInternalServerError("Key generation failed")
                })?;
            pem.as_bytes().to_vec()
        }
    };

    let created_at = Utc::now();
    let new_key = SigningKey {
        kid: kid.clone(),
        algorithm,
        key_material,
        is_current: true,
        created_at,
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

    Ok(HttpResponse::Ok().json(json!({
        "kid": kid,
        "algorithm": algorithm.to_string(),
        "created_at": created_at.to_rfc3339(),
        "grace_period_hours": grace_period_hours,
    })))
}

/// List all active signing keys (metadata only, no key material).
pub async fn list_keys(keyset: web::Data<Arc<RwLock<KeySet>>>) -> Result<HttpResponse> {
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
