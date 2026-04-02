# Documentation Overhaul — Design Spec

**Date:** 2026-04-02
**Status:** Draft
**Audience:** Developers integrating the OAuth2 server + Contributors/forkers

## Problem

The documentation has 3 critical inaccuracies, 8+ files with stale endpoint paths, 9 undocumented security features, and a 10-section navigation that is too complex. The README is 794 lines and duplicates most of the mkdocs content.

## Goals

1. Fix all factual inaccuracies (code vs docs mismatches)
2. Document Wave 1 & Wave 2 security features
3. Consolidate mkdocs navigation from 10 sections to 5
4. Slim the README to a GitHub landing page, not a second reference site
5. Fill stub pages (admin dashboard/clients/tokens)

## Non-Goals

- Rewriting flow/observability docs (already accurate)
- Adding new doc pages beyond what's needed for security coverage
- Changing the mkdocs theme or tooling

---

## 1. Navigation Restructure

Collapse 10 top-level sections into 5 using the "funnel" model: learn, use, deploy, contribute.

### Current (10 sections)

Home, Getting Started, Guides, Reference, Architecture, Observability, Deployment, Operations, Development

### New (5 sections)

```yaml
nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
      - Quick Start: getting-started/quickstart.md
      - Configuration: getting-started/configuration.md
      - Social Login Setup: getting-started/social-login-setup.md
  - Using the Server:
      - OAuth2 Flows:
          - Authorization Code: flows/authorization-code.md
          - Client Credentials: flows/client-credentials.md
          - Password Grant: flows/password.md
          - Refresh Token: flows/refresh-token.md
      - API Reference:
          - Endpoints: api/endpoints.md
          - OpenAPI (Swagger UI): api/openapi.md
          - Authentication: api/authentication.md
          - Error Handling: api/errors.md
      - Admin Panel:
          - Dashboard: admin/dashboard.md
          - Client Management: admin/clients.md
          - Token Management: admin/tokens.md
      - Eventing:
          - Overview: eventing.md
          - Examples: examples/eventing.md
      - Cookbook:
          - Service-to-Service: examples/service-to-service.md
  - Deploying & Operating:
      - Docker Hub Image: deployment/dockerhub.md
      - Docker: deployment/docker.md
      - Kubernetes: deployment/kubernetes.md
      - Production & Security: deployment/production.md
      - Metrics: observability/metrics.md
      - SLOs: observability/slos.md
      - Tracing & Logging: observability/tracing-and-logging.md
      - Health Checks: observability/health.md
      - Runbooks: operations/runbooks.md
  - Development:
      - Architecture Overview: architecture/overview.md
      - Actor Model: architecture/actors.md
      - Database: architecture/database.md
      - Contributing: development/contributing.md
      - Testing: development/testing.md
      - CI/CD: development/cicd.md
```

### Merges

- `observability/tracing.md` + `observability/logging.md` → `observability/tracing-and-logging.md`
- "Production" page renamed to "Production & Security" (absorbs new security content)
- Old files kept as-is on disk (nav controls visibility); tracing/logging merge creates one new file

---

## 2. Content Fixes — Stale Paths

All references to `POST /clients/register` must become `POST /admin/clients/register` with a note about admin authentication.

### Files to update

| File | Location |
|------|----------|
| README.md | Lines 541, 611 |
| docs/index.md | Lines 183, 296 |
| docs/getting-started/quickstart.md | Line 33 |
| docs/api/endpoints.md | Line 238 |
| docs/admin/clients.md | Line 5 |
| docs/examples/eventing.md | Line 72 |
| SUMMARY.md | Line 190 |
| AGENTIC_QUICKSTART.md | Line 169 |

All curl examples must include admin authentication (session cookie or equivalent).

---

## 3. Content Fixes — Critical Mismatches

### 3a. CORS env var name

**File:** `docs/getting-started/configuration.md` (line 258)
**Wrong:** `OAUTH2_CORS_ALLOWED_ORIGINS`
**Correct:** `OAUTH2_ALLOWED_ORIGINS`

### 3b. CORS default behavior

**File:** `docs/getting-started/configuration.md` (line 258)
**Wrong:** Default is `*` (allow all)
**Correct:** Default is empty (deny all cross-origin requests)

### 3c. `GET /` redirect target

**File:** README.md (line 516)
**Wrong:** "Redirects to login page"
**Correct:** "Redirects to profile page"

### 3d. Okta/Auth0 status

**Files:** `docs/getting-started/social-login-setup.md`, README.md
**Issue:** Described as fully functional, but code returns HTTP 503
**Fix:** Add admonition warning: "Not yet implemented — returns 503"

### 3e. Rate limiting consistency

**Files:** `docs/api/endpoints.md`, `docs/getting-started/configuration.md`
**Fix:** Mark as "(Planned)" consistently in both files

### 3f. Contributing project structure

**File:** `docs/development/contributing.md` (lines 69-84)
**Issue:** Shows flat `src/` layout
**Fix:** Update to `crates/` workspace layout matching actual project

### 3g. Session key length

**File:** `docs/getting-started/configuration.md` (line 129)
**Wrong:** "min 64 chars"
**Correct:** "128 hex characters (64 bytes, hex-encoded)"

---

## 4. Missing Endpoints in README

Add to README endpoint list:

| Endpoint | Description |
|----------|-------------|
| `GET/POST /oauth/userinfo` | OpenID Connect UserInfo |
| `GET /.well-known/jwks.json` | JSON Web Key Set |
| `GET /profile` | User profile page |
| `POST /auth/login` | Login form submission |
| `POST /events/ingest` | Event ingestion |
| `GET /events/health` | Event system health |
| `/admin/api/*` routes | Admin API (dashboard, clients, tokens, users) |

---

## 5. Missing Metrics in README

Add to README metrics list:

- `oauth2_server_http_requests_total_by_route` (CounterVec: method/route/status)
- `oauth2_server_http_request_duration_seconds_by_route` (HistogramVec: method/route/status)
- `oauth2_server_oauth_authorization_codes_issued` (IntCounter)
- `oauth2_server_oauth_failed_authentications` (IntCounter)

---

## 6. Security Documentation (New Content)

### 6a. Production & Security page

Expand `docs/deployment/production.md` with a "Security Features" section covering:

1. **Startup Validation**
   - `validate_for_production()`: aborts if JWT secret is insecure default or < 32 bytes
   - `validate_seed_password_for_production()`: aborts if seed password is "changeme"
   - Bypass: `OAUTH2_ALLOW_INSECURE_DEFAULTS=1` (development only)

2. **HTTP Security Headers** (applied by default via `DefaultHeaders`)
   - `X-Frame-Options: DENY`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: no-referrer`
   - `Content-Security-Policy` (configured for CDN resources used by templates)

3. **CORS Policy**
   - Fail-closed by default (denies all cross-origin)
   - Configure via `OAUTH2_ALLOWED_ORIGINS` (comma-separated list)

4. **Open Redirect Prevention**
   - `is_safe_redirect()` validates `return_to` parameters
   - Only allows redirects to the server's own origin

5. **Session Security**
   - Session ID renewed after login (prevents session fixation)
   - Secure cookie attributes in production

6. **Admin Authentication**
   - All `/admin/*` routes require `AdminGuard` middleware
   - Unauthenticated requests redirect to `/auth/login`

7. **JWT Secret Enforcement**
   - Must be >= 32 characters
   - Must not be the default insecure value
   - Server refuses to start otherwise

### 6b. README Security section update

Replace current Security bullets (README lines 102-111) with updated list including all Wave 1 & 2 features.

### 6c. Configuration doc additions

Add to `docs/getting-started/configuration.md`:

| Variable | Description | Default |
|----------|-------------|---------|
| `OAUTH2_ALLOW_INSECURE_DEFAULTS` | Skip production validation (dev only) | unset |
| `OAUTH2_SEED_PASSWORD` | Initial admin user password | "changeme" (aborts in prod) |
| `OAUTH2_SEED_USERNAME` | Initial admin username | — |
| `OAUTH2_SEED_EMAIL` | Initial admin email | — |
| `OAUTH2_ID_TOKEN_PRIVATE_KEY_PEM` | RS256 private key for id_token signing | — |
| `OAUTH2_ID_TOKEN_KID` | Key ID for JWKS | — |
| `OAUTH2_ID_TOKEN_ALG` | Signing algorithm (RS256/HS256) | HS256 |

### 6d. Architecture overview update

Add security features to the feature list in `docs/architecture/overview.md`.

---

## 7. Tracing + Logging Merge

Combine `docs/observability/tracing.md` and `docs/observability/logging.md` into `docs/observability/tracing-and-logging.md`.

Structure:
- Intro (both use `tracing` + `tracing-subscriber`)
- Structured Logging section (from logging.md)
- Distributed Tracing section (from tracing.md)
- Configuration reference (combined env vars)

Old files remain on disk but are removed from nav.

---

## 8. README Slimming

Current: 794 lines. Target: ~300 lines.

### Keep

- Overview + badges + screenshot
- Feature bullet list (compact, no sub-sections)
- Mermaid overview diagram
- Quick install (clone, migrate, run — 6 lines)
- Corrected endpoint list
- Architecture diagram
- Brief config example (HOCON + env var, 20 lines max)
- Links to docs, contributing, license

### Remove (already covered in mkdocs)

- Full HOCON configuration blocks (~200 lines of social login config)
- Detailed social login env var sections (~100 lines)
- Detailed API examples (covered by quickstart.md)
- E2E docker compose instructions (covered by deployment docs)
- Full metrics list with descriptions (covered by observability docs)
- OpenTelemetry Jaeger example (covered by tracing docs)
- Detailed testing commands (covered by testing.md)

### Add

- "Full Documentation" link pointing to mkdocs site
- Security highlights (brief list)
- Corrected endpoints including userinfo, JWKS, admin routes

---

## 9. Index Page Slimming

Current: 357 lines with heavy redundancy.

### Keep

- Intro paragraph
- Feature highlights (compact)
- Flow overview diagrams
- "Next Steps" links (5 items)

### Remove

- Inline "Documentation Structure" section (sidebar nav handles this)
- Duplicate "Example Usage" section (quickstart covers this)
- Duplicate "Key Features" section (already in feature highlights)
- "Monitoring" section (covered by observability docs)
- "Support and Community" boilerplate

---

## 10. Admin Stub Pages

Expand the three admin stub pages with actual content:

### `docs/admin/dashboard.md` (currently 17 lines)

Add:
- How to access (`/admin`, requires admin role)
- AdminGuard authentication requirement
- Available dashboard views (clients, tokens, users)
- Admin API endpoints list

### `docs/admin/clients.md` (currently 13 lines)

Add:
- Corrected endpoint: `POST /admin/clients/register`
- Admin authentication requirement
- Client registration request/response examples
- Client deletion via `DELETE /admin/api/clients/{id}`

### `docs/admin/tokens.md` (currently 15 lines)

Add:
- Token listing via admin API
- Token revocation via `POST /admin/api/tokens/{id}/revoke`
- Admin authentication requirement

---

## Summary of Changes

| Category | Files affected | Type |
|----------|---------------|------|
| Nav restructure | mkdocs.yml | Edit |
| Stale paths | 8 files | Edit |
| Critical mismatches | 4 files | Edit |
| Missing endpoints | README.md | Edit |
| Missing metrics | README.md | Edit |
| Security docs | production.md, configuration.md, overview.md, README.md | Edit + new content |
| Tracing + logging merge | New file, nav update | New + edit |
| README slimming | README.md | Major edit |
| Index slimming | docs/index.md | Major edit |
| Admin stubs | 3 files | Expand |
| Contributing structure | contributing.md | Edit |

Total: ~20 files touched, 1 new file created, 0 files deleted.
