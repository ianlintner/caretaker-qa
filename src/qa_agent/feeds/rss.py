"""Security-news RSS fetcher.

Parses a fixed set of feeds into :class:`NewsItem`. Network access is via
httpx so the module is testable with respx; feedparser only parses the bytes
returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from qa_agent.models import NewsItem

DEFAULT_FEEDS: list[tuple[str, str]] = [
    ("bleepingcomputer", "https://www.bleepingcomputer.com/feed/"),
    ("thehackernews", "https://feeds.feedburner.com/TheHackersNews"),
    ("krebsonsecurity", "https://krebsonsecurity.com/feed/"),
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15), reraise=True)
async def fetch_rss(
    since: datetime,
    *,
    feeds: list[tuple[str, str]] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[NewsItem]:
    """Fetch + parse RSS feeds, returning items published on/after ``since``.

    Failures on individual feeds raise (after retries) — a feed that's been
    unreachable for hours should not silently disappear from the brief.
    """
    sources = feeds or DEFAULT_FEEDS
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True)
    try:
        items: list[NewsItem] = []
        for name, url in sources:
            resp = await c.get(url)
            resp.raise_for_status()
            items.extend(_parse_feed(name, resp.text, since))
        return items
    finally:
        if own_client:
            await c.aclose()


def _parse_feed(source: str, text: str, since: datetime) -> list[NewsItem]:
    """Return :class:`NewsItem` entries from ``text`` published on/after ``since``.

    ``feedparser.parse`` returns an unsized bag of keys; we defensively pull
    only what we need.
    """
    parsed: Any = feedparser.parse(text)
    items: list[NewsItem] = []
    for entry in getattr(parsed, "entries", []) or []:
        published = _entry_datetime(entry)
        if published is None or published < since:
            continue
        title = getattr(entry, "title", None) or entry.get("title", "")
        link = getattr(entry, "link", None) or entry.get("link", "")
        summary = getattr(entry, "summary", None) or entry.get("summary", "")
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                link=link,
                published=published,
                source=source,
                summary=summary,
            )
        )
    return items


def _entry_datetime(entry: Any) -> datetime | None:
    """Best-effort datetime extractor from an RSS entry.

    Prefers the parsed struct_time; falls back to string parsing.
    """
    struct = getattr(entry, "published_parsed", None) or entry.get("published_parsed")
    if struct is not None:
        try:
            year, month, day, hour, minute, second = struct[:6]
            return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
        except (TypeError, ValueError):
            return None
    raw = getattr(entry, "published", None) or entry.get("published")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
