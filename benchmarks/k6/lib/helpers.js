/**
 * Shared helpers for OAuth2 benchmark k6 scripts.
 *
 * Each server has slightly different endpoint paths and client setup
 * procedures. This module normalises those differences.
 */

// Server endpoint configurations
export const SERVERS = {
  rust: {
    name: "rust-oauth2-server",
    language: "Rust",
    baseUrl: "http://bench-rust:8080",
    tokenEndpoint: "/oauth/token",
    introspectEndpoint: "/oauth/introspect",
    discoveryEndpoint: "/.well-known/openid-configuration",
    healthEndpoint: "/health",
    // client_credentials uses POST body
    tokenPayload: {
      grant_type: "client_credentials",
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      scope: "openid profile email",
    },
    introspectPayload: (token) => ({
      token: token,
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
    }),
  },

  "rust-mongo": {
    name: "rust-oauth2-server-mongo",
    language: "Rust (MongoDB)",
    baseUrl: "http://bench-rust-mongo:8080",
    tokenEndpoint: "/oauth/token",
    introspectEndpoint: "/oauth/introspect",
    discoveryEndpoint: "/.well-known/openid-configuration",
    healthEndpoint: "/health",
    // client_credentials uses POST body
    tokenPayload: {
      grant_type: "client_credentials",
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      scope: "openid profile email",
    },
    introspectPayload: (token) => ({
      token: token,
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
    }),
  },

  keycloak: {
    name: "Keycloak",
    language: "Java",
    baseUrl: "http://bench-keycloak:8080",
    tokenEndpoint: "/realms/benchmark/protocol/openid-connect/token",
    introspectEndpoint:
      "/realms/benchmark/protocol/openid-connect/token/introspect",
    discoveryEndpoint: "/realms/benchmark/.well-known/openid-configuration",
    healthEndpoint: "/health/ready",
    tokenPayload: {
      grant_type: "client_credentials",
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      scope: "openid profile email",
    },
    introspectPayload: (token) => ({
      token: token,
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
    }),
  },

  hydra: {
    name: "Ory Hydra",
    language: "Go",
    baseUrl: "http://bench-hydra:4444",
    adminUrl: "http://bench-hydra:4445",
    tokenEndpoint: "/oauth2/token",
    introspectEndpoint: "/oauth2/introspect", // admin API
    discoveryEndpoint: "/.well-known/openid-configuration",
    healthEndpoint: "/health/ready",
    tokenPayload: {
      grant_type: "client_credentials",
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      scope: "openid",
    },
    introspectPayload: (token) => ({
      token: token,
    }),
    // Hydra introspection is on admin port
    introspectUrl: "http://bench-hydra:4445",
  },

  authentik: {
    name: "Authentik",
    language: "Python",
    baseUrl: "http://bench-authentik:9000",
    tokenEndpoint: "/application/o/token/",
    introspectEndpoint: "/application/o/introspect/",
    discoveryEndpoint:
      "/application/o/benchmark/.well-known/openid-configuration",
    healthEndpoint: "/-/health/ready/",
    tokenPayload: {
      grant_type: "client_credentials",
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      scope: "openid profile email",
    },
    introspectPayload: (token) => ({
      token: token,
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
    }),
  },

  "node-oidc": {
    name: "node-oidc-provider",
    language: "Node.js",
    baseUrl: "http://bench-node-oidc:3000",
    tokenEndpoint: "/token",
    introspectEndpoint: "/token/introspection",
    discoveryEndpoint: "/.well-known/openid-configuration",
    healthEndpoint: "/health",
    tokenPayload: {
      grant_type: "client_credentials",
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      scope: "openid profile email",
    },
    introspectPayload: (token) => ({
      token: token,
      client_id: "bench-client",
      client_secret: "bench-secret-12345678",
      token_type_hint: "access_token",
    }),
  },
};

/**
 * Get the server configuration from the SERVER env variable.
 */
export function getServerConfig() {
  const serverKey = __ENV.SERVER || "rust";
  const config = SERVERS[serverKey];
  if (!config) {
    throw new Error(
      `Unknown server: ${serverKey}. Valid: ${Object.keys(SERVERS).join(", ")}`,
    );
  }
  return config;
}

/**
 * Encode an object as application/x-www-form-urlencoded.
 */
export function formEncode(obj) {
  return Object.entries(obj)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
}

/**
 * Standard k6 request params for OAuth2 token requests.
 */
export function tokenRequestParams() {
  return {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    tags: { name: "token_request" },
  };
}

/**
 * Standard load profile stages.
 * Controlled by LOAD_PROFILE env: light | medium | heavy
 */
export function getStages() {
  const profile = __ENV.LOAD_PROFILE || "light";

  const profiles = {
    light: [
      { duration: "15s", target: 10 }, // ramp up
      { duration: "30s", target: 50 }, // steady
      { duration: "15s", target: 50 }, // hold
      { duration: "10s", target: 0 }, // ramp down
    ],
    medium: [
      { duration: "15s", target: 50 },
      { duration: "30s", target: 200 },
      { duration: "30s", target: 200 },
      { duration: "15s", target: 0 },
    ],
    heavy: [
      { duration: "20s", target: 100 },
      { duration: "30s", target: 500 },
      { duration: "60s", target: 500 },
      { duration: "20s", target: 0 },
    ],
  };

  return profiles[profile] || profiles.light;
}

/**
 * Standard thresholds for all tests.
 */
export function getThresholds() {
  return {
    http_req_duration: ["p(95)<2000", "p(99)<5000"],
    http_req_failed: ["rate<0.05"],
    http_reqs: ["rate>0"],
  };
}
