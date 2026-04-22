"""Tests for ``qa_agent.cli``."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from qa_agent.cli import _parse_since, main


def test_parse_since_duration() -> None:
    # Duration parsing: compact Nh/d/w.
    dt = _parse_since("24h")
    assert dt.tzinfo is not None


def test_parse_since_iso() -> None:
    dt = _parse_since("2026-04-22T00:00:00+00:00")
    assert dt.year == 2026


def test_parse_since_invalid() -> None:
    import click

    with pytest.raises(click.BadParameter):
        _parse_since("garbage")


def test_cli_dry_run_on_empty_watchlist(tmp_path: Path) -> None:
    wl = tmp_path / "wl.yml"
    wl.write_text("repos: []\n")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", "--watchlist", str(wl), "--dry-run", "--since", "24h"],
    )
    assert result.exit_code == 0, result.output
    assert "Security relevance brief" in result.output
    assert "nothing to scan" in result.output.lower()
