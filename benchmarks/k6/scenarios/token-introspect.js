/**
 * k6 Load Test: Token Introspection
 *
 * Tests the introspection endpoint — first obtains a token via
 * client_credentials, then introspects it repeatedly.
 *
 * Usage:
 *   k6 run --env SERVER=rust --env LOAD_PROFILE=light token-introspect.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  getServerConfig,
  formEncode,
  tokenRequestParams,
  getStages,
  getThresholds,
} from "../lib/helpers.js";

const config = getServerConfig();

const introspectSuccess = new Rate("introspect_success");
const introspectDuration = new Trend("introspect_duration", true);

export const options = {
  stages: getStages(),
  thresholds: getThresholds(),
  tags: {
    server: config.name,
    language: config.language,
    test: "token_introspect",
  },
  summaryTrendStats: [
    "avg",
    "min",
    "med",
    "max",
    "p(50)",
    "p(90)",
    "p(95)",
    "p(99)",
    "count",
  ],
};

// Obtain a token in setup phase (run once)
export function setup() {
  const url = `${config.baseUrl}${config.tokenEndpoint}`;
  const body = formEncode(config.tokenPayload);
  const params = tokenRequestParams();

  const res = http.post(url, body, params);
  if (res.status !== 200) {
    throw new Error(
      `Setup failed: could not obtain token (status ${res.status}): ${res.body}`,
    );
  }

  const data = JSON.parse(res.body);
  return { accessToken: data.access_token };
}

export default function (data) {
  const introspectBase = config.introspectUrl || config.baseUrl;
  const url = `${introspectBase}${config.introspectEndpoint}`;
  const payload = config.introspectPayload(data.accessToken);
  const body = formEncode(payload);
  const params = {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    tags: { name: "introspect_request" },
  };

  const res = http.post(url, body, params);

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
    "token is active": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.active === true;
      } catch (error) {
        return false;
      }
    },
  });

  introspectSuccess.add(success);
  introspectDuration.add(res.timings.duration);

  sleep(0.1);
}

export function handleSummary(data) {
  const server = __ENV.SERVER || "rust";
  const profile = __ENV.LOAD_PROFILE || "light";
  const iteration = __ENV.ITERATION || "1";

  return {
    [`/results/${server}_token-introspect_${profile}_${iteration}.json`]:
      JSON.stringify(data, null, 2),
  };
}
