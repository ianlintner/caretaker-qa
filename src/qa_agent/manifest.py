"""Fetch + parse a repo's dependency manifest to extract declared packages.

Supports:

* ``pyproject.toml`` (PEP 621 ``project.dependencies`` + optional-dependencies)
* ``requirements.txt`` (one line per dep)
* ``package.json`` (``dependencies`` + ``devDependencies``)
* ``go.mod`` (``require`` block)
* ``Cargo.toml`` (``[dependencies]``)
* ``.github/workflows/*.yml`` (``uses: owner/name@ver`` for ``ecosystem: actions``)

All parsers are deliberately lenient: we're extracting package *names* for
matcher keying, not installing anything. Version ranges are ignored here —
the matcher stage reads them from advisories.

Everything runs off a :class:`httpx.AsyncClient`; tests mock the client.
"""

from __future__ import annotations

import json
import re
import tomllib
from typing import TYPE_CHECKING

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from qa_agent.models import Ecosystem, WatchlistRepo

if TYPE_CHECKING:
    pass

RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"

_MANIFEST_BY_ECOSYSTEM: dict[Ecosystem, tuple[str, ...]] = {
    "pypi": ("pyproject.toml", "requirements.txt"),
    "npm": ("package.json",),
    "go": ("go.mod",),
    "cargo": ("Cargo.toml",),
    "actions": (".github/workflows",),
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
async def fetch_dependencies(
    repo: WatchlistRepo,
    *,
    client: httpx.AsyncClient | None = None,
) -> set[str]:
    """Return the set of declared package names for ``repo``.

    A return value of ``set()`` means either the repo has no deps in the
    recognised ecosystem or the raw file is 404 — we don't distinguish
    because the matcher treats both as "nothing to match against."
    """
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True)
    try:
        candidates: tuple[str, ...]
        if repo.manifest:
            candidates = (repo.manifest,)
        else:
            candidates = _MANIFEST_BY_ECOSYSTEM.get(repo.ecosystem, ())
        deps: set[str] = set()
        for path in candidates:
            url = RAW_URL.format(owner=repo.owner, repo=repo.repo, path=path)
            resp = await c.get(url)
            if resp.status_code == 200:
                deps.update(_parse(path, resp.text, repo.ecosystem))
        return deps
    finally:
        if own_client:
            await c.aclose()


def _parse(path: str, text: str, ecosystem: Ecosystem) -> set[str]:
    if path.endswith("pyproject.toml") or path == "pyproject.toml":
        return _parse_pyproject(text)
    if path.endswith("requirements.txt"):
        return _parse_requirements(text)
    if path.endswith("package.json"):
        return _parse_package_json(text)
    if path.endswith("go.mod"):
        return _parse_go_mod(text)
    if path.endswith("Cargo.toml"):
        return _parse_cargo_toml(text)
    if ecosystem == "actions" and path.endswith(".yml"):
        return _parse_actions_workflow(text)
    return set()


def _parse_pyproject(text: str) -> set[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return set()
    deps: set[str] = set()
    project = data.get("project") or {}
    for entry in project.get("dependencies", []) or []:
        name = _pep508_name(entry)
        if name:
            deps.add(name)
    for extras in (project.get("optional-dependencies") or {}).values():
        for entry in extras:
            name = _pep508_name(entry)
            if name:
                deps.add(name)
    return deps


_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)")


def _pep508_name(spec: str) -> str | None:
    m = _PEP508_NAME.match(spec)
    if not m:
        return None
    return m.group(1).lower()


def _parse_requirements(text: str) -> set[str]:
    deps: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = _pep508_name(line)
        if name:
            deps.add(name)
    return deps


def _parse_package_json(text: str) -> set[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return set()
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            deps.update(k.lower() for k in block)
    return deps


_GO_REQUIRE_RE = re.compile(r"^\s*([a-z0-9][a-z0-9._\-/]+)\s+v[\d.]+", re.MULTILINE)


def _parse_go_mod(text: str) -> set[str]:
    deps: set[str] = set()
    in_require = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if stripped == ")" and in_require:
            in_require = False
            continue
        if stripped.startswith("require "):
            m = _GO_REQUIRE_RE.match(stripped[8:])
            if m:
                deps.add(m.group(1).lower())
            continue
        if in_require:
            m = _GO_REQUIRE_RE.match(stripped)
            if m:
                deps.add(m.group(1).lower())
    return deps


def _parse_cargo_toml(text: str) -> set[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return set()
    deps: set[str] = set()
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        block = data.get(section) or {}
        if isinstance(block, dict):
            deps.update(k.lower() for k in block)
    return deps


_USES_RE = re.compile(r"uses:\s*([A-Za-z0-9][A-Za-z0-9._\-/]+)(?:@([A-Za-z0-9._\-]+))?")


def _parse_actions_workflow(text: str) -> set[str]:
    deps: set[str] = set()
    for m in _USES_RE.finditer(text):
        name = m.group(1)
        if "/" in name:
            deps.add(name.lower())
    return deps
