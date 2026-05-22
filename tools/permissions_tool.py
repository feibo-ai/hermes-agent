"""LLM-callable permission administration (Epic TEA-88).

Lets an owner manage roles/users/policy *by conversation*. The tool is
owner-gated (requires ``manage.roles`` — see tool_policy), every mutation is
audited, and mutating actions (grant/revoke/enable/disable) require an explicit
``confirm=true`` second call so a preview can be shown to the human first.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error


def _result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def permissions_tool(
    action: str,
    identity: Optional[str] = None,
    role: Optional[str] = None,
    decision: Optional[str] = None,
    privileged: bool = False,
    limit: Optional[int] = None,
    confirm: bool = False,
) -> str:
    try:
        from agent.permissions import admin, get_current_identity, get_engine
        from agent.permissions.engine import PermissionDenied
        from hermes_constants import get_hermes_home
    except Exception as exc:  # pragma: no cover - defensive
        return tool_error(f"permissions subsystem unavailable: {exc}", success=False)

    home = get_hermes_home()
    eng = get_engine()
    actor = get_current_identity()

    # --- read-only actions -------------------------------------------------
    if action == "users":
        return _result({"success": True, "users": admin.list_users(eng.policy),
                        "enabled": eng.policy.enabled, "default_role": eng.policy.default_role})
    if action == "roles":
        return _result({"success": True, "roles": admin.list_roles(eng.policy)})
    if action == "policy":
        return _result({"success": True, "policy": admin.show_policy(eng.policy)})
    if action == "audit":
        event_type = "privileged_mutation" if privileged else None
        events = admin.audit_list(home, decision=decision, event_type=event_type, limit=limit)
        return _result({"success": True, "events": events, "count": len(events)})

    # --- mutating actions (preview unless confirm=true) --------------------
    if action in ("grant", "revoke"):
        if not identity or not role:
            return tool_error("identity and role are required for grant/revoke.", success=False)
        if not confirm:
            prep = "to" if action == "grant" else "from"
            return _result({
                "success": False,
                "needs_confirmation": True,
                "preview": f"About to {action} role '{role}' {prep} identity '{identity}'.",
                "instruction": ("Show this to the human and ONLY re-call with the same "
                                "action/identity/role plus confirm=true after they explicitly approve. "
                                "Never set confirm=true on your own."),
            })
        try:
            fn = admin.grant_role if action == "grant" else admin.revoke_role
            res = fn(home, identity, role, actor, eng)
            return _result({"success": True, "applied": action, **res})
        except PermissionDenied as exc:
            return tool_error(f"Permission denied: {exc}", success=False)
        except Exception as exc:
            return tool_error(f"{action} failed: {exc}", success=False)

    if action in ("enable", "disable"):
        if not confirm:
            return _result({
                "success": False,
                "needs_confirmation": True,
                "preview": f"About to {action} permission enforcement globally for this Hermes home.",
                "instruction": ("Confirm with the human, then re-call with confirm=true. "
                                "Never set confirm=true on your own."),
            })
        try:
            res = admin.set_enabled(home, action == "enable", actor, eng)
            return _result({"success": True, "applied": action, **res})
        except PermissionDenied as exc:
            return tool_error(f"Permission denied: {exc}", success=False)
        except Exception as exc:
            return tool_error(f"{action} failed: {exc}", success=False)

    return tool_error(
        f"Unknown action '{action}'. Use: users, roles, policy, audit, grant, revoke, enable, disable.",
        success=False,
    )


def check_permissions_tool_requirements() -> bool:
    """No external requirements — capability gating (manage.roles) is enforced
    by the permission layer (tool_policy + enforcement)."""
    return True


PERMISSIONS_SCHEMA: dict[str, Any] = {
    "name": "permissions",
    "description": (
        "Administer Hermes multi-user permissions (owner-only). Read actions: "
        "'users' (list users+roles), 'roles' (list roles+capabilities), 'policy' "
        "(show effective policy), 'audit' (list audit events; optional decision="
        "allow|deny, privileged=true, limit). Mutating actions: 'grant'/'revoke' "
        "(identity + role), 'enable'/'disable' (toggle enforcement). MUTATIONS "
        "REQUIRE A TWO-STEP CONFIRMATION: first call WITHOUT confirm to get a "
        "preview, show it to the human, and only re-call with confirm=true after "
        "they explicitly approve. Identity ids look like 'telegram:123', "
        "'feishu:ou_...', 'local:owner'. Roles: owner|admin|member|mentor|guest."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["users", "roles", "policy", "audit",
                         "grant", "revoke", "enable", "disable"],
                "description": "The administration action to perform.",
            },
            "identity": {"type": "string", "description": "Identity id for grant/revoke (e.g. 'telegram:123')."},
            "role": {"type": "string", "description": "Role name for grant/revoke (owner|admin|member|mentor|guest|<custom>)."},
            "decision": {"type": "string", "enum": ["allow", "deny"], "description": "audit filter: only allowed or denied decisions."},
            "privileged": {"type": "boolean", "description": "audit filter: only privileged mutations."},
            "limit": {"type": "integer", "description": "audit: max number of most-recent events."},
            "confirm": {"type": "boolean", "description": "Set true ONLY after the human approves a previewed mutation."},
        },
        "required": ["action"],
    },
}


registry.register(
    name="permissions",
    toolset="permissions",
    schema=PERMISSIONS_SCHEMA,
    handler=lambda args, **kw: permissions_tool(
        action=args.get("action"),
        identity=args.get("identity"),
        role=args.get("role"),
        decision=args.get("decision"),
        privileged=bool(args.get("privileged", False)),
        limit=args.get("limit"),
        confirm=bool(args.get("confirm", False)),
    ),
    check_fn=check_permissions_tool_requirements,
    emoji="🔐",
)
