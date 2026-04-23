"""NVD 2.0 CVE feed.

Docs: https://nvd.nist.gov/developers/vulnerabilities

We request only a window, not the full catalogue, so the response stays small
and we never paginate beyond the first page in the default case. The NVD API
is rate-limited to 5 requests / 30s anonymously; this module makes one call
per scan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from qa_agent.models import Advisory, Severity

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Return True only for transient failures worth retrying.

    - HTTP 429 and 5xx → retry (rate-limit / server-side transient).
    - ``httpx.RequestError`` (connect/timeout/network) → retry.
    - Everything else (4xx client errors, parsing bugs, …) → fail fast.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, httpx.RequestError)  # network-level only; everything else fails fast


def _severity_of(metric: dict[str, Any]) -> tuple[Severity, float | None]:
    """Extract a ``(severity, cvss)`` tuple from an NVD metrics block.

    NVD returns metrics in one of ``cvssMetricV31`` / ``cvssMetricV30`` /
    ``cvssMetricV2`` depending on what's available. We prefer the newest.
    """
    for key in ("cvssMetricV31", "cvssMetricV30"):
        block = metric.get(key)
        if block:
            data = block[0].get("cvssData", {})
            score = data.get("baseScore")
            sev = str(data.get("baseSeverity", "")).lower() or "unknown"
            return _normalise_severity(sev), float(score) if score is not None else None
    v2 = metric.get("cvssMetricV2")
    if v2:
        data = v2[0].get("cvssData", {})
        score = data.get("baseScore")
        sev = str(v2[0].get("baseSeverity", "")).lower() or "unknown"
        return _normalise_severity(sev), float(score) if score is not None else None
    return "unknown", None


def _normalise_severity(value: str) -> Severity:
    """Map NVD severity strings onto our :data:`Severity` literal."""
    match value.lower():
        case "critical":
            return "critical"
        case "high":
            return "high"
        case "medium" | "moderate":
            return "medium"
        case "low":
            return "low"
        case _:
            return "unknown"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=30),
    retry=retry_if_exception(_is_retryable_http_error),
    reraise=True,
)
async def fetch_nvd(
    since: datetime,
    until: datetime,
    *,
    client: httpx.AsyncClient | None = None,
    results_per_page: int = 200,
) -> list[Advisory]:
    """Return advisories published in ``[since, until)``.

    Raises on HTTP error (after retries) rather than silently returning ``[]``.
    """
    params = {
        "pubStartDate": since.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "pubEndDate": until.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "resultsPerPage": str(results_per_page),
    }
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    try:
        resp = await c.get(NVD_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            await c.aclose()

    advisories: list[Advisory] = []
    for vuln in payload.get("vulnerabilities", []):
        cve = vuln.get("cve", {})
        cve_id = cve.get("id")
        if not cve_id:
            continue
        descs = cve.get("descriptions", [])
        summary = next((d.get("value", "") for d in descs if d.get("lang") == "en"), "")
        severity, cvss = _severity_of(cve.get("metrics", {}) or {})
        refs = [r.get("url", "") for r in cve.get("references", []) if r.get("url")]
        published_str = cve.get("published")
        if not published_str:
            continue
        published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        # NVD doesn't enumerate affected packages in a stable machine-readable
        # form across all advisories; we leave the field empty and rely on
        # OSV / GHSA for structured package matching. The title + summary
        # stays useful for the LLM judge.
        advisories.append(
            Advisory(
                id=cve_id,
                source="nvd",
                title=cve_id,
                summary=summary,
                severity=severity,
                cvss=cvss,
                published=published,
                references=refs,
            )
        )
    return advisories
