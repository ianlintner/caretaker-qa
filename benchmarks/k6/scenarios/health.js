/**
 * k6 Load Test: Health Check Endpoint
 *
 * Baseline HTTP performance test — measures the absolute minimum
 * response time for each server's health/readiness endpoint.
 *
 * Usage:
 *   k6 run --env SERVER=rust --env LOAD_PROFILE=light health.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import { getServerConfig, getStages, getThresholds } from "../lib/helpers.js";

const config = getServerConfig();

const healthSuccess = new Rate("health_success");
const healthDuration = new Trend("health_duration", true);

export const options = {
  stages: getStages(),
  thresholds: getThresholds(),
  tags: {
    server: config.name,
    language: config.language,
    test: "health",
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
  const url = `${config.baseUrl}${config.healthEndpoint}`;
  const params = { tags: { name: "health_request" } };

  const res = http.get(url, params);

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
  });

  healthSuccess.add(success);
  healthDuration.add(res.timings.duration);

  sleep(0.05);
}

export function handleSummary(data) {
  const server = __ENV.SERVER || "rust";
  const profile = __ENV.LOAD_PROFILE || "light";
  const iteration = __ENV.ITERATION || "1";

  return {
    [`/results/${server}_health_${profile}_${iteration}.json`]: JSON.stringify(
      data,
      null,
      2,
    ),
  };
}
