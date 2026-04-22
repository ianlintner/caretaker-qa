"""Parse ``watchlist.yml``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import TypeAdapter

from qa_agent.models import WatchlistRepo

_WATCHLIST_ADAPTER = TypeAdapter(list[WatchlistRepo])


def load_watchlist(path: str | Path) -> list[WatchlistRepo]:
    """Parse a YAML watchlist into a validated list of :class:`WatchlistRepo`.

    The YAML root must be a mapping with a ``repos`` key. Unknown keys on
    each entry are rejected by the pydantic model, so typos surface at load
    time rather than as a silent match miss later.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"watchlist file not found: {p}")
    data = yaml.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top-level YAML must be a mapping")
    repos = data.get("repos") or []
    if not isinstance(repos, list):
        raise ValueError(f"{p}: 'repos' must be a list")
    return _WATCHLIST_ADAPTER.validate_python(repos)
