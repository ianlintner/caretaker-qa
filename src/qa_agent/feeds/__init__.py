"""Feed fetchers — NVD, OSV, GHSA, RSS.

Each module exposes an async ``fetch(since, until) -> list[Advisory | NewsItem]``.
The ``auth`` helper exports ``auth_headers_for(name)`` so fetchers can
attach the per-feed credentials when the matching env var is set.
"""

from __future__ import annotations

from qa_agent.feeds.auth import auth_headers_for, credential_status, known_feeds
from qa_agent.feeds.ghsa import fetch_ghsa
from qa_agent.feeds.nvd import fetch_nvd
from qa_agent.feeds.osv import fetch_osv
from qa_agent.feeds.rss import fetch_rss

__all__ = [
    "auth_headers_for",
    "credential_status",
    "fetch_ghsa",
    "fetch_nvd",
    "fetch_osv",
    "fetch_rss",
    "known_feeds",
]
