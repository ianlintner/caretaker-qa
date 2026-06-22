"""End-to-end tests for ``qa_agent.relevance_graph``.

All network + LLM calls are stubbed — this test verifies the wiring and the
brief-assembly logic only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from qa_agent.models import Advisory, Brief, JudgeVerdict, WatchlistRepo
from qa_agent.relevance_graph import run_scan


@pytest.mark.asyncio
async def test_run_scan_promotes_direct_match_and_judge_verdict(
    pypi_advisory: Advisory, topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    async def _fake_nvd(*_: Any, **__: Any) -> list[Advisory]:
        return [topic_advisory]

    async def _fake_osv(*_: Any, **__: Any) -> list[Advisory]:
        return [pypi_advisory]

    async def _fake_ghsa(*_: Any, **__: Any) -> list[Advisory]:
        return []

    async def _fake_deps(repo: WatchlistRepo) -> set[str]:
        return {"pydantic", "httpx"}

    async def _fake_judge(advisory: Advisory, repo: WatchlistRepo) -> JudgeVerdict:
        return JudgeVerdict(
            advisory_id=advisory.id,
            repo=f"{repo.owner}/{repo.repo}",
            relevant=True,
            confidence="high",
            rationale="Advisory mentions fastapi topic; repo declares fastapi.",
        )

    brief = await run_scan(
        since=datetime(2026, 4, 22, tzinfo=UTC),
        until=datetime(2026, 4, 23, tzinfo=UTC),
        watchlist=[pypi_repo],
        judge_fn=_fake_judge,
        fetch_nvd_fn=_fake_nvd,
        fetch_osv_fn=_fake_osv,
        fetch_ghsa_fn=_fake_ghsa,
        fetch_deps_fn=_fake_deps,
    )

    assert isinstance(brief, Brief)
    assert brief.repos_scanned == 1
    assert brief.feed_counts == {"nvd": 1, "osv": 1, "ghsa": 0}
    by_id = {e.advisory.id: e for e in brief.entries}
    assert by_id[pypi_advisory.id].relevance == "direct"
    assert by_id[topic_advisory.id].relevance == "likely"


@pytest.mark.asyncio
async def test_run_scan_drops_judge_non_relevant(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    async def _fake_nvd(*_: Any, **__: Any) -> list[Advisory]:
        return [topic_advisory]

    async def _empty(*_: Any, **__: Any) -> list[Advisory]:
        return []

    async def _fake_deps(repo: WatchlistRepo) -> set[str]:
        return {"requests"}  # no overlap, no topic -> still ambiguous via topic

    async def _fake_judge(advisory: Advisory, repo: WatchlistRepo) -> JudgeVerdict:
        return JudgeVerdict(
            advisory_id=advisory.id,
            repo=f"{repo.owner}/{repo.repo}",
            relevant=False,
            confidence="medium",
            rationale="Advisory targets reverse proxies; repo doesn't front one.",
        )

    brief = await run_scan(
        since=datetime(2026, 4, 22, tzinfo=UTC),
        until=datetime(2026, 4, 23, tzinfo=UTC),
        watchlist=[pypi_repo],
        judge_fn=_fake_judge,
        fetch_nvd_fn=_fake_nvd,
        fetch_osv_fn=_empty,
        fetch_ghsa_fn=_empty,
        fetch_deps_fn=_fake_deps,
    )
    assert brief.entries == []


@pytest.mark.asyncio
async def test_run_scan_continues_when_nvd_unavailable(
    pypi_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    """Scan must succeed even if the NVD feed raises (e.g. 503)."""
    import httpx

    async def _nvd_503(*_: Any, **__: Any) -> list[Advisory]:
        resp = httpx.Response(503)
        raise httpx.HTTPStatusError(
            "503", request=httpx.Request("GET", "https://nvd"), response=resp
        )

    async def _fake_osv(*_: Any, **__: Any) -> list[Advisory]:
        return [pypi_advisory]

    async def _empty(*_: Any, **__: Any) -> list[Advisory]:
        return []

    async def _fake_deps(repo: WatchlistRepo) -> set[str]:
        return {"pydantic", "httpx"}

    brief = await run_scan(
        since=datetime(2026, 4, 22, tzinfo=UTC),
        until=datetime(2026, 4, 23, tzinfo=UTC),
        watchlist=[pypi_repo],
        fetch_nvd_fn=_nvd_503,
        fetch_osv_fn=_fake_osv,
        fetch_ghsa_fn=_empty,
        fetch_deps_fn=_fake_deps,
    )

    assert isinstance(brief, Brief)
    # NVD was unavailable — scan still produced results from OSV
    assert brief.feed_counts["nvd"] == 0
    assert brief.feed_counts["osv"] == 1
    assert any(e.advisory.id == pypi_advisory.id for e in brief.entries)


@pytest.mark.asyncio
async def test_run_scan_skips_failed_judge_calls(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    """A judge that raises should be skipped, not crash the whole scan."""
    async def _fake_nvd(*_: Any, **__: Any) -> list[Advisory]:
        return [topic_advisory]

    async def _empty(*_: Any, **__: Any) -> list[Advisory]:
        return []

    async def _fake_deps(repo: WatchlistRepo) -> set[str]:
        return {"requests"}  # triggers ambiguous path

    async def _failing_judge(advisory: Advisory, repo: WatchlistRepo) -> JudgeVerdict:
        raise TimeoutError("simulated LLM timeout")

    brief = await run_scan(
        since=datetime(2026, 4, 22, tzinfo=UTC),
        until=datetime(2026, 4, 23, tzinfo=UTC),
        watchlist=[pypi_repo],
        judge_fn=_failing_judge,
        fetch_nvd_fn=_fake_nvd,
        fetch_osv_fn=_empty,
        fetch_ghsa_fn=_empty,
        fetch_deps_fn=_fake_deps,
    )
    # Failed judge verdicts are skipped — ambiguous items don't appear
    assert isinstance(brief, Brief)
    # No entry should be present (no direct match and judge failed)
    assert not any(e.advisory.id == topic_advisory.id for e in brief.entries)
