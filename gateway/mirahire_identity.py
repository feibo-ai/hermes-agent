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
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
    token = os.environ.get("MIRAHIRE_API_TOKEN", "")
    if not token:
        logger.warning(
            "MIRAHIRE_API_TOKEN unset; cannot resolve union_id=%s", union_id
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
    if not os.environ.get("MIRAHIRE_API_TOKEN"):
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
      - MIRAHIRE_API_TOKEN is unset (integration not enabled here).
    """
    import asyncio

    if not union_id or not os.environ.get("MIRAHIRE_API_TOKEN"):
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
