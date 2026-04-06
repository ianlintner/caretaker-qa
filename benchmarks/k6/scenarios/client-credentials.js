/**
 * k6 Load Test: OAuth2 Client Credentials Grant
 *
 * Primary benchmark — tests the token endpoint with client_credentials grant.
 * This is the most apples-to-apples comparison since it's a single POST
 * request that exercises JWT signing, client auth, and token persistence.
 *
 * Usage:
 *   k6 run --env SERVER=rust --env LOAD_PROFILE=light client-credentials.js
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

// Custom metrics
const tokenSuccess = new Rate("token_success");
const tokenDuration = new Trend("token_duration", true);

export const options = {
  stages: getStages(),
  thresholds: getThresholds(),
  tags: {
    server: config.name,
    language: config.language,
    test: "client_credentials",
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
  const url = `${config.baseUrl}${config.tokenEndpoint}`;
  const body = formEncode(config.tokenPayload);
  const params = tokenRequestParams();

  const res = http.post(url, body, params);

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
    "has access_token": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.access_token !== undefined;
      } catch (error) {
        return false;
      }
    },
    "has token_type": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.token_type !== undefined;
      } catch (error) {
        return false;
      }
    },
  });

  tokenSuccess.add(success);
  tokenDuration.add(res.timings.duration);

  // Small think time to simulate realistic client behavior
  sleep(0.1);
}

export function handleSummary(data) {
  const server = __ENV.SERVER || "rust";
  const profile = __ENV.LOAD_PROFILE || "light";
  const iteration = __ENV.ITERATION || "1";

  return {
    [`/results/${server}_client-credentials_${profile}_${iteration}.json`]:
      JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: "  ", enableColors: true }),
  };
}

// Inline text summary since k6 doesn't always have the extension
function textSummary(data, opts) {
  const metrics = data.metrics;
  const fmt = (v) =>
    typeof v === "number" && isFinite(v) ? v.toFixed(2) : "n/a";
  const lines = [
    `\n  ┌─── ${data.root_group.name || "default"} ───`,
    `  │ Server: ${__ENV.SERVER || "rust"} | Profile: ${__ENV.LOAD_PROFILE || "light"}`,
    `  │`,
  ];

  if (metrics.http_req_duration) {
    const d = metrics.http_req_duration.values;
    lines.push(
      `  │ http_req_duration ─── avg=${fmt(d.avg)}ms  med=${fmt(d.med)}ms  p95=${fmt(d["p(95)"])}ms  p99=${fmt(d["p(99)"])}ms`,
    );
  }
  if (metrics.http_reqs) {
    lines.push(
      `  │ http_reqs ────────── ${metrics.http_reqs.values.count}  (${fmt(metrics.http_reqs.values.rate)}/s)`,
    );
  }
  if (metrics.http_req_failed) {
    lines.push(
      `  │ http_req_failed ──── ${fmt(metrics.http_req_failed.values.rate * 100)}%`,
    );
  }
  if (metrics.token_success) {
    lines.push(
      `  │ token_success ────── ${fmt(metrics.token_success.values.rate * 100)}%`,
    );
  }

  lines.push("  └───────────────────────\n");
  return lines.join("\n");
}
