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
from urllib.parse import urlparse, urlunparse

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
# Regex / constants
# ---------------------------------------------------------------------------

# Matches http(s):// at the start of a string — used to detect URL display text.
_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)

_REDACTED_TOKEN = "[REDACTED DECEPTIVE LINK]"


# ---------------------------------------------------------------------------
# Link extraction (balanced-parens aware)
# ---------------------------------------------------------------------------


def _scan_links(text: str) -> list[tuple[int, int, str, str]]:
    """Return a list of ``(start, end, display, href)`` for every Markdown link.

    Handles hrefs that contain parentheses (balanced or ``\\``-escaped), so
    URLs like ``https://en.wikipedia.org/wiki/Knuth_(book)`` are parsed
    correctly and cannot evade redaction by embedding an unbalanced ``)``.
    """
    results: list[tuple[int, int, str, str]] = []
    i = 0
    n = len(text)

    while i < n:
        # Locate the next opening bracket.
        bracket_open = text.find("[", i)
        if bracket_open == -1:
            break

        # Scan display text up to the closing `]`, honouring `\` escapes.
        j = bracket_open + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == "]":
                break
            j += 1
        if j >= n:
            i = bracket_open + 1
            continue
        bracket_close = j

        # The very next character must be `(`.
        if bracket_close + 1 >= n or text[bracket_close + 1] != "(":
            i = bracket_close + 1
            continue
        paren_open = bracket_close + 1

        # Scan href with depth counting so balanced inner parens are included.
        k = paren_open + 1
        depth = 1
        while k < n and depth > 0:
            if text[k] == "\\":
                k += 2
                continue
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
            k += 1
        if depth != 0:
            # Unmatched opening paren — not a valid link; skip past it.
            i = bracket_close + 1
            continue

        paren_close = k - 1
        display = text[bracket_open + 1 : bracket_close]
        href = text[paren_open + 1 : paren_close]
        results.append((bracket_open, paren_close + 1, display, href))
        i = paren_close + 1

    return results


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _is_url(text: str) -> bool:
    return bool(_URL_SCHEME_RE.match(text.strip()))


_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def _strip_default_port(scheme: str, netloc: str) -> str:
    """Remove the port from *netloc* when it is the default for *scheme*.

    e.g. ``example.com:443`` with scheme ``https`` → ``example.com``
         ``example.com:8080`` with scheme ``https`` → ``example.com:8080``
    """
    if ":" not in netloc:
        return netloc
    host, _, port_str = netloc.rpartition(":")
    try:
        port = int(port_str)
    except ValueError:
        return netloc
    if _DEFAULT_PORTS.get(scheme) == port:
        return host
    return netloc


def _normalise(url: str) -> str:
    """Normalise *url* for mismatch comparison.

    - Scheme and host are lowercased.
    - Default ports (80 for http, 443 for https) are stripped so that
      ``https://example.com/foo`` and ``https://example.com:443/foo`` compare
      as equal and do not produce a false positive.
    - Path, query, and fragment retain their original case because those
      components are case-sensitive for many real-world URLs.
    - A single trailing slash on the path is stripped.
    """
    url = url.strip()
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = _strip_default_port(scheme, parsed.netloc.lower())
        normalised = parsed._replace(
            scheme=scheme,
            netloc=netloc,
            path=parsed.path.rstrip("/"),
        )
        return urlunparse(normalised)
    except ValueError:  # pragma: no cover
        return url.rstrip("/")


def _is_mismatch(display: str, href: str) -> bool:
    """Return True when display text looks like a URL that differs from href."""
    if not _is_url(display):
        return False
    return _normalise(display) != _normalise(href)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply(text: str) -> str:
    """Scan *text* for deceptive Markdown links and redact them.

    Returns the sanitised text.  Increments
    :data:`GUARDRAIL_FILTER_OUTPUT_HIT` once per redacted link.
    """
    links = _scan_links(text)
    if not links:
        return text

    # Rebuild the string by concatenating clean slices and redaction tokens,
    # processing links right-to-left so earlier offsets stay valid.
    chunks: list[str] = []
    cursor = len(text)
    for start, end, display, href in reversed(links):
        # Append the tail slice that follows this link (or previous link end).
        chunks.append(text[end:cursor])
        if _is_mismatch(display, href):
            GUARDRAIL_FILTER_OUTPUT_HIT.increment()
            chunks.append(_REDACTED_TOKEN)
        else:
            chunks.append(text[start:end])
        cursor = start
    chunks.append(text[:cursor])
    return "".join(reversed(chunks))


__all__ = ["GUARDRAIL_FILTER_OUTPUT_HIT", "apply"]
