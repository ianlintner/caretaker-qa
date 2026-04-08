# Rust OAuth2 Server

[![CI](https://github.com/ianlintner/rust-oauth2-server/actions/workflows/ci.yml/badge.svg)](https://github.com/ianlintner/rust-oauth2-server/actions/workflows/ci.yml)

Self-hosted OAuth2 and OIDC in Rust with Actix, an admin UI, generated OpenAPI, eventing, and Kubernetes-ready deployment assets.

## Start in 60 seconds

```bash
cp .env.example .env
# set OAUTH2_JWT_SECRET, OAUTH2_SESSION_KEY, and OAUTH2_SEED_PASSWORD
cargo run
```

Then open:

- app: `http://localhost:8080`
- login: `http://localhost:8080/auth/login`
- admin: `http://localhost:8080/admin`
- Swagger UI: `http://localhost:8080/swagger-ui`

The default local path uses SQLite. If you want Postgres plus the supporting services, use `docker compose up -d` instead.

## What actually ships

- OAuth2: Authorization Code + PKCE, Client Credentials, introspection, revocation
- OIDC: discovery, JWKS, UserInfo
- Admin surface: HTML dashboard plus JSON admin API
- Operations: `/health`, `/ready`, `/metrics`, OpenTelemetry export
- Runtime controls: rate limiting, eventing, resilience middleware, Redis-backed distributed profile
- Deployment assets: Docker, Docker Compose, Kustomize overlays under `k8s/`

Important reality checks:

- refresh-token and password grants are present in code paths but disabled by default
- Google, Microsoft, GitHub, and Azure login flows are wired; `/auth/login/azure` prefers `OAUTH2_AZURE_*` config and falls back to Microsoft if unset; Okta/Auth0 currently return `503`
- the repo ships Kustomize manifests, not Helm charts

## Docs by job

- run it locally: [`docs/getting-started/quickstart.md`](docs/getting-started/quickstart.md)
- configure it: [`docs/getting-started/configuration.md`](docs/getting-started/configuration.md)
- integrate a client: [`docs/usage/oauth2-oidc.md`](docs/usage/oauth2-oidc.md)
- manage/administer it: [`docs/usage/admin-api.md`](docs/usage/admin-api.md)
- deploy and operate it: [`docs/operations/deployment.md`](docs/operations/deployment.md), [`docs/operations/observability.md`](docs/operations/observability.md), [`docs/operations/runbooks.md`](docs/operations/runbooks.md)
- extend the workspace: [`docs/development/architecture.md`](docs/development/architecture.md), [`docs/development/extending.md`](docs/development/extending.md)
- contribute safely: [`docs/development/testing.md`](docs/development/testing.md), [`docs/development/contributing.md`](docs/development/contributing.md)

Deep repo-local guides intentionally live outside the docs-site nav:

- Kubernetes: [`k8s/README.md`](k8s/README.md)
- prebuilt container image: [`DOCKERHUB.md`](DOCKERHUB.md)
- MCP wrapper: [`mcp-server/README.md`](mcp-server/README.md)
- benchmark harness: [`benchmarks/README.md`](benchmarks/README.md)

## Workspace shape

The server is a Cargo workspace, not a single monolith:

- `crates/oauth2-core` — domain types
- `crates/oauth2-ports` — storage/integration traits
- `crates/oauth2-actix` — handlers, middleware, actors
- `crates/oauth2-server` — runtime assembly and route wiring
- `crates/oauth2-events` / `oauth2-ratelimit` / `oauth2-resilience` — operational behavior
- `mcp-server/` — separate Node.js MCP wrapper

If you are changing behavior, the main source-of-truth files are:

- `.env.example`
- `application.conf.example`
- `crates/oauth2-server/src/lib.rs`
- `mcp-server/src/index.js`

## Contributor gate

Before considering any change done, run the same local gates CI expects:

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --verbose --all-features --locked
```

If you changed docs, also run:

```bash
python3 -m mkdocs build --strict
```

That’s the short front door. The rest of the old manual got evicted on purpose.
