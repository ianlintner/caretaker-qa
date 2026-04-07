# Configuration

The goal of this page is not to copy every possible knob into prose. It is to show you the settings you need most often and point you to the files that actually define the full runtime contract.

## Source of truth

Use these files when you need the exact key names and defaults:

- `.env.example` for environment-driven setups
- `application.conf.example` for HOCON-backed setups

Runtime precedence is:

1. environment variables
2. `application.conf`
3. built-in defaults

## Minimum local config

For a useful local run, these are the only values you usually need to touch:

| Variable               | Why it matters                                                         |
| ---------------------- | ---------------------------------------------------------------------- |
| `OAUTH2_DATABASE_URL`  | Defaults to SQLite and is fine for local work.                         |
| `OAUTH2_JWT_SECRET`    | Required for token signing; startup fails on insecure defaults.        |
| `OAUTH2_SESSION_KEY`   | Keeps sessions stable across restarts. Use a 128-character hex string. |
| `OAUTH2_SEED_PASSWORD` | Password for the seeded admin account.                                 |
| `RUST_LOG`             | Runtime log level.                                                     |

Example:

```dotenv
OAUTH2_DATABASE_URL=sqlite:oauth2.db
OAUTH2_JWT_SECRET=replace-with-a-random-32+-char-secret
OAUTH2_SESSION_KEY=replace-with-128-hex-characters
OAUTH2_SEED_PASSWORD=replace-with-a-local-admin-password
RUST_LOG=info
```

## Common production settings

| Variable                                              | Use it when                                              |
| ----------------------------------------------------- | -------------------------------------------------------- |
| `OAUTH2_SERVER_PUBLIC_BASE_URL`                       | the externally visible URL differs from the bind address |
| `OAUTH2_ALLOWED_ORIGINS`                              | browsers call the server cross-origin                    |
| `OAUTH2_DATABASE_MAX_CONNECTIONS` / `MIN_CONNECTIONS` | you need to tune the storage pool                        |
| `OTEL_EXPORTER_OTLP_ENDPOINT`                         | you want traces exported to an OTEL collector or Jaeger  |
| `OAUTH2_SERVER_WORKERS`                               | you want to pin Actix worker count                       |
| `OAUTH2_SERVER_TRUST_PROXY_HEADERS`                   | the server sits behind a trusted reverse proxy           |

## Security-sensitive settings

These are worth calling out because the server enforces or depends on them.

| Variable                         | Notes                                                       |
| -------------------------------- | ----------------------------------------------------------- |
| `OAUTH2_JWT_SECRET`              | Must be strong and must not use the insecure default.       |
| `OAUTH2_SESSION_KEY`             | Persistent 64-byte key encoded as 128 hex characters.       |
| `OAUTH2_SEED_PASSWORD`           | The server aborts if it is still `changeme` in normal mode. |
| `OAUTH2_ALLOW_INSECURE_DEFAULTS` | Development-only escape hatch. Never set in production.     |

Generate a session key:

```bash
openssl rand -hex 64
```

## Social login

Supported providers today:

- Google
- Microsoft
- GitHub
- Azure AD

Configured but not fully implemented yet:

- Okta
- Auth0

Each provider follows the same pattern: client id, client secret, and redirect URI. Example:

```bash
export OAUTH2_GOOGLE_CLIENT_ID=your-client-id
export OAUTH2_GOOGLE_CLIENT_SECRET=your-client-secret
export OAUTH2_GOOGLE_REDIRECT_URI=http://localhost:8080/auth/callback/google
```

## OIDC signing

If you want RS256 id tokens and a populated JWKS endpoint, configure:

| Variable                          | Purpose                       |
| --------------------------------- | ----------------------------- |
| `OAUTH2_ID_TOKEN_PRIVATE_KEY_PEM` | RSA private key PEM           |
| `OAUTH2_ID_TOKEN_KID`             | key id published through JWKS |
| `OAUTH2_ID_TOKEN_ALG`             | usually `RS256`               |

If these are not set, id tokens fall back to HS256 using `OAUTH2_JWT_SECRET`.

## Eventing

Runtime defaults:

- `OAUTH2_EVENTS_ENABLED=true`
- `OAUTH2_EVENTS_BACKEND=in_memory`
- `OAUTH2_EVENTS_FILTER_MODE=allow_all`

Feature-gated broker backends:

| Backend       | Build requirement          |
| ------------- | -------------------------- |
| Redis Streams | `--features events-redis`  |
| Kafka         | `--features events-kafka`  |
| RabbitMQ      | `--features events-rabbit` |

## Distributed runtime settings

These matter only once you move beyond a single-instance deployment.

| Variable                          | What it controls                    |
| --------------------------------- | ----------------------------------- |
| `OAUTH2_DATABASE_READ_URL`        | optional read replica               |
| `OAUTH2_CACHE_REDIS_URL`          | Redis L2 cache                      |
| `OAUTH2_TOKEN_ACTOR_SHARDS`       | per-process token actor shard count |
| `OAUTH2_RATE_LIMIT_ENABLED`       | request throttling                  |
| `OAUTH2_RATE_LIMIT_BACKEND`       | `in_memory` or `redis`              |
| `OAUTH2_RATE_LIMIT_REDIS_URL`     | Redis limiter backend               |
| `OAUTH2_JWT_STATELESS_VALIDATION` | JWT-only introspection path         |

For the full clustered profile, build with:

```bash
cargo build --release --features distributed
```

## HOCON vs env files

Use environment variables when:

- you deploy with containers or Kubernetes
- secrets come from a secret manager
- you want a twelve-factor-style setup

Use `application.conf` when:

- you want a checked-in local baseline
- you prefer grouped config over a long env file
- you are mixing defaults with a few environment overrides

## Related pages

- [Quickstart](quickstart.md)
- [OAuth & OIDC](../usage/oauth2-oidc.md)
- [Deployment](../operations/deployment.md)
