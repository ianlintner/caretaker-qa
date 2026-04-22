"""Report writers — render a :class:`Brief` as Markdown + JSON."""

from __future__ import annotations

import json
from pathlib import Path

from qa_agent.models import Brief, ReportEntry

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "unknown": 4,
}


def render_markdown(brief: Brief) -> str:
    """Render a :class:`Brief` as a self-contained Markdown digest.

    The output is stable enough to commit to the repo: advisories are sorted
    by severity then by ID, so an unchanged scan produces an identical file.
    """
    lines: list[str] = []
    window = (
        f"{brief.since.isoformat(timespec='minutes')} → {brief.until.isoformat(timespec='minutes')}"
    )
    lines.append(f"# Security relevance brief — {brief.generated_at.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append(f"Window: {window}  •  Repos scanned: {brief.repos_scanned}")
    feed_bits = ", ".join(f"{k}={v}" for k, v in sorted(brief.feed_counts.items()))
    if feed_bits:
        lines.append(f"Feeds: {feed_bits}")
    lines.append("")

    if not brief.entries:
        lines.append("No relevant advisories in this window.")
        lines.append("")
        return "\n".join(lines)

    ranked = sorted(
        brief.entries,
        key=lambda e: (_SEVERITY_ORDER.get(e.severity, 99), e.advisory.id),
    )
    for group in ("direct", "likely", "speculative"):
        group_entries = [e for e in ranked if e.relevance == group]
        if not group_entries:
            continue
        heading = {
            "direct": "## Direct matches",
            "likely": "## Likely-relevant",
            "speculative": "## Speculative",
        }[group]
        lines.append(heading)
        lines.append("")
        for entry in group_entries:
            lines.extend(_render_entry(entry))
        lines.append("")
    return "\n".join(lines)


def _render_entry(entry: ReportEntry) -> list[str]:
    adv = entry.advisory
    cvss = f"  •  CVSS {adv.cvss:.1f}" if adv.cvss is not None else ""
    refs = "\n".join(f"  - <{r}>" for r in adv.references[:3])
    block = [
        f"### {adv.id} — {entry.repo}",
        f"_severity: **{entry.severity}**  •  source: {adv.source}{cvss}_",
        "",
        adv.summary.strip() or adv.title.strip(),
        "",
        f"**Why flagged:** {entry.rationale}",
    ]
    if refs:
        block.append("")
        block.append("References:")
        block.append(refs)
    block.append("")
    return block


def render_json(brief: Brief) -> str:
    """Render the brief as JSON. Equivalent to ``brief.model_dump_json(indent=2)``."""
    return brief.model_dump_json(indent=2)


def write(brief: Brief, out_md: Path, out_json: Path | None = None) -> None:
    """Write Markdown + optional JSON to disk, creating parent dirs."""
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(brief))
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(render_json(brief))


__all__ = ["render_json", "render_markdown", "write"]

# Defensive re-export so test imports stay short.
_ = json
