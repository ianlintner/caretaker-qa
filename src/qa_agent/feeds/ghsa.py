"""GitHub Advisory Database feed.

Queries the public REST endpoint ``/advisories`` (no auth required, but rate
limits are much higher with a token). Docs:
https://docs.github.com/en/rest/security-advisories/global-advisories
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from qa_agent.models import Advisory, Ecosystem

GHSA_URL = "https://api.github.com/advisories"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15), reraise=True)
async def fetch_ghsa(
    since: datetime,
    until: datetime,
    *,
    client: httpx.AsyncClient | None = None,
    per_page: int = 100,
) -> list[Advisory]:
    """Fetch published GHSA advisories in ``[since, until)``.

    The GHSA endpoint's ``published`` filter accepts a range string of the
    form ``YYYY-MM-DDTHH:MM:SSZ..YYYY-MM-DDTHH:MM:SSZ``. We only request one
    page; anything more would go outside a 24-hour window by the time we
    hit the rate limit.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "published": f"{since.strftime('%Y-%m-%dT%H:%M:%SZ')}..{until.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "per_page": str(per_page),
        "sort": "published",
        "direction": "desc",
    }
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    try:
        resp = await c.get(GHSA_URL, headers=headers, params=params)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            await c.aclose()

    advisories: list[Advisory] = []
    if not isinstance(payload, list):
        return advisories
    for item in payload:
        advisory = _parse_advisory(item)
        if advisory is not None:
            advisories.append(advisory)
    return advisories


def _parse_advisory(item: dict[str, Any]) -> Advisory | None:
    ghsa_id = item.get("ghsa_id")
    if not ghsa_id:
        return None
    published_str = item.get("published_at")
    if not published_str:
        return None
    published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
    severity = _severity(item.get("severity"))
    cvss_block = item.get("cvss") or {}
    cvss_score = cvss_block.get("score") if isinstance(cvss_block, dict) else None
    affected_packages: list[str] = []
    affected_ranges: list[str] = []
    ecosystem_seen: Ecosystem | None = None
    for vuln in item.get("vulnerabilities", []) or []:
        pkg = vuln.get("package", {}) or {}
        name = pkg.get("name")
        eco = pkg.get("ecosystem")
        if name:
            affected_packages.append(name)
        if eco:
            mapped = _ghsa_to_ecosystem(eco)
            if mapped is not None:
                ecosystem_seen = mapped
        vulnerable_range = vuln.get("vulnerable_version_range")
        if vulnerable_range:
            affected_ranges.append(vulnerable_range)
    return Advisory(
        id=ghsa_id,
        source="ghsa",
        title=item.get("summary") or ghsa_id,
        summary=item.get("description", "") or "",
        severity=severity,
        cvss=float(cvss_score) if isinstance(cvss_score, (int, float)) else None,
        published=published,
        ecosystem=ecosystem_seen,
        affected_packages=sorted(set(affected_packages)),
        affected_ranges=sorted(set(affected_ranges)),
        references=[
            url for ref in item.get("references", []) or [] if (url := _extract_ref_url(ref))
        ],
    )


def _extract_ref_url(ref: Any) -> str:
    """Return the URL string from a reference entry.

    The GHSA API may return references as plain strings or as dicts with a
    ``url`` key. This helper normalises both formats.
    """
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        return str(ref.get("url", "") or "")
    return ""


def _severity(value: Any) -> str:
    raw = str(value or "").lower()
    if raw in {"critical", "high", "medium", "low"}:
        return raw
    if raw == "moderate":
        return "medium"
    return "unknown"


def _ghsa_to_ecosystem(value: str) -> Ecosystem | None:
    match value.lower():
        case "pip":
            return "pypi"
        case "npm":
            return "npm"
        case "go":
            return "go"
        case "rust":
            return "cargo"
        case "actions":
            return "actions"
        case _:
            return None
