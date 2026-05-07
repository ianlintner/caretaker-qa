"""OSV.dev query feed.

OSV gives structured ``affected`` blocks with ecosystem + package name, which
is what the matcher actually wants. We query the ``/querybatch`` endpoint so
we can ask about every watched package in one round-trip.

Docs: https://google.github.io/osv.dev/api/
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from qa_agent.models import Advisory, Ecosystem

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"

_ECOSYSTEM_TO_OSV: dict[Ecosystem, str] = {
    "pypi": "PyPI",
    "npm": "npm",
    "go": "Go",
    "cargo": "crates.io",
    "actions": "GitHub Actions",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15), reraise=True)
async def fetch_osv(
    packages: list[tuple[Ecosystem, str]],
    *,
    since: datetime,
    client: httpx.AsyncClient | None = None,
) -> list[Advisory]:
    """Fetch OSV advisories affecting any of ``packages`` published on/after ``since``.

    ``packages`` is a list of ``(ecosystem, package_name)`` tuples. The function
    asks OSV for all vulns affecting each package, then filters client-side to
    the ``since`` window. OSV's querybatch doesn't accept a date filter, so the
    client-side filter is required.
    """
    if not packages:
        return []

    queries = [
        {"package": {"ecosystem": _ECOSYSTEM_TO_OSV[eco], "name": name}} for eco, name in packages
    ]
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    try:
        batch = await c.post(OSV_BATCH_URL, json={"queries": queries})
        batch.raise_for_status()
        batch_payload = batch.json()
        vuln_ids: set[str] = set()
        for result in batch_payload.get("results", []):
            for vuln in result.get("vulns", []) or []:
                vid = vuln.get("id")
                if vid:
                    vuln_ids.add(vid)
        advisories: list[Advisory] = []
        for vid in vuln_ids:
            resp = await c.get(OSV_VULN_URL.format(id=vid))
            if resp.status_code != 200:
                continue
            advisory = _parse_vuln(resp.json())
            if advisory is None:
                continue
            if advisory.published >= since:
                advisories.append(advisory)
        return advisories
    finally:
        if own_client:
            await c.aclose()


def _parse_vuln(data: dict[str, Any]) -> Advisory | None:
    vid = data.get("id")
    if not vid:
        return None
    published_str = data.get("published")
    if not published_str:
        return None
    published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
    severity_entries = data.get("severity", []) or []
    severity, cvss = _severity(severity_entries)
    affected_packages: list[str] = []
    affected_ranges: list[str] = []
    ecosystem_seen: Ecosystem | None = None
    for aff in data.get("affected", []) or []:
        pkg = aff.get("package", {}) or {}
        name = pkg.get("name")
        eco = pkg.get("ecosystem")
        if name:
            affected_packages.append(name)
        if eco:
            mapped = _osv_to_ecosystem(eco)
            if mapped is not None:
                ecosystem_seen = mapped
        for ranges in aff.get("ranges", []) or []:
            events = ranges.get("events", []) or []
            affected_ranges.extend(
                f"{evt.get('introduced', '0')}..{evt.get('fixed', '∞')}"
                for evt in events
                if "introduced" in evt or "fixed" in evt
            )
    return Advisory(
        id=vid,
        source="osv",
        title=data.get("summary") or vid,
        summary=data.get("details", "") or "",
        severity=severity,
        cvss=cvss,
        published=published,
        ecosystem=ecosystem_seen,
        affected_packages=sorted(set(affected_packages)),
        affected_ranges=sorted(set(affected_ranges)),
        references=[
            ref.get("url", "") for ref in data.get("references", []) or [] if ref.get("url")
        ],
    )


def _osv_to_ecosystem(value: str) -> Ecosystem | None:
    match value.lower():
        case "pypi":
            return "pypi"
        case "npm":
            return "npm"
        case "go":
            return "go"
        case "crates.io":
            return "cargo"
        case "github actions":
            return "actions"
        case _:
            return None


def _severity(entries: list[dict[str, Any]]) -> tuple[str, float | None]:
    """Return ``(severity, cvss)`` from the OSV severity array.

    OSV severity entries have ``type`` (CVSS_V3 / CVSS_V2) and ``score``
    (vector string). We don't parse the vector — CVSS score comes from
    ``database_specific`` or is left unknown.
    """
    if not entries:
        return "unknown", None
    for entry in entries:
        score = entry.get("score")
        if isinstance(score, int | float):
            num = float(score)
            if num >= 9.0:
                return "critical", num
            if num >= 7.0:
                return "high", num
            if num >= 4.0:
                return "medium", num
            if num > 0:
                return "low", num
    return "unknown", None
