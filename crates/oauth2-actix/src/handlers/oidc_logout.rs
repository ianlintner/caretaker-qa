use actix_session::Session;
use actix_web::{web, HttpResponse, Result};
use serde::Deserialize;
use serde_json::json;
use url::Url;

use oauth2_core::OAuth2Error;
use oauth2_ports::DynStorage;

#[derive(Debug, Deserialize)]
pub struct LogoutQuery {
    #[allow(dead_code)] // Reserved for stricter RP validation in a follow-up.
    pub id_token_hint: Option<String>,
    pub post_logout_redirect_uri: Option<String>,
    pub state: Option<String>,
}

fn validate_post_logout_redirect_uri_shape(uri: &str) -> Result<Url, OAuth2Error> {
    let parsed = Url::parse(uri)
        .map_err(|_| OAuth2Error::invalid_request("Invalid post_logout_redirect_uri"))?;

    match parsed.scheme() {
        "http" | "https" => {}
        _ => {
            return Err(OAuth2Error::invalid_request(
                "post_logout_redirect_uri must use http or https",
            ));
        }
    }

    if parsed.fragment().is_some() {
        return Err(OAuth2Error::invalid_request(
            "post_logout_redirect_uri must not contain a fragment",
        ));
    }

    Ok(parsed)
}

async fn is_registered_post_logout_redirect(
    storage: &DynStorage,
    candidate: &str,
) -> Result<bool, OAuth2Error> {
    let clients = storage.list_all_clients().await?;
    Ok(clients.iter().any(|client| {
        client
            .get_redirect_uris()
            .iter()
            .any(|uri| uri == candidate)
    }))
}

/// OIDC RP-Initiated Logout endpoint.
///
/// Current behavior:
/// - Always terminates the local user session.
/// - Optionally redirects to a registered `post_logout_redirect_uri`.
/// - Preserves `state` by appending it as a query parameter to the redirect URI.
pub async fn logout(
    query: web::Query<LogoutQuery>,
    session: Session,
    storage: web::Data<DynStorage>,
) -> Result<HttpResponse, OAuth2Error> {
    // Invalidate local session first.
    session.purge();

    if let Some(post_logout_redirect_uri) = query.post_logout_redirect_uri.as_deref() {
        let mut parsed = validate_post_logout_redirect_uri_shape(post_logout_redirect_uri)?;

        let is_registered =
            is_registered_post_logout_redirect(storage.get_ref(), post_logout_redirect_uri).await?;

        if !is_registered {
            return Err(OAuth2Error::invalid_request(
                "Unregistered post_logout_redirect_uri",
            ));
        }

        if let Some(state) = query.state.as_deref() {
            parsed.query_pairs_mut().append_pair("state", state);
        }

        return Ok(HttpResponse::Found()
            .append_header(("Location", parsed.to_string()))
            .finish());
    }

    Ok(HttpResponse::Ok().json(json!({ "status": "logged_out" })))
}
