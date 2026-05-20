"""Phase 2 (TEA-90) — tool / command / dangerous-approval enforcement.

These are the pure decision helpers that get wired into model_tools,
tools/approval.py and cli.process_command.
"""

from agent.permissions import (
    AuditLog,
    Identity,
    PermissionEngine,
    load_policy,
)
from agent.permissions.enforcement import (
    can_approve_dangerous,
    check_command,
    check_tool_call,
    command_required_capability,
    filter_tool_definitions,
)


def _engine(enabled=True, audit=None):
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "local:owner": {"roles": ["owner"]},
        "tg:admin": {"roles": ["admin"]},
        "tg:member": {"roles": ["member"]},
        "tg:guest": {"roles": ["guest"]},
    }}})
    return PermissionEngine(pol, audit=audit)


def _ident(idid, role):
    return Identity(id=idid, roles=(role,))


def _defs(*names):
    return [{"type": "function", "function": {"name": n, "parameters": {}}} for n in names]


# --- schema filtering -------------------------------------------------------

def test_member_cannot_see_admin_only_tool_schema():
    eng = _engine()
    member = _ident("tg:member", "member")
    defs = _defs("web_search", "read_file", "skill_manage", "terminal")
    visible = {d["function"]["name"] for d in filter_tool_definitions(defs, member, eng)}
    assert "web_search" in visible
    assert "read_file" in visible
    # admin-only tools hidden from members
    assert "skill_manage" not in visible
    assert "terminal" not in visible


def test_owner_sees_all_tool_schemas():
    eng = _engine()
    owner = _ident("local:owner", "owner")
    defs = _defs("web_search", "skill_manage", "terminal", "browser_navigate")
    visible = {d["function"]["name"] for d in filter_tool_definitions(defs, owner, eng)}
    assert visible == {"web_search", "skill_manage", "terminal", "browser_navigate"}


def test_filter_is_noop_when_disabled():
    eng = _engine(enabled=False)
    member = _ident("tg:member", "member")
    defs = _defs("web_search", "skill_manage", "terminal")
    visible = {d["function"]["name"] for d in filter_tool_definitions(defs, member, eng)}
    assert visible == {"web_search", "skill_manage", "terminal"}


# --- execution guard --------------------------------------------------------

def test_member_direct_admin_tool_call_is_rejected():
    eng = _engine()
    member = _ident("tg:member", "member")
    denied = check_tool_call("skill_manage", member, eng)
    assert denied is not None
    assert denied.capability == "skill.update"


def test_member_safe_tool_call_allowed():
    eng = _engine()
    member = _ident("tg:member", "member")
    assert check_tool_call("web_search", member, eng) is None


def test_denied_tool_call_is_audited():
    audit = AuditLog()
    eng = _engine(audit=audit)
    member = _ident("tg:member", "member")
    check_tool_call("terminal", member, eng)
    deny = audit.query(decision="deny")
    assert len(deny) == 1
    assert deny[0].capability == "tool.use.shell"


def test_tool_guard_noop_when_disabled():
    eng = _engine(enabled=False)
    member = _ident("tg:member", "member")
    assert check_tool_call("skill_manage", member, eng) is None


# --- dangerous approval gate ------------------------------------------------

def test_only_owner_admin_can_approve_dangerous():
    eng = _engine()
    assert can_approve_dangerous(_ident("local:owner", "owner"), eng) is True
    assert can_approve_dangerous(_ident("tg:admin", "admin"), eng) is True
    assert can_approve_dangerous(_ident("tg:member", "member"), eng) is False
    assert can_approve_dangerous(_ident("tg:guest", "guest"), eng) is False


def test_dangerous_approval_allowed_when_disabled():
    eng = _engine(enabled=False)
    assert can_approve_dangerous(_ident("tg:guest", "guest"), eng) is True


# --- privileged slash command gating ----------------------------------------

def test_privileged_command_capability_map():
    assert command_required_capability("yolo") == "tool.approve.dangerous"
    assert command_required_capability("approve") == "tool.approve.dangerous"
    assert command_required_capability("help") is None  # unprivileged


def test_member_blocked_from_privileged_command():
    eng = _engine()
    member = _ident("tg:member", "member")
    assert check_command("yolo", member, eng) is not None
    assert check_command("help", member, eng) is None


def test_owner_allowed_privileged_command():
    eng = _engine()
    owner = _ident("local:owner", "owner")
    assert check_command("yolo", owner, eng) is None
