"""Token authentication helper for feed fetchers.

NVD and GHSA both throttle anonymous access aggressively — NVD's public
rate limit is 5 requests/30s and GHSA caps unauthenticated GraphQL at
60 points/hour. When the matching env vars are set
(``NVD_API_KEY`` / ``GITHUB_TOKEN``), we attach the credentials so the
relevant feed fetchers run on the higher-quota path.

Kept deliberately small and side-effect-free: ``auth_headers_for(name)``
returns the headers a feed should add to its outgoing request, or an
empty dict when no credentials are configured. The fetchers stay
unchanged when running in their default anonymous mode.

The shape mirrors how the upstream SDK auth-providers compose so we
can swap to a real provider chain (Azure Key Vault, AWS Secrets
Manager) later without touching the call sites.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedCredential:
    """Where the credential lives + which header carries it."""

    env_var: str
    header_name: str
    header_template: str  # e.g. "Bearer {token}" or "{token}"


# Per-feed credential layout. Add new feeds here when their fetcher
# starts supporting authenticated access.
_CREDENTIALS: Mapping[str, FeedCredential] = {
    "nvd": FeedCredential(
        env_var="NVD_API_KEY",
        header_name="apiKey",
        header_template="{token}",
    ),
    "ghsa": FeedCredential(
        env_var="GITHUB_TOKEN",
        header_name="Authorization",
        header_template="Bearer {token}",
    ),
}


def auth_headers_for(feed_name: str) -> dict[str, str]:
    """Return the auth headers a feed should add to outbound HTTP calls.

    Returns an empty dict when the matching env var is unset or empty,
    so callers can unconditionally do ``headers = {**defaults,
    **auth_headers_for(name)}`` without branching.
    """
    cred = _CREDENTIALS.get(feed_name)
    if cred is None:
        return {}
    raw = os.environ.get(cred.env_var, "").strip()
    if not raw:
        logger.debug("auth: %s env var %s unset; using anonymous", feed_name, cred.env_var)
        return {}
    return {cred.header_name: cred.header_template.format(token=raw)}


def credential_status() -> dict[str, bool]:
    """Diagnostic helper — returns ``{feed: has_token}`` for every known feed.

    Used by ``qa_agent doctor`` to surface which feeds will run on the
    rate-limited anonymous path so operators see it once at startup
    rather than discovering it via 429 retries at runtime.
    """
    return {
        name: bool(os.environ.get(cred.env_var, "").strip()) for name, cred in _CREDENTIALS.items()
    }


def known_feeds() -> list[str]:
    """All feed names recognised by the auth helper."""
    return list(_CREDENTIALS)


__all__ = [
    "FeedCredential",
    "auth_headers_for",
    "credential_status",
    "known_feeds",
]
