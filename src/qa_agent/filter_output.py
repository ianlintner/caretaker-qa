"""Output guardrail — detects and redacts deceptive Markdown links.

A *deceptive Markdown link* is one where the display text is itself a URL
that differs from the href target, e.g.::

    [https://trusted.example.com](https://attacker.test/phish)

This is the redirect-cloaking pattern tracked in Wave A5 (#505).

When a mismatch is found the link is replaced with a safe redacted token so
the comment/report is never published with the phishing URL.  Every redaction
increments the ``GUARDRAIL_FILTER_OUTPUT_HIT`` counter exposed on this module.

Usage::

    from qa_agent.filter_output import GUARDRAIL_FILTER_OUTPUT_HIT, apply

    safe_text = apply(raw_text)
    hits_so_far = GUARDRAIL_FILTER_OUTPUT_HIT.total
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from threading import Lock

# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


@dataclass
class _Counter:
    """Thread-safe integer counter."""

    total: int = field(default=0)
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def increment(self) -> None:
        with self._lock:
            self.total += 1

    def reset(self) -> None:
        """Reset to zero (used in tests)."""
        with self._lock:
            self.total = 0


GUARDRAIL_FILTER_OUTPUT_HIT: _Counter = _Counter()

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Matches http(s):// at the start of a string — used to detect URL display text.
_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)

# Matches [display text](url).
# Capture groups:
#   1 — display text (the visible part)
#   2 — href (the actual link destination)
_MD_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(([^)]+)\)",
)

_REDACTED_TOKEN = "[REDACTED DECEPTIVE LINK]"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _is_url(text: str) -> bool:
    return bool(_URL_SCHEME_RE.match(text.strip()))


def _normalise(url: str) -> str:
    """Strip trailing slashes for comparison."""
    return url.strip().rstrip("/").lower()


def _is_mismatch(display: str, href: str) -> bool:
    """Return True when display text looks like a URL that differs from href."""
    if not _is_url(display):
        return False
    return _normalise(display) != _normalise(href)


def _redact_match(m: re.Match[str]) -> str:
    display = m.group(1)
    href = m.group(2)
    if _is_mismatch(display, href):
        GUARDRAIL_FILTER_OUTPUT_HIT.increment()
        return _REDACTED_TOKEN
    return m.group(0)


def apply(text: str) -> str:
    """Scan *text* for deceptive Markdown links and redact them.

    Returns the sanitised text.  Increments
    :data:`GUARDRAIL_FILTER_OUTPUT_HIT` once per redacted link.
    """
    return _MD_LINK_RE.sub(_redact_match, text)


__all__ = ["GUARDRAIL_FILTER_OUTPUT_HIT", "apply"]
