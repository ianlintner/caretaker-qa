# Rust OAuth2 Server

[![CI/CD Pipeline](https://github.com/ianlintner/rust_oauth2_server/actions/workflows/ci.yml/badge.svg)](https://github.com/ianlintner/rust_oauth2_server/actions/workflows/ci.yml)

Self-hosted OAuth2 and OIDC in Rust with Actix, an admin UI, code-generated OpenAPI, eventing, rate limiting, and Kubernetes-ready ops hooks.

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
- Google, Microsoft, GitHub, and Azure login routes are wired; Okta/Auth0 currently return `503`
- the repo ships Kustomize manifests, not Helm charts

## Docs by job

- run it locally: [`docs/getting-started/quickstart.md`](docs/getting-started/quickstart.md)
- configure it: [`docs/getting-started/configuration.md`](docs/getting-started/configuration.md)
- integrate a client: [`docs/usage/oauth2-oidc.md`](docs/usage/oauth2-oidc.md)
- manage/administer it: [`docs/usage/admin-api.md`](docs/usage/admin-api.md)
- deploy and operate it: [`docs/operations/deployment.md`](docs/operations/deployment.md), [`docs/operations/observability.md`](docs/operations/observability.md), [`docs/operations/runbooks.md`](docs/operations/runbooks.md)
- extend the workspace: [`docs/development/architecture.md`](docs/development/architecture.md), [`docs/development/extending.md`](docs/development/extending.md)
- contribute safely: [`docs/development/testing.md`](docs/development/testing.md), [`docs/development/contributing.md`](docs/development/contributing.md)

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

That’s the short front door. The rest of the novel got evicted on purpose.

# Redis Streams (requires --features events-redis)
export OAUTH2_EVENTS_REDIS_URL=redis://localhost:6379
export OAUTH2_EVENTS_REDIS_STREAM=oauth2:events
export OAUTH2_EVENTS_REDIS_MAXLEN=10000

# Kafka (requires --features events-kafka)
export OAUTH2_EVENTS_KAFKA_BROKERS=localhost:9092
export OAUTH2_EVENTS_KAFKA_TOPIC=oauth2-events
export OAUTH2_EVENTS_KAFKA_CLIENT_ID=rust-oauth2-server

# RabbitMQ (requires --features events-rabbit)
export OAUTH2_EVENTS_RABBIT_URL=amqp://guest:guest@localhost:5672/%2f
export OAUTH2_EVENTS_RABBIT_EXCHANGE=oauth2.events
export OAUTH2_EVENTS_RABBIT_ROUTING_KEY=auth.*
```

See [Eventing Documentation](docs/eventing.md) and [Examples](docs/examples/eventing.md) for more details.

### Social Login Configuration

Configure social login providers using HOCON or environment variables. Providers are only enabled when their credentials are provided.

**Using HOCON** (`application.conf`):

```hocon
social {
  google {
    enabled = false  # Set to true and provide credentials to enable
    # These values are loaded from environment variables:
    # OAUTH2_GOOGLE_CLIENT_ID
    # OAUTH2_GOOGLE_CLIENT_SECRET
    # OAUTH2_GOOGLE_REDIRECT_URI
  }

  microsoft {
    enabled = false
    # OAUTH2_MICROSOFT_CLIENT_ID
    # OAUTH2_MICROSOFT_CLIENT_SECRET
    # OAUTH2_MICROSOFT_REDIRECT_URI
    # OAUTH2_MICROSOFT_TENANT_ID (optional, defaults to "common")
  }

  github {
    enabled = false
    # OAUTH2_GITHUB_CLIENT_ID
    # OAUTH2_GITHUB_CLIENT_SECRET
    # OAUTH2_GITHUB_REDIRECT_URI
  }

  okta {
    enabled = false
    # OAUTH2_OKTA_CLIENT_ID
    # OAUTH2_OKTA_CLIENT_SECRET
    # OAUTH2_OKTA_REDIRECT_URI
    # OAUTH2_OKTA_DOMAIN (required)
  }

  auth0 {
    enabled = false
    # OAUTH2_AUTH0_CLIENT_ID
    # OAUTH2_AUTH0_CLIENT_SECRET
    # OAUTH2_AUTH0_REDIRECT_URI
    # OAUTH2_AUTH0_DOMAIN (required)
  }
}
```

**Using Environment Variables**:

#### Google OAuth2

```bash
export OAUTH2_GOOGLE_CLIENT_ID=your-google-client-id
export OAUTH2_GOOGLE_CLIENT_SECRET=your-google-client-secret
export OAUTH2_GOOGLE_REDIRECT_URI=http://localhost:8080/auth/callback/google
```

#### Microsoft/Azure AD

```bash
export OAUTH2_MICROSOFT_CLIENT_ID=your-microsoft-client-id
export OAUTH2_MICROSOFT_CLIENT_SECRET=your-microsoft-client-secret
export OAUTH2_MICROSOFT_REDIRECT_URI=http://localhost:8080/auth/callback/microsoft
export OAUTH2_MICROSOFT_TENANT_ID=common  # or your tenant ID
```

#### GitHub

```bash
export OAUTH2_GITHUB_CLIENT_ID=your-github-client-id
export OAUTH2_GITHUB_CLIENT_SECRET=your-github-client-secret
export OAUTH2_GITHUB_REDIRECT_URI=http://localhost:8080/auth/callback/github
```

#### Okta

```bash
export OAUTH2_OKTA_CLIENT_ID=your-okta-client-id
export OAUTH2_OKTA_CLIENT_SECRET=your-okta-client-secret
export OAUTH2_OKTA_REDIRECT_URI=http://localhost:8080/auth/callback/okta
export OAUTH2_OKTA_DOMAIN=your-okta-domain.okta.com
```

#### Auth0

```bash
export OAUTH2_AUTH0_CLIENT_ID=your-auth0-client-id
export OAUTH2_AUTH0_CLIENT_SECRET=your-auth0-client-secret
export OAUTH2_AUTH0_REDIRECT_URI=http://localhost:8080/auth/callback/auth0
export OAUTH2_AUTH0_DOMAIN=your-tenant.auth0.com
```

## 📍 Endpoints

### User Interface

- `GET /` - Redirects to login page
- `GET /auth/login` - Modern login page with social login options
- `GET /error` - Error page with detailed error information

### Social Login

- `GET /auth/login/google` - Initiate Google login
- `GET /auth/login/microsoft` - Initiate Microsoft/Azure AD login
- `GET /auth/login/github` - Initiate GitHub login
- `GET /auth/login/azure` - Initiate Azure AD login
- `GET /auth/login/okta` - Initiate Okta login
- `GET /auth/login/auth0` - Initiate Auth0 login
- `GET /auth/callback/{provider}` - OAuth callback handler
- `GET /auth/success` - Authentication success page
- `POST /auth/logout` - Logout endpoint

### OAuth2 Endpoints

- `GET /oauth/authorize` - Authorization endpoint
- `POST /oauth/token` - Token endpoint
- `POST /oauth/introspect` - Token introspection
- `POST /oauth/revoke` - Token revocation

### Client Management

- `POST /clients/register` - Register a new OAuth2 client

### Discovery

- `GET /.well-known/openid-configuration` - OAuth2 server metadata

### Admin & Monitoring

- `GET /admin` - Admin dashboard
- `GET /health` - Health check endpoint
- `GET /ready` - Readiness check endpoint
- `GET /metrics` - Prometheus metrics

### API Documentation

- `GET /swagger-ui` - Interactive API documentation

## 📊 Metrics

The server exposes Prometheus metrics at `/metrics`:

- `oauth2_server_http_requests_total` - Total HTTP requests
- `oauth2_server_http_request_duration_seconds` - Request duration histogram
- `oauth2_server_oauth_token_issued_total` - Tokens issued counter
- `oauth2_server_oauth_token_revoked_total` - Tokens revoked counter
- `oauth2_server_oauth_clients_total` - Total registered clients
- `oauth2_server_oauth_active_tokens` - Active tokens gauge
- `oauth2_server_db_queries_total` - Database queries counter
- `oauth2_server_db_query_duration_seconds` - DB query duration histogram

## 🔍 OpenTelemetry

The server exports traces to an OTLP endpoint (default: `http://localhost:4317`). Configure your OpenTelemetry collector to receive traces.

Example with Jaeger:

```bash
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

Then access Jaeger UI at `http://localhost:16686`

## 🧪 Testing

### Run Unit Tests

```bash
cargo test
```

### Run Integration Tests

```bash
cargo test --test integration
```

### Run BDD Tests

```bash
cargo test --test bdd
```

## 📚 API Examples

### Register a Client

```bash
curl -X POST http://localhost:8080/clients/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "My Application",
    "redirect_uris": ["http://localhost:3000/callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "scope": "read write"
  }'
```

### Authorization Code Flow

1. **Get Authorization Code**:

```text
http://localhost:8080/oauth/authorize?response_type=code&client_id=CLIENT_ID&redirect_uri=http://localhost:3000/callback&scope=read&code_challenge=CODE_CHALLENGE&code_challenge_method=S256
```

1. **Exchange Code for Token**:

```bash
curl -X POST http://localhost:8080/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=AUTH_CODE&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&code_verifier=CODE_VERIFIER"
```

Note: `redirect_uri` is optional in the token request (OAuth 2.1). For backward compatibility, you may include it; if provided, it must exactly match the `redirect_uri` used at the authorization step.

### Client Credentials Flow

```bash
curl -X POST http://localhost:8080/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=read"
```

### Token Introspection

```bash
curl -X POST http://localhost:8080/oauth/introspect \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=ACCESS_TOKEN"
```

## 🏗️ Architecture

The server uses the Actor model for concurrent, fault-tolerant request handling:

```mermaid
graph TB
    subgraph "Client Layer"
        Client1[Web Apps]
        Client2[Mobile Apps]
        Client3[Services]
    end

    subgraph "OAuth2 Server"
        LB[Load Balancer]
        MW[Middleware Stack]

        subgraph "Handlers"
            OAuth[OAuth Handler]
            Token[Token Handler]
            ClientH[Client Handler]
        end

        subgraph "Actor System"
            TokenA[Token Actor]
            ClientA[Client Actor]
            AuthA[Auth Actor]
        end
    end

    subgraph "Data & Observability"
        DB[(Database)]
        Metrics[Prometheus]
        Traces[Jaeger]
    end

    Client1 --> LB
    Client2 --> LB
    Client3 --> LB

    LB --> MW
    MW --> OAuth
    MW --> Token
    MW --> ClientH

    OAuth --> AuthA
    Token --> TokenA
    ClientH --> ClientA

    TokenA --> DB
    ClientA --> DB
    AuthA --> DB
    MW --> Metrics
    MW --> Traces

    style LB fill:#ff9800,color:#fff
    style TokenA fill:#4caf50,color:#fff
    style ClientA fill:#2196f3,color:#fff
    style AuthA fill:#9c27b0,color:#fff
    style DB fill:#f3e5f5
```

### Key Components

- **Actix-Web Server**: High-performance async HTTP server
- **Actor Model**: Isolated, concurrent request processing
- **SQLx Database**: Compile-time verified queries
- **JWT Tokens**: Stateless authentication
- **Middleware Stack**: Metrics, tracing, CORS, authentication
- **OpenTelemetry**: Distributed tracing and observability

### OAuth2 Flows

```mermaid
graph LR
    subgraph AuthCodeFlow["Authorization Code Flow"]
        User1[User] -->|Login| Auth1["/oauth/authorize"]
        Auth1 -->|Code| Client1[Client]
        Client1 -->|Exchange| Token1["/oauth/token"]
        Token1 -->|Access Token| Client1
    end

    subgraph ClientCredsFlow["Client Credentials Flow"]
        Service[Service] -->|Credentials| Token2["/oauth/token"]
        Token2 -->|Access Token| Service
    end

    style Auth1 fill:#4caf50,color:#fff
    style Token1 fill:#2196f3,color:#fff
    style Token2 fill:#2196f3,color:#fff
```

For detailed architecture documentation, see [Architecture Overview](docs/architecture/overview.md).

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

For development guidelines, see [Contributing Guide](docs/development/contributing.md).

## 📚 Documentation

Comprehensive documentation is available in the `/docs` directory:

- **[Getting Started](docs/getting-started/installation.md)** - Installation and quick start
- **[Configuration](docs/getting-started/configuration.md)** - Complete configuration guide
- **[Architecture](docs/architecture/overview.md)** - System design and components
- **[OAuth2 Flows](docs/flows/authorization-code.md)** - Detailed flow documentation
- **[API Reference](docs/api/endpoints.md)** - Endpoint documentation
- **[Deployment](docs/deployment/docker.md)** - Production deployment guides
- **[Kubernetes Deployment](k8s/README.md)** - K8s manifests and guides
- **[Distributed Scaling](docs/deployment/distributed-scaling.md)** - Regional shards,
  clustered runtime, and global auth topology
- **[MCP Server](mcp-server/README.md)** - AI integration with Model Context Protocol
- **[Observability](docs/observability/metrics.md)** - Monitoring and troubleshooting

### Agent Instructions

For AI-assisted development and operations, see:

- **[Development Agent](.github/agents/development.md)** - Coding guidelines and development workflow
- **[Operations Agent](.github/agents/operations.md)** - Deployment and troubleshooting
- **[Database Agent](.github/agents/database.md)** - Database management and optimization
- **[Security Agent](.github/agents/security.md)** - Security best practices and guidelines

## 📄 License

This project is licensed under either of:

- MIT License
- Apache License, Version 2.0

at your option.

## 🔗 Resources

- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)
- [PKCE RFC 7636](https://tools.ietf.org/html/rfc7636)
- [Token Introspection RFC 7662](https://tools.ietf.org/html/rfc7662)
- [Token Revocation RFC 7009](https://tools.ietf.org/html/rfc7009)
- [Actix Web Documentation](https://actix.rs/)
- [Keycloak](https://www.keycloak.org/) - Inspiration for feature set
