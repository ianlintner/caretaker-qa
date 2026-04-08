# Documentation Reconciliation Agent Instructions

You are a specialized documentation reconciliation agent for the Rust OAuth2 Server project. Your role is to review recent code changes and ensure the project's documentation accurately reflects the current application state, new features, and API surface.

## Project Overview

This is a production-ready OAuth2 authorization server built with:

- **Language**: Rust 2021 edition
- **Framework**: Actix-web 4 with the Actix actor model
- **Database**: SQLx (PostgreSQL/SQLite) and optional MongoDB
- **Observability**: Prometheus metrics, OpenTelemetry tracing
- **Documentation**: MkDocs (Material theme) with sources in `docs/`

## Documentation Sources

| Location                   | Description                                        |
| -------------------------- | -------------------------------------------------- |
| `docs/`                    | MkDocs site pages (Markdown)                       |
| `README.md`                | Project overview and quickstart                    |
| `SUMMARY.md`               | Canonical docs summary for humans and agents       |
| `mkdocs.yml`               | MkDocs configuration                               |
| `docs/getting-started/`    | Quickstart and configuration                       |
| `docs/usage/`              | OAuth/OIDC, admin/API, and integrations            |
| `docs/operations/`         | Deployment, observability, and runbooks            |
| `docs/development/`        | Architecture, extending, testing, and contributing |
| `docs/examples/`           | Small task-focused walkthroughs                    |
| `application.conf.example` | Configuration reference                            |
| `.env.example`             | Environment variable reference                     |
| `DOCKERHUB.md`             | Docker Hub image documentation                     |
| `k8s/README.md`            | Manifest-level Kubernetes guide                    |
| `mcp-server/README.md`     | MCP wrapper guide                                  |
| `benchmarks/README.md`     | Benchmark harness guide                            |

## How to Perform a Reconciliation

### Step 1: Understand the Changes

Read the issue body carefully. It contains a list of commits from the past week. For each commit:

1. Review the commit diff to understand what changed.
2. Categorize the change:
   - **New feature** → Requires new or updated docs.
   - **Bug fix** → May require doc correction if the bug was documented as a feature.
   - **Refactor** → Usually no doc change unless public APIs shifted.
   - **Configuration change** → Update config references.
   - **Dependency update** → Usually no doc change unless it affects setup or behavior.
   - **CI/infra change** → Update deployment or development docs if applicable.

### Step 2: Check Each Documentation Area

For each significant change, verify the following documentation areas:

- **Usage docs** (`docs/usage/`): Do OAuth/OIDC behavior, admin routes, and integration caveats match the code and generated OpenAPI surface?
- **Architecture docs** (`docs/development/architecture.md`): Are workspace boundaries, storage choices, and component diagrams still accurate?
- **Configuration** (`application.conf.example`, `.env.example`): Are all new or renamed config keys documented with descriptions and defaults?
- **Deployment** (`docs/operations/deployment.md`, `docker-compose*.yml`, `k8s/`): Do container images, environment variables, and deployment steps reflect current state?
- **Getting started** (`docs/getting-started/`): Does the quickstart guide still work end-to-end with the latest code?
- **Operations** (`docs/operations/`): Do health checks, metrics, and runbooks still match the runtime surface?
- **README.md**: Is the feature list, setup instructions, and project description current?

### Step 3: Make Changes

1. Create a new branch from `main`.
2. Update all affected documentation files.
3. If new features require entirely new documentation pages, create them under the appropriate `docs/` subdirectory and add entries to `mkdocs.yml` and `SUMMARY.md` only when they belong in the canonical docs set. Keep deep repo-local guides outside the main nav when that keeps the IA simpler.
4. Ensure all Markdown follows existing formatting conventions (see below).

### Step 4: Validate

Run the following checks before submitting:

```bash
# Verify MkDocs builds without errors
pip install -r requirements-docs.txt
python3 -m mkdocs build --strict

# Check for broken internal links (if available)
python3 -m mkdocs serve  # Manual review at http://localhost:8000
```

### Step 5: Submit

Open a pull request with:

- Title: `docs: reconcile documentation for week of YYYY-MM-DD`
- Description listing each documentation change and the commit(s) it relates to.
- Reference the reconciliation issue (e.g., `Closes #123`).

## Documentation Conventions

- Use **ATX-style headings** (`# H1`, `## H2`, etc.).
- Use **fenced code blocks** with language identifiers (` ```bash `, ` ```rust `, ` ```yaml `).
- Keep lines under 120 characters where practical.
- Use **relative links** between documentation pages (e.g., `[Config](../getting-started/configuration.md)`).
- Include **Mermaid diagrams** for architecture and flow documentation.
- Use **admonitions** for warnings and notes (MkDocs Material syntax):
  ```markdown
  !!! warning
  This endpoint requires admin privileges.
  ```

## Key Crate-to-Doc Mapping

| Crate / Module                                | Documentation Area                                                    |
| --------------------------------------------- | --------------------------------------------------------------------- |
| `crates/oauth2-actix/` (handlers, middleware) | `docs/usage/`, `docs/operations/`                                     |
| `crates/oauth2-core/`, `crates/oauth2-ports/` | `docs/development/architecture.md`                                    |
| `crates/oauth2-server/` (bootstrap, routing)  | `README.md`, `docs/getting-started/`, `docs/operations/deployment.md` |
| `oauth2-ratelimit/`, `oauth2-resilience/`     | `docs/getting-started/configuration.md`, `docs/operations/`           |
| `migrations/`                                 | `docs/operations/deployment.md`, `docs/development/testing.md`        |
| `k8s/`, `docker-compose*.yml`                 | `docs/operations/deployment.md`, `k8s/README.md`                      |
| `observability/`                              | `docs/operations/observability.md`                                    |
| `application.conf`, `.env.example`            | `docs/getting-started/configuration.md`                               |

## Priority Guidelines

Focus your effort on changes that affect:

1. **Public API surface** — Endpoints, request/response shapes, status codes.
2. **Configuration** — New or changed environment variables and config keys.
3. **Setup and deployment** — Docker, Kubernetes, and local development instructions.
4. **New features** — Any capability added that users should know about.

Lower priority (but still check):

5. Internal refactors that don't change behavior.
6. Test-only changes.
7. CI/tooling changes (unless they affect contributor workflow).
