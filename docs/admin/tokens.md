# Token Management

## Authentication

All token management endpoints require admin authentication via the `AdminGuard` middleware. Unauthenticated requests are redirected to `/auth/login`.

## Standard Token Endpoints

These endpoints are available to all authenticated clients:

| Endpoint              | Method | Description                 |
| --------------------- | ------ | --------------------------- |
| `/oauth/token`        | `POST` | Issue a new token           |
| `/oauth/introspect`   | `POST` | Introspect (validate) token |
| `/oauth/revoke`       | `POST` | Revoke a token              |

## Admin Token Endpoints

These endpoints are restricted to admin users:

| Endpoint                        | Method | Description        |
| ------------------------------- | ------ | ------------------ |
| `/admin/api/tokens`             | `GET`  | List all tokens    |
| `/admin/api/tokens/{id}/revoke` | `POST` | Revoke a token     |

### List Tokens

```bash
curl http://localhost:8080/admin/api/tokens \
  -b "session_cookie=YOUR_ADMIN_SESSION"
```

### Revoke a Token (Admin)

```bash
curl -X POST http://localhost:8080/admin/api/tokens/{token_id}/revoke \
  -b "session_cookie=YOUR_ADMIN_SESSION"
```

## See Also

- [API Endpoints](../api/endpoints.md)
- [Authentication](../api/authentication.md)
- [Dashboard](dashboard.md)
