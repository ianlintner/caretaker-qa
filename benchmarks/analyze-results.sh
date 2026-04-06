#!/usr/bin/env bash
###############################################################################
# OAuth2 Benchmark Results Analyzer
#
# Parses k6 JSON summary files and generates a comparison table.
#
# Usage:
#   ./analyze-results.sh                     # Analyze all results
#   ./analyze-results.sh --format csv        # Output CSV
#   ./analyze-results.sh --format markdown   # Output Markdown table
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
FORMAT="${1:-markdown}"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

if [[ ! -d "$RESULTS_DIR" ]]; then
  echo "No results directory found. Run benchmarks first."
  exit 1
fi

# Check for jq
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for analysis. Install with: brew install jq"
  exit 1
fi

# ── Parse summary files ─────────────────────────────────────────────────────
# Expected filename pattern: {server}_{scenario}_{profile}_{iteration}_summary.json

server_name_for_key() {
  local server="$1"
  case "$server" in
    rust) echo "Rust OAuth2" ;;
    rust-mongo) echo "Rust OAuth2 (Mongo)" ;;
    keycloak) echo "Keycloak (Java)" ;;
    hydra) echo "Ory Hydra (Go)" ;;
    authentik) echo "Authentik (Python)" ;;
    node-oidc) echo "node-oidc (Node.js)" ;;
    *) echo "$server" ;;
  esac
}

server_lang_for_key() {
  local server="$1"
  case "$server" in
    rust) echo "Rust" ;;
    rust-mongo) echo "Rust" ;;
    keycloak) echo "Java" ;;
    hydra) echo "Go" ;;
    authentik) echo "Python" ;;
    node-oidc) echo "Node.js" ;;
    *) echo "unknown" ;;
  esac
}

server_tag_for_key() {
  local server="$1"
  case "$server" in
    rust) echo "rust-oauth2-server" ;;
    rust-mongo) echo "rust-oauth2-server-mongo" ;;
    keycloak) echo "Keycloak" ;;
    hydra) echo "Ory Hydra" ;;
    authentik) echo "Authentik" ;;
    node-oidc) echo "node-oidc-provider" ;;
    *) echo "$server" ;;
  esac
}

test_tag_for_scenario() {
  local scenario="$1"
  case "$scenario" in
    client-credentials) echo "client_credentials" ;;
    token-introspect) echo "token_introspect" ;;
    discovery) echo "discovery" ;;
    health) echo "health" ;;
    *) echo "$scenario" ;;
  esac
}

parse_results_from_raw() {
  local scenario="$1"
  local server="$2"
  local raw_file="$RESULTS_DIR/raw.json"

  if [[ ! -f "$raw_file" ]]; then
    echo "N/A|N/A|N/A|N/A|N/A|N/A|N/A"
    return
  fi

  local server_tag test_tag
  server_tag=$(server_tag_for_key "$server")
  test_tag=$(test_tag_for_scenario "$scenario")

  local parsed
  parsed=$(python3 - "$raw_file" "$server_tag" "$test_tag" <<'PY'
import json
import math
import sys
from datetime import datetime

raw_file, server_tag, test_tag = sys.argv[1], sys.argv[2], sys.argv[3]

durations = []
fails = []
req_times = []

def parse_iso(ts: str):
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    return datetime.fromisoformat(ts).timestamp()

with open(raw_file, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get('type') != 'Point':
            continue

        metric = obj.get('metric')
        data = obj.get('data', {})
        tags = data.get('tags', {})

        if tags.get('server') != server_tag or tags.get('test') != test_tag:
            continue

        if metric == 'http_reqs':
            req_times.append(parse_iso(data.get('time')))
        elif metric == 'http_req_duration':
            durations.append(float(data.get('value', 0.0)))
        elif metric == 'http_req_failed':
            fails.append(float(data.get('value', 0.0)))

if not req_times or not durations:
    print('N/A|N/A|N/A|N/A|N/A|N/A|N/A')
    sys.exit(0)

durations_sorted = sorted(durations)

def percentile(values, p):
    if not values:
        return 0.0
    idx = int(math.floor((len(values) - 1) * p))
    return values[idx]

count = len(req_times)
tmin = min(req_times)
tmax = max(req_times)
span = max(tmax - tmin, 1e-9)
rps = count / span if count > 1 else float(count)

avg = sum(durations) / len(durations)
med = percentile(durations_sorted, 0.50)
p95 = percentile(durations_sorted, 0.95)
p99 = percentile(durations_sorted, 0.99)
fail_pct = (sum(fails) / len(fails) * 100.0) if fails else 0.0

print(f"{rps:.1f}|{avg:.2f}|{med:.2f}|{p95:.2f}|{p99:.2f}|{count}|{fail_pct:.2f}%")
PY
)

  echo "$parsed"
}

# Collect all unique server+scenario combinations
parse_results() {
  local scenario="$1"
  local server="$2"

  # Find all iterations for this server+scenario
  local files=()
  while IFS= read -r f; do
    files+=("$f")
  done < <(find "$RESULTS_DIR" -name "${server}_${scenario}_*_summary.json" 2>/dev/null | sort)

  if [[ ${#files[@]} -eq 0 ]]; then
    parse_results_from_raw "$scenario" "$server"
    return
  fi

  # Average metrics across iterations
  local total_rps=0 total_avg=0 total_med=0 total_p95=0 total_p99=0 total_count=0 total_fail=0
  local n=0

  for file in "${files[@]}"; do
    local rps avg med p95 p99 count fail_rate

    rps=$(jq -r '.metrics.http_reqs.rate // 0' "$file" 2>/dev/null || echo 0)
    avg=$(jq -r '.metrics.http_req_duration.avg // 0' "$file" 2>/dev/null || echo 0)
    med=$(jq -r '.metrics.http_req_duration.med // 0' "$file" 2>/dev/null || echo 0)
    p95=$(jq -r '.metrics.http_req_duration["p(95)"] // 0' "$file" 2>/dev/null || echo 0)
    p99=$(jq -r '.metrics.http_req_duration["p(99)"] // 0' "$file" 2>/dev/null || echo 0)
    count=$(jq -r '.metrics.http_reqs.count // 0' "$file" 2>/dev/null || echo 0)
    fail_rate=$(jq -r '.metrics.http_req_failed.value // 0' "$file" 2>/dev/null || echo 0)

    total_rps=$(echo "$total_rps + $rps" | bc -l)
    total_avg=$(echo "$total_avg + $avg" | bc -l)
    total_med=$(echo "$total_med + $med" | bc -l)
    total_p95=$(echo "$total_p95 + $p95" | bc -l)
    total_p99=$(echo "$total_p99 + $p99" | bc -l)
    total_count=$(echo "$total_count + $count" | bc -l)
    total_fail=$(echo "$total_fail + $fail_rate" | bc -l)
    n=$((n + 1))
  done

  if [[ $n -eq 0 ]]; then
    echo "N/A|N/A|N/A|N/A|N/A|N/A|N/A"
    return
  fi

  local avg_rps avg_avg avg_med avg_p95 avg_p99 avg_count avg_fail
  avg_rps=$(printf "%.1f" "$(echo "$total_rps / $n" | bc -l)")
  avg_avg=$(printf "%.2f" "$(echo "$total_avg / $n" | bc -l)")
  avg_med=$(printf "%.2f" "$(echo "$total_med / $n" | bc -l)")
  avg_p95=$(printf "%.2f" "$(echo "$total_p95 / $n" | bc -l)")
  avg_p99=$(printf "%.2f" "$(echo "$total_p99 / $n" | bc -l)")
  avg_count=$(printf "%.0f" "$(echo "$total_count / $n" | bc -l)")
  avg_fail=$(printf "%.2f" "$(echo "$total_fail / $n * 100" | bc -l)")

  echo "${avg_rps}|${avg_avg}|${avg_med}|${avg_p95}|${avg_p99}|${avg_count}|${avg_fail}%"
}

render_bar() {
  local value="$1"
  local max="$2"
  local width=20

  if [[ "$value" == "N/A" || "$max" == "N/A" ]]; then
    echo "N/A"
    return
  fi

  if [[ "$(echo "$max <= 0" | bc -l)" -eq 1 ]]; then
    echo "$(printf '%*s' "$width" '' | tr ' ' '░')"
    return
  fi

  local filled
  filled=$(printf "%.0f" "$(echo "($value / $max) * $width" | bc -l)")
  if (( filled < 0 )); then filled=0; fi
  if (( filled > width )); then filled=$width; fi
  local empty=$((width - filled))

  printf '%*s' "$filled" '' | tr ' ' '█'
  printf '%*s' "$empty" '' | tr ' ' '░'
}

best_server_by_rps() {
  local scenario="$1"
  local best_server=""
  local best_rps="0"

  for server in $SERVERS; do
    local data rps
    data=$(parse_results "$scenario" "$server")
    IFS='|' read -r rps _ _ _ _ _ _ <<< "$data"

    if [[ "$rps" == "N/A" ]]; then
      continue
    fi

    if [[ "$(echo "$rps > $best_rps" | bc -l)" -eq 1 ]]; then
      best_rps="$rps"
      best_server="$server"
    fi
  done

  if [[ -z "$best_server" ]]; then
    echo "N/A|N/A"
  else
    echo "${best_server}|${best_rps}"
  fi
}

render_mermaid_pie_for_scenario() {
  local scenario="$1"
  local lines=()
  local has_data=false

  for server in $SERVERS; do
    local data rps
    data=$(parse_results "$scenario" "$server")
    IFS='|' read -r rps _ _ _ _ _ _ <<< "$data"

    if [[ "$rps" == "N/A" ]]; then
      continue
    fi

    has_data=true
    lines+=("    \"$(server_name_for_key "$server")\" : ${rps}")
  done

  if [[ "$has_data" != "true" ]]; then
    return
  fi

  echo '```mermaid'
  echo 'pie showData'
  echo "    title ${scenario} throughput share (Req/s)"
  for line in "${lines[@]}"; do
    echo "$line"
  done
  echo '```'
}

# ── Generate report ──────────────────────────────────────────────────────────
SCENARIOS="client-credentials token-introspect discovery health"
SERVERS="rust rust-mongo keycloak hydra authentik node-oidc"
REPORT_FILE="${RESULTS_DIR}/comparison-report.md"

{
  echo "# OAuth2 Server Load Test Comparison Report"
  echo ""
  echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo ""
  echo "> [!IMPORTANT]"
  echo "> These benchmark numbers are **relative local-machine comparisons**."
  echo "> Treat absolute Req/s and latency as environment-specific; focus on **ratios** and ordering trends."
  echo ""
  echo "## Executive Summary"
  echo ""
  echo "| Scenario | Winner (Req/s) | Winner Throughput |"
  echo "|----------|-----------------|------------------:|"

  for scenario in $SCENARIOS; do
    winner_data=$(best_server_by_rps "$scenario")
    IFS='|' read -r winner_server winner_rps <<< "$winner_data"

    if [[ "$winner_server" == "N/A" ]]; then
      echo "| ${scenario} | N/A | N/A |"
    else
      echo "| ${scenario} | $(server_name_for_key "$winner_server") | ${winner_rps} |"
    fi
  done
  echo ""

  for scenario in $SCENARIOS; do
    max_rps="0"
    max_latency="0"
    for server in $SERVERS; do
      data=$(parse_results "$scenario" "$server")
      IFS='|' read -r rps avg _ _ _ _ _ <<< "$data"

      if [[ "$rps" != "N/A" && "$(echo "$rps > $max_rps" | bc -l)" -eq 1 ]]; then
        max_rps="$rps"
      fi
      if [[ "$avg" != "N/A" && "$(echo "$avg > $max_latency" | bc -l)" -eq 1 ]]; then
        max_latency="$avg"
      fi
    done

    echo ""
    echo "## ${scenario}"
    echo ""
    echo "| Server | Req/s | Avg (ms) | Median (ms) | p95 (ms) | p99 (ms) | Total Reqs | Error Rate |"
    echo "|--------|------:|--------:|----------:|--------:|--------:|-----------:|-----------:|"

    for server in $SERVERS; do
      name="$(server_name_for_key "$server")"
      data=$(parse_results "$scenario" "$server")

      IFS='|' read -r rps avg med p95 p99 count fail <<< "$data"
      echo "| ${name} | ${rps} | ${avg} | ${med} | ${p95} | ${p99} | ${count} | ${fail} |"
    done

    echo ""
    echo "### Visual Comparison"
    echo ""
    echo "| Server | Throughput (relative) | Avg Latency (relative) |"
    echo "|--------|-----------------------|------------------------|"

    for server in $SERVERS; do
      data=$(parse_results "$scenario" "$server")
      IFS='|' read -r rps avg _ _ _ _ _ <<< "$data"
      throughput_bar=$(render_bar "$rps" "$max_rps")
      latency_bar=$(render_bar "$avg" "$max_latency")

      if [[ "$rps" == "N/A" ]]; then
        echo "| $(server_name_for_key "$server") | N/A | N/A |"
      else
        echo "| $(server_name_for_key "$server") | ${throughput_bar} ${rps} req/s | ${latency_bar} ${avg} ms |"
      fi
    done

    echo ""
    echo "### Throughput Share (Mermaid)"
    echo ""
    render_mermaid_pie_for_scenario "$scenario"
    echo ""
  done

  # ── Performance multiplier comparison ────────────────────────────────────
  echo ""
  echo "## Performance Comparison (vs Rust baseline)"
  echo ""
  echo "Higher is better for Req/s. Lower is better for latency."
  echo ""

  for scenario in $SCENARIOS; do
    echo "### ${scenario}"
    echo ""

    rust_data=$(parse_results "$scenario" "rust")
    IFS='|' read -r rust_rps rust_avg _ _ _ _ _ <<< "$rust_data"

    if [[ "$rust_rps" == "N/A" ]]; then
      echo "_No Rust data available for comparison._"
      echo ""
      continue
    fi

    echo "| Server | Throughput vs Rust | Latency vs Rust |"
    echo "|--------|------------------:|----------------:|"

    for server in $SERVERS; do
      name="$(server_name_for_key "$server")"
      data=$(parse_results "$scenario" "$server")
      IFS='|' read -r rps avg _ _ _ _ _ <<< "$data"

      if [[ "$rps" == "N/A" ]]; then
        echo "| ${name} | N/A | N/A |"
        continue
      fi
      throughput_ratio=$(printf "%.2fx" "$(echo "$rps / $rust_rps" | bc -l 2>/dev/null || echo 0)")
      latency_ratio=$(printf "%.2fx" "$(echo "$avg / $rust_avg" | bc -l 2>/dev/null || echo 0)")

      echo "| ${name} | ${throughput_ratio} | ${latency_ratio} |"
    done
    echo ""
  done

  echo "## Notes"
  echo ""
  echo "- Throughput ratio > 1.0x means faster than Rust baseline for that scenario."
  echo "- Latency ratio < 1.0x means lower average latency than Rust baseline."
  echo "- Use at least 3 iterations per scenario for stable directional results."
  echo "- Run medium/heavy profiles to validate scaling behavior under pressure."

} > "$REPORT_FILE"

echo -e "${GREEN}Report generated:${NC} ${REPORT_FILE}"

# Also print to stdout
cat "$REPORT_FILE"

# ── CSV export ───────────────────────────────────────────────────────────────
CSV_FILE="${RESULTS_DIR}/comparison-data.csv"
{
  echo "server,language,scenario,requests_per_second,avg_ms,median_ms,p95_ms,p99_ms,total_requests,error_rate"

  for scenario in $SCENARIOS; do
    for server in $SERVERS; do
      data=$(parse_results "$scenario" "$server")
      IFS='|' read -r rps avg med p95 p99 count fail <<< "$data"
      lang="$(server_lang_for_key "$server")"
      echo "${server},${lang},${scenario},${rps},${avg},${med},${p95},${p99},${count},${fail}"
    done
  done
} > "$CSV_FILE"

echo -e "${GREEN}CSV exported:${NC} ${CSV_FILE}"
