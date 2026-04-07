# OAuth2 Server MCP Server

Thin MCP stdio wrapper around selected Rust OAuth2 Server HTTP endpoints.

This is useful for local automation and demos, but it is intentionally small. It is not a full admin control plane.

## What it can do

- request client-credentials tokens
- exchange authorization codes
- introspect and revoke tokens
- fetch health, readiness, metrics, and discovery documents
- call the admin client-registration endpoint

## Important limitations

- the wrapper is **not session-aware**
- `register_client` targets the admin-protected route `POST /admin/clients/register`
- `refresh_token` is exposed as a tool, but many deployments reject the refresh grant by default
- there is no user CRUD, dashboard automation, or general admin login flow here

## Setup

```bash
cd mcp-server
npm install
cp .env.example .env
```

Set at least:

```env
OAUTH2_BASE_URL=http://localhost:8080
```

Run it:

```bash
npm start
```

For development with auto-reload:

```bash
npm run dev
```

## Client configuration example

```json
{
  "mcpServers": {
    "oauth2-server": {
      "command": "node",
      "args": ["/path/to/rust_oauth2_server/mcp-server/src/index.js"],
      "env": {
        "OAUTH2_BASE_URL": "http://localhost:8080"
      }
    }
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `register_client` | calls `POST /admin/clients/register` |
| `get_token` | client credentials token request |
| `exchange_code` | authorization code exchange |
| `refresh_token` | refresh-token request |
| `introspect_token` | token introspection |
| `revoke_token` | token revocation |
| `get_health` | health probe |
| `get_readiness` | readiness probe |
| `get_metrics` | raw Prometheus metrics |
| `get_openid_config` | OIDC discovery document |

## Source of truth

If the README and reality ever disagree, trust these first:

- `src/index.js`
- `../docs/usage/oauth2-oidc.md`
- `../docs/usage/admin-api.md`
- `../docs/usage/integrations.md`

## Troubleshooting

### Server not connecting

- make sure the OAuth2 server is running at `OAUTH2_BASE_URL`
- verify the port is reachable
- check server logs for rejected requests

### Tool fails with auth errors

- confirm the client credentials are valid
- remember that admin-scoped calls need admin access, and this wrapper does not perform browser login
- remember that refresh-token requests fail on deployments where refresh grants remain disabled

## Security notes

- never commit real `.env` files
- use HTTPS in production
- keep scopes narrow
- treat the MCP wrapper like any other client integration: logs and credentials matter
