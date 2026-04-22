"""Tests for ``qa_agent.manifest``."""

from __future__ import annotations

import httpx
import pytest
import respx

from qa_agent.manifest import fetch_dependencies
from qa_agent.models import WatchlistRepo


@pytest.mark.asyncio
@respx.mock
async def test_pyproject_parsing() -> None:
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/pyproject.toml").mock(
        return_value=httpx.Response(
            200,
            text="""
[project]
name = "example"
dependencies = [
    "pydantic>=2.8",
    "httpx",
    "some_with_extras[cache]>=1.0",
]

[project.optional-dependencies]
dev = ["pytest", "ruff"]
""".lstrip(),
        )
    )
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/requirements.txt").mock(
        return_value=httpx.Response(404)
    )

    repo = WatchlistRepo(owner="o", repo="r", ecosystem="pypi")
    deps = await fetch_dependencies(repo)
    assert deps == {"pydantic", "httpx", "some_with_extras", "pytest", "ruff"}


@pytest.mark.asyncio
@respx.mock
async def test_package_json_parsing() -> None:
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/package.json").mock(
        return_value=httpx.Response(
            200,
            text='{"dependencies": {"react": "^18", "Axios": "^1"}, "devDependencies": {"vitest": "^1"}}',
        )
    )
    repo = WatchlistRepo(owner="o", repo="r", ecosystem="npm")
    deps = await fetch_dependencies(repo)
    assert deps == {"react", "axios", "vitest"}


@pytest.mark.asyncio
@respx.mock
async def test_go_mod_parsing() -> None:
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/go.mod").mock(
        return_value=httpx.Response(
            200,
            text="""
module example.com/foo

go 1.22

require (
    github.com/gin-gonic/gin v1.9.1
    golang.org/x/sys v0.20.0
)
""".lstrip(),
        )
    )
    repo = WatchlistRepo(owner="o", repo="r", ecosystem="go")
    deps = await fetch_dependencies(repo)
    assert {"github.com/gin-gonic/gin", "golang.org/x/sys"}.issubset(deps)


@pytest.mark.asyncio
@respx.mock
async def test_actions_workflow_parsing() -> None:
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/.github/workflows/ci.yml").mock(
        return_value=httpx.Response(
            200,
            text="""
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
""".strip(),
        )
    )
    repo = WatchlistRepo(
        owner="o",
        repo="r",
        ecosystem="actions",
        manifest=".github/workflows/ci.yml",
    )
    deps = await fetch_dependencies(repo)
    assert {"actions/checkout", "actions/setup-python"}.issubset(deps)


@pytest.mark.asyncio
@respx.mock
async def test_missing_manifest_returns_empty_set() -> None:
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/pyproject.toml").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/requirements.txt").mock(
        return_value=httpx.Response(404)
    )
    repo = WatchlistRepo(owner="o", repo="r", ecosystem="pypi")
    assert await fetch_dependencies(repo) == set()


@pytest.mark.asyncio
@respx.mock
async def test_malformed_toml_returns_empty() -> None:
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/pyproject.toml").mock(
        return_value=httpx.Response(200, text="this is not toml [ = )")
    )
    respx.get("https://raw.githubusercontent.com/o/r/HEAD/requirements.txt").mock(
        return_value=httpx.Response(404)
    )
    repo = WatchlistRepo(owner="o", repo="r", ecosystem="pypi")
    assert await fetch_dependencies(repo) == set()
