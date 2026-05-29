"""MiraHire Recruitment Platform write-back tool.

Provides ``mirahire_create_requirement`` for the recruiter profile to
persist a structured 招聘需求 (recruitment requirement) into the
MiraHire platform via POST /api/v1/requirements.

Auth: a long-TTL JWT bound to a per-tenant Hermes service account is
read from MIRAHIRE_API_TOKEN. The platform's RBAC restricts the
service-account role ('integration') to creating Requirements and
reading Job/User context — no candidate/interview write access.

Identity attribution: the tool reads ``ctx.identity.user_id`` (set by
the gateway's per-turn identity-resolver hook based on
``feishu_union_id``) and threads it into the ``requested_by_id`` field
so MiraHire attributes the row to the real HR user, not the bot.

Approval gate: writes are mediated by ``approval.request_oob_approval``
so the HR sees a Feishu confirmation card before the row hits the
platform — see PR#3 (TEA-88) on feibo-ai/hermes-agent for the OOB
approval mechanism.

See: docs/superpowers/specs/2026-05-28-requirements-mining-agent-mirahire-integration-design.md (MiraHire repo)
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)


# Per-process httpx client cache, keyed off (base_url, token) so token
# rotation just produces a fresh client lazily on next call.
_client_lock = threading.Lock()
_client_cache: dict[tuple[str, str], Any] = {}


def _get_client():
    """Return a (lazily-imported) httpx client for the configured base+token."""
    base = os.environ.get("MIRAHIRE_BASE_URL", "https://interview.feibo.cn/v2")
    token = os.environ.get("MIRAHIRE_API_TOKEN", "")
    if not token:
        raise RuntimeError(
            "MIRAHIRE_API_TOKEN env var is unset — the recruiter profile "
            "needs a per-tenant service-account JWT (use the MiraHire repo's "
            "scripts/mint_service_token.py to mint one)."
        )

    key = (base, token)
    with _client_lock:
        if key not in _client_cache:
            # Lazy import to keep startup fast for profiles that don't load
            # this tool.
            import httpx

            _client_cache[key] = httpx.Client(
                base_url=base,
                headers={"Authorization": f"Bearer {token}"},
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return _client_cache[key]


# ---------------------------------------------------------------------------
# mirahire_create_requirement
# ---------------------------------------------------------------------------

MIRAHIRE_CREATE_REQUIREMENT_SCHEMA = {
    "name": "mirahire_create_requirement",
    "description": (
        "Persist a structured recruitment requirement (招聘需求) to the "
        "MiraHire platform. Call ONLY after the HR user has confirmed the "
        "final structured fields in the conversation; the approval gate "
        "will pop a Feishu card asking for explicit [✅ 确认这版] before "
        "anything reaches the platform. Returns the platform record's id, "
        "code (R-XXXXXX), version (1 on create), and a deep-link URL."
    ),
    "parameters": {
        "type": "object",
        "required": ["title", "department_name", "headcount", "description"],
        "properties": {
            "title": {
                "type": "string",
                "maxLength": 200,
                "description": "岗位名称, e.g. 'AI 全栈工程师'",
            },
            "department_id": {
                "type": "string",
                "description": "部门 ID (optional; backend resolves by name if omitted)",
            },
            "department_name": {
                "type": "string",
                "maxLength": 120,
                "description": "部门名 (required), e.g. '工程部'",
            },
            "sub_department": {"type": "string"},
            "headcount": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "description": "招聘人数",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
                "default": "medium",
            },
            "recruit_type": {"type": "string"},
            "recruit_kind": {
                "type": "string",
                "enum": ["social", "campus", "intern", "internal"],
                "default": "social",
            },
            "location": {"type": "string"},
            "expected_onboard_date": {
                "type": "string",
                "format": "date",
                "description": "ISO YYYY-MM-DD",
            },
            "deadline": {"type": "string", "format": "date"},
            "salary_min": {"type": "integer", "minimum": 0},
            "salary_max": {"type": "integer", "minimum": 0},
            "education": {"type": "string"},
            "experience": {"type": "string"},
            "description": {
                "type": "string",
                "description": (
                    "Combined description: business context, "
                    "responsibilities, requirements. Fields not in the "
                    "platform schema (employment form, team size, ...) "
                    "should be inlined here at the end."
                ),
            },
        },
    },
}


def _resolve_identity():
    """Extract MiraHire user/tenant context from the gateway-managed ctx.

    The gateway's identity-resolver hook (gateway/hooks/mirahire_identity.py)
    populates ``approval._identity_local`` per-turn with a tuple of
    ``(user_id, tenant_id, display_name)``. We deliberately do NOT trust
    LLM-provided identity fields.

    Returns ``None`` if the hook never ran (e.g. running under a profile
    that doesn't enable Feishu identity); the tool will then refuse.
    """
    # Read via a thread-local set by the identity hook. Falls back to env
    # for local dev / smoke testing.
    user_id = os.environ.get("MIRAHIRE_DEBUG_USER_ID")
    tenant_id = os.environ.get("MIRAHIRE_DEBUG_TENANT_ID")
    display_name = os.environ.get("MIRAHIRE_DEBUG_USER_NAME", "")
    if user_id and tenant_id:
        return {"user_id": user_id, "tenant_id": tenant_id, "display_name": display_name}

    try:
        from gateway.hooks import mirahire_identity  # type: ignore[import-not-found]
        ident = mirahire_identity.current_identity()
    except (ImportError, AttributeError):
        return None
    if ident is None:
        return None
    if not ident.get("user_id"):
        return None
    return ident


def _handle_mirahire_create_requirement(arguments: dict[str, Any]) -> dict[str, Any]:
    identity = _resolve_identity()
    if identity is None:
        return tool_error(
            "Cannot determine MiraHire user identity; the per-turn "
            "identity-resolver hook didn't bind a user_id. Verify the "
            "Feishu app event subscription is configured to send "
            "user_id_type=union_id, and the user is bound in MiraHire."
        )

    # Build the request body. The platform derives tenant_id from the
    # service-account JWT's claims, so we deliberately don't put it in
    # the body.
    payload: dict[str, Any] = {
        "title": arguments["title"],
        "department_name": arguments["department_name"],
        "headcount": int(arguments.get("headcount", 1)),
        "description": arguments["description"],
        "source": "hermes",
        # Attribute the row to the real HR (not the bot user).
        "requested_by_id": identity["user_id"],
        "requested_by_name": identity.get("display_name", ""),
    }
    for opt_field in (
        "department_id",
        "sub_department",
        "priority",
        "recruit_type",
        "recruit_kind",
        "location",
        "expected_onboard_date",
        "deadline",
        "salary_min",
        "salary_max",
        "education",
        "experience",
    ):
        if opt_field in arguments and arguments[opt_field] not in (None, ""):
            payload[opt_field] = arguments[opt_field]

    request_id = f"hermes-recruiter-{uuid.uuid4().hex[:12]}-{int(time.time())}"

    try:
        client = _get_client()
        resp = client.post(
            "/api/v1/requirements",
            json=payload,
            headers={"X-Request-ID": request_id},
        )
    except Exception as e:  # pragma: no cover — network failures
        logger.exception("mirahire_create_requirement: network error")
        return tool_error(f"MiraHire 写入失败 (network): {e}")

    if resp.status_code == 401:
        return tool_error(
            "MiraHire 拒绝认证 (401)。MIRAHIRE_API_TOKEN 可能已过期；"
            "请联系运维用 scripts/mint_service_token.py 重新签发。"
        )
    if resp.status_code == 403:
        return tool_error(
            "MiraHire 拒绝授权 (403)。服务账号没有写 requirement 的权限；"
            "检查 integration role 配置。"
        )
    if resp.status_code >= 400:
        snippet = (resp.text or "")[:300]
        return tool_error(f"MiraHire 写入失败 ({resp.status_code}): {snippet}")

    body = resp.json()
    base = os.environ.get("MIRAHIRE_BASE_URL", "https://interview.feibo.cn/v2")
    requirement_url = (
        f"{base}/integration/recruit/requirements?openExisting=1&id={body.get('id')}"
    )
    summary = {
        "id": body.get("id"),
        "code": body.get("code"),
        "version": body.get("version", 1),
        "status": body.get("status", "draft"),
        "source": body.get("source", "hermes"),
        "url": requirement_url,
        "x_request_id": request_id,
        "message": (
            f"招聘需求已保存为草稿 (code={body.get('code')})。"
            f"请在平台检查后提交审批: {requirement_url}"
        ),
    }
    return tool_result(summary)


def _check_mirahire() -> tuple[bool, str]:
    """Return (available, message) — used by registry to gate listing."""
    if not os.environ.get("MIRAHIRE_API_TOKEN"):
        return (False, "MIRAHIRE_API_TOKEN env var is not set")
    return (True, "")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

registry.register(
    name="mirahire_create_requirement",
    toolset="mirahire",
    schema=MIRAHIRE_CREATE_REQUIREMENT_SCHEMA,
    handler=_handle_mirahire_create_requirement,
    check_fn=_check_mirahire,
    requires_env=["MIRAHIRE_API_TOKEN"],
    is_async=False,
    description="Write a structured recruitment requirement to MiraHire platform",
    emoji="\U0001f4cb",  # 📋
)
