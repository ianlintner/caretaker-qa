-- Initialize separate databases for each OAuth2 server
-- All servers share the same PostgreSQL instance for fair comparison

CREATE DATABASE oauth2_rust;
CREATE DATABASE oauth2_keycloak;
CREATE DATABASE oauth2_hydra;
CREATE DATABASE oauth2_authentik;
CREATE DATABASE oauth2_node_oidc;

-- Grant full access to the shared user
GRANT ALL PRIVILEGES ON DATABASE oauth2_rust TO postgres;
GRANT ALL PRIVILEGES ON DATABASE oauth2_keycloak TO postgres;
GRANT ALL PRIVILEGES ON DATABASE oauth2_hydra TO postgres;
GRANT ALL PRIVILEGES ON DATABASE oauth2_authentik TO postgres;
GRANT ALL PRIVILEGES ON DATABASE oauth2_node_oidc TO postgres;
