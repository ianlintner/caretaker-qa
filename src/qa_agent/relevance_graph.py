"""LangGraph relevance pipeline — fetch → match → judge → report.

The graph is linear, not a graph in the loopy sense, because the pipeline
doesn't branch. We use LangGraph anyway for two reasons:

1. Each node is typed, so a downstream refactor that adds a branch (e.g.
   "if repo is in the caretaker fleet, write a draft PR") has a natural
   home.
2. Checkpointing lets us resume a scan without re-fetching feeds, which
   matters when the LLM judge stage is the slow step.

Node I/O is a single :class:`ScanState`. We keep the state flat so it's easy
to snapshot for debugging.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from qa_agent.feeds import fetch_ghsa, fetch_nvd, fetch_osv
from qa_agent.manifest import fetch_dependencies
from qa_agent.matcher import match
from qa_agent.models import (
    Advisory,
    Brief,
    Ecosystem,
    JudgeVerdict,
    MatchVerdict,
    ReportEntry,
    WatchlistRepo,
)
from qa_agent.relevance_llm import judge as default_judge


class ScanState(TypedDict, total=False):
    """Shared state passed between graph nodes."""

    since: datetime
    until: datetime
    watchlist: list[WatchlistRepo]
    advisories: list[Advisory]
    repo_deps: dict[str, set[str]]
    verdicts: list[MatchVerdict]
    judge_verdicts: list[JudgeVerdict]
    brief: Brief
    feed_counts: dict[str, int]


JudgeFn = Callable[[Advisory, WatchlistRepo], Awaitable[JudgeVerdict]]


def build_graph(
    *,
    judge_fn: JudgeFn | None = None,
    fetch_nvd_fn: Any = fetch_nvd,
    fetch_osv_fn: Any = fetch_osv,
    fetch_ghsa_fn: Any = fetch_ghsa,
    fetch_deps_fn: Any = fetch_dependencies,
) -> Any:
    """Compile the scan graph.

    All fetchers + the judge are injectable so tests can pass fakes. The
    defaults call the real HTTP endpoints.
    """
    judge_fn = judge_fn or default_judge

    async def fetch_feeds(state: ScanState) -> ScanState:
        since = state["since"]
        until = state["until"]
        packages: list[tuple[Ecosystem, str]] = []
        # We pre-fetch deps for OSV's querybatch; done separately so it's
        # also available to the matcher.
        repo_deps: dict[str, set[str]] = {}
        for repo in state["watchlist"]:
            deps = await fetch_deps_fn(repo)
            repo_deps[f"{repo.owner}/{repo.repo}"] = deps
            for name in deps:
                packages.append((repo.ecosystem, name))

        nvd_adv = await fetch_nvd_fn(since, until)
        osv_adv = await fetch_osv_fn(packages, since=since) if packages else []
        ghsa_adv = await fetch_ghsa_fn(since, until)

        by_id: dict[str, Advisory] = {}
        for adv in list(nvd_adv) + list(osv_adv) + list(ghsa_adv):
            by_id.setdefault(adv.id, adv)
        return {
            "advisories": list(by_id.values()),
            "repo_deps": repo_deps,
            "feed_counts": {
                "nvd": len(nvd_adv),
                "osv": len(osv_adv),
                "ghsa": len(ghsa_adv),
            },
        }

    def deterministic_match(state: ScanState) -> ScanState:
        verdicts: list[MatchVerdict] = []
        for advisory in state["advisories"]:
            for repo in state["watchlist"]:
                deps = state["repo_deps"].get(f"{repo.owner}/{repo.repo}", set())
                verdicts.append(match(advisory, repo, deps))
        return {"verdicts": verdicts}

    async def judge_ambiguous(state: ScanState) -> ScanState:
        judge_verdicts: list[JudgeVerdict] = []
        advisories_by_id = {a.id: a for a in state["advisories"]}
        repos_by_name = {f"{r.owner}/{r.repo}": r for r in state["watchlist"]}
        for verdict in state["verdicts"]:
            if verdict.status != "ambiguous":
                continue
            advisory = advisories_by_id.get(verdict.advisory_id)
            repo = repos_by_name.get(verdict.repo)
            if advisory is None or repo is None:
                continue
            judge_verdicts.append(await judge_fn(advisory, repo))
        return {"judge_verdicts": judge_verdicts}

    def assemble_brief(state: ScanState) -> ScanState:
        advisories_by_id = {a.id: a for a in state["advisories"]}
        judge_by_key = {(jv.advisory_id, jv.repo): jv for jv in state.get("judge_verdicts", [])}
        entries: list[ReportEntry] = []
        for verdict in state["verdicts"]:
            advisory = advisories_by_id.get(verdict.advisory_id)
            if advisory is None:
                continue
            if verdict.status == "match":
                entries.append(
                    ReportEntry(
                        advisory=advisory,
                        repo=verdict.repo,
                        severity=advisory.severity,
                        relevance="direct",
                        rationale=verdict.reason,
                    )
                )
            elif verdict.status == "ambiguous":
                jv = judge_by_key.get((verdict.advisory_id, verdict.repo))
                if jv is None or not jv.relevant:
                    continue
                relevance = "likely" if jv.confidence == "high" else "speculative"
                entries.append(
                    ReportEntry(
                        advisory=advisory,
                        repo=verdict.repo,
                        severity=advisory.severity,
                        relevance=relevance,
                        rationale=jv.rationale,
                    )
                )
        brief = Brief(
            generated_at=state["until"],
            since=state["since"],
            until=state["until"],
            entries=entries,
            feed_counts=state.get("feed_counts", {}),
            repos_scanned=len(state["watchlist"]),
        )
        return {"brief": brief}

    graph = StateGraph(ScanState)
    graph.add_node("fetch", fetch_feeds)
    graph.add_node("match", deterministic_match)
    graph.add_node("judge", judge_ambiguous)
    graph.add_node("assemble", assemble_brief)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "match")
    graph.add_edge("match", "judge")
    graph.add_edge("judge", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


async def run_scan(
    since: datetime,
    until: datetime,
    watchlist: list[WatchlistRepo],
    *,
    judge_fn: JudgeFn | None = None,
    fetch_nvd_fn: Any = fetch_nvd,
    fetch_osv_fn: Any = fetch_osv,
    fetch_ghsa_fn: Any = fetch_ghsa,
    fetch_deps_fn: Any = fetch_dependencies,
) -> Brief:
    """Run the compiled graph end-to-end. Returns the final :class:`Brief`."""
    graph = build_graph(
        judge_fn=judge_fn,
        fetch_nvd_fn=fetch_nvd_fn,
        fetch_osv_fn=fetch_osv_fn,
        fetch_ghsa_fn=fetch_ghsa_fn,
        fetch_deps_fn=fetch_deps_fn,
    )
    state: ScanState = {
        "since": since,
        "until": until,
        "watchlist": watchlist,
    }
    result = await graph.ainvoke(state)
    brief = result["brief"]
    assert isinstance(brief, Brief)
    return brief
