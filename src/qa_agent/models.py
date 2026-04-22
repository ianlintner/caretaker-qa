"""Pydantic models shared across feeds, matcher, judge, and report."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "high", "medium", "low", "unknown"]
Ecosystem = Literal["pypi", "npm", "go", "cargo", "actions"]


class Advisory(BaseModel):
    """A normalised advisory from NVD / OSV / GHSA.

    Fields map to the least-common-denominator across the three feeds so the
    matcher downstream does not care about provenance.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="CVE-YYYY-NNNN or GHSA-xxxx-xxxx-xxxx")
    source: Literal["nvd", "osv", "ghsa"]
    title: str
    summary: str = ""
    severity: Severity = "unknown"
    cvss: float | None = None
    published: datetime
    ecosystem: Ecosystem | None = None
    affected_packages: list[str] = Field(default_factory=list)
    affected_ranges: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    """A generic security-news article pulled from an RSS feed."""

    model_config = ConfigDict(frozen=True)

    title: str
    link: str
    published: datetime
    source: str
    summary: str = ""


class WatchlistRepo(BaseModel):
    """A repo to match advisories against."""

    model_config = ConfigDict(frozen=True)

    owner: str
    repo: str
    ecosystem: Ecosystem
    topics: list[str] = Field(default_factory=list)
    manifest: str | None = None


class MatchVerdict(BaseModel):
    """Outcome of the deterministic matcher for (advisory, repo)."""

    model_config = ConfigDict(frozen=True)

    advisory_id: str
    repo: str
    status: Literal["match", "no_match", "ambiguous"]
    reason: str
    matched_package: str | None = None


class JudgeVerdict(BaseModel):
    """Structured LLM output for ambiguous items.

    The judge returns a relevance classification plus a short human-readable
    justification. We constrain its output space with this model so downstream
    code can trust the fields.
    """

    advisory_id: str
    repo: str
    relevant: bool = Field(..., description="True if an operator should act on this.")
    confidence: Literal["high", "medium", "low"]
    rationale: str = Field(..., max_length=500)


class ReportEntry(BaseModel):
    """One line item in the final brief."""

    advisory: Advisory
    repo: str
    severity: Severity
    relevance: Literal["direct", "likely", "speculative"]
    rationale: str


class Brief(BaseModel):
    """The full output of a scan run."""

    generated_at: datetime
    since: datetime
    until: datetime
    entries: list[ReportEntry] = Field(default_factory=list)
    feed_counts: dict[str, int] = Field(default_factory=dict)
    repos_scanned: int = 0
