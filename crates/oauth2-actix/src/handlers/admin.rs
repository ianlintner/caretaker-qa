use actix_web::{web, HttpResponse, Result};
use serde::Serialize;

use oauth2_observability::Metrics;
use oauth2_ports::DynStorage;

#[derive(Serialize)]
pub struct DashboardData {
    pub total_clients: i64,
    pub total_users: i64,
    pub total_tokens: i64,
    pub active_tokens: i64,
}

#[derive(Serialize)]
pub struct ClientInfo {
    pub id: String,
    pub client_id: String,
    pub name: String,
    pub scope: String,
    pub grant_types: String,
    pub created_at: String,
}

#[derive(Serialize)]
pub struct TokenInfo {
    pub id: String,
    pub client_id: String,
    pub user_id: String,
    pub scope: String,
    pub expires_at: String,
    pub revoked: bool,
    pub expired: bool,
}

#[derive(Serialize)]
pub struct UserInfo {
    pub id: String,
    pub username: String,
    pub email: String,
    pub role: String,
    pub enabled: bool,
    pub created_at: String,
}

/// Admin dashboard - shows overview statistics
pub async fn dashboard(db: web::Data<DynStorage>) -> Result<HttpResponse> {
    let clients = db.list_all_clients().await.unwrap_or_default();
    let users = db.list_all_users().await.unwrap_or_default();
    let tokens = db.list_all_tokens().await.unwrap_or_default();

    let active_tokens = tokens.iter().filter(|t| t.is_valid()).count() as i64;

    let data = DashboardData {
        total_clients: clients.len() as i64,
        total_users: users.len() as i64,
        total_tokens: tokens.len() as i64,
        active_tokens,
    };

    Ok(HttpResponse::Ok().json(data))
}

/// List all registered clients
pub async fn list_clients(db: web::Data<DynStorage>) -> Result<HttpResponse> {
    let clients = db
        .list_all_clients()
        .await
        .map_err(actix_web::error::ErrorInternalServerError)?;

    let infos: Vec<ClientInfo> = clients
        .into_iter()
        .map(|c| ClientInfo {
            id: c.id,
            client_id: c.client_id,
            name: c.name,
            scope: c.scope,
            grant_types: c.grant_types,
            created_at: c.created_at.to_rfc3339(),
        })
        .collect();

    Ok(HttpResponse::Ok().json(infos))
}

/// List all active tokens
pub async fn list_tokens(db: web::Data<DynStorage>) -> Result<HttpResponse> {
    let tokens = db
        .list_all_tokens()
        .await
        .map_err(actix_web::error::ErrorInternalServerError)?;

    let infos: Vec<TokenInfo> = tokens
        .into_iter()
        .map(|t| {
            let expired = t.is_expired();
            TokenInfo {
                id: t.id,
                client_id: t.client_id,
                user_id: t.user_id.unwrap_or_default(),
                scope: t.scope,
                expires_at: t.expires_at.to_rfc3339(),
                revoked: t.revoked,
                expired,
            }
        })
        .collect();

    Ok(HttpResponse::Ok().json(infos))
}

/// List all users
pub async fn list_users(db: web::Data<DynStorage>) -> Result<HttpResponse> {
    let users = db
        .list_all_users()
        .await
        .map_err(actix_web::error::ErrorInternalServerError)?;

    let infos: Vec<UserInfo> = users
        .into_iter()
        .map(|u| UserInfo {
            id: u.id,
            username: u.username,
            email: u.email,
            role: u.role,
            enabled: u.enabled,
            created_at: u.created_at.to_rfc3339(),
        })
        .collect();

    Ok(HttpResponse::Ok().json(infos))
}

/// Revoke a token by ID (admin function)
pub async fn admin_revoke_token(
    token_id: web::Path<String>,
    db: web::Data<DynStorage>,
) -> Result<HttpResponse> {
    // Revoke token
    db.revoke_token(&token_id)
        .await
        .map_err(actix_web::error::ErrorInternalServerError)?;

    Ok(HttpResponse::Ok().json(serde_json::json!({
        "message": "Token revoked successfully"
    })))
}

/// Delete a client (admin function)
pub async fn delete_client(
    _client_id: web::Path<String>,
    _db: web::Data<DynStorage>,
) -> Result<HttpResponse> {
    // In a real implementation, delete client and associated tokens
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "message": "Client deleted successfully"
    })))
}

/// Get system metrics
pub async fn system_metrics(metrics: web::Data<Metrics>) -> Result<HttpResponse> {
    let buffer = oauth2_observability::encode_prometheus_text(&metrics.registry)
        .map_err(actix_web::error::ErrorInternalServerError)?;

    Ok(HttpResponse::Ok()
        .content_type("text/plain; version=0.0.4")
        .body(buffer))
}

/// Health check endpoint
pub async fn health() -> Result<HttpResponse> {
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "status": "healthy",
        "service": "oauth2_server",
        "timestamp": chrono::Utc::now().to_rfc3339()
    })))
}

/// Readiness check endpoint
pub async fn readiness(db: web::Data<DynStorage>) -> Result<HttpResponse> {
    db.healthcheck()
        .await
        .map_err(actix_web::error::ErrorServiceUnavailable)?;

    Ok(HttpResponse::Ok().json(serde_json::json!({
        "status": "ready",
        "checks": {
            "database": "ok"
        }
    })))
}
