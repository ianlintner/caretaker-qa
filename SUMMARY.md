# Project Summary - Rust OAuth2 Server

## What this repo is

A Rust + Actix OAuth2/OIDC server assembled from a Cargo workspace.

Core facts:

- `src/main.rs` is a thin delegating binary that calls `oauth2_server::run()`
- default local storage is SQLite
- Postgres is supported through SQLx
- MongoDB is optional behind `--features mongo`
- rate limiting, resilience middleware, and eventing are shipped
- Kustomize overlays are shipped; Helm charts are not

## Canonical docs set

The repository deliberately keeps a smaller docs surface now. The canonical pages are:

- `README.md`
- `docs/index.md`
- `docs/getting-started/quickstart.md`
- `docs/getting-started/configuration.md`
- `docs/usage/oauth2-oidc.md`
- `docs/usage/admin-api.md`
- `docs/usage/integrations.md`
- `docs/operations/deployment.md`
- `docs/operations/observability.md`
- `docs/operations/runbooks.md`
- `docs/development/architecture.md`
- `docs/development/extending.md`
- `docs/development/testing.md`
- `docs/development/contributing.md`

## Source of truth

When docs and assumptions disagree, check these files first:

- `.env.example`
- `application.conf.example`
- `crates/oauth2-server/src/lib.rs`
- generated Swagger / OpenAPI output
- `mcp-server/src/index.js`

## Behavior that commonly drifts in docs

- refresh-token and password grants exist in code paths but are disabled by default
- Google, Microsoft, GitHub, and Azure social login routes are wired; Okta/Auth0 currently return `503`
- rate limiting is implemented and configurable
- the root route redirects to `/profile`
- admin routes live under `/admin/*` and are protected by `AdminGuard`

## Contributor gate

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --verbose --all-features --locked
```

If you need a longer narrative, use the docs site. This file exists to keep future summaries from drifting into fan fiction.
- Admin user management UI
- Audit log viewer
- OAuth2 device flow
- JWT key rotation
- Redis session store

## Performance Considerations

- Actor model for concurrent request handling
- Connection pooling for database access
- Session management with secure cookies
- Efficient JWT validation
- Prometheus metrics with minimal overhead

## Security Best Practices

- Always use HTTPS in production
- Store secrets securely (use secret management services)
- Rotate JWT secrets regularly
- Implement rate limiting
- Monitor audit logs
- Keep dependencies updated
- Use strong client secrets
- Validate redirect URIs strictly

## License

MIT OR Apache-2.0

## Credits

Inspired by:

- [Keycloak](https://www.keycloak.org/) - Feature set reference
- [RFC 6749](https://tools.ietf.org/html/rfc6749) - OAuth 2.0 Authorization Framework
- [RFC 7636](https://tools.ietf.org/html/rfc7636) - PKCE
- [RFC 7662](https://tools.ietf.org/html/rfc7662) - Token Introspection
- [RFC 7009](https://tools.ietf.org/html/rfc7009) - Token Revocation
- [RFC 8414](https://tools.ietf.org/html/rfc8414) - Authorization Server Metadata

## Support

- Repository: <https://github.com/ianlintner/rust_oauth2_server>
- Issues: <https://github.com/ianlintner/rust_oauth2_server/issues>
- Documentation: See `/docs` directory

---

**Project Status**: ✅ Production-ready with comprehensive feature set complete!
