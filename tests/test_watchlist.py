"""Tests for ``qa_agent.watchlist``."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_agent.watchlist import load_watchlist


def test_load_watchlist_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "wl.yml"
    p.write_text(
        """
repos:
  - owner: octo
    repo: octocat
    ecosystem: pypi
    topics: [demo]
  - owner: octo
    repo: other
    ecosystem: npm
""".strip()
    )
    repos = load_watchlist(p)
    assert [(r.owner, r.repo, r.ecosystem) for r in repos] == [
        ("octo", "octocat", "pypi"),
        ("octo", "other", "npm"),
    ]
    assert repos[0].topics == ["demo"]
    assert repos[1].topics == []


def test_load_watchlist_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_watchlist(tmp_path / "nope.yml")


def test_load_watchlist_rejects_list_root(tmp_path: Path) -> None:
    p = tmp_path / "wl.yml"
    p.write_text("- just: a list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_watchlist(p)


def test_load_watchlist_rejects_repos_not_a_list(tmp_path: Path) -> None:
    p = tmp_path / "wl.yml"
    p.write_text("repos: {a: 1}\n")
    with pytest.raises(ValueError, match="list"):
        load_watchlist(p)


def test_load_watchlist_empty_file_returns_empty_list(tmp_path: Path) -> None:
    p = tmp_path / "wl.yml"
    p.write_text("")
    assert load_watchlist(p) == []
