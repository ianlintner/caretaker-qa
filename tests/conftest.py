"""Shared fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qa_agent.models import Advisory, WatchlistRepo


@pytest.fixture
def pypi_advisory() -> Advisory:
    return Advisory(
        id="GHSA-aaaa-bbbb-cccc",
        source="ghsa",
        title="Remote code execution in pydantic",
        summary="A crafted model config causes RCE under certain conditions.",
        severity="high",
        cvss=7.8,
        published=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
        ecosystem="pypi",
        affected_packages=["pydantic"],
        affected_ranges=["<2.8.1"],
        references=["https://example.com/advisory/1"],
    )


@pytest.fixture
def topic_advisory() -> Advisory:
    """No direct package match, but mentions a topic keyword."""
    return Advisory(
        id="CVE-2026-0001",
        source="nvd",
        title="Cache poisoning in FastAPI reverse proxies",
        summary="A misconfiguration in some FastAPI deployments allows cache poisoning.",
        severity="medium",
        cvss=6.1,
        published=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
        ecosystem=None,
        affected_packages=[],
        references=[],
    )


@pytest.fixture
def pypi_repo() -> WatchlistRepo:
    return WatchlistRepo(
        owner="example",
        repo="app",
        ecosystem="pypi",
        topics=["web", "fastapi"],
    )
