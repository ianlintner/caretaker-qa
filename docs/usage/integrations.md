# Integrations

This project has three major integration surfaces beyond the core OAuth endpoints:

1. social login providers
2. the eventing subsystem
3. the standalone MCP server

## Social login

| Provider | Status | Routes |
| --- | --- | --- |
| Google | Shipped | `/auth/login/google`, `/auth/callback/google` |
| Microsoft | Shipped | `/auth/login/microsoft`, `/auth/callback/microsoft` |
| GitHub | Shipped | `/auth/login/github`, `/auth/callback/github` |
| Azure AD | Shipped | `/auth/login/azure` reuses the Microsoft flow |
| Okta | Not implemented | `/auth/login/okta` currently returns HTTP 503 |
| Auth0 | Not implemented | `/auth/login/auth0` currently returns HTTP 503 |

Minimum provider configuration is just the provider credentials and redirect URI. See `.env.example` and `application.conf.example` for the exact variable names.

Example for Google:

```bash
export OAUTH2_GOOGLE_CLIENT_ID=your-client-id
export OAUTH2_GOOGLE_CLIENT_SECRET=your-client-secret
export OAUTH2_GOOGLE_REDIRECT_URI=http://localhost:8080/auth/callback/google
```

## Eventing

The server can emit auth events and also ingest external event envelopes.

### Runtime behavior

- eventing is enabled by default
- the default backend is `in_memory`
- filtering modes are `allow_all`, `include`, and `exclude`
- the health probe is `GET /events/health`
- external ingestion is `POST /events/ingest`

### Backends

| Backend | Status | How to enable |
| --- | --- | --- |
| `in_memory` | Shipped | Default runtime mode |
| `console` | Shipped | `OAUTH2_EVENTS_BACKEND=console` |
| `both` | Shipped | `OAUTH2_EVENTS_BACKEND=both` |
| Redis Streams | Feature-gated | Build with `--features events-redis` |
| Kafka | Feature-gated | Build with `--features events-kafka` |
| RabbitMQ | Feature-gated | Build with `--features events-rabbit` |

Example Redis Streams setup:

```bash
cargo run --features events-redis
```

```bash
export OAUTH2_EVENTS_BACKEND=redis
export OAUTH2_EVENTS_REDIS_URL=redis://127.0.0.1:6379
export OAUTH2_EVENTS_REDIS_STREAM=oauth2_events
```

## MCP server

The repository includes a separate Node.js MCP server in `mcp-server/`.

### What it actually does

| Tool | Purpose |
| --- | --- |
| `register_client` | Register a client through the admin registration endpoint |
| `get_token` | Client credentials token request |
| `exchange_code` | Authorization code token exchange |
| `refresh_token` | Refresh-token request |
| `introspect_token` | Token introspection |
| `revoke_token` | Token revocation |
| `get_health` | Health probe |
| `get_readiness` | Readiness probe |
| `get_metrics` | Metrics fetch |
| `get_openid_config` | Discovery fetch |

It does **not** currently expose general-purpose user CRUD.

### Quick setup

```bash
cd mcp-server
npm install
cp .env.example .env
npm start
```

Then configure your MCP client to run `mcp-server/src/index.js` with `OAUTH2_BASE_URL` pointed at the running server.

See [`mcp-server/README.md`](../../mcp-server/README.md) for the repo-local guide.

## Source-of-truth files

When you are unsure whether integration behavior is real or aspirational, check:

- `crates/oauth2-server/src/lib.rs` for registered routes
- `application.conf.example` for runtime config keys
- `mcp-server/src/index.js` for exposed MCP tools
- `crates/oauth2-events/` for event backends and plugin support

## Related pages

- [OAuth & OIDC](oauth2-oidc.md)
- [Configuration](../getting-started/configuration.md)
- [Admin & API](admin-api.md)
