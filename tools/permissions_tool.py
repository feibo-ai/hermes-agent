"""LLM-callable permission administration (Epic TEA-88).

Lets an owner manage roles/users/policy *by conversation* — for their own
profile, or (for a global super-admin) for another profile on the same machine
(cross-profile central management).

Security:
- the tool is owner-gated (requires ``manage.roles`` — see tool_policy);
- mutations go through Hermes' out-of-band approval (the human gets an
  approve/deny prompt the model cannot fake); fail-closed if no approval channel;
- cross-profile actions additionally require the actor to be a **global
  super-admin** for the target profile (``global-permissions.yaml`` outside any
  profile); over-reach is denied fail-closed and audited;
- cross-profile mutations are dual-audited (central profile + target profile);
- every change is audited.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error


def _result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _request_human_approval(action: str, identity: Optional[str], role: Optional[str],
                            profile_label: str) -> str:
    """Block for an out-of-band human approve/deny. Returns once/session/always
    (approved) or 'deny'. Fail-closed: any error -> deny."""
    try:
        from tools.approval import prompt_dangerous_approval
        from tools.terminal_tool import _get_approval_callback

        if action in ("grant", "revoke"):
            prep = "to" if action == "grant" else "from"
            human = f"{action} role '{role}' {prep} identity '{identity}'"
        else:
            human = f"{action} permission enforcement (global)"
        return prompt_dangerous_approval(
            command=f"permissions {action} {identity or ''} {role or ''} @{profile_label}".strip(),
            description=f"PERMISSION CHANGE in profile '{profile_label}' — {human}",
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
    target_profile: Optional[str] = None,
) -> str:
    try:
        from agent.permissions import admin, get_current_identity, get_engine, global_admin, profiles
        from agent.permissions import AuditLog, load_policy
        from agent.permissions.engine import PermissionDenied
        from hermes_constants import get_hermes_home
    except Exception as exc:  # pragma: no cover - defensive
        return tool_error(f"permissions subsystem unavailable: {exc}", success=False)

    eng = get_engine()           # central (this) profile's engine — also gates manage.roles
    actor = get_current_identity()

    # --- resolve scope: this profile, or a cross-profile target -----------
    cross = False
    profile_label = profiles.current_profile_name() or "default"
    home = get_hermes_home()
    scope_policy = eng.policy

    if target_profile:
        thome = profiles.resolve_profile_home(target_profile)
        if thome is None:
            return tool_error(f"Unknown profile '{target_profile}'. Use the 'profiles' action "
                              "or check `hermes profile list`.", success=False)
        if thome.resolve() != profiles.current_profile_home().resolve():
            # cross-profile: require global super-admin authority for this target
            if not global_admin.can_manage_profile(actor.id, target_profile):
                if eng.audit is not None:
                    eng.audit.record_decision(actor, "manage.profile", "deny",
                                              resource=f"profile:{target_profile}",
                                              reason="actor is not a global super-admin for target")
                return _result({
                    "success": False, "approved": False,
                    "message": (f"Denied: '{actor.id}' is not authorized to manage profile "
                                f"'{target_profile}'. Cross-profile management requires being a "
                                "global super-admin for that profile."),
                })
            cross = True
            home = thome
            profile_label = target_profile
            scope_policy = load_policy(home=home)

    # --- list available profiles (read) ------------------------------------
    if action == "profiles":
        return _result({"success": True, "profiles": profiles.list_profiles(),
                        "current": profiles.current_profile_name() or "default"})

    # --- read-only actions (scoped) ---------------------------------------
    if action == "users":
        return _result({"success": True, "profile": profile_label,
                        "users": admin.list_users(scope_policy),
                        "enabled": scope_policy.enabled, "default_role": scope_policy.default_role})
    if action == "roles":
        return _result({"success": True, "profile": profile_label, "roles": admin.list_roles(scope_policy)})
    if action == "policy":
        return _result({"success": True, "profile": profile_label, "policy": admin.show_policy(scope_policy)})
    if action == "audit":
        event_type = "privileged_mutation" if privileged else None
        events = admin.audit_list(home, decision=decision, event_type=event_type, limit=limit)
        return _result({"success": True, "profile": profile_label, "events": events, "count": len(events)})

    # --- mutating actions: require out-of-band human approval --------------
    if action in ("grant", "revoke"):
        if not identity or not role:
            return tool_error("identity and role are required for grant/revoke.", success=False)
    elif action not in ("enable", "disable"):
        return tool_error(
            f"Unknown action '{action}'. Use: profiles, users, roles, policy, audit, "
            "grant, revoke, enable, disable.", success=False,
        )

    if _request_human_approval(action, identity, role, profile_label) == "deny":
        return _result({
            "success": False, "approved": False, "profile": profile_label,
            "message": ("Change NOT applied — the human did not approve (or no approval channel "
                        "was available). Permission changes require an explicit out-of-band "
                        "approval that you cannot grant on the user's behalf."),
        })

    try:
        if action == "grant":
            res = admin.grant_role(home, identity, role, actor, eng)
        elif action == "revoke":
            res = admin.revoke_role(home, identity, role, actor, eng)
        else:  # enable / disable
            res = admin.set_enabled(home, action == "enable", actor, eng)
    except PermissionDenied as exc:
        return tool_error(f"Permission denied: {exc}", success=False)
    except Exception as exc:
        return tool_error(f"{action} failed: {exc}", success=False)

    # Dual audit: admin.* logged to the central engine's audit; for a
    # cross-profile change also record it in the *target* profile's audit log.
    if cross:
        try:
            ta = AuditLog(path=home / "audit" / "permissions.jsonl")
            ta.record_privileged_mutation(
                actor, f"manage.roles.{action}.via_central",
                resource=(f"user:{identity}" if identity else "policy"),
                metadata={"role": role, "central_profile": profiles.current_profile_name() or "default"},
            )
        except Exception:
            pass

    return _result({"success": True, "approved": True, "applied": action,
                    "profile": profile_label, **res})


def check_permissions_tool_requirements() -> bool:
    """No external requirements — capability gating (manage.roles) is enforced
    by the permission layer (tool_policy + enforcement)."""
    return True


PERMISSIONS_SCHEMA: dict[str, Any] = {
    "name": "permissions",
    "description": (
        "Administer Hermes multi-user permissions (owner-only). Read actions: "
        "'profiles' (list manageable profiles), 'users', 'roles', 'policy', 'audit'. "
        "Mutating actions: 'grant'/'revoke' (identity + role), 'enable'/'disable'. "
        "EVERY MUTATION triggers an out-of-band approve/deny prompt to the human "
        "and is applied only if they approve — you cannot approve on their behalf; "
        "just call the tool and report the result. Set 'target_profile' to manage "
        "ANOTHER profile (cross-profile / central management): this additionally "
        "requires you (the actor) to be a registered global super-admin for that "
        "profile, else it is denied. Omit target_profile to manage the current "
        "profile. Identity ids look like 'telegram:123', 'feishu:ou_...'. Roles: "
        "owner|admin|member|mentor|guest."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["profiles", "users", "roles", "policy", "audit",
                         "grant", "revoke", "enable", "disable"],
                "description": "The administration action to perform.",
            },
            "identity": {"type": "string", "description": "Identity id for grant/revoke (e.g. 'telegram:123')."},
            "role": {"type": "string", "description": "Role name for grant/revoke (owner|admin|member|mentor|guest|<custom>)."},
            "target_profile": {"type": "string", "description": "Manage another profile by name (cross-profile; requires global super-admin). Omit for the current profile."},
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
        target_profile=args.get("target_profile"),
    ),
    check_fn=check_permissions_tool_requirements,
    emoji="🔐",
)
