/**
 * k6 Load Test: OIDC Discovery Endpoint
 *
 * Tests the .well-known/openid-configuration endpoint.
 * Measures pure HTTP response performance and JSON serialisation.
 *
 * Usage:
 *   k6 run --env SERVER=rust --env LOAD_PROFILE=light discovery.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import { getServerConfig, getStages, getThresholds } from "../lib/helpers.js";

const config = getServerConfig();

const discoverySuccess = new Rate("discovery_success");
const discoveryDuration = new Trend("discovery_duration", true);

export const options = {
  stages: getStages(),
  thresholds: getThresholds(),
  tags: {
    server: config.name,
    language: config.language,
    test: "discovery",
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

export default function () {
  const url = `${config.baseUrl}${config.discoveryEndpoint}`;
  const params = { tags: { name: "discovery_request" } };

  const res = http.get(url, params);

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
    "has issuer": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.issuer !== undefined;
      } catch (error) {
        return false;
      }
    },
    "has token_endpoint": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.token_endpoint !== undefined;
      } catch (error) {
        return false;
      }
    },
  });

  discoverySuccess.add(success);
  discoveryDuration.add(res.timings.duration);

  sleep(0.05);
}

export function handleSummary(data) {
  const server = __ENV.SERVER || "rust";
  const profile = __ENV.LOAD_PROFILE || "light";
  const iteration = __ENV.ITERATION || "1";

  return {
    [`/results/${server}_discovery_${profile}_${iteration}.json`]:
      JSON.stringify(data, null, 2),
  };
}
