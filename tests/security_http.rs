use actix::{Actor, Addr};
use actix_session::{storage::CookieSessionStore, Session, SessionMiddleware};
use actix_web::{cookie::Key, test, web, App, HttpResponse};

use oauth2_actix::handlers::wellknown::OidcConfig;
use oauth2_core::{Client, OAuth2Error, TokenResponse, User};
use oauth2_observability::Metrics;

fn s256_challenge(verifier: &str) -> String {
    use base64::{engine::general_purpose, Engine as _};
    use sha2::{Digest, Sha256};
    let hash = Sha256::digest(verifier.as_bytes());
    general_purpose::URL_SAFE_NO_PAD.encode(hash)
}

fn extract_query_param(url: &str, key: &str) -> Option<String> {
    // Very small helper for test-only parsing.
    let (_base, query) = url.split_once('?')?;
    for pair in query.split('&') {
        let (k, v) = pair.split_once('=').unwrap_or((pair, ""));
        if k == key {
            return Some(v.to_string());
        }
    }
    None
}

/// Test-only handler that establishes a session for the mock user_123.
async fn test_set_session(session: Session) -> HttpResponse {
    session.insert("user_id", "user_123").unwrap();
    session.insert("authenticated", true).unwrap();
    HttpResponse::Ok().finish()
}

/// Extract the session cookie value from a Set-Cookie header.
fn extract_session_cookie(
    resp: &actix_web::dev::ServiceResponse<impl actix_web::body::MessageBody>,
) -> String {
    resp.response()
        .headers()
        .get(actix_web::http::header::SET_COOKIE)
        .and_then(|h| h.to_str().ok())
        .expect("session cookie should be set")
        .split(';')
        .next()
        .unwrap()
        .to_string()
}

async fn setup_context(
    client: Client,
) -> (
    Addr<oauth2_actix::actors::TokenActor>,
    Addr<oauth2_actix::actors::ClientActor>,
    Addr<oauth2_actix::actors::AuthActor>,
    String,
    Metrics,
    OidcConfig,
) {
    let storage = oauth2_storage_factory::create_storage("sqlite::memory:")
        .await
        .expect("create storage");
    storage.init().await.expect("init storage");
    storage.save_client(&client).await.expect("save client");

    // The authorize endpoint reads user_id from the session (set by test_set_session).
    // SQL backends enforce an FK from authorization_codes.user_id -> users.id, so we must ensure
    // this user exists for authorize() to succeed.
    let now = chrono::Utc::now();
    let user = User {
        id: "user_123".to_string(),
        username: "user_123".to_string(),
        password_hash: "not_used_in_security_http_tests".to_string(),
        email: "user_123@example.test".to_string(),
        enabled: true,
        role: "user".to_string(),
        created_at: now,
        updated_at: now,
    };
    storage.save_user(&user).await.expect("save user");

    let jwt_secret = "test_jwt_secret".to_string();
    let metrics = Metrics::new().expect("metrics");

    let token_actor =
        oauth2_actix::actors::TokenActor::new(storage.clone(), jwt_secret.clone()).start();
    let client_actor = oauth2_actix::actors::ClientActor::new(storage.clone()).start();
    let auth_actor = oauth2_actix::actors::AuthActor::new(storage.clone()).start();

    let oidc_config = OidcConfig {
        issuer: "http://localhost".to_string(),
        jwt_secret: jwt_secret.clone(),
        id_token_alg: "HS256".to_string(),
        id_token_kid: None,
        id_token_private_key_pem: None,
    };

    (
        token_actor,
        client_actor,
        auth_actor,
        jwt_secret,
        metrics,
        oidc_config,
    )
}

#[actix_web::test]
async fn authorize_rejects_unregistered_redirect_uri() {
    let client = Client::new(
        "client_a".to_string(),
        "secret_a".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // NOTE: percent-encode redirect_uri so the request URI is always valid and decodes back to the
    // exact string stored for the client.
    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);
    let req = test::TestRequest::get().uri(&format!("/oauth/authorize?response_type=code&client_id=client_a&redirect_uri=https%3A%2F%2Fevil.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256")).to_request();
    let resp = test::call_service(&app, req).await;

    assert_eq!(resp.status(), 400);
    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_request");
}

#[actix_web::test]
async fn authorize_rejects_implicit_response_type() {
    let client = Client::new(
        "client_a".to_string(),
        "secret_a".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);
    let req = test::TestRequest::get().uri(&format!("/oauth/authorize?response_type=token&client_id=client_a&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256")).to_request();
    let resp = test::call_service(&app, req).await;

    assert_eq!(resp.status(), 400);
    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_request");
}

#[actix_web::test]
async fn token_client_credentials_rejects_invalid_secret() {
    let client = Client::new(
        "client_cc".to_string(),
        "secret_cc".to_string(),
        vec!["https://unused.example/cb".to_string()],
        vec!["client_credentials".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "client_credentials"),
            ("client_id", "client_cc"),
            ("client_secret", "wrong"),
            ("scope", "read"),
        ])
        .to_request();

    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 401);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_client");
}

/// RFC 6749 §2.3.1: client credentials in Basic auth are URL-encoded before
/// base64-encoding.  Verify that secrets containing special chars (`/`, `+`)
/// are correctly decoded so the constant-time comparison matches.
#[actix_web::test]
async fn token_basic_auth_decodes_url_encoded_secret() {
    use base64::{engine::general_purpose, Engine as _};

    // Secret containing `/` and `+` — just like the production value.
    let raw_secret = "/Xahug+MGm1vCzn0Obrz6agxB9p/b1ccatLLn6cSHJDttRqxWUIV5YaL09VhzhLv";

    let client = Client::new(
        "client_special".to_string(),
        raw_secret.to_string(),
        vec!["https://unused.example/cb".to_string()],
        vec!["client_credentials".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(web::scope("/oauth").route(
                "/token",
                web::post().to(oauth2_actix::handlers::oauth::token),
            )),
    )
    .await;

    // Build Basic auth header with URL-encoded credentials (Go oauth2 style).
    use percent_encoding::{utf8_percent_encode, NON_ALPHANUMERIC};
    let encoded_id = utf8_percent_encode("client_special", NON_ALPHANUMERIC).to_string();
    let encoded_secret = utf8_percent_encode(raw_secret, NON_ALPHANUMERIC).to_string();
    let basic = general_purpose::STANDARD.encode(format!("{encoded_id}:{encoded_secret}"));

    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .insert_header(("Authorization", format!("Basic {basic}")))
        .set_form([("grant_type", "client_credentials"), ("scope", "read")])
        .to_request();
    let resp = test::call_service(&app, req).await;

    // Should succeed (200), not fail with invalid_client (401).
    assert_eq!(
        resp.status(),
        200,
        "URL-encoded Basic auth should decode to match the stored secret"
    );

    let body: TokenResponse = test::read_body_json(resp).await;
    assert!(!body.access_token.is_empty());
}

#[actix_web::test]
async fn token_response_has_no_store_headers() {
    let client = Client::new(
        "client_cc".to_string(),
        "secret_cc".to_string(),
        vec!["https://unused.example/cb".to_string()],
        vec!["client_credentials".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "client_credentials"),
            ("client_id", "client_cc"),
            ("client_secret", "secret_cc"),
            ("scope", "read"),
        ])
        .to_request();

    let resp = test::call_service(&app, req).await;
    assert!(resp.status().is_success());

    let cache_control = resp
        .headers()
        .get(actix_web::http::header::CACHE_CONTROL)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");
    assert!(cache_control.contains("no-store"));

    let pragma = resp
        .headers()
        .get(actix_web::http::header::PRAGMA)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");
    assert!(pragma.contains("no-cache"));

    let _body: TokenResponse = test::read_body_json(resp).await;
}

#[actix_web::test]
async fn authorize_requires_pkce_s256() {
    let client = Client::new(
        "client_ac".to_string(),
        "secret_ac".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Missing PKCE parameters should be rejected.
    let req = test::TestRequest::get().uri("/oauth/authorize?response_type=code&client_id=client_ac&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read").to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 400);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_request");
}

#[actix_web::test]
async fn pkce_allows_public_exchange_and_prevents_downgrade() {
    let client = Client::new(
        "client_pkce".to_string(),
        "secret_pkce".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                Key::generate(),
            ))
            .route("/test/login", web::get().to(test_set_session))
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Establish an authenticated session
    let login_req = test::TestRequest::get().uri("/test/login").to_request();
    let login_resp = test::call_service(&app, login_req).await;
    let session_cookie = extract_session_cookie(&login_resp);

    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);

    // Get a code with PKCE
    let req = test::TestRequest::get().uri(&format!("/oauth/authorize?response_type=code&client_id=client_pkce&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256")).insert_header(("Cookie", session_cookie.as_str())).to_request();
    let resp = test::call_service(&app, req).await;
    if resp.status() != 302 {
        let status = resp.status();
        let body = test::read_body(resp).await;
        panic!(
            "expected 302 from /oauth/authorize (PKCE), got {status} body={}",
            String::from_utf8_lossy(&body)
        );
    }

    let loc = resp
        .headers()
        .get(actix_web::http::header::LOCATION)
        .and_then(|h| h.to_str().ok())
        .unwrap();
    let code = extract_query_param(loc, "code").expect("code");

    // Missing verifier: should be rejected.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_pkce"),
            ("client_secret", "secret_pkce"),
            ("code", code.as_str()),
            ("redirect_uri", "https://good.example/cb"),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 400);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_grant");

    // Missing client_secret: should be rejected (token endpoint requires client auth).
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_pkce"),
            ("code", code.as_str()),
            ("redirect_uri", "https://good.example/cb"),
            ("code_verifier", verifier),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 401);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_client");

    // Correct exchange: include verifier and client_secret.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_pkce"),
            ("client_secret", "secret_pkce"),
            ("code", code.as_str()),
            ("redirect_uri", "https://good.example/cb"),
            ("code_verifier", verifier),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert!(resp.status().is_success());
}

#[actix_web::test]
async fn token_authorization_code_exchange_allows_missing_redirect_uri() {
    let client = Client::new(
        "client_oauth21".to_string(),
        "secret_oauth21".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                Key::generate(),
            ))
            .route("/test/login", web::get().to(test_set_session))
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Establish an authenticated session
    let login_req = test::TestRequest::get().uri("/test/login").to_request();
    let login_resp = test::call_service(&app, login_req).await;
    let session_cookie = extract_session_cookie(&login_resp);

    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);

    // Get a code with PKCE
    let req = test::TestRequest::get().uri(&format!(
        "/oauth/authorize?response_type=code&client_id=client_oauth21&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256"
    )).insert_header(("Cookie", session_cookie.as_str())).to_request();
    let resp = test::call_service(&app, req).await;
    if resp.status() != 302 {
        let status = resp.status();
        let body = test::read_body(resp).await;
        panic!(
            "expected 302 from /oauth/authorize (PKCE), got {status} body={}",
            String::from_utf8_lossy(&body)
        );
    }

    let loc = resp
        .headers()
        .get(actix_web::http::header::LOCATION)
        .and_then(|h| h.to_str().ok())
        .unwrap();
    let code = extract_query_param(loc, "code").expect("code");

    // OAuth 2.1 token request style: omit redirect_uri.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_oauth21"),
            ("client_secret", "secret_oauth21"),
            ("code", code.as_str()),
            ("code_verifier", verifier),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert!(resp.status().is_success());
}

#[actix_web::test]
async fn token_authorization_code_exchange_rejects_wrong_redirect_uri_when_provided() {
    let client = Client::new(
        "client_redirect_mismatch".to_string(),
        "secret_redirect_mismatch".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                Key::generate(),
            ))
            .route("/test/login", web::get().to(test_set_session))
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Establish an authenticated session
    let login_req = test::TestRequest::get().uri("/test/login").to_request();
    let login_resp = test::call_service(&app, login_req).await;
    let session_cookie = extract_session_cookie(&login_resp);

    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);

    // Get a code bound to the correct redirect_uri.
    let req = test::TestRequest::get().uri(&format!(
        "/oauth/authorize?response_type=code&client_id=client_redirect_mismatch&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256"
    )).insert_header(("Cookie", session_cookie.as_str())).to_request();
    let resp = test::call_service(&app, req).await;
    if resp.status() != 302 {
        let status = resp.status();
        let body = test::read_body(resp).await;
        panic!(
            "expected 302 from /oauth/authorize (PKCE), got {status} body={}",
            String::from_utf8_lossy(&body)
        );
    }

    let loc = resp
        .headers()
        .get(actix_web::http::header::LOCATION)
        .and_then(|h| h.to_str().ok())
        .unwrap();
    let code = extract_query_param(loc, "code").expect("code");

    // OAuth 2.0 backward-compat style: include redirect_uri, but wrong => invalid_grant.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_redirect_mismatch"),
            ("client_secret", "secret_redirect_mismatch"),
            ("code", code.as_str()),
            ("redirect_uri", "https://evil.example/cb"),
            ("code_verifier", verifier),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 400);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_grant");
}

#[actix_web::test]
async fn authorization_code_cannot_be_reused() {
    let client = Client::new(
        "client_reuse".to_string(),
        "secret_reuse".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                Key::generate(),
            ))
            .route("/test/login", web::get().to(test_set_session))
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Establish an authenticated session
    let login_req = test::TestRequest::get().uri("/test/login").to_request();
    let login_resp = test::call_service(&app, login_req).await;
    let session_cookie = extract_session_cookie(&login_resp);

    // Get a code (PKCE required)
    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);
    let req = test::TestRequest::get().uri(&format!("/oauth/authorize?response_type=code&client_id=client_reuse&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256")).insert_header(("Cookie", session_cookie.as_str())).to_request();
    let resp = test::call_service(&app, req).await;
    if resp.status() != 302 {
        let status = resp.status();
        let body = test::read_body(resp).await;
        panic!(
            "expected 302 from /oauth/authorize (reuse), got {status} body={}",
            String::from_utf8_lossy(&body)
        );
    }

    let loc = resp
        .headers()
        .get(actix_web::http::header::LOCATION)
        .and_then(|h| h.to_str().ok())
        .unwrap();
    let code = extract_query_param(loc, "code").expect("code");

    // First exchange succeeds.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_reuse"),
            ("client_secret", "secret_reuse"),
            ("code", code.as_str()),
            ("redirect_uri", "https://good.example/cb"),
            ("code_verifier", verifier),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert!(resp.status().is_success());

    // Second exchange fails.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_reuse"),
            ("client_secret", "secret_reuse"),
            ("code", code.as_str()),
            ("redirect_uri", "https://good.example/cb"),
            ("code_verifier", verifier),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 400);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_grant");
}

#[actix_web::test]
async fn well_known_metadata_matches_supported_flows() {
    let client = Client::new(
        "client_meta".to_string(),
        "secret_meta".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    let req = test::TestRequest::get()
        .uri("/.well-known/openid-configuration")
        .to_request();

    let resp = test::call_service(&app, req).await;
    assert!(resp.status().is_success());

    let body: serde_json::Value = test::read_body_json(resp).await;

    let rts = body
        .get("response_types_supported")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    assert!(!rts.iter().any(|v| v == "token"));

    let gts = body
        .get("grant_types_supported")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    assert!(!gts.iter().any(|v| v == "refresh_token"));
    assert!(!gts.iter().any(|v| v == "password"));

    let pkce_methods = body
        .get("code_challenge_methods_supported")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    assert!(pkce_methods.iter().any(|v| v == "S256"));
    assert!(!pkce_methods.iter().any(|v| v == "plain"));
}

#[actix_web::test]
async fn authorize_redirect_has_clickjacking_and_referrer_headers() {
    let client = Client::new(
        "client_hdr".to_string(),
        "secret_hdr".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                Key::generate(),
            ))
            .route("/test/login", web::get().to(test_set_session))
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Establish an authenticated session
    let login_req = test::TestRequest::get().uri("/test/login").to_request();
    let login_resp = test::call_service(&app, login_req).await;
    let session_cookie = extract_session_cookie(&login_resp);

    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(verifier);
    let req = test::TestRequest::get().uri(&format!("/oauth/authorize?response_type=code&client_id=client_hdr&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256")).insert_header(("Cookie", session_cookie.as_str())).to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 302);

    let rp = resp
        .headers()
        .get(actix_web::http::header::REFERRER_POLICY)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");
    assert!(rp.contains("no-referrer"));

    let xfo = resp
        .headers()
        .get(actix_web::http::header::X_FRAME_OPTIONS)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");
    assert!(xfo.contains("DENY"));

    let csp = resp
        .headers()
        .get(actix_web::http::header::CONTENT_SECURITY_POLICY)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");
    assert!(csp.contains("frame-ancestors"));
}

#[actix_web::test]
async fn pkce_rejects_short_verifier() {
    let client = Client::new(
        "client_short".to_string(),
        "secret_short".to_string(),
        vec!["https://good.example/cb".to_string()],
        vec!["authorization_code".to_string()],
        "read".to_string(),
        "test".to_string(),
    );

    let (token_actor, client_actor, auth_actor, jwt_secret, metrics, oidc_config) =
        setup_context(client).await;
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                Key::generate(),
            ))
            .route("/test/login", web::get().to(test_set_session))
            .app_data(web::Data::new(token_actor))
            .app_data(web::Data::new(client_actor))
            .app_data(web::Data::new(auth_actor))
            .app_data(web::Data::new(jwt_secret))
            .app_data(web::Data::new(metrics))
            .app_data(web::Data::new(oidc_config))
            .service(
                web::scope("/oauth")
                    .route(
                        "/authorize",
                        web::get().to(oauth2_actix::handlers::oauth::authorize),
                    )
                    .route(
                        "/token",
                        web::post().to(oauth2_actix::handlers::oauth::token),
                    )
                    .route(
                        "/introspect",
                        web::post().to(oauth2_actix::handlers::token::introspect),
                    )
                    .route(
                        "/revoke",
                        web::post().to(oauth2_actix::handlers::token::revoke),
                    ),
            )
            .service(web::scope("/.well-known").route(
                "/openid-configuration",
                web::get().to(oauth2_actix::handlers::wellknown::openid_configuration),
            )),
    )
    .await;

    // Establish an authenticated session
    let login_req = test::TestRequest::get().uri("/test/login").to_request();
    let login_resp = test::call_service(&app, login_req).await;
    let session_cookie = extract_session_cookie(&login_resp);

    // Use a valid-length verifier to mint a code.
    let good_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    let challenge = s256_challenge(good_verifier);
    let req = test::TestRequest::get().uri(&format!("/oauth/authorize?response_type=code&client_id=client_short&redirect_uri=https%3A%2F%2Fgood.example%2Fcb&scope=read&code_challenge={challenge}&code_challenge_method=S256")).insert_header(("Cookie", session_cookie.as_str())).to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 302);

    let loc = resp
        .headers()
        .get(actix_web::http::header::LOCATION)
        .and_then(|h| h.to_str().ok())
        .unwrap();
    let code = extract_query_param(loc, "code").expect("code");

    // Exchange with a too-short verifier should fail.
    let req = test::TestRequest::post()
        .uri("/oauth/token")
        .set_form([
            ("grant_type", "authorization_code"),
            ("client_id", "client_short"),
            ("client_secret", "secret_short"),
            ("code", code.as_str()),
            ("redirect_uri", "https://good.example/cb"),
            ("code_verifier", "short"),
        ])
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 400);

    let body: OAuth2Error = test::read_body_json(resp).await;
    assert_eq!(body.error, "invalid_grant");
}

#[test]
fn admin_check_requires_role_not_username() {
    use oauth2_core::User;
    use chrono::Utc;

    // A user named "admin" with role "user" must NOT be admin
    let impersonator = User {
        id: "u1".to_string(),
        username: "admin".to_string(),
        password_hash: "x".to_string(),
        email: "hacker@evil.com".to_string(),
        enabled: true,
        role: "user".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    assert!(!impersonator.is_admin(), "username='admin' with role='user' must not grant admin");

    // A user with role "admin" but a different username MUST be admin
    let real_admin = User {
        id: "u2".to_string(),
        username: "alice".to_string(),
        password_hash: "x".to_string(),
        email: "alice@corp.com".to_string(),
        enabled: true,
        role: "admin".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    assert!(real_admin.is_admin(), "role='admin' must grant admin regardless of username");
}

#[test]
fn insecure_jwt_secret_is_rejected_without_opt_in() {
    // Without OAUTH2_ALLOW_INSECURE_DEFAULTS=1, the known default must fail validation.
    // With it set, validation should pass (allows test environments to work).
    use oauth2_config::{Config, INSECURE_DEFAULT_JWT_SECRET};

    // RAII guard: removes OAUTH2_ALLOW_INSECURE_DEFAULTS on drop (including on panic),
    // preventing env-var pollution from leaking into concurrently-running tests.
    struct EnvCleanup;
    impl Drop for EnvCleanup {
        fn drop(&mut self) {
            std::env::remove_var("OAUTH2_ALLOW_INSECURE_DEFAULTS");
        }
    }
    let _guard = EnvCleanup;

    std::env::remove_var("OAUTH2_ALLOW_INSECURE_DEFAULTS");
    let mut config = Config::default();
    config.jwt.secret = INSECURE_DEFAULT_JWT_SECRET.to_string();

    let result = config.validate_for_production();
    assert!(result.is_err(), "insecure secret must fail validation without opt-in");
    assert!(
        result.unwrap_err().contains("OAUTH2_JWT_SECRET"),
        "error must reference OAUTH2_JWT_SECRET"
    );

    std::env::set_var("OAUTH2_ALLOW_INSECURE_DEFAULTS", "1");
    let result2 = config.validate_for_production();
    assert!(
        result2.is_ok(),
        "insecure secret must be allowed with OAUTH2_ALLOW_INSECURE_DEFAULTS=1"
    );
}

#[test]
fn open_redirect_validation_rejects_external_urls() {
    use oauth2_actix::handlers::login::is_safe_redirect;

    let safe = ["/profile", "/oauth/authorize?client_id=x", "/admin"];
    let unsafe_urls = [
        "https://evil.com",
        "//evil.com",
        "/\\evil.com",
        "javascript:alert(1)",
        "http://localhost@evil.com",
        "  https://evil.com",
    ];

    for url in &safe {
        assert!(is_safe_redirect(url), "Expected safe: {url}");
    }
    for url in &unsafe_urls {
        assert!(!is_safe_redirect(url), "Expected unsafe: {url}");
    }
}

#[actix_web::test]
async fn client_registration_requires_admin_session() {
    use actix_session::{storage::CookieSessionStore, SessionMiddleware};
    use actix_web::{cookie::Key, test, web, App};
    use oauth2_actix::handlers::client::register_client;
    use oauth2_actix::middleware::admin_guard::AdminGuard;

    // Minimal storage for the handler
    let storage = oauth2_storage_factory::create_storage("sqlite::memory:")
        .await
        .expect("create storage");
    storage.init().await.expect("init storage");
    let dyn_storage: oauth2_ports::storage::DynStorage = std::sync::Arc::new(storage);

    let session_key = Key::generate();
    let app = test::init_service(
        App::new()
            .app_data(web::Data::new(dyn_storage))
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                session_key.clone(),
            ))
            .service(
                web::scope("/admin")
                    .wrap(AdminGuard)
                    .route(
                        "/clients/register",
                        web::post().to(register_client),
                    ),
            ),
    )
    .await;

    let req = test::TestRequest::post()
        .uri("/admin/clients/register")
        .set_json(serde_json::json!({
            "client_name": "malicious-client",
            "redirect_uris": ["https://attacker.com/callback"],
            "grant_types": ["authorization_code"],
            "scope": "openid profile"
        }))
        .to_request();

    let resp = test::call_service(&app, req).await;
    let status = resp.status().as_u16();

    // AdminGuard redirects unauthenticated users to /auth/login (302).
    // It must never return 201 Created.
    assert_ne!(status, 201, "unauthenticated client registration must be rejected, got {status}");
    assert_eq!(status, 302, "unauthenticated request should redirect to login, got {status}");
}

#[actix_web::test]
async fn cors_empty_allowed_origins_denies_cross_origin() {
    use actix_cors::Cors;

    // Cors::default() with no .allowed_origin() calls is fail-closed: it emits no
    // Access-Control-Allow-Origin header, effectively denying all cross-origin requests.
    let cors = Cors::default()
        .allow_any_method()
        .allow_any_header()
        .max_age(3600);

    let app = test::init_service(
        App::new()
            .wrap(cors)
            .route("/", web::get().to(|| async { HttpResponse::Ok().finish() })),
    )
    .await;

    let req = test::TestRequest::get()
        .uri("/")
        .insert_header(("Origin", "https://evil.example.com"))
        .to_request();

    let resp = test::call_service(&app, req).await;

    assert!(
        !resp.headers().contains_key("access-control-allow-origin"),
        "Cors::default() with no allowed origins should not emit Access-Control-Allow-Origin"
    );
}

#[test]
fn cors_allowed_origins_parsed_correctly() {
    use oauth2_config::Config;

    // Note: std::env::set_var is not thread-safe when tests run in parallel.
    // The serial_test crate is not a dependency here; take care if parallelism is a concern.
    // SAFETY: This test sets and immediately restores OAUTH2_ALLOWED_ORIGINS.  It is
    // intentionally a single-threaded unit test (no async runtime, no shared state beyond
    // the process environment), so the risk of races with other tests is low in practice.
    unsafe {
        std::env::set_var(
            "OAUTH2_ALLOWED_ORIGINS",
            "https://app.example.com, https://admin.example.com, ",
        );
    }

    // Config::default() tries application.conf first (HOCON), then falls back to
    // from_env_fallback().  Either code path reads OAUTH2_ALLOWED_ORIGINS and applies
    // the same split/trim/filter logic, so both exercise the real production path.
    let config = Config::default();

    unsafe {
        std::env::remove_var("OAUTH2_ALLOWED_ORIGINS");
    }

    let origins = &config.server.allowed_origins;
    assert_eq!(
        origins.len(),
        2,
        "Expected exactly 2 origins after parsing (trailing comma/space must be stripped), got: {:?}",
        origins
    );
    assert_eq!(origins[0], "https://app.example.com");
    assert_eq!(origins[1], "https://admin.example.com");
}
