#!/usr/bin/env bash
set -euo pipefail

image="${1:-}"
out="${2:-/tmp/imagetools.txt}"
max_attempts="${MAX_ATTEMPTS:-10}"
delay="${INITIAL_DELAY_SECONDS:-3}"

if [[ -z "${image}" ]]; then
  echo "Usage: .github/scripts/validate_multiarch_manifest.sh <image> [output-file]" >&2
  exit 2
fi

for attempt in $(seq 1 "${max_attempts}"); do
  echo "Attempt ${attempt}/${max_attempts}: Inspecting manifest for ${image}"

  if docker buildx imagetools inspect "${image}" | tee "${out}"; then
    if grep -Eqi 'linux/amd64' "${out}" && grep -Eqi 'linux/arm64' "${out}"; then
      echo "Validated multi-arch manifest for ${image}"
      exit 0
    fi

    echo "Manifest present but missing expected linux/amd64 and linux/arm64 entries; retrying..."
  else
    echo "Manifest not yet available; retrying..."
  fi

  sleep "${delay}"
  delay=$((delay * 2))
  if [[ "${delay}" -gt 30 ]]; then
    delay=30
  fi
done

echo "Failed to validate multi-arch manifest for ${image}" >&2
echo "Last output:" >&2
cat "${out}" >&2 || true
exit 1