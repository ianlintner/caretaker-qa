"""Tests for ``qa_agent.feeds``."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from qa_agent.feeds.ghsa import fetch_ghsa
from qa_agent.feeds.nvd import fetch_nvd
from qa_agent.feeds.osv import fetch_osv
from qa_agent.feeds.rss import fetch_rss


@pytest.mark.asyncio
@respx.mock
async def test_nvd_parses_v31_metrics() -> None:
    payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-0042",
                    "descriptions": [
                        {"lang": "en", "value": "Example summary."},
                        {"lang": "de", "value": "Beispiel."},
                    ],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}}
                        ]
                    },
                    "references": [{"url": "https://example.com/1"}],
                    "published": "2026-04-22T08:00:00.000",
                }
            }
        ]
    }
    respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adv = await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert len(adv) == 1
    assert adv[0].id == "CVE-2026-0042"
    assert adv[0].severity == "critical"
    assert adv[0].cvss == 9.1
    assert "Example summary" in adv[0].summary


@pytest.mark.asyncio
@respx.mock
async def test_osv_returns_empty_when_no_packages() -> None:
    adv = await fetch_osv([], since=datetime(2026, 4, 22, tzinfo=UTC))
    assert adv == []


@pytest.mark.asyncio
@respx.mock
async def test_osv_filters_by_since_window() -> None:
    respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"vulns": [{"id": "GHSA-old"}, {"id": "GHSA-new"}]}]},
        )
    )
    respx.get("https://api.osv.dev/v1/vulns/GHSA-old").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "GHSA-old",
                "summary": "stale advisory",
                "published": "2026-01-01T00:00:00Z",
                "affected": [{"package": {"ecosystem": "PyPI", "name": "pkg"}}],
            },
        )
    )
    respx.get("https://api.osv.dev/v1/vulns/GHSA-new").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "GHSA-new",
                "summary": "fresh advisory",
                "published": "2026-04-22T10:00:00Z",
                "affected": [{"package": {"ecosystem": "PyPI", "name": "pkg"}}],
            },
        )
    )
    adv = await fetch_osv(
        [("pypi", "pkg")],
        since=datetime(2026, 4, 22, tzinfo=UTC),
    )
    ids = {a.id for a in adv}
    assert "GHSA-new" in ids
    assert "GHSA-old" not in ids


@pytest.mark.asyncio
@respx.mock
async def test_ghsa_parses_published_range() -> None:
    payload = [
        {
            "ghsa_id": "GHSA-xxxx-yyyy-zzzz",
            "summary": "An advisory",
            "description": "details",
            "severity": "high",
            "cvss": {"score": 7.5},
            "published_at": "2026-04-22T09:00:00Z",
            "vulnerabilities": [
                {
                    "package": {"ecosystem": "pip", "name": "pydantic"},
                    "vulnerable_version_range": "< 2.8.1",
                }
            ],
            "references": [{"url": "https://example.com/a"}],
        }
    ]
    respx.get("https://api.github.com/advisories").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adv = await fetch_ghsa(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert len(adv) == 1
    assert adv[0].id == "GHSA-xxxx-yyyy-zzzz"
    assert adv[0].ecosystem == "pypi"
    assert adv[0].affected_packages == ["pydantic"]
    assert adv[0].severity == "high"


@pytest.mark.asyncio
@respx.mock
async def test_rss_filters_by_since() -> None:
    feed_text = """
<?xml version="1.0"?>
<rss version="2.0">
<channel>
<item>
  <title>Old news</title>
  <link>https://e/old</link>
  <pubDate>Mon, 01 Jan 2026 00:00:00 +0000</pubDate>
  <description>old</description>
</item>
<item>
  <title>Fresh news</title>
  <link>https://e/new</link>
  <pubDate>Wed, 22 Apr 2026 09:00:00 +0000</pubDate>
  <description>fresh</description>
</item>
</channel>
</rss>
""".strip()
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(200, text=feed_text))
    items = await fetch_rss(
        datetime(2026, 4, 22, tzinfo=UTC),
        feeds=[("example", "https://example.com/feed")],
    )
    titles = {i.title for i in items}
    assert "Fresh news" in titles
    assert "Old news" not in titles


@pytest.mark.asyncio
@respx.mock
async def test_nvd_parses_v30_and_v2_fallback() -> None:
    payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-1",
                    "descriptions": [{"lang": "en", "value": "v30"}],
                    "metrics": {
                        "cvssMetricV30": [
                            {"cvssData": {"baseScore": 5.5, "baseSeverity": "MODERATE"}}
                        ]
                    },
                    "published": "2026-04-22T08:00:00.000",
                }
            },
            {
                "cve": {
                    "id": "CVE-2026-2",
                    "descriptions": [{"lang": "en", "value": "v2"}],
                    "metrics": {
                        "cvssMetricV2": [
                            {
                                "baseSeverity": "LOW",
                                "cvssData": {"baseScore": 2.5, "baseSeverity": "LOW"},
                            }
                        ]
                    },
                    "published": "2026-04-22T08:00:00.000",
                }
            },
            {
                "cve": {
                    # Missing metrics block → severity=unknown, cvss=None.
                    "id": "CVE-2026-3",
                    "descriptions": [{"lang": "en", "value": "bare"}],
                    "published": "2026-04-22T08:00:00.000",
                }
            },
        ]
    }
    respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adv = await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    by_id = {a.id: a for a in adv}
    assert by_id["CVE-2026-1"].severity == "medium"
    assert by_id["CVE-2026-2"].severity == "low"
    assert by_id["CVE-2026-3"].severity == "unknown"


@pytest.mark.asyncio
@respx.mock
async def test_nvd_drops_entries_without_id_or_published() -> None:
    payload = {
        "vulnerabilities": [
            {"cve": {"descriptions": [{"lang": "en", "value": "no id"}]}},
            {"cve": {"id": "CVE-no-date"}},
        ]
    }
    respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adv = await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert adv == []


@pytest.mark.asyncio
@respx.mock
async def test_nvd_http_error_retries_then_raises() -> None:
    respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))


@pytest.mark.asyncio
@respx.mock
async def test_nvd_429_retries_and_succeeds() -> None:
    """A single 429 response must be retried; a subsequent 200 must succeed."""
    ok_payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-0429",
                    "descriptions": [{"lang": "en", "value": "rate-limit retry"}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 5.0, "baseSeverity": "MEDIUM"}}
                        ]
                    },
                    "references": [],
                    "published": "2026-04-22T08:00:00.000",
                }
            }
        ]
    }
    route = respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
    route.side_effect = [
        httpx.Response(429),
        httpx.Response(200, json=ok_payload),
    ]
    adv = await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert len(adv) == 1
    assert adv[0].id == "CVE-2026-0429"
    assert adv[0].severity == "medium"


@pytest.mark.asyncio
@respx.mock
async def test_nvd_non_retryable_4xx_raises_immediately() -> None:
    """Client errors other than 429 (e.g. 403) must not be retried."""
    route = respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
    route.mock(return_value=httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert exc_info.value.response.status_code == 403
    # Only one HTTP call should have been made (no retries for 403).
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_nvd_non_http_exception_does_not_retry() -> None:
    """Parsing/logic errors (e.g. ValueError) must not be retried."""
    route = respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
    # Return a body that cannot be parsed as JSON to trigger a ValueError.
    route.mock(return_value=httpx.Response(200, content=b"not-json"))
    with pytest.raises(ValueError):
        await fetch_nvd(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    # Only one HTTP call should have been made — no retries for parse errors.
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_osv_skips_missing_vulns() -> None:
    respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(
            200, json={"results": [{"vulns": [{"id": "GHSA-404"}, {"id": "GHSA-bad"}]}]}
        )
    )
    respx.get("https://api.osv.dev/v1/vulns/GHSA-404").mock(return_value=httpx.Response(404))
    # GHSA-bad has no published_at; _parse_vuln returns None.
    respx.get("https://api.osv.dev/v1/vulns/GHSA-bad").mock(
        return_value=httpx.Response(200, json={"id": "GHSA-bad"})
    )
    adv = await fetch_osv([("pypi", "pkg")], since=datetime(2026, 4, 22, tzinfo=UTC))
    assert adv == []


@pytest.mark.asyncio
@respx.mock
async def test_osv_severity_score_buckets() -> None:
    respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(200, json={"results": [{"vulns": [{"id": "X-1"}]}]})
    )
    respx.get("https://api.osv.dev/v1/vulns/X-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "X-1",
                "published": "2026-04-22T10:00:00Z",
                "severity": [{"score": 4.5}],
                "affected": [
                    {
                        "package": {"ecosystem": "PyPI", "name": "pkg"},
                        "ranges": [{"events": [{"introduced": "0"}, {"fixed": "1.2.3"}]}],
                    }
                ],
            },
        )
    )
    adv = await fetch_osv([("pypi", "pkg")], since=datetime(2026, 4, 22, tzinfo=UTC))
    assert len(adv) == 1
    assert adv[0].severity == "medium"
    assert adv[0].cvss == 4.5


@pytest.mark.asyncio
@respx.mock
async def test_ghsa_empty_response() -> None:
    respx.get("https://api.github.com/advisories").mock(return_value=httpx.Response(200, json=[]))
    adv = await fetch_ghsa(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert adv == []


@pytest.mark.asyncio
@respx.mock
async def test_ghsa_unexpected_payload_shape() -> None:
    respx.get("https://api.github.com/advisories").mock(
        return_value=httpx.Response(200, json={"unexpected": "dict"})
    )
    adv = await fetch_ghsa(datetime(2026, 4, 22, tzinfo=UTC), datetime(2026, 4, 23, tzinfo=UTC))
    assert adv == []


# Silence the unused import warning on json in environments where respx does
# its own body marshalling.
_ = json
