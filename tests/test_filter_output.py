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


# ---------------------------------------------------------------------------
# Parentheses in hrefs (balanced-parens parser)
# ---------------------------------------------------------------------------


def test_href_with_parentheses_clean_passes_through() -> None:
    """A safe link whose href contains balanced parens must not be altered."""
    url = "https://en.wikipedia.org/wiki/Knuth_(book)"
    payload = f"[{url}]({url})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_deceptive_link_with_parens_in_href_is_redacted() -> None:
    """Deceptive link where the href contains balanced parens must still be caught."""
    display = "https://trusted.example.com"
    href = "https://attacker.test/phish_(evil)"
    payload = f"[{display}]({href})"
    result = apply(payload)
    assert "[REDACTED DECEPTIVE LINK]" in result
    assert "attacker.test" not in result
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 1


def test_href_with_nested_parens_clean_passes_through() -> None:
    """Deeper nesting e.g. /path/(a_(b)) must not cause a false positive."""
    url = "https://example.com/path/(a_(b))"
    payload = f"[{url}]({url})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


# ---------------------------------------------------------------------------
# Escaped characters in display / href
# ---------------------------------------------------------------------------


def test_escaped_bracket_in_display_does_not_confuse_parser() -> None:
    """A `\\]` inside display text must not prematurely end the display span."""
    # This is not a URL display text so it should pass through unchanged.
    payload = r"[text\] more](https://example.com)"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_escaped_paren_in_href_does_not_truncate() -> None:
    """A `\\)` inside the href must not be treated as the link close."""
    url = r"https://example.com/path\)extra"
    # Non-URL display — should pass through unchanged.
    payload = f"[label]({url})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


# ---------------------------------------------------------------------------
# Path-case sensitivity
# ---------------------------------------------------------------------------


def test_path_case_difference_is_detected_as_mismatch() -> None:
    """Different path case must be flagged — paths are case-sensitive."""
    display = "https://example.com/Resource"
    href = "https://example.com/resource"
    payload = f"[{display}]({href})"
    result = apply(payload)
    assert "[REDACTED DECEPTIVE LINK]" in result
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 1


def test_host_case_difference_is_not_a_mismatch() -> None:
    """Host is case-insensitive; EXAMPLE.COM == example.com."""
    url_lower = "https://example.com/path"
    url_upper = "https://EXAMPLE.COM/path"
    payload = f"[{url_upper}]({url_lower})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_scheme_case_difference_is_not_a_mismatch() -> None:
    """Scheme is case-insensitive; HTTPS == https."""
    payload = "[HTTPS://example.com/path](https://example.com/path)"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


# ---------------------------------------------------------------------------
# Default-port normalisation
# ---------------------------------------------------------------------------


def test_https_default_port_443_not_a_mismatch() -> None:
    """https://example.com:443/foo and https://example.com/foo are the same URL."""
    with_port = "https://example.com:443/foo"
    without_port = "https://example.com/foo"
    payload = f"[{with_port}]({without_port})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_http_default_port_80_not_a_mismatch() -> None:
    """http://example.com:80/foo and http://example.com/foo are the same URL."""
    with_port = "http://example.com:80/foo"
    without_port = "http://example.com/foo"
    payload = f"[{with_port}]({without_port})"
    result = apply(payload)
    assert result == payload
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 0


def test_non_default_port_is_still_a_mismatch() -> None:
    """A non-default port (e.g. :8080) must still be flagged as a mismatch."""
    display = "https://example.com:8080/foo"
    href = "https://example.com/foo"
    payload = f"[{display}]({href})"
    result = apply(payload)
    assert "[REDACTED DECEPTIVE LINK]" in result
    assert GUARDRAIL_FILTER_OUTPUT_HIT.total == 1
