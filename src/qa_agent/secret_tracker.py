"""Last-seen tracker for runtime secrets / credentials.

The qa_agent reads a small set of env-var-borne credentials at startup
(NVD API key, GitHub token, Azure API key/base, and a few feed-side
auth headers). Operators want a cheap "did this run actually have the
credential, and when did we last see it?" diagnostic — both for
catching expired-but-not-rotated secrets *before* they cause feed
failures, and for compliance auditors who need to show "yes, this
credential rotated within N days."

The tracker is deliberately tiny:

* writes a JSON line per (secret-name, observation-time) to an audit
  log under ``$XDG_STATE_HOME/qa-agent/secret-audit.jsonl`` (defaults
  to ``~/.local/state/qa-agent/...``);
* tracks only *presence* and a SHA-256 fingerprint of the credential —
  never the credential itself, and never the prefix-suffix breadcrumbs
  some other tools log (those have leaked production tokens to logs
  enough times that we don't want any in-band representation here);
* exposes ``stale(secret_name, max_age) -> bool`` so the
  ``secret-audit.yml`` workflow can diff the audit log against a
  rotation policy.

Storage is append-only by design — the rotation history *is* the
record we need. ``compact()`` is offered for ops who want to roll
older entries into a summary, but the default behaviour is to keep
every observation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)


_DEFAULT_AUDIT_DIRNAME: Final = "qa-agent"
_DEFAULT_AUDIT_FILENAME: Final = "secret-audit.jsonl"


@dataclass(frozen=True)
class SecretObservation:
    """One row in the audit log."""

    name: str  # the env-var name; never the value
    fingerprint: str  # SHA-256(name || value), prefix-truncated to 16 hex
    observed_at: dt.datetime  # tz-aware UTC
    present: bool  # False when the env var is unset/empty

    def to_jsonl(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "fingerprint": self.fingerprint,
                "observed_at": self.observed_at.isoformat(),
                "present": self.present,
            },
            sort_keys=True,
        )

    @classmethod
    def from_jsonl(cls, line: str) -> SecretObservation:
        d = json.loads(line)
        return cls(
            name=d["name"],
            fingerprint=d["fingerprint"],
            observed_at=dt.datetime.fromisoformat(d["observed_at"]),
            present=bool(d["present"]),
        )


def _audit_path() -> Path:
    """Return the audit-log path, honouring ``$XDG_STATE_HOME``."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / _DEFAULT_AUDIT_DIRNAME / _DEFAULT_AUDIT_FILENAME


def _fingerprint(name: str, value: str) -> str:
    """Return a stable, non-reversible identity for a credential.

    Salted with the variable name so the same token used under two
    different env vars (a misconfiguration we want to surface) shows
    up as two distinct fingerprints. Truncated to 16 hex chars to
    keep the log scannable; the full SHA-256 is overkill for this
    diagnostic and costs disk for no gain.
    """
    h = hashlib.sha256()
    h.update(name.encode("utf-8"))
    h.update(b"\x00")
    h.update(value.encode("utf-8"))
    return h.hexdigest()[:16]


def observe(
    names: Iterable[str],
    *,
    audit_path: Path | None = None,
    now: dt.datetime | None = None,
    env: dict[str, str] | None = None,
) -> list[SecretObservation]:
    """Record one observation per ``name`` in ``names``.

    ``audit_path``, ``now`` and ``env`` are exposed so tests can pin
    them; the production call site uses real ``os.environ`` and
    ``datetime.now(UTC)``.
    """
    env = env if env is not None else dict(os.environ)
    now = now or dt.datetime.now(dt.UTC)
    path = audit_path or _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    observations: list[SecretObservation] = []
    with path.open("a", encoding="utf-8") as fh:
        for name in names:
            value = (env.get(name) or "").strip()
            present = bool(value)
            obs = SecretObservation(
                name=name,
                fingerprint=_fingerprint(name, value) if present else "",
                observed_at=now,
                present=present,
            )
            fh.write(obs.to_jsonl() + "\n")
            observations.append(obs)
            if not present:
                logger.warning("secret_tracker: %s is unset or empty", name)
    return observations


def stale(
    name: str,
    max_age: dt.timedelta,
    *,
    audit_path: Path | None = None,
    now: dt.datetime | None = None,
) -> bool:
    """Return True when the most recent fingerprint for ``name`` is older than ``max_age``.

    A name with no recorded observations is considered stale (you've
    never seen the credential at all — that's worse than expired).
    Different fingerprints reset the clock; the same fingerprint
    seen multiple times does not.
    """
    path = audit_path or _audit_path()
    if not path.is_file():
        return True
    now = now or dt.datetime.now(dt.UTC)
    last_rotation: dt.datetime | None = None
    last_fingerprint: str | None = None
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obs = SecretObservation.from_jsonl(raw)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Tolerate corrupt rows — the audit log is append-only and
                # one malformed line shouldn't lose the rotation history.
                continue
            if obs.name != name or not obs.present:
                continue
            if obs.fingerprint != last_fingerprint:
                last_rotation = obs.observed_at
                last_fingerprint = obs.fingerprint
    if last_rotation is None:
        return True
    return (now - last_rotation) > max_age


__all__ = [
    "SecretObservation",
    "observe",
    "stale",
]
