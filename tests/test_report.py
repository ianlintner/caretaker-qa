"""Tests for ``qa_agent.report``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from qa_agent.models import Advisory, Brief, ReportEntry
from qa_agent.report import render_json, render_markdown, write


def _advisory() -> Advisory:
    return Advisory(
        id="CVE-2026-0001",
        source="nvd",
        title="Example",
        summary="A short summary.",
        severity="critical",
        cvss=9.3,
        published=datetime(2026, 4, 22, tzinfo=UTC),
        affected_packages=["pydantic"],
        references=["https://e/1", "https://e/2"],
    )


def _brief() -> Brief:
    adv = _advisory()
    return Brief(
        generated_at=datetime(2026, 4, 22, 12, tzinfo=UTC),
        since=datetime(2026, 4, 21, 12, tzinfo=UTC),
        until=datetime(2026, 4, 22, 12, tzinfo=UTC),
        entries=[
            ReportEntry(
                advisory=adv,
                repo="example/app",
                severity="critical",
                relevance="direct",
                rationale="declared dep 'pydantic' named in advisory",
            )
        ],
        feed_counts={"nvd": 4, "osv": 2, "ghsa": 1},
        repos_scanned=5,
    )


def test_render_markdown_sorts_by_severity() -> None:
    brief = _brief()
    # Add a lower-severity entry.
    second = ReportEntry(
        advisory=_advisory().model_copy(update={"id": "CVE-2026-0002", "severity": "low"}),
        repo="example/app",
        severity="low",
        relevance="direct",
        rationale="some reason",
    )
    brief = brief.model_copy(update={"entries": [second, brief.entries[0]]})
    out = render_markdown(brief)
    idx0 = out.index("CVE-2026-0001")
    idx1 = out.index("CVE-2026-0002")
    # Critical first.
    assert idx0 < idx1


def test_render_markdown_empty_brief_friendly() -> None:
    brief = _brief().model_copy(update={"entries": []})
    out = render_markdown(brief)
    assert "No relevant advisories" in out


def test_render_json_roundtrip() -> None:
    brief = _brief()
    raw = render_json(brief)
    assert '"id": "CVE-2026-0001"' in raw
    assert '"relevance": "direct"' in raw


def test_write_creates_parent(tmp_path: Path) -> None:
    out = tmp_path / "reports" / "2026-04-22.md"
    out_json = tmp_path / "reports" / "2026-04-22.json"
    write(_brief(), out, out_json)
    assert out.exists() and out.read_text().startswith("# Security relevance brief")
    assert out_json.exists() and '"repos_scanned": 5' in out_json.read_text()
