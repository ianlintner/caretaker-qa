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

import html
import threading

import nh3

# Module-level hit counter — incremented atomically whenever sanitize_input
# strips at least one tag.  Bounded cardinality: this is a single monotonic
# integer, not per-repo.
GUARDRAIL_SANITIZE_INPUT_HIT: int = 0
_counter_lock = threading.Lock()


def sanitize_input(text: str) -> str:
    """Strip HTML from *text* before it is embedded in an LLM prompt.

    Uses ``nh3`` (backed by the Rust ``ammonia`` crate) with an empty tag
    allowlist so:

    * All HTML tags are removed.
    * The *content* of ``<script>`` and ``<style>`` elements is also removed.
    * Entity-encoded tags (``&lt;img onerror=x&gt;``) are decoded first and
      then stripped, so they cannot survive by hiding behind entities.
    * Bare angle-bracket expressions used in comparisons (``1 < 2 > 0``) or
      version constraints (``pkg<2.0``) are preserved unchanged.

    Returns the sanitized string unchanged if no HTML was present.
    Increments :data:`GUARDRAIL_SANITIZE_INPUT_HIT` once per call that
    removes at least one tag or encoded tag.
    """
    global GUARDRAIL_SANITIZE_INPUT_HIT
    # Step 1 — decode any HTML entities so entity-encoded tags are exposed.
    decoded = html.unescape(text)
    # Step 2 — strip all tags; nh3 also removes script/style content and
    # escapes bare < / > to &lt; / &gt;.
    nh3_cleaned = nh3.clean(decoded, tags=set())
    # Step 3 — restore the &lt;/&gt; that nh3 added for bare angle-brackets so
    # comparison operators and version constraints survive intact.
    cleaned = html.unescape(nh3_cleaned)
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
