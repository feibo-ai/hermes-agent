"""Decision helpers wired into tool dispatch, slash commands, and the
dangerous-command approval flow (TEA-90).

All helpers accept an explicit ``identity`` / ``engine`` for testability and
fall back to the process engine + current-identity context when omitted, so
deep call sites can call them with no arguments.
"""

from __future__ import annotations

from typing import Optional

from .context import get_current_identity, get_engine
from .engine import PermissionDenied, PermissionEngine
from .identity import Identity
from .tool_policy import required_capability_for_tool

# Privileged slash commands -> capability required to run them.
_COMMAND_CAPABILITIES: dict[str, str] = {
    "yolo": "tool.approve.dangerous",
    "approve": "tool.approve.dangerous",
    "deny": "tool.approve.dangerous",
    "permissions": "manage.roles",
    "audit": "read.audit",
}


def _engine(engine: Optional[PermissionEngine]) -> PermissionEngine:
    return engine if engine is not None else get_engine()


def _identity(identity: Optional[Identity]) -> Identity:
    return identity if identity is not None else get_current_identity()


def filter_tool_definitions(
    defs: list,
    identity: Optional[Identity] = None,
    engine: Optional[PermissionEngine] = None,
) -> list:
    """Drop tool schemas the identity isn't permitted to use."""
    eng = _engine(engine)
    if not eng.policy.enabled:
        return defs
    ident = _identity(identity)
    overrides = eng.policy.tool_capabilities
    out = []
    for d in defs:
        name = (d.get("function") or {}).get("name") if isinstance(d, dict) else None
        if not name:
            out.append(d)
            continue
        cap = required_capability_for_tool(name, overrides)
        if eng.can(ident, cap, audit=False):
            out.append(d)
    return out


def check_tool_call(
    tool_name: str,
    identity: Optional[Identity] = None,
    engine: Optional[PermissionEngine] = None,
    resource: Optional[str] = None,
) -> Optional[PermissionDenied]:
    """Return None if allowed, else a (non-raised) PermissionDenied. Denials
    are audited; allows are not, to keep the audit log signal-heavy."""
    eng = _engine(engine)
    if not eng.policy.enabled:
        return None
    ident = _identity(identity)
    cap = required_capability_for_tool(tool_name, eng.policy.tool_capabilities)
    if eng.can(ident, cap, resource=resource, audit=False):
        return None
    if eng.audit is not None:
        eng.audit.record_decision(ident, cap, "deny", resource=resource or f"tool:{tool_name}",
                                  reason="tool call blocked")
    return PermissionDenied(ident.id, cap, resource or f"tool:{tool_name}")


def can_approve_dangerous(
    identity: Optional[Identity] = None,
    engine: Optional[PermissionEngine] = None,
) -> bool:
    """Whether the identity may grant a durable dangerous-command approval."""
    eng = _engine(engine)
    if not eng.policy.enabled:
        return True
    ident = _identity(identity)
    return eng.can(ident, "tool.approve.dangerous", audit=False)


def command_required_capability(command_name: str) -> Optional[str]:
    return _COMMAND_CAPABILITIES.get(command_name)


def check_command(
    command_name: str,
    identity: Optional[Identity] = None,
    engine: Optional[PermissionEngine] = None,
) -> Optional[PermissionDenied]:
    """Return None if the command is allowed/unprivileged, else PermissionDenied."""
    cap = command_required_capability(command_name)
    if cap is None:
        return None
    eng = _engine(engine)
    if not eng.policy.enabled:
        return None
    ident = _identity(identity)
    if eng.can(ident, cap, resource=f"command:{command_name}", audit=False):
        return None
    if eng.audit is not None:
        eng.audit.record_decision(ident, cap, "deny", resource=f"command:{command_name}",
                                  reason="privileged command blocked")
    return PermissionDenied(ident.id, cap, f"command:{command_name}")
