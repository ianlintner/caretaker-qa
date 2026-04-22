"""NVD 2.0 API feed fetcher.

Fetches CVE advisories published within [since, until) from the NIST NVD REST API v2.
Retries on transient failures (5xx, network errors) with tenacity.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from qa_agent.models import Advisory

_NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_DATE_FMT = "%Y-%m-%dT%H:%M:%S.000"

_RETRY_STATUS = {429, 500, 502, 503, 504}


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def fetch_nvd(
    since: datetime,
    until: datetime,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[Advisory]:
    """Fetch NVD CVEs published in [since, until).

    Handles HTTP 429 rate-limit responses with exponential backoff retry.
    Fixes #9: previously raised immediately on 429.
    """
    params = {
        "pubStartDate": since.strftime(_DATE_FMT),
        "pubEndDate": until.strftime(_DATE_FMT),
        "resultsPerPage": 100,
    }
    _client = client or httpx.AsyncClient(timeout=30.0)
    try:
        resp = await _client.get(_NVD_URL, params=params)
        if resp.status_code in _RETRY_STATUS:
            resp.raise_for_status()
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    finally:
        if client is None:
            await _client.aclose()

    advisories: list[Advisory] = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id")
        published_str = cve.get("published")
        if not cve_id or not published_str:
            continue
        try:
            published = datetime.strptime(published_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue

        descriptions = cve.get("descriptions", [])
        summary = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")

        metrics = cve.get("metrics", {})
        severity, cvss = _extract_severity(metrics)

        refs = [r["url"] for r in cve.get("references", []) if "url" in r]

        advisories.append(
            Advisory(
                id=cve_id,
                summary=summary,
                severity=severity,
                cvss=cvss,
                published=published,
                references=refs,
                source="nvd",
            )
        )
    return advisories


def _extract_severity(metrics: dict[str, Any]) -> tuple[str, float | None]:
    for key in ("cvssMetricV31", "cvssMetricV30"):
        entries = metrics.get(key, [])
        if entries:
            data = entries[0].get("cvssData", {})
            raw = data.get("baseSeverity", "unknown").lower()
            severity = "medium" if raw == "moderate" else raw
            return severity, data.get("baseScore")
    for entry in metrics.get("cvssMetricV2", []):
        data = entry.get("cvssData", {})
        raw = (entry.get("baseSeverity") or data.get("baseSeverity", "unknown")).lower()
        return raw, data.get("baseScore")
    return "unknown", None
