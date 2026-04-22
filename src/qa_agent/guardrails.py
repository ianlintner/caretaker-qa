"""Input-sanitization guardrails applied before LLM ingestion.

All advisory text flows through :func:`sanitize_input` before it reaches the
LLM prompt.  This prevents raw HTML/script payloads that appear in third-party
feed data (or in crafted issue bodies — see QA scenario 06) from reaching the
model context.

The :data:`GUARDRAIL_SANITIZE_INPUT_HIT` counter is incremented every time a
sanitization pass actually strips content, giving operators a metric to alert
on (Wave A5).
"""

from __future__ import annotations

import re
import threading

# Matches any well-formed or partial HTML/XML tag including self-closing ones.
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)

# Module-level hit counter — incremented atomically whenever sanitize_input
# strips at least one tag.  Bounded cardinality: this is a single monotonic
# integer, not per-repo.
GUARDRAIL_SANITIZE_INPUT_HIT: int = 0
_counter_lock = threading.Lock()


def sanitize_input(text: str) -> str:
    """Strip HTML tags from *text* before it is embedded in an LLM prompt.

    Returns the sanitized string unchanged if no tags were present.
    Increments :data:`GUARDRAIL_SANITIZE_INPUT_HIT` once per call that
    removes at least one tag.
    """
    global GUARDRAIL_SANITIZE_INPUT_HIT
    cleaned = _HTML_TAG_RE.sub("", text)
    if cleaned != text:
        with _counter_lock:
            GUARDRAIL_SANITIZE_INPUT_HIT += 1
    return cleaned


def get_sanitize_hit_count() -> int:
    """Return the current value of :data:`GUARDRAIL_SANITIZE_INPUT_HIT`."""
    return GUARDRAIL_SANITIZE_INPUT_HIT


def reset_sanitize_hit_count() -> None:
    """Reset the hit counter to zero.  Intended for use in tests only."""
    global GUARDRAIL_SANITIZE_INPUT_HIT
    with _counter_lock:
        GUARDRAIL_SANITIZE_INPUT_HIT = 0
