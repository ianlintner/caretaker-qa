# Copilot Instructions — rust-oauth2-server

## CI Gate Checklist

Before considering any code change complete, **always** run the full CI
gate sequence locally and fix any failures:

```bash
# 1. Formatting (must exit 0)
cargo fmt --all -- --check

# 2. Lints — warnings are errors (must exit 0)
cargo clippy --all-targets --all-features -- -D warnings

# 3. Tests (must exit 0)
cargo test --verbose --all-features --locked
```

If `cargo fmt` fails, run `cargo fmt --all` to auto-fix, then re-check.

## Common Pitfalls

- **Long lines**: `tracing::debug!(...)` with multiple fields and chained
  `.map_err(|e| ...)` calls frequently exceed the line-length limit.
  Always verify formatting after adding tracing or error-mapping code.
- **Conditional compilation**: Variables mutated only inside
  `#[cfg(feature = "...")]` blocks produce `unused_mut` warnings when
  the feature is off. Annotate them with `#[allow(unused_mut)]`.
- **Test app_data**: Any new `web::Data<T>` parameter added to a handler
  must also be injected in every test setup in `tests/security_http.rs`
  (there are 15+ test functions with independent `App::new()` builders).

## Project Structure

- Workspace with multiple crates under `crates/`.
- Feature flags: `redis-cache`, `mongo`, `sqlx` (default).
- Actix-web 4 + Actix actors for the HTTP/actor layer.
- Tests live in `tests/` (integration) and inline `#[cfg(test)]` modules.
