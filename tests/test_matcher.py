"""Tests for ``qa_agent.matcher``."""

from __future__ import annotations

from qa_agent.matcher import match
from qa_agent.models import Advisory, WatchlistRepo


def test_direct_package_match_flags_match(
    pypi_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    verdict = match(pypi_advisory, pypi_repo, deps={"pydantic", "httpx"})
    assert verdict.status == "match"
    assert verdict.matched_package == "pydantic"
    assert "pydantic" in verdict.reason


def test_no_match_when_ecosystem_differs(
    pypi_advisory: Advisory,
) -> None:
    npm_repo = WatchlistRepo(owner="x", repo="y", ecosystem="npm", topics=[])
    verdict = match(pypi_advisory, npm_repo, deps={"react"})
    assert verdict.status == "no_match"


def test_topic_mention_with_no_package_is_ambiguous(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    verdict = match(topic_advisory, pypi_repo, deps={"requests"})
    assert verdict.status == "ambiguous"
    assert "topic" in verdict.reason


def test_topic_absent_and_no_name_match_is_no_match(
    pypi_advisory: Advisory,
) -> None:
    # Same ecosystem, different package, no topic overlap.
    repo = WatchlistRepo(owner="x", repo="y", ecosystem="pypi", topics=["unrelated"])
    verdict = match(pypi_advisory, repo, deps={"requests"})
    assert verdict.status == "no_match"


def test_case_insensitive_package_match(pypi_advisory: Advisory, pypi_repo: WatchlistRepo) -> None:
    # Advisory lists "Pydantic", repo dep is lowercase. Matcher should handle.
    upper = pypi_advisory.model_copy(update={"affected_packages": ["Pydantic"]})
    verdict = match(upper, pypi_repo, deps={"pydantic"})
    assert verdict.status == "match"
