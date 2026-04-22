"""Tests for ``qa_agent.relevance_llm``."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qa_agent.models import Advisory, JudgeVerdict, WatchlistRepo
from qa_agent.relevance_llm import judge


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
async def test_judge_parses_valid_json(topic_advisory: Advisory, pypi_repo: WatchlistRepo) -> None:
    body = json.dumps(
        {
            "advisory_id": topic_advisory.id,
            "repo": f"{pypi_repo.owner}/{pypi_repo.repo}",
            "relevant": True,
            "confidence": "high",
            "rationale": "Repo declares fastapi topic and advisory targets fastapi proxies.",
        }
    )
    verdict = await judge(topic_advisory, pypi_repo, completion=_fake_completion(body))
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.relevant is True
    assert verdict.confidence == "high"


@pytest.mark.asyncio
async def test_judge_backfills_missing_identifiers(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    body = json.dumps({"relevant": False, "confidence": "low", "rationale": "Unrelated to topic."})
    verdict = await judge(topic_advisory, pypi_repo, completion=_fake_completion(body))
    assert verdict.advisory_id == topic_advisory.id
    assert verdict.repo == "example/app"


@pytest.mark.asyncio
async def test_judge_retries_on_invalid_json_then_fails(
    topic_advisory: Advisory, pypi_repo: WatchlistRepo
) -> None:
    with pytest.raises(json.JSONDecodeError):
        await judge(topic_advisory, pypi_repo, completion=_fake_completion("not json{{"))
