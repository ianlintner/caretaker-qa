#![allow(dead_code)]

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[cfg_attr(feature = "sqlx", derive(sqlx::FromRow))]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct User {
    pub id: String,
    pub username: String,
    pub password_hash: String,
    pub email: String,
    pub enabled: bool,
    /// User role: "admin" or "user" (default).
    #[serde(default = "default_role")]
    pub role: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

fn default_role() -> String {
    "user".to_string()
}

impl User {
    pub fn new(username: String, password_hash: String, email: String) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4().to_string(),
            username,
            password_hash,
            email,
            enabled: true,
            role: "user".to_string(),
            created_at: now,
            updated_at: now,
        }
    }

    /// Check if the user has admin privileges.
    ///
    /// A user is considered admin if their `role` field is `"admin"`, their
    /// username is `"admin"`, or their email appears in the `OAUTH2_ADMIN_EMAILS`
    /// environment variable (comma-separated list).
    pub fn is_admin(&self) -> bool {
        if self.role == "admin" || self.username == "admin" {
            return true;
        }
        if let Ok(admin_emails) = std::env::var("OAUTH2_ADMIN_EMAILS") {
            let email_lower = self.email.to_lowercase();
            return admin_emails
                .split(',')
                .map(|e| e.trim().to_lowercase())
                .any(|e| e == email_lower);
        }
        false
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UserCredentials {
    pub username: String,
    pub password: String,
}
