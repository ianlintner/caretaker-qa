# Admin Dashboard

## Accessing the Dashboard

Navigate to `/admin` in your browser. The admin panel requires authentication via the `AdminGuard` middleware — unauthenticated requests are redirected to `/auth/login`.

You must be logged in with an admin-role account.

## Available Views

The dashboard provides:

- **Clients** — registered OAuth2 clients and their configuration
- **Tokens** — active tokens, recent issuances, and revocation controls
- **Users** — registered user accounts

## Admin API Endpoints

The admin UI consumes these JSON endpoints (all require admin authentication):

| Endpoint                        | Method   | Description            |
| ------------------------------- | -------- | ---------------------- |
| `/admin/api/dashboard`          | `GET`    | Dashboard summary data |
| `/admin/api/clients`            | `GET`    | List all clients       |
| `/admin/clients/register`       | `POST`   | Register a new client  |
| `/admin/api/clients/{id}`       | `DELETE` | Delete a client        |
| `/admin/api/tokens`             | `GET`    | List tokens            |
| `/admin/api/tokens/{id}/revoke` | `POST`   | Revoke a token         |
| `/admin/api/users`              | `GET`    | List users             |

## See Also

- [Client Management](clients.md)
- [Token Management](tokens.md)
- [API Endpoints](../api/endpoints.md)
