"""Click-based CLI entry point."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

from qa_agent.models import Advisory, JudgeVerdict, WatchlistRepo
from qa_agent.relevance_graph import run_scan
from qa_agent.report import render_json, render_markdown, write
from qa_agent.watchlist import load_watchlist

_SINCE_RE = re.compile(r"(\d+)([hdw])")


def _parse_since(value: str) -> datetime:
    """Parse ``--since`` as ``<N>[hdw]`` or an ISO-8601 timestamp."""
    stripped = value.strip()
    m = _SINCE_RE.fullmatch(stripped)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        delta = {
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
            "w": timedelta(weeks=amount),
        }[unit]
        return datetime.now(UTC) - delta
    try:
        parsed = datetime.fromisoformat(stripped)
    except ValueError as exc:
        raise click.BadParameter(
            f"--since must be a duration like '24h' / '7d' / '1w' or ISO-8601; got {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


@click.group()
@click.version_option()
def main() -> None:
    """caretaker-qa — security-relevance agent."""


@main.command()
@click.option(
    "--since",
    default="24h",
    show_default=True,
    help="Window lower bound: '24h', '7d', '1w', or ISO-8601 timestamp.",
)
@click.option(
    "--watchlist",
    "watchlist_path",
    default="watchlist.yml",
    show_default=True,
    type=click.Path(exists=True),
)
@click.option(
    "--out",
    "out_md",
    default=None,
    type=click.Path(),
    help="Write Markdown brief here. Defaults to stdout.",
)
@click.option(
    "--out-json",
    "out_json",
    default=None,
    type=click.Path(),
    help="Also write JSON payload here.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Skip LLM calls; ambiguous items are dropped instead of judged.",
)
def scan(
    since: str,
    watchlist_path: str,
    out_md: str | None,
    out_json: str | None,
    dry_run: bool,
) -> None:
    """Run a single scan and emit a Markdown brief + optional JSON."""
    since_dt = _parse_since(since)
    until_dt = datetime.now(UTC)
    watchlist = load_watchlist(watchlist_path)
    if not watchlist:
        click.echo("# Security relevance brief\n\nNo watched repos; nothing to scan.")
        return

    async def _noop_judge(
        advisory: Advisory, repo: WatchlistRepo
    ) -> JudgeVerdict:  # pragma: no cover - trivial
        raise RuntimeError("dry-run judge should never be invoked")

    brief = asyncio.run(
        run_scan(
            since_dt,
            until_dt,
            watchlist,
            judge_fn=_noop_judge if dry_run else None,
        )
    )

    if out_md:
        write(brief, Path(out_md), Path(out_json) if out_json else None)
        click.echo(f"Wrote {out_md}", err=True)
        if out_json:
            click.echo(f"Wrote {out_json}", err=True)
    else:
        click.echo(render_markdown(brief))
        if out_json:
            Path(out_json).parent.mkdir(parents=True, exist_ok=True)
            Path(out_json).write_text(render_json(brief))
            click.echo(f"Wrote {out_json}", err=True)


if __name__ == "__main__":
    main()
