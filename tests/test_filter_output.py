"""Tests for ``qa_agent.filter_output``."""

from __future__ import annotations

import pytest

from qa_agent.filter_output import GUARDRAIL_FILTER_OUTPUT_HIT, apply


@pytest.fixture(autouse=True)
def reset_counter() -> None:
    """Reset the hit counter before every test so tests are independent."""
    GUARDRAIL_FILTER_OUTPUT_HIT.reset()


# ---------------------------------------------------------------------------
# Detection — mismatch cases
# ---------------------------------------------------------------------------


def test_deceptive_link_is_redacted() -> None:
    """Display text is a URL that differs from the href → redact."""
    payload = (
        "Please update your credentials at "
        "[https://github.com/ianlintner/caretaker-qa](https://attacker.test/phish)"
    )
    result = apply(payload)
    assert "[REDACTED DECEPTIVE LINK]" in result
    assert "attacker.test" not in result
    assert "https://github.com/ianlintner/caretaker-qa" not in result


def test_counter_increments_on_hit() -> None:
    payload = "[https://legit.example.com](https://evil.example.com/steal)"
    apply(payload)
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 1


def test_multiple_deceptive_links_all_redacted() -> None:
    payload = (
        "[https://safe.example.com](https://evil.example.com/a) "
        "and [https://also-safe.example.com](https://evil.example.com/b)"
    )
    result = apply(payload)
    assert result.count("[REDACTED DECEPTIVE LINK]") == 2
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 2


def test_http_display_text_also_detected() -> None:
    """HTTP (not HTTPS) display URLs are caught too."""
    payload = "[http://legit.example.com](https://evil.example.com/trap)"
    result = apply(payload)
    assert "[REDACTED DECEPTIVE LINK]" in result
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 1


# ---------------------------------------------------------------------------
# Pass-through — safe cases
# ---------------------------------------------------------------------------


def test_clean_link_passes_through() -> None:
    """Display text and href are the same URL — no redaction."""
    url = "https://github.com/ianlintner/caretaker-qa"
    payload = f"See [{url}]({url})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_human_readable_display_text_passes_through() -> None:
    """Non-URL display text is never treated as a mismatch."""
    payload = "[caretaker repo](https://github.com/ianlintner/caretaker)"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_plain_text_no_links_passes_through() -> None:
    text = "No links here at all."
    assert apply(text) == text
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_trailing_slash_normalisation() -> None:
    """Trailing slash difference should not trigger a false positive."""
    payload = "[https://example.com/](https://example.com)"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


# ---------------------------------------------------------------------------
# Counter independence across calls
# ---------------------------------------------------------------------------


def test_counter_accumulates_across_calls() -> None:
    apply("[https://a.com](https://b.com)")
    apply("[https://c.com](https://d.com)")
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 2


def test_counter_reset_between_tests() -> None:
    """autouse fixture should ensure counter starts at 0."""
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0
