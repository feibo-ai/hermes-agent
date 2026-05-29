"""MiraHire identity-resolver hook for the recruiter profile.

The Feishu platform delivers each inbound message with a sender
``union_id`` (per the app's event subscription setting). This module:

  1. Stashes the inbound sender's union_id (+ resolved MiraHire identity)
     into a contextvar at the start of each agent turn.
  2. Exposes ``current_identity()`` so the ``mirahire_create_requirement``
     tool can read who the current human is before writing.

Wiring (deployment-time):
  - Feishu app event subscription must send ``user_id_type=union_id``
    (set in https://open.feishu.cn → 应用 → 事件订阅 → 配置).
  - The recruiter profile's Feishu platform handler in
    ``gateway/platforms/feishu.py`` must call
    ``bind_identity_for_turn(union_id=event.sender.union_id)`` before
    forwarding the message to the agent loop.

If the hook is not wired, ``current_identity()`` returns ``None`` and the
mirahire tool will refuse the write (fail-closed).

See: docs/superpowers/specs/2026-05-28-requirements-mining-agent-mirahire-integration-design.md §6.4
"""

from __future__ import annotations

import contextvars
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bearer-token provider
# ---------------------------------------------------------------------------
# The deployed MiraHire backends run KEYCLOAK_ENABLED=true and validate tokens
# via Keycloak JWKS (RS256). So in production the bot authenticates as a
# Keycloak *service account* via the client_credentials grant. For local /
# test backends (KEYCLOAK_ENABLED=false) a static self-built HS256 token in
# MIRAHIRE_API_TOKEN still works.
#
# Env:
#   MIRAHIRE_KEYCLOAK_TOKEN_URL  – realm token endpoint
#       (…/realms/<realm>/protocol/openid-connect/token)
#   MIRAHIRE_KEYCLOAK_CLIENT_ID  – confidential client with service accounts on
#   MIRAHIRE_KEYCLOAK_CLIENT_SECRET
#   MIRAHIRE_API_TOKEN           – static fallback (local/test only)
_token_lock = threading.Lock()
_kc_token_cache: dict[str, Any] = {"token": None, "exp": 0.0}


def _integration_configured() -> bool:
    """True if either auth mode is configured. Cheap (env-only, no network).

    Used by the per-message no-op guards so deployments without the
    integration pay nothing.
    """
    if os.environ.get("MIRAHIRE_KEYCLOAK_CLIENT_ID") and os.environ.get(
        "MIRAHIRE_KEYCLOAK_CLIENT_SECRET"
    ):
        return True
    return bool(os.environ.get("MIRAHIRE_API_TOKEN"))


def get_bearer_token() -> Optional[str]:
    """Return a bearer token for MiraHire API calls (or None if unconfigured).

    Prefers Keycloak client_credentials (cached until ~30s before expiry);
    falls back to the static MIRAHIRE_API_TOKEN.
    """
    token_url = os.environ.get("MIRAHIRE_KEYCLOAK_TOKEN_URL")
    client_id = os.environ.get("MIRAHIRE_KEYCLOAK_CLIENT_ID")
    client_secret = os.environ.get("MIRAHIRE_KEYCLOAK_CLIENT_SECRET")

    if token_url and client_id and client_secret:
        now = time.time()
        with _token_lock:
            cached = _kc_token_cache.get("token")
            if cached and now < float(_kc_token_cache.get("exp", 0.0)) - 30:
                return cached
            try:
                import httpx

                resp = httpx.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                body = resp.json()
                tok = body.get("access_token")
                if not tok:
                    logger.error("Keycloak token response missing access_token")
                    return None
                _kc_token_cache["token"] = tok
                _kc_token_cache["exp"] = now + float(body.get("expires_in", 300))
                return tok
            except Exception:  # pragma: no cover — network/credential errors
                logger.exception("Keycloak client_credentials token fetch failed")
                return None

    return os.environ.get("MIRAHIRE_API_TOKEN") or None


# Contextvar carrying the resolved MiraHire identity for the current turn.
# Set by ``bind_identity_for_turn`` at the start of each Feishu inbound
# message; consumed by ``current_identity`` from within tool handlers.
_identity_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "mirahire_identity", default=None
)


def current_identity() -> Optional[dict[str, Any]]:
    """Return the active turn's resolved MiraHire identity (or None).

    Returned dict shape:
        {"user_id": str, "tenant_id": str, "role": str, "display_name": str}
    """
    return _identity_var.get()


def _resolve_via_mirahire(union_id: str) -> Optional[dict[str, Any]]:
    """Call MiraHire's /internal/users/by-feishu-union/{union_id} endpoint.

    Returns the parsed response dict, or None on 404 / network failure.
    Uses MIRAHIRE_API_TOKEN and MIRAHIRE_BASE_URL from env.
    """
    base = os.environ.get("MIRAHIRE_BASE_URL", "https://interview.feibo.cn/v2")
    token = get_bearer_token()
    if not token:
        logger.warning(
            "No MiraHire bearer token (Keycloak client_credentials nor static "
            "MIRAHIRE_API_TOKEN configured); cannot resolve union_id=%s",
            union_id,
        )
        return None

    try:
        import httpx

        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{base}/internal/users/by-feishu-union/{union_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            logger.warning(
                "MiraHire by-feishu-union returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None
        return resp.json()
    except Exception:  # pragma: no cover — network errors
        logger.exception("MiraHire identity resolution failed for %s", union_id)
        return None


def bind_identity_for_turn(*, union_id: str | None) -> Optional[dict[str, Any]]:
    """Resolve and bind the current turn's identity. Idempotent within a turn.

    Returns the resolved identity dict (or None). Sets the contextvar so
    ``current_identity()`` returns the same value during the turn.

    Synchronous variant — safe to call from non-async code. For the async
    inbound hot path (the Feishu platform handler), prefer
    ``bind_identity_for_turn_async`` so the blocking MiraHire HTTP call
    doesn't stall the event loop.
    """
    if not union_id:
        _identity_var.set(None)
        return None

    # No-op fast path for deployments that don't enable the integration:
    # avoids a wasted MiraHire call on every message.
    if not _integration_configured():
        _identity_var.set(None)
        return None

    cached = _identity_var.get()
    if cached and cached.get("_source_union_id") == union_id:
        return cached  # already bound for this turn

    resolved = _resolve_via_mirahire(union_id)
    if resolved is None:
        _identity_var.set(None)
        return None

    # Attach the source key for cache short-circuiting.
    resolved["_source_union_id"] = union_id
    _identity_var.set(resolved)
    return resolved


async def bind_identity_for_turn_async(*, union_id: str | None) -> Optional[dict[str, Any]]:
    """Async-safe identity binding for the inbound message hot path.

    Runs the blocking MiraHire resolution in a worker thread so the
    gateway event loop is never stalled. The contextvar is then set on
    the calling task, so any tool invoked downstream in the same async
    context sees it via ``current_identity()``.

    No-op (sets None) when:
      - union_id is empty (Feishu app not configured for union_id), or
      - the integration is not configured here (no Keycloak client creds
        and no static MIRAHIRE_API_TOKEN).
    """
    import asyncio

    if not union_id or not _integration_configured():
        _identity_var.set(None)
        return None

    cached = _identity_var.get()
    if cached and cached.get("_source_union_id") == union_id:
        return cached

    resolved = await asyncio.to_thread(_resolve_via_mirahire, union_id)
    if resolved is None:
        _identity_var.set(None)
        return None

    resolved["_source_union_id"] = union_id
    _identity_var.set(resolved)
    return resolved


def reset_identity_for_turn() -> None:
    """Clear the identity binding (call on session end / agent end)."""
    _identity_var.set(None)
