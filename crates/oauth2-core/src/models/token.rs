#![allow(dead_code)]

use chrono::{DateTime, Duration, Utc};
use jsonwebtoken::{Algorithm, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[cfg(feature = "openapi")]
use utoipa::ToSchema;

#[cfg_attr(feature = "openapi", derive(ToSchema))]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,   // Subject (user ID)
    pub iss: String,   // Issuer
    pub aud: String,   // Audience (client ID)
    pub exp: i64,      // Expiration time
    pub iat: i64,      // Issued at
    pub scope: String, // Scopes
    pub jti: String,   // JWT ID
    #[serde(skip_serializing_if = "Option::is_none")]
    pub client_id: Option<String>,
}

/// OIDC ID Token claims (returned when `openid` scope is requested).
#[cfg_attr(feature = "openapi", derive(ToSchema))]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdTokenClaims {
    pub iss: String,           // Issuer
    pub sub: String,           // Subject (user ID)
    pub aud: String,           // Audience (client ID)
    pub exp: i64,              // Expiration time
    pub iat: i64,              // Issued at
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nonce: Option<String>, // Nonce from authorize request
    #[serde(skip_serializing_if = "Option::is_none")]
    pub at_hash: Option<String>, // Access token hash
    #[serde(skip_serializing_if = "Option::is_none")]
    pub email: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub preferred_username: Option<String>,
}

impl IdTokenClaims {
    pub fn new(
        issuer: &str,
        subject: String,
        client_id: String,
        duration_seconds: i64,
        access_token: Option<&str>,
    ) -> Self {
        let now = Utc::now();
        let exp = now + Duration::seconds(duration_seconds);

        // Compute at_hash: left half of SHA-256 of the access_token, base64url-encoded
        let at_hash = access_token.map(|at| {
            use sha2::{Digest, Sha256};
            let hash = Sha256::digest(at.as_bytes());
            let left_half = &hash[..16]; // left 128 bits
            base64_url_encode(left_half)
        });

        Self {
            iss: issuer.to_string(),
            sub: subject,
            aud: client_id,
            exp: exp.timestamp(),
            iat: now.timestamp(),
            nonce: None,
            at_hash,
            email: None,
            preferred_username: None,
        }
    }

    pub fn encode(&self, secret: &str) -> Result<String, jsonwebtoken::errors::Error> {
        jsonwebtoken::encode(
            &Header::default(),
            self,
            &EncodingKey::from_secret(secret.as_ref()),
        )
    }

    pub fn encode_rs256(
        &self,
        private_key_pem: &str,
        kid: Option<&str>,
    ) -> Result<String, jsonwebtoken::errors::Error> {
        let mut header = Header::new(Algorithm::RS256);
        header.kid = kid.map(|s| s.to_string());
        let key = EncodingKey::from_rsa_pem(private_key_pem.as_bytes())?;
        jsonwebtoken::encode(&header, self, &key)
    }
}

/// Base64url encode without padding (per RFC 7515).
fn base64_url_encode(data: &[u8]) -> String {
    use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
    URL_SAFE_NO_PAD.encode(data)
}

impl Claims {
    pub fn new(subject: String, client_id: String, scope: String, duration_seconds: i64) -> Self {
        let now = Utc::now();
        let exp = now + Duration::seconds(duration_seconds);

        Self {
            sub: subject,
            iss: "rust_oauth2_server".to_string(),
            aud: client_id.clone(),
            exp: exp.timestamp(),
            iat: now.timestamp(),
            scope,
            jti: Uuid::new_v4().to_string(),
            client_id: Some(client_id),
        }
    }

    pub fn encode(&self, secret: &str) -> Result<String, jsonwebtoken::errors::Error> {
        jsonwebtoken::encode(
            &Header::default(),
            self,
            &EncodingKey::from_secret(secret.as_ref()),
        )
    }

    pub fn decode(token: &str, secret: &str) -> Result<Self, jsonwebtoken::errors::Error> {
        let token_data = jsonwebtoken::decode::<Claims>(
            token,
            &DecodingKey::from_secret(secret.as_ref()),
            &Validation::default(),
        )?;
        Ok(token_data.claims)
    }
}

#[cfg_attr(feature = "sqlx", derive(sqlx::FromRow))]
#[cfg_attr(feature = "openapi", derive(ToSchema))]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Token {
    pub id: String,
    pub access_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub refresh_token: Option<String>,
    pub token_type: String,
    pub expires_in: i32,
    pub scope: String,
    pub client_id: String,
    pub user_id: Option<String>,
    pub created_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub revoked: bool,
}

impl Token {
    pub fn new(
        access_token: String,
        refresh_token: Option<String>,
        client_id: String,
        user_id: Option<String>,
        scope: String,
        expires_in: i32,
    ) -> Self {
        let now = Utc::now();
        let expires_at = now + Duration::seconds(i64::from(expires_in));

        Self {
            id: Uuid::new_v4().to_string(),
            access_token,
            refresh_token,
            token_type: "Bearer".to_string(),
            expires_in,
            scope,
            client_id,
            user_id,
            created_at: now,
            expires_at,
            revoked: false,
        }
    }

    pub fn is_expired(&self) -> bool {
        Utc::now() > self.expires_at
    }

    pub fn is_valid(&self) -> bool {
        !self.revoked && !self.is_expired()
    }
}

#[cfg_attr(feature = "openapi", derive(ToSchema))]
#[derive(Debug, Serialize, Deserialize)]
pub struct TokenResponse {
    pub access_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub refresh_token: Option<String>,
    pub token_type: String,
    pub expires_in: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
    /// OIDC id_token – present when the `openid` scope was requested.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id_token: Option<String>,
}

impl TokenResponse {
    /// Attach an OIDC id_token to an existing response.
    pub fn with_id_token(mut self, id_token: String) -> Self {
        self.id_token = Some(id_token);
        self
    }
}

impl From<Token> for TokenResponse {
    fn from(token: Token) -> Self {
        Self {
            access_token: token.access_token,
            refresh_token: token.refresh_token,
            token_type: token.token_type,
            expires_in: token.expires_in,
            scope: Some(token.scope),
            id_token: None,
        }
    }
}

#[cfg_attr(feature = "openapi", derive(ToSchema))]
#[derive(Debug, Serialize, Deserialize)]
pub struct IntrospectionResponse {
    pub active: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub client_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub username: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub token_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exp: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub iat: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sub: Option<String>,
}
