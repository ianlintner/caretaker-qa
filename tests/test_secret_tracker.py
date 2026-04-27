"""Tests for ``qa_agent.secret_tracker``.

Coverage:
- ``observe()`` writes one JSONL row per name, marks unset vars
  ``present=False`` with empty fingerprint
- fingerprints are stable, salted by name, and never include the value
- ``stale()`` returns True for never-seen names
- ``stale()`` resets only when the fingerprint changes (same value
  seen N times must not look like N rotations)
- ``stale()`` tolerates corrupt JSONL rows without losing history
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from qa_agent.secret_tracker import (
    SecretObservation,
    _fingerprint,
    observe,
    stale,
)


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "secret-audit.jsonl"


def test_observe_writes_one_row_per_name(audit_path: Path) -> None:
    rows = observe(
        ["NVD_API_KEY", "GITHUB_TOKEN", "AZURE_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "abc", "GITHUB_TOKEN": "ghp_xx", "AZURE_API_KEY": ""},
        now=dt.datetime(2026, 4, 27, tzinfo=dt.UTC),
    )
    assert len(rows) == 3
    assert audit_path.is_file()
    lines = audit_path.read_text().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["name"] == "NVD_API_KEY"
    assert parsed[0]["present"] is True
    assert parsed[2]["name"] == "AZURE_API_KEY"
    assert parsed[2]["present"] is False
    assert parsed[2]["fingerprint"] == ""  # unset → no fingerprint


def test_fingerprint_is_salted_by_name() -> None:
    """Same value under two different names produces different fingerprints —
    surfaces the operator misconfiguration of pasting the same token into
    two slots."""
    a = _fingerprint("NVD_API_KEY", "shared-token")
    b = _fingerprint("GITHUB_TOKEN", "shared-token")
    assert a != b


def test_fingerprint_is_stable_for_same_input() -> None:
    a = _fingerprint("X", "y")
    b = _fingerprint("X", "y")
    assert a == b
    # And short — 16 hex chars.
    assert len(a) == 16
    int(a, 16)  # parses as hex


def test_fingerprint_does_not_contain_value() -> None:
    """Sanity check: the fingerprint must not include any prefix /
    suffix of the credential. The previous implementation in a sister
    project once leaked the first 4 chars; we don't."""
    fp = _fingerprint("X", "ghp_supersecret_token")
    assert "ghp" not in fp
    assert "secret" not in fp


def test_observation_jsonl_round_trip() -> None:
    obs = SecretObservation(
        name="X",
        fingerprint="0123456789abcdef",
        observed_at=dt.datetime(2026, 4, 27, 12, 0, tzinfo=dt.UTC),
        present=True,
    )
    line = obs.to_jsonl()
    restored = SecretObservation.from_jsonl(line)
    assert restored == obs


def test_stale_true_when_never_observed(audit_path: Path) -> None:
    """Never-seen credentials are stale — that's worse than expired."""
    assert stale("NVD_API_KEY", dt.timedelta(days=30), audit_path=audit_path) is True


def test_stale_false_for_recent_observation(audit_path: Path) -> None:
    now = dt.datetime(2026, 4, 27, tzinfo=dt.UTC)
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "abc"},
        now=now - dt.timedelta(days=1),
    )
    assert (
        stale(
            "NVD_API_KEY",
            dt.timedelta(days=30),
            audit_path=audit_path,
            now=now,
        )
        is False
    )


def test_stale_resets_only_on_fingerprint_change(audit_path: Path) -> None:
    """Same value seen 100 times must not look like 100 rotations.

    The rotation timestamp is the *first* time the current fingerprint
    appeared, not the most recent observation — so an environment that
    keeps re-observing the same token forever stays at a fixed
    rotation date and eventually trips ``stale``.
    """
    now = dt.datetime(2026, 4, 27, tzinfo=dt.UTC)
    # Observe the same value at t=-40d and t=-1d.
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "same-token"},
        now=now - dt.timedelta(days=40),
    )
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "same-token"},
        now=now - dt.timedelta(days=1),
    )
    # 30-day rotation policy → stale (first sighting was 40d ago).
    assert stale("NVD_API_KEY", dt.timedelta(days=30), audit_path=audit_path, now=now) is True
    # Now a real rotation: a different token at t=-1d.
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "rotated-token"},
        now=now - dt.timedelta(days=1),
    )
    assert stale("NVD_API_KEY", dt.timedelta(days=30), audit_path=audit_path, now=now) is False


def test_stale_tolerates_corrupt_rows(audit_path: Path) -> None:
    """One malformed JSON line must not lose the rotation history."""
    now = dt.datetime(2026, 4, 27, tzinfo=dt.UTC)
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "x"},
        now=now - dt.timedelta(days=1),
    )
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write("{this is not json}\n")
        fh.write("\n")  # also an empty line
    assert stale("NVD_API_KEY", dt.timedelta(days=30), audit_path=audit_path, now=now) is False


def test_stale_treats_a_b_a_sequence_as_no_new_rotation(audit_path: Path) -> None:
    """A→B→A is not three rotations.

    Operator rolls back to a previously-used credential (or a token
    re-issuer happens to mint the same value twice). Naive
    last-fingerprint-changes logic would reset the clock to the third
    observation, treating re-use of an old credential as a fresh
    rotation. The seen-fingerprints set fix surfaces the *novelty* of
    each fingerprint instead — only fingerprints never previously
    observed advance the rotation clock.

    Sequence:
      t=-40d: token "A"     (first sighting of A — anchors the clock)
      t=-20d: token "B"     (rotation — new anchor)
      t=-1d:  token "A"     (re-use of A; should NOT reset the clock)

    With a 25-day rotation policy:
      * If A→B→A erroneously resets the clock to t=-1d, stale → False.
      * Correctly, the most recent *novel* fingerprint is B at t=-20d
        which is < 25 days, so still False.

    With a 15-day rotation policy:
      * Erroneous logic: clock at t=-1d → stale = False.
      * Correct logic: clock at t=-20d (B's first sighting), 20 days
        is past the 15-day window → stale = True. This is the
        regression we want.
    """
    now = dt.datetime(2026, 4, 27, tzinfo=dt.UTC)
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "A"},
        now=now - dt.timedelta(days=40),
    )
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "B"},
        now=now - dt.timedelta(days=20),
    )
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "A"},
        now=now - dt.timedelta(days=1),
    )

    # 25d window: B's first sighting (t=-20d) is inside the window → fresh.
    assert stale("NVD_API_KEY", dt.timedelta(days=25), audit_path=audit_path, now=now) is False
    # 15d window: B's first sighting is outside the window → stale.
    # The naive implementation pre-fix would have reported False here
    # because A's reappearance at t=-1d would have looked like a rotation.
    assert stale("NVD_API_KEY", dt.timedelta(days=15), audit_path=audit_path, now=now) is True


def test_unset_observation_is_not_a_rotation(audit_path: Path) -> None:
    """An unset/empty observation (``present=False``) must not be treated
    as a rotation point — otherwise an env var that was set, briefly
    cleared, and then set again would look 'fresh' even if the token is
    the same."""
    now = dt.datetime(2026, 4, 27, tzinfo=dt.UTC)
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "old-token"},
        now=now - dt.timedelta(days=40),
    )
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": ""},  # briefly missing
        now=now - dt.timedelta(days=20),
    )
    observe(
        ["NVD_API_KEY"],
        audit_path=audit_path,
        env={"NVD_API_KEY": "old-token"},  # same as before, not a rotation
        now=now - dt.timedelta(days=1),
    )
    # First sighting of the surviving fingerprint was 40d ago → stale.
    assert stale("NVD_API_KEY", dt.timedelta(days=30), audit_path=audit_path, now=now) is True
