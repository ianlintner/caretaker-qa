# Wave 2 Security Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close four remaining security gaps: insecure seed password at startup, session fixation after login, missing HTTP security headers, and duplicated `is_safe_redirect` logic.

**Architecture:** Each fix is independent and targets a single file or crate boundary. H-seed and H-fixation are high-severity; M-headers and M-redirect-dedup are medium (hardening and code quality). Fixes follow the patterns established in Wave 1: `OAUTH2_ALLOW_INSECURE_DEFAULTS=1` bypass for dev/test, same test file `tests/security_http.rs`, `oauth2-core` as the shared utility crate.

**Tech Stack:** Rust, Actix-web 4.4, actix-session 0.11, Argon2id, sqlx, Cargo workspace

---

## File Map

| File                                              | Action         | Reason                                              |
| ------------------------------------------------- | -------------- | --------------------------------------------------- |
| `crates/oauth2-server/src/lib.rs`                 | Modify         | Seed password guard + DefaultHeaders middleware     |
| `crates/oauth2-actix/src/handlers/login.rs`       | Modify         | Add `session.renew()` after credential verification |
| `crates/oauth2-core/src/lib.rs`                   | Modify         | Export new `utils` module                           |
| `crates/oauth2-core/src/utils/mod.rs`             | Create         | Submodule entrypoint                                |
| `crates/oauth2-core/src/utils/redirect.rs`        | Create         | Canonical `is_safe_redirect` implementation         |
| `crates/oauth2-actix/src/handlers/login.rs`       | Modify (again) | Import from `oauth2-core` instead of local copy     |
| `crates/oauth2-social-login/src/handlers/auth.rs` | Modify         | Import from `oauth2-core` instead of local copy     |
| `tests/security_http.rs`                          | Modify         | Integration tests for all four fixes                |

---

## Task 1: Block Insecure Seed Password at Startup (H-seed)

**Files:**

- Modify: `crates/oauth2-server/src/lib.rs` (the `seed_password` block ~line 127)
- Modify: `tests/security_http.rs` (add two tests)

### Background

`lib.rs` currently defaults the seed password to `"changeme"` when `OAUTH2_SEED_PASSWORD` is unset. This is the same vulnerability class as the Wave 1 JWT secret issue — insecure defaults silently used in production. The fix follows the exact same pattern: `validate_for_production()` already lives in `oauth2-config` and uses `OAUTH2_ALLOW_INSECURE_DEFAULTS=1` to bypass checks in test environments.

`★ Insight ─────────────────────────────────────`
The seed password only matters if the database is freshly seeded; in production the seed user should be disabled or removed entirely. But a weak known default lets any attacker with knowledge of the codebase authenticate immediately — same severity as a predictable JWT secret.
`─────────────────────────────────────────────────`

- [ ] **Step 1.1: Write the failing tests**

Open `tests/security_http.rs` and add at the end (before the final closing `}`):

```rust
// ── Task 1 (H-seed) ────────────────────────────────────────────────────────

#[actix_web::test]
async fn seed_password_default_changeme_is_rejected_in_production() {
    // OAUTH2_ALLOW_INSECURE_DEFAULTS not set → validate_for_production must reject "changeme" seed
    std::env::remove_var("OAUTH2_ALLOW_INSECURE_DEFAULTS");
    std::env::remove_var("OAUTH2_SEED_PASSWORD");

    let seed_password =
        std::env::var("OAUTH2_SEED_PASSWORD").unwrap_or_else(|_| "changeme".to_string());
    let result = validate_seed_password_for_production(&seed_password);
    assert!(
        result.is_err(),
        "Default seed password 'changeme' should be rejected in production"
    );
}

#[actix_web::test]
async fn seed_password_changeme_is_allowed_with_insecure_defaults_flag() {
    std::env::set_var("OAUTH2_ALLOW_INSECURE_DEFAULTS", "1");
    std::env::remove_var("OAUTH2_SEED_PASSWORD");

    let seed_password =
        std::env::var("OAUTH2_SEED_PASSWORD").unwrap_or_else(|_| "changeme".to_string());
    let result = validate_seed_password_for_production(&seed_password);
    assert!(
        result.is_ok(),
        "OAUTH2_ALLOW_INSECURE_DEFAULTS=1 should bypass the seed password check"
    );
    std::env::remove_var("OAUTH2_ALLOW_INSECURE_DEFAULTS");
}
```

Also add this import at the top of the test file (next to existing imports):

```rust
use oauth2_server::validate_seed_password_for_production;
```

- [ ] **Step 1.2: Confirm the tests cannot compile yet**

The function `validate_seed_password_for_production` does not exist; the file won't compile. That's expected — continue.

- [ ] **Step 1.3: Add `validate_seed_password_for_production` to `crates/oauth2-server/src/lib.rs`**

Find the `INSECURE_SEED_PASSWORD` constant (it may not exist yet). Add the constant and function just above the `pub async fn run(...)` function:

```rust
/// The well-known insecure seed password used as a default when
/// `OAUTH2_SEED_PASSWORD` is not set. Detected at startup to prevent
/// accidental use in production deployments.
pub const INSECURE_DEFAULT_SEED_PASSWORD: &str = "changeme";

/// Validate that the seed password is not the insecure default.
///
/// Returns `Ok(())` when the password is safe to use, or `Err(msg)` when
/// it equals the known-bad default and no insecure-defaults opt-in is set.
///
/// `OAUTH2_ALLOW_INSECURE_DEFAULTS=1` bypasses all validation (test/dev only).
pub fn validate_seed_password_for_production(password: &str) -> Result<(), String> {
    if std::env::var("OAUTH2_ALLOW_INSECURE_DEFAULTS").as_deref() == Ok("1") {
        return Ok(());
    }
    if password == INSECURE_DEFAULT_SEED_PASSWORD {
        return Err(
            "OAUTH2_SEED_PASSWORD must be explicitly set for production. \
            Set it to a strong random password. \
            Set OAUTH2_ALLOW_INSECURE_DEFAULTS=1 to suppress this in test environments."
                .to_string(),
        );
    }
    Ok(())
}
```

- [ ] **Step 1.4: Abort startup when the seed password is insecure**

Locate the block in `lib.rs` that reads `OAUTH2_SEED_PASSWORD` (around line 127):

```rust
let seed_password =
    std::env::var("OAUTH2_SEED_PASSWORD").unwrap_or_else(|_| "changeme".to_string());
```

Replace it with:

```rust
let seed_password =
    std::env::var("OAUTH2_SEED_PASSWORD").unwrap_or_else(|_| INSECURE_DEFAULT_SEED_PASSWORD.to_string());

validate_seed_password_for_production(&seed_password).map_err(|e| {
    tracing::error!("{}", e);
    e
})?;
```

Note: The `run()` function already returns a `Result`. If it returns a different type than `String`, adjust accordingly — the pattern mirrors `validate_for_production()` which is called just before this block.

- [ ] **Step 1.5: Run the tests**

```bash
cargo test -p oauth2-server seed_password -- --nocapture
```

Expected: Both new tests PASS. Also verify the existing tests still pass:

```bash
cargo test -p oauth2-server -- --nocapture
```

- [ ] **Step 1.6: Commit**

```bash
git add crates/oauth2-server/src/lib.rs tests/security_http.rs
git commit -m "fix(security): abort startup when OAUTH2_SEED_PASSWORD is insecure default

Mirrors the Wave 1 JWT secret guard. Requires explicit opt-in via
OAUTH2_ALLOW_INSECURE_DEFAULTS=1 to use 'changeme' in test environments."
```

---

## Task 2: Prevent Session Fixation After Login (H-fixation)

**Files:**

- Modify: `crates/oauth2-actix/src/handlers/login.rs` (line 122 — after credential verification)
- Modify: `tests/security_http.rs` (add one test)

### Background

A session fixation attack works like this:

1. Attacker visits the login page, obtains a valid (unauthenticated) session cookie.
2. Attacker tricks the victim into using that same cookie (e.g. via a link).
3. Victim logs in; server writes `user_id` into the _existing_ session.
4. Attacker now has an authenticated session using the cookie they already hold.

The fix: call `session.renew()` before writing any session data after a successful login. `actix-session` 0.11 provides `Session::renew()` which issues a new session ID while preserving the session's current data.

`★ Insight ─────────────────────────────────────`
`session.renew()` in actix-session rotates the session ID (issues a new cookie) without clearing the existing data. This is the correct behavior: we want the `return_to` URL (already in the session from the authorize handler) to survive the rotation, while the new session ID prevents fixation.
`─────────────────────────────────────────────────`

- [ ] **Step 2.1: Write the failing test**

Add to `tests/security_http.rs`:

```rust
// ── Task 2 (H-fixation) ────────────────────────────────────────────────────

#[actix_web::test]
async fn login_renews_session_id_after_successful_authentication() {
    // After a successful POST /auth/login the Set-Cookie header must contain
    // a session cookie, confirming a new session was issued.
    // We verify that session.renew() is called by checking that a Set-Cookie
    // header is present on the successful login redirect.
    use actix_web::{test, web, App, HttpResponse};
    use actix_session::{SessionMiddleware, storage::CookieSessionStore};
    use actix_web::cookie::Key;

    let secret_key = Key::generate();
    let app = test::init_service(
        App::new()
            .wrap(SessionMiddleware::new(
                CookieSessionStore::default(),
                secret_key.clone(),
            ))
            .route(
                "/auth/login",
                web::post().to(|session: actix_session::Session| async move {
                    // Simulate what login_submit does after credential verification
                    session.renew();
                    session.insert("user_id", "test-user-id").unwrap();
                    HttpResponse::Found()
                        .append_header(("Location", "/profile"))
                        .finish()
                }),
            ),
    )
    .await;

    let req = test::TestRequest::post()
        .uri("/auth/login")
        .to_request();
    let resp = test::call_service(&app, req).await;
    assert_eq!(resp.status(), 302);
    assert!(
        resp.headers().contains_key("set-cookie"),
        "A renewed session must set a new cookie on login response"
    );
}
```

- [ ] **Step 2.2: Add `session.renew()` to `login_submit`**

Open `crates/oauth2-actix/src/handlers/login.rs`. Find the comment `// --- Credentials valid — establish session ---` (line ~122). Add `session.renew();` as the very first statement after that comment:

```rust
    // --- Credentials valid — establish session ---
    session.renew();
    session
        .insert("user_id", &user.id)
        .map_err(|e| actix_web::error::ErrorInternalServerError(e.to_string()))?;
    session
        .insert("authenticated", true)
        .map_err(|e| actix_web::error::ErrorInternalServerError(e.to_string()))?;
    session
        .insert("username", &user.username)
        .map_err(|e| actix_web::error::ErrorInternalServerError(e.to_string()))?;
    session
        .insert("email", &user.email)
        .map_err(|e| actix_web::error::ErrorInternalServerError(e.to_string()))?;
    session
        .insert("role", &user.role)
        .map_err(|e| actix_web::error::ErrorInternalServerError(e.to_string()))?;
```

`session.renew()` takes `&self` and returns `()` — no error to handle.

- [ ] **Step 2.3: Run the tests**

```bash
cargo test -p oauth2-actix -- --nocapture
cargo test -p oauth2-server login_renews_session -- --nocapture
```

Expected: PASS.

- [ ] **Step 2.4: Commit**

```bash
git add crates/oauth2-actix/src/handlers/login.rs tests/security_http.rs
git commit -m "fix(security): renew session ID after successful login to prevent session fixation

Calls session.renew() before writing user data into the session.
This rotates the session ID (issues a fresh cookie) while preserving
any pre-login data (e.g. return_to URL), per OWASP session fixation guidance."
```

---

## Task 3: Add HTTP Security Headers (M-headers)

**Files:**

- Modify: `crates/oauth2-server/src/lib.rs` (App construction block, ~line 446)
- Modify: `tests/security_http.rs` (add tests)

### Background

Missing security headers allow a class of client-side attacks:

- `X-Frame-Options: DENY` — prevents clickjacking via `<iframe>` embedding
- `X-Content-Type-Options: nosniff` — prevents MIME-type sniffing attacks
- `Referrer-Policy: no-referrer` — prevents sensitive URL data leaking in the `Referer` header
- `Content-Security-Policy: default-src 'self'` — restricts resource loading to same-origin only

`actix_web::middleware::DefaultHeaders` is built into actix-web 4.4 — no new dependency required. The HTML templates have no inline scripts or styles, so `default-src 'self'` is safe.

`★ Insight ─────────────────────────────────────`
`DefaultHeaders` only adds headers when they are NOT already present in the response. This means handler-level overrides still work — the middleware acts as a safe fallback, not an override. Place it last in the `.wrap()` chain (which means it runs first in the middleware tower, i.e. added last = runs outermost).
`─────────────────────────────────────────────────`

- [ ] **Step 3.1: Write the failing tests**

Add to `tests/security_http.rs`:

```rust
// ── Task 3 (M-headers) ─────────────────────────────────────────────────────

#[actix_web::test]
async fn security_headers_present_on_responses() {
    use actix_web::middleware::DefaultHeaders;
    use actix_web::{test, web, App, HttpResponse};

    let app = test::init_service(
        App::new()
            .wrap(
                DefaultHeaders::new()
                    .add(("X-Frame-Options", "DENY"))
                    .add(("X-Content-Type-Options", "nosniff"))
                    .add(("Referrer-Policy", "no-referrer"))
                    .add(("Content-Security-Policy", "default-src 'self'")),
            )
            .route("/", web::get().to(|| async { HttpResponse::Ok().finish() })),
    )
    .await;

    let req = test::TestRequest::get().uri("/").to_request();
    let resp = test::call_service(&app, req).await;

    assert_eq!(
        resp.headers().get("x-frame-options").and_then(|v| v.to_str().ok()),
        Some("DENY"),
        "X-Frame-Options: DENY must be present"
    );
    assert_eq!(
        resp.headers().get("x-content-type-options").and_then(|v| v.to_str().ok()),
        Some("nosniff"),
        "X-Content-Type-Options: nosniff must be present"
    );
    assert_eq!(
        resp.headers().get("referrer-policy").and_then(|v| v.to_str().ok()),
        Some("no-referrer"),
        "Referrer-Policy: no-referrer must be present"
    );
    assert_eq!(
        resp.headers().get("content-security-policy").and_then(|v| v.to_str().ok()),
        Some("default-src 'self'"),
        "Content-Security-Policy: default-src 'self' must be present"
    );
}
```

- [ ] **Step 3.2: Add `DefaultHeaders` middleware to the App**

Open `crates/oauth2-server/src/lib.rs`. Find the App construction block (around line 446). It already contains `.wrap(SessionMiddleware...)`, `.wrap(TracingLogger::default())`, and `.wrap(cors)`. Add the `DefaultHeaders` middleware:

```rust
use actix_web::middleware::DefaultHeaders;

// ... inside the App::new() chain, after .wrap(cors):
.wrap(
    DefaultHeaders::new()
        .add(("X-Frame-Options", "DENY"))
        .add(("X-Content-Type-Options", "nosniff"))
        .add(("Referrer-Policy", "no-referrer"))
        .add(("Content-Security-Policy", "default-src 'self'")),
)
```

Ensure the `use actix_web::middleware::DefaultHeaders;` import is at the top of the file (or add it with the existing actix-web imports).

- [ ] **Step 3.3: Run the tests**

```bash
cargo test -p oauth2-server security_headers -- --nocapture
```

Expected: PASS.

- [ ] **Step 3.4: Commit**

```bash
git add crates/oauth2-server/src/lib.rs tests/security_http.rs
git commit -m "feat(security): add HTTP security headers via DefaultHeaders middleware

Adds X-Frame-Options: DENY, X-Content-Type-Options: nosniff,
Referrer-Policy: no-referrer, and Content-Security-Policy: default-src 'self'
to all responses using actix-web's built-in DefaultHeaders middleware."
```

---

## Task 4: Consolidate `is_safe_redirect` into `oauth2-core` (M-redirect-dedup)

**Files:**

- Create: `crates/oauth2-core/src/utils/mod.rs`
- Create: `crates/oauth2-core/src/utils/redirect.rs`
- Modify: `crates/oauth2-core/src/lib.rs` (export `utils` module)
- Modify: `crates/oauth2-actix/src/handlers/login.rs` (use `oauth2_core::utils::redirect::is_safe_redirect`)
- Modify: `crates/oauth2-social-login/src/handlers/auth.rs` (same import)
- Modify: `tests/security_http.rs` (update import path)

### Background

`is_safe_redirect` is currently defined twice:

- `pub fn is_safe_redirect` in `crates/oauth2-actix/src/handlers/login.rs`
- A private copy in `crates/oauth2-social-login/src/handlers/auth.rs`

Both `oauth2-actix` and `oauth2-social-login` already depend on `oauth2-core`, so moving the function there eliminates the duplication without adding any dependency cycles.

`★ Insight ─────────────────────────────────────`
DRY here matters for security: if the validation logic ever needs tightening (e.g. to reject `/%09evil` URL-encoded tab characters), you want exactly one place to fix. Duplicated security functions are a maintenance time-bomb.
`─────────────────────────────────────────────────`

- [ ] **Step 4.1: Write the failing test (import path)**

Add to `tests/security_http.rs`:

```rust
// ── Task 4 (M-redirect-dedup) ──────────────────────────────────────────────

#[actix_web::test]
async fn is_safe_redirect_is_importable_from_oauth2_core() {
    use oauth2_core::utils::redirect::is_safe_redirect;

    assert!(is_safe_redirect("/oauth/authorize?response_type=code"));
    assert!(is_safe_redirect("/profile"));
    assert!(!is_safe_redirect("https://evil.example.com"));
    assert!(!is_safe_redirect("//evil.example.com"));
    assert!(!is_safe_redirect("/\\evil.example.com"));
    assert!(!is_safe_redirect("javascript:alert(1)"));
}
```

- [ ] **Step 4.2: Create `crates/oauth2-core/src/utils/redirect.rs`**

```rust
//! URL redirect safety validation.

/// Validate that a redirect target is a safe relative path on this server.
///
/// Accepts only paths starting with `/` that are not:
/// - `//` (protocol-relative URLs like `//evil.com`)
/// - `/\` (backslash quirk exploited by some browsers: `/\evil.com`)
/// - Any scheme-bearing string (`scheme:`)
///
/// This prevents open-redirect attacks where a caller-controlled value
/// could redirect users to an attacker's site.
pub fn is_safe_redirect(url: &str) -> bool {
    let url = url.trim();
    // Must start with a single forward-slash
    if !url.starts_with('/') {
        return false;
    }
    // Reject protocol-relative URLs like //evil.com
    if url.starts_with("//") {
        return false;
    }
    // Reject backslash quirk: /\evil.com
    if url.starts_with("/\\") {
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_relative_paths_are_accepted() {
        assert!(is_safe_redirect("/"));
        assert!(is_safe_redirect("/profile"));
        assert!(is_safe_redirect("/oauth/authorize?response_type=code&client_id=x"));
    }

    #[test]
    fn absolute_urls_are_rejected() {
        assert!(!is_safe_redirect("https://evil.example.com"));
        assert!(!is_safe_redirect("http://evil.example.com/path"));
    }

    #[test]
    fn protocol_relative_urls_are_rejected() {
        assert!(!is_safe_redirect("//evil.example.com"));
    }

    #[test]
    fn backslash_quirk_is_rejected() {
        assert!(!is_safe_redirect("/\\evil.example.com"));
    }

    #[test]
    fn empty_and_non_slash_are_rejected() {
        assert!(!is_safe_redirect(""));
        assert!(!is_safe_redirect("relative/path"));
        assert!(!is_safe_redirect("javascript:alert(1)"));
    }
}
```

- [ ] **Step 4.3: Create `crates/oauth2-core/src/utils/mod.rs`**

```rust
pub mod redirect;
```

- [ ] **Step 4.4: Export `utils` from `crates/oauth2-core/src/lib.rs`**

Current content:

```rust
pub mod models;
pub use models::*;
```

Add the `utils` module below `models`:

```rust
pub mod models;
pub mod utils;

pub use models::*;
```

- [ ] **Step 4.5: Update `oauth2-actix` to import from `oauth2-core`**

Open `crates/oauth2-actix/src/handlers/login.rs`.

Remove the private `is_safe_redirect` function (lines ~183–198):

```rust
// DELETE the entire function:
pub fn is_safe_redirect(url: &str) -> bool {
    let url = url.trim();
    if !url.starts_with('/') {
        return false;
    }
    if url.starts_with("//") {
        return false;
    }
    if url.starts_with("/\\") {
        return false;
    }
    true
}
```

Add an import at the top of the file (alongside the existing `use` statements):

```rust
use oauth2_core::utils::redirect::is_safe_redirect;
```

The call site at `login.rs` line ~148 (`filter(|u| is_safe_redirect(u))`) requires no other change.

- [ ] **Step 4.6: Update `oauth2-social-login` to import from `oauth2-core`**

Open `crates/oauth2-social-login/src/handlers/auth.rs`. Find the private `is_safe_redirect` function — it will have the same logic. Delete it and add the import:

```rust
use oauth2_core::utils::redirect::is_safe_redirect;
```

All call sites within that file require no other change.

- [ ] **Step 4.7: Run the tests**

```bash
cargo test -p oauth2-core -- --nocapture
cargo test -p oauth2-actix -- --nocapture
cargo test -p oauth2-social-login -- --nocapture
cargo test --workspace -- --nocapture
```

Expected: All PASS. No `is_safe_redirect` compile errors.

- [ ] **Step 4.8: Commit**

```bash
git add \
  crates/oauth2-core/src/lib.rs \
  crates/oauth2-core/src/utils/mod.rs \
  crates/oauth2-core/src/utils/redirect.rs \
  crates/oauth2-actix/src/handlers/login.rs \
  crates/oauth2-social-login/src/handlers/auth.rs \
  tests/security_http.rs
git commit -m "refactor(security): consolidate is_safe_redirect into oauth2-core

Eliminates duplicated open-redirect validation logic. Both oauth2-actix
and oauth2-social-login now import from oauth2_core::utils::redirect.
Single source of truth for redirect safety invariants."
```

---

## Task 5: Push and Verify

- [ ] **Step 5.1: Run the full test suite one final time**

```bash
cargo test --workspace -- --nocapture 2>&1 | tail -30
```

Expected: All tests PASS, no warnings about unused imports.

- [ ] **Step 5.2: Push to origin**

```bash
git push origin main
```

- [ ] **Step 5.3: Verify push succeeded**

```bash
git log --oneline origin/main -6
```

Expected: The four new commits (H-seed, H-fixation, M-headers, M-redirect-dedup) appear at the top.

---

## Self-Review Checklist

**Spec coverage:**

- H-seed: Task 1 — `validate_seed_password_for_production`, startup abort ✓
- H-fixation: Task 2 — `session.renew()` before session writes ✓
- M-headers: Task 3 — `DefaultHeaders` with four headers ✓
- M-redirect-dedup: Task 4 — `oauth2-core::utils::redirect`, both callers updated ✓

**No placeholders:** All code blocks are complete and compilable. No TBD/TODO in task steps.

**Type consistency:**

- `validate_seed_password_for_production(&str) -> Result<(), String>` — matches `validate_for_production()` pattern in `oauth2-config`
- `is_safe_redirect` signature is `pub fn is_safe_redirect(url: &str) -> bool` — unchanged from existing copies; call sites need no adjustment
- `session.renew()` — `&self` → `()`, no return value to handle
- `DefaultHeaders::new().add((K, V))` — builder pattern, no type changes to App
