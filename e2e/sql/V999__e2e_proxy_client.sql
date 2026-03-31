-- E2E-only client seed for docker-compose.e2e.yml
-- This migration is intentionally scoped to the dedicated e2e compose stack.

INSERT INTO clients (id, client_id, client_secret, redirect_uris, grant_types, scope, name, created_at, updated_at)
VALUES (
    'e2e-proxy-client-id',
    'e2e_proxy_client',
    'e2e_proxy_secret',
    '["http://localhost:4180/_oauth2/callback"]',
    '["authorization_code", "client_credentials"]',
    'openid profile email read write',
    'E2E Proxy Client',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO NOTHING;
