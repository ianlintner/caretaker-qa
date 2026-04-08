
# Rust OAuth2 Server

[![Build Status](https://github.com/ianlintner/rust-oauth2-server/actions/workflows/ci.yml/badge.svg)](https://github.com/ianlintner/rust-oauth2-server/actions/workflows/ci.yml)

Self-Hosted OAuth2 and OIDC in Rust with Actix, an admin UI, generated OpenAPI, eventing, and kubernetes-ready deployment assets.

<p align="center"><img width="256" alt="rustoauth2" src="https://github.com/user-attachments/assets/0a009caa-a37a-4c87-88d3-373229e01e0b" /></p>

## Start in 60 seconds

```bash
cp .env.example .env
# set OAUTH2_JWT_SECRET, OAUTH2_SESSION_KEY, and OAUTH2_SEED_PASSWORD
cargo run
```

Then open:

- app: "http://localhost:8080"
- login: "http://localhost:8080/auth/login"
- admin: "http://localhost:8080/admin"
- Swagger UI: "http://localhost:8080/swagger-ui"

The default local path uses SQLite. If you want Postgres plus the supporting services, use `docker compose up -d` instead.

## What actually ships
