# Client Management

## Authentication

All client management endpoints require admin authentication via the `AdminGuard` middleware. Unauthenticated requests are redirected to `/auth/login`.

Log in at `/auth/login` with an admin account, then use the session cookie for API calls.

## Register a Client

**Endpoint:** `POST /admin/clients/register`

```bash
curl -X POST http://localhost:8080/admin/clients/register \
  -H "Content-Type: application/json" \
  -b "session_cookie=YOUR_ADMIN_SESSION" \
  -d '{
    "client_name": "My Application",
    "redirect_uris": ["http://localhost:3000/callback"],
    "grant_types": ["authorization_code"],
    "scope": "read write"
  }'
```

**Response:**

```json
{
  "client_id": "8f9a7b6c-5d4e-3f2a-1b0c-9d8e7f6a5b4c",
  "client_secret": "secret_1a2b3c4d5e6f7g8h9i0j",
  "client_name": "My Application",
  "redirect_uris": ["http://localhost:3000/callback"],
  "grant_types": ["authorization_code"],
  "scope": "read write"
}
```

## List Clients

**Endpoint:** `GET /admin/api/clients`

```bash
curl http://localhost:8080/admin/api/clients \
  -b "session_cookie=YOUR_ADMIN_SESSION"
```

## Delete a Client

**Endpoint:** `DELETE /admin/api/clients/{id}`

```bash
curl -X DELETE http://localhost:8080/admin/api/clients/{client_id} \
  -b "session_cookie=YOUR_ADMIN_SESSION"
```

## See Also

- [API Endpoints](../api/endpoints.md)
- [Client Credentials Flow](../flows/client-credentials.md)
- [Dashboard](dashboard.md)
