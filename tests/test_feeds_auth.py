"""Tests for the feed-auth helper.

Coverage:
- ``auth_headers_for`` returns the right header when env var is set
- empty / unset env var produces an empty dict (anonymous path)
- unknown feed names return an empty dict (no crash)
- ``credential_status`` is a pure diagnostic — it never reads beyond env
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from qa_agent.feeds.auth import (
    auth_headers_for,
    credential_status,
    known_feeds,
)


@pytest.fixture
def clean_env() -> Iterator[None]:
    """Strip auth env vars before each test so order can't leak state."""
    keys = ["NVD_API_KEY", "GITHUB_TOKEN"]
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_known_feeds_includes_nvd_and_ghsa() -> None:
    feeds = known_feeds()
    assert "nvd" in feeds
    assert "ghsa" in feeds


def test_anonymous_when_env_unset(clean_env: None) -> None:
    assert auth_headers_for("nvd") == {}
    assert auth_headers_for("ghsa") == {}


def test_nvd_uses_api_key_header(clean_env: None) -> None:
    os.environ["NVD_API_KEY"] = "abc123"
    headers = auth_headers_for("nvd")
    assert headers == {"apiKey": "abc123"}


def test_ghsa_uses_bearer_authorization(clean_env: None) -> None:
    os.environ["GITHUB_TOKEN"] = "ghp_xxx"
    headers = auth_headers_for("ghsa")
    assert headers == {"Authorization": "Bearer ghp_xxx"}


def test_empty_string_treated_as_anonymous(clean_env: None) -> None:
    """Empty / whitespace-only env var must not produce an
    ``apiKey: `` header — that's worse than anonymous (servers
    sometimes reject empty credentials with a 400 instead of falling
    through to the anonymous-quota path)."""
    os.environ["NVD_API_KEY"] = "   "
    assert auth_headers_for("nvd") == {}


def test_unknown_feed_returns_empty_dict(clean_env: None) -> None:
    """Defensive: a typo'd feed name must not raise — fetchers should
    keep running on the anonymous path rather than crashing the whole
    fetcher stage."""
    assert auth_headers_for("nonexistent-feed") == {}


def test_credential_status_reflects_env_state(clean_env: None) -> None:
    os.environ["NVD_API_KEY"] = "x"
    status = credential_status()
    assert status["nvd"] is True
    assert status["ghsa"] is False
