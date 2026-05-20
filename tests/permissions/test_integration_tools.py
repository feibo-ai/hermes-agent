"""Phase 2 (TEA-90) — end-to-end enforcement through the real model_tools
dispatch + schema-building code paths."""

import json

import pytest

import model_tools
from agent.permissions import (
    AuditLog,
    PermissionEngine,
    load_policy,
    reset_current_identity,
    reset_engine,
    set_current_identity,
    set_engine,
)


@pytest.fixture(autouse=True)
def _clear_tool_cache():
    model_tools._tool_defs_cache.clear()
    yield
    model_tools._tool_defs_cache.clear()


def _setup(role="member", enabled=True):
    audit = AuditLog()
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "tg:u": {"roles": [role]},
    }}})
    eng = PermissionEngine(pol, audit=audit)
    set_engine(eng)
    ident = eng.resolve(platform="tg", user_id="u")
    token = set_current_identity(ident)
    return eng, audit, token


def _teardown(token):
    reset_current_identity(token)
    reset_engine()


def test_member_tool_schema_excludes_admin_only_tools():
    eng, audit, token = _setup("member")
    try:
        defs = model_tools.get_tool_definitions(
            enabled_toolsets=["skills", "terminal", "web"], quiet_mode=True
        )
        names = {d["function"]["name"] for d in defs}
        # member-safe tools remain visible
        assert "skills_list" in names
        assert "skill_view" in names
        # admin-only tools are filtered out of what the model can see
        assert "skill_manage" not in names
        assert "terminal" not in names
    finally:
        _teardown(token)


def test_owner_tool_schema_includes_admin_tools():
    eng, audit, token = _setup("owner")
    try:
        # owner resolves via the implicit local owner mapping; give the gateway
        # user the owner role explicitly above
        defs = model_tools.get_tool_definitions(
            enabled_toolsets=["skills", "terminal"], quiet_mode=True
        )
        names = {d["function"]["name"] for d in defs}
        # proves the admin tools are actually present pre-filter
        assert "skill_manage" in names
        assert "terminal" in names
    finally:
        _teardown(token)


def test_member_direct_admin_tool_call_blocked_before_dispatch():
    eng, audit, token = _setup("member")
    try:
        result = model_tools.handle_function_call("skill_manage",
                                                  {"action": "create", "name": "x"})
        data = json.loads(result)
        assert "error" in data
        assert "is not permitted to" in data["error"]
        # the denial is captured in the audit log
        assert len(audit.query(decision="deny")) >= 1
    finally:
        _teardown(token)


def test_member_safe_tool_not_blocked_by_permission():
    eng, audit, token = _setup("member")
    try:
        # an unknown but "safe" tool: the permission guard must let it through
        # (it then fails downstream for an unrelated reason, which is fine).
        result = model_tools.handle_function_call("definitely_not_a_real_tool_xyz", {})
        assert "is not permitted to" not in result
    finally:
        _teardown(token)


def test_disabled_enforcement_allows_admin_tool_call():
    eng, audit, token = _setup("member", enabled=False)
    try:
        # with enforcement off, the guard is a no-op (single-user CLI default)
        defs = model_tools.get_tool_definitions(enabled_toolsets=["skills"], quiet_mode=True)
        names = {d["function"]["name"] for d in defs}
        assert "skill_manage" in names
    finally:
        _teardown(token)
