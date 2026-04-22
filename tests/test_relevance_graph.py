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
