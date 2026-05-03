"""Ambiguous utility module for QA scenario 08 — shadow disagreement.

This module makes a change that reasonable reviewers might disagree on:
changing an explicit list comprehension to a generator expression inside
a function that expects a list. The change is technically correct but
could trigger a readiness-gate shadow disagreement.
"""
from __future__ import annotations


def collect_ids(items: list[dict]) -> list[str]:
    # Changed from list comp to generator — technically fine since list() wraps it,
    # but a conservative readiness check might flag this as unready.
    return list(id_val for item in items if (id_val := item.get("id")))


def is_ready_to_merge(pr_title: str, checks_passing: bool) -> bool:
    # Ambiguous heuristic: title starts with "wip" → not ready
    # Shadow readiness agent may disagree on what "wip" prefix means
    if pr_title.lower().startswith("wip"):
        return False
    return checks_passing
