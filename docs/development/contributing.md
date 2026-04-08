# Contributing

Thanks for helping. This repo is a workspace with a lot of surface area, so the shortest path to a good contribution is: change the smallest thing that solves the problem, update the real source of truth, and run the full gate before you declare victory.

## Required local gate

Run these before opening or updating a PR:

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --verbose --all-features --locked
```

If formatting fails, run `cargo fmt --all` and then re-run the gate.

If you changed docs, also run:

```bash
python3 -m mkdocs build --strict
```

## Normal workflow

1. branch from `main`
2. make the smallest code change that fixes the issue
3. update tests and docs in the same branch
4. run the local gate
5. open a PR with the why, the change, and how you verified it

Conventional commits are welcome, but correctness beats poetry.

## Where changes usually belong

| Change type                        | Start here                                                          | Usually update docs here                                       |
| ---------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------- |
| OAuth routes, handlers, middleware | `crates/oauth2-actix/`                                              | `docs/usage/oauth2-oidc.md` or `docs/usage/admin-api.md`       |
| Route registration / app wiring    | `crates/oauth2-server/src/lib.rs`                                   | `docs/development/architecture.md`, relevant usage/ops page    |
| Config keys or defaults            | `crates/oauth2-config/`, `.env.example`, `application.conf.example` | `docs/getting-started/configuration.md`                        |
| Storage behavior                   | `crates/oauth2-storage-*`                                           | `docs/development/extending.md`                                |
| Deployment/runtime assets          | `docker-compose*.yml`, `k8s/`, `scripts/`                           | `docs/operations/deployment.md`, `docs/operations/runbooks.md` |
| MCP wrapper                        | `mcp-server/src/index.js`                                           | `mcp-server/README.md`, `docs/usage/integrations.md`           |
| Docker, Kubernetes, benchmarks     | `DOCKERHUB.md`, `k8s/README.md`, `benchmarks/README.md`             | link from the smallest relevant docs page                      |

## Docs governance

To keep drift down, treat these files as canonical before you touch prose:

- `.env.example`
- `application.conf.example`
- `crates/oauth2-server/src/lib.rs`
- generated OpenAPI / Swagger surface
- `mcp-server/src/index.js`

Documentation rules for this repo:

- keep the README as a front door, not a second manual
- keep the MkDocs site task-oriented and short
- keep specialist detail in repo-local guides (`DOCKERHUB.md`, `k8s/README.md`, `mcp-server/README.md`, `benchmarks/README.md`)
- delete stale duplicate pages instead of preserving them “just in case”
- keep deep examples next to code or repo-local READMEs, not copied into many docs pages
- when behavior changes, update the smallest relevant docs page instead of adding another one

## Known repo pitfalls

- new `web::Data<T>` handler dependencies must also be injected in `tests/security_http.rs`
- long `tracing::*` calls and chained `map_err` blocks often need formatting help
- variables mutated only inside `#[cfg(feature = ...)]` sections may need `#[allow(unused_mut)]`
- feature-gated behavior must be documented in both `.env.example` and `application.conf.example`

## What a good PR includes

- the code change
- the relevant tests
- any config updates
- the smallest matching docs update
- a short verification note with the commands you ran

## Need orientation?

Start with:

- [Architecture](architecture.md)
- [Extending](extending.md)
- [Testing](testing.md)

Less ceremony, more correct software.
