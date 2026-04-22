"""Deterministic matcher — decides if an advisory affects a watched repo.

Returns one of three statuses per ``(advisory, repo)`` pair:

* ``match`` — advisory names a package that the repo declares as a dep, and
  we're confident enough to flag it without asking the LLM.
* ``no_match`` — the advisory's ecosystem or package name does not overlap
  with the repo's declared deps.
* ``ambiguous`` — there's a signal (topic keyword, related package family)
  but not a clean name match. These get routed to the LLM judge.

Keeping this stage deterministic is the point — the LLM stays a narrow
escalation path, not a fanout.
"""

from __future__ import annotations

from qa_agent.models import Advisory, MatchVerdict, WatchlistRepo


def match(
    advisory: Advisory,
    repo: WatchlistRepo,
    deps: set[str],
) -> MatchVerdict:
    """Return a verdict for a single ``(advisory, repo)`` pair."""
    adv_ecosystem_matches = advisory.ecosystem is None or advisory.ecosystem == repo.ecosystem

    # Direct name match (cheapest signal).
    advisory_packages_lower = {p.lower() for p in advisory.affected_packages}
    for pkg in advisory_packages_lower:
        if pkg in deps:
            return MatchVerdict(
                advisory_id=advisory.id,
                repo=f"{repo.owner}/{repo.repo}",
                status="match",
                reason=f"declared dep '{pkg}' named in advisory",
                matched_package=pkg,
            )

    # Non-matching ecosystem with no topic signal → early out.
    if not adv_ecosystem_matches and not _topic_signal(advisory, repo):
        return MatchVerdict(
            advisory_id=advisory.id,
            repo=f"{repo.owner}/{repo.repo}",
            status="no_match",
            reason=f"ecosystem {advisory.ecosystem} does not match repo {repo.ecosystem}",
        )

    # Same ecosystem but no direct package match + mentions one of the
    # repo's topics in title/summary → ambiguous, hand to the judge.
    if _topic_signal(advisory, repo):
        return MatchVerdict(
            advisory_id=advisory.id,
            repo=f"{repo.owner}/{repo.repo}",
            status="ambiguous",
            reason="advisory text mentions a declared topic but not a declared dep",
        )

    return MatchVerdict(
        advisory_id=advisory.id,
        repo=f"{repo.owner}/{repo.repo}",
        status="no_match",
        reason="no package name overlap and no topic signal",
    )


def _topic_signal(advisory: Advisory, repo: WatchlistRepo) -> bool:
    """True if any of ``repo.topics`` appears in the advisory's title/summary."""
    if not repo.topics:
        return False
    haystack = f"{advisory.title} {advisory.summary}".lower()
    return any(topic.lower() in haystack for topic in repo.topics)
