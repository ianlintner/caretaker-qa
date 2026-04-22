"""LLM judge for ambiguous match verdicts.

Takes an advisory + a repo's topics/deps and returns a
:class:`~qa_agent.models.JudgeVerdict`. Uses LiteLLM so the model name is
config-driven; defaults to ``azure_ai/gpt-4o`` matching caretaker.

The prompt is deliberately narrow: *given this advisory and this repo, is
it relevant?* Not *write a brief* — the brief assembly is a separate stage.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from qa_agent.models import Advisory, JudgeVerdict, WatchlistRepo

_DEFAULT_MODEL = "azure_ai/gpt-4o"

_SYSTEM_PROMPT = """You are a security triage assistant. You are given a
vulnerability advisory and a public repo's ecosystem + topics. Decide whether
the advisory is relevant to that repo's operators — i.e. whether they should
act on it within the next business day.

Respond with a compact JSON object matching this schema:
{
  "advisory_id": string,
  "repo": string (owner/name),
  "relevant": boolean,
  "confidence": "high" | "medium" | "low",
  "rationale": string (≤ 500 chars, plain, no markdown)
}

A repo is RELEVANT if the advisory names a library, framework, transitive
dep, or platform the repo clearly depends on at the declared topics level.
A repo is NOT RELEVANT if the advisory targets an unrelated ecosystem, an
obscure module the repo does not plausibly use, or a component explicitly
disabled by the repo's description.

Be stricter than a news aggregator would be. When unsure, return
relevant=false with confidence=low and a one-sentence rationale."""


def _build_user_prompt(advisory: Advisory, repo: WatchlistRepo) -> str:
    return (
        f"ADVISORY id={advisory.id} source={advisory.source} severity={advisory.severity}\n"
        f"title: {advisory.title}\n"
        f"summary: {advisory.summary[:800]}\n"
        f"affected_packages: {', '.join(advisory.affected_packages) or '(none declared)'}\n"
        f"ecosystem: {advisory.ecosystem or 'unspecified'}\n\n"
        f"REPO owner={repo.owner} name={repo.repo} ecosystem={repo.ecosystem}\n"
        f"topics: {', '.join(repo.topics) or '(none)'}\n"
    )


async def judge(
    advisory: Advisory,
    repo: WatchlistRepo,
    *,
    completion: Any | None = None,
    model: str | None = None,
) -> JudgeVerdict:
    """Return a :class:`JudgeVerdict` for this ``(advisory, repo)`` pair.

    ``completion`` is an optional awaitable for tests; production calls use
    LiteLLM's ``acompletion``. We constrain the output with a Pydantic
    model and retry once on schema failure.
    """
    model_name = model or os.environ.get("LITELLM_MODEL", _DEFAULT_MODEL)
    acompletion = completion or _default_completion()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(advisory, repo)},
    ]

    for attempt in range(2):
        resp = await acompletion(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=400,
        )
        text = _extract_content(resp)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            if attempt == 0:
                continue
            raise
        # Ensure required scalar fields even if the model omitted them.
        payload.setdefault("advisory_id", advisory.id)
        payload.setdefault("repo", f"{repo.owner}/{repo.repo}")
        try:
            return JudgeVerdict.model_validate(payload)
        except ValidationError:
            if attempt == 0:
                continue
            raise

    # Defensive fallback; mypy wants it.
    raise RuntimeError("judge: unreachable — retry loop should have returned or raised")


def _default_completion() -> Any:
    """Return LiteLLM's async completion function."""
    from litellm import acompletion

    return acompletion


def _extract_content(resp: Any) -> str:
    """Pull assistant text out of a LiteLLM ``acompletion`` response.

    LiteLLM returns an OpenAI-compatible shape:
    ``resp.choices[0].message.content``.
    """
    choice = resp.choices[0] if hasattr(resp, "choices") else resp["choices"][0]
    message = getattr(choice, "message", None) or choice["message"]
    content = getattr(message, "content", None) or message["content"]
    if not isinstance(content, str):
        raise ValueError(f"judge: completion returned non-string content: {type(content)}")
    return content
