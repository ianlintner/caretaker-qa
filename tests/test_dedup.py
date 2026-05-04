"""Tests for the dedup module."""

from __future__ import annotations

from qa_agent.dedup import SeenSet, fingerprint


def test_fingerprint_is_stable() -> None:
    assert fingerprint("CVE-2024-1234", "acme/demo") == fingerprint("CVE-2024-1234", "acme/demo")


def test_fingerprint_differs_for_different_inputs() -> None:
    a = fingerprint("CVE-2024-1234", "acme/demo")
    b = fingerprint("CVE-2024-9999", "acme/demo")
    assert a != b


def test_seen_set_records_and_queries() -> None:
    seen = SeenSet()
    assert not seen.contains("CVE-2024-1234", "acme/demo")
    seen.add("CVE-2024-1234", "acme/demo")
    assert seen.contains("CVE-2024-1234", "acme/demo")


def test_seen_set_len_deduplicates() -> None:
    seen = SeenSet()
    seen.add("CVE-2024-1234", "acme/demo")
    seen.add("CVE-2024-1234", "acme/demo")  # duplicate — should not inflate count
    seen.add("CVE-2024-9999", "acme/demo")
    assert len(seen) == 2


def test_fingerprint_rejects_none_inputs() -> None:
    import pytest

    with pytest.raises(ValueError):
        fingerprint(None, "acme/demo")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        fingerprint("CVE-2024-1234", None)  # type: ignore[arg-type]
