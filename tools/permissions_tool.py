"""LLM-callable permission administration (Epic TEA-88).

Lets an owner manage roles/users/policy *by conversation*. The tool is
owner-gated (requires ``manage.roles`` — see tool_policy) and every mutation is
audited. Mutations are NOT applied on the LLM's say-so: each grant/revoke/
enable/disable goes through Hermes' out-of-band approval (the same path used for
dangerous shell commands), so the human gets an approve/deny prompt the model
cannot fake. If no approval channel is available, the change is denied
(fail-closed).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error


def _result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _request_human_approval(action: str, identity: Optional[str], role: Optional[str]) -> str:
    """Block for an out-of-band human approve/deny. Returns one of
    once/session/always (approved) or 'deny'. Fail-closed: any error -> deny."""
    try:
        from tools.approval import prompt_dangerous_approval
        from tools.terminal_tool import _get_approval_callback

        if action in ("grant", "revoke"):
            prep = "to" if action == "grant" else "from"
            human = f"{action} role '{role}' {prep} identity '{identity}'"
        else:
            human = f"{action} permission enforcement (global)"
        return prompt_dangerous_approval(
            command=f"permissions {action} {identity or ''} {role or ''}".strip(),
            description=f"PERMISSION CHANGE — {human}",
            allow_permanent=False,
            approval_callback=_get_approval_callback(),
        )
    except Exception:
        return "deny"


def permissions_tool(
    action: str,
    identity: Optional[str] = None,
    role: Optional[str] = None,
    decision: Optional[str] = None,
    privileged: bool = False,
    limit: Optional[int] = None,
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

    # --- mutating actions: require out-of-band human approval --------------
    if action in ("grant", "revoke"):
        if not identity or not role:
            return tool_error("identity and role are required for grant/revoke.", success=False)
    elif action not in ("enable", "disable"):
        return tool_error(
            f"Unknown action '{action}'. Use: users, roles, policy, audit, grant, revoke, enable, disable.",
            success=False,
        )

    if _request_human_approval(action, identity, role) == "deny":
        return _result({
            "success": False,
            "approved": False,
            "message": ("Change NOT applied — the human did not approve (or no approval "
                        "channel was available). Permission changes require an explicit "
                        "out-of-band approval that you cannot grant on the user's behalf."),
        })

    try:
        if action == "grant":
            res = admin.grant_role(home, identity, role, actor, eng)
        elif action == "revoke":
            res = admin.revoke_role(home, identity, role, actor, eng)
        else:  # enable / disable
            res = admin.set_enabled(home, action == "enable", actor, eng)
        return _result({"success": True, "approved": True, "applied": action, **res})
    except PermissionDenied as exc:
        return tool_error(f"Permission denied: {exc}", success=False)
    except Exception as exc:
        return tool_error(f"{action} failed: {exc}", success=False)


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
        "(identity + role), 'enable'/'disable' (toggle enforcement). EVERY MUTATION "
        "triggers an out-of-band approve/deny prompt to the human and is applied "
        "only if they approve — you cannot approve on their behalf; just call the "
        "tool and report the result. Identity ids look like 'telegram:123', "
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
    ),
    check_fn=check_permissions_tool_requirements,
    emoji="🔐",
)
