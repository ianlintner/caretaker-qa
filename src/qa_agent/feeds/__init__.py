"""Feed fetchers — NVD, OSV, GHSA, RSS.

Each module exposes an async ``fetch(since, until) -> list[Advisory | NewsItem]``.
"""

from __future__ import annotations

from qa_agent.feeds.ghsa import fetch_ghsa
from qa_agent.feeds.nvd import fetch_nvd
from qa_agent.feeds.osv import fetch_osv
from qa_agent.feeds.rss import fetch_rss

__all__ = ["fetch_ghsa", "fetch_nvd", "fetch_osv", "fetch_rss"]
