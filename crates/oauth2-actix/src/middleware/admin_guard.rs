//! Middleware that restricts access to admin-level users.
//!
//! Checks the session for `role == "admin"` or matches the user's email
//! against the `OAUTH2_ADMIN_EMAILS` environment variable. Unauthenticated
//! requests redirect to `/auth/login`; authenticated but non-admin requests
//! receive a 302 redirect to `OAUTH2_NON_ADMIN_REDIRECT` (defaults to
//! `https://profile.cat-herding.net`).

use actix_session::SessionExt;
use actix_web::{
    body::EitherBody,
    dev::{forward_ready, Service, ServiceRequest, ServiceResponse, Transform},
    Error, HttpResponse,
};
use futures::future::LocalBoxFuture;
use std::future::{ready, Ready};
use std::rc::Rc;

/// Actix-web middleware that gates access to admin-only routes.
pub struct AdminGuard;

impl<S, B> Transform<S, ServiceRequest> for AdminGuard
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<EitherBody<B>>;
    type Error = Error;
    type InitError = ();
    type Transform = AdminGuardService<S>;
    type Future = Ready<Result<Self::Transform, Self::InitError>>;

    fn new_transform(&self, service: S) -> Self::Future {
        ready(Ok(AdminGuardService {
            service: Rc::new(service),
        }))
    }
}

pub struct AdminGuardService<S> {
    service: Rc<S>,
}

/// Check if the given email is in the admin emails list.
fn is_admin_email(email: &str) -> bool {
    if let Ok(admin_emails) = std::env::var("OAUTH2_ADMIN_EMAILS") {
        let email_lower = email.to_lowercase();
        return admin_emails
            .split(',')
            .map(|e| e.trim().to_lowercase())
            .any(|e| e == email_lower);
    }
    false
}

impl<S, B> Service<ServiceRequest> for AdminGuardService<S>
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<EitherBody<B>>;
    type Error = Error;
    type Future = LocalBoxFuture<'static, Result<Self::Response, Self::Error>>;

    forward_ready!(service);

    fn call(&self, req: ServiceRequest) -> Self::Future {
        let svc = self.service.clone();

        Box::pin(async move {
            let session = req.get_session();

            // Check if user is authenticated at all
            let user_id: Option<String> = session.get("user_id").unwrap_or(None);
            if user_id.is_none() {
                // Not logged in — redirect to login
                let response = HttpResponse::Found()
                    .append_header(("Location", "/auth/login?error=login_required"))
                    .finish();
                return Ok(req.into_response(response).map_into_right_body());
            }

            // Check admin privileges:
            // 1. Session role == "admin"
            // 2. Session username == "admin"
            // 3. Session email matches OAUTH2_ADMIN_EMAILS
            let role: String = session
                .get("role")
                .unwrap_or(None)
                .unwrap_or_else(|| "user".to_string());
            let username: String = session.get("username").unwrap_or(None).unwrap_or_default();
            let email: String = session.get("email").unwrap_or(None).unwrap_or_default();

            let is_admin = role == "admin" || username == "admin" || is_admin_email(&email);

            if !is_admin {
                // Authenticated but not admin — redirect to profile site
                let redirect_url = std::env::var("OAUTH2_NON_ADMIN_REDIRECT")
                    .unwrap_or_else(|_| "https://profile.cat-herding.net".to_string());
                tracing::warn!(
                    username = %username,
                    email = %email,
                    "Non-admin user attempted to access admin dashboard, redirecting"
                );
                let response = HttpResponse::Found()
                    .append_header(("Location", redirect_url.as_str()))
                    .finish();
                return Ok(req.into_response(response).map_into_right_body());
            }

            // Admin access granted
            let res = svc.call(req).await?;
            Ok(res.map_into_left_body())
        })
    }
}
