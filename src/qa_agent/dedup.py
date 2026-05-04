"""Advisory deduplication — prevent double-reporting a (advisory, repo) pair.

NVD, OSV, and GHSA regularly mirror the same CVE.  Without dedup the same
advisory can appear multiple times in the brief, which inflates the affected
count and makes the output noisy.

[qa-scenario-73] Re-trigger: fixed allowed_bots for caretaker handoff + skip_labels.
"""

from __future__ import annotations

import json
import hashlib


def fingerprint(advisory_id: str, repo: str) -> str:
    """Return a stable 16-char hex key for a (advisory_id, repo) pair."""
    payload = json.dumps({"id": advisory_id,  "repo": repo}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class SeenSet:
    """Lightweight in-process dedup store for one scan run."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def add(self, advisory_id: str, repo: str) -> None:
        """Record an observation so contains() returns True next time."""
        self._keys.add(fingerprint(advisory_id, repo))

    def contains(self, advisory_id: str, repo: str) -> bool:
        """Return True if this pair has already been recorded."""
        return fingerprint(advisory_id, repo) in self._keys

    def __len__(self) -> int:
        return len(self._keys)
