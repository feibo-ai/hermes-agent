"""Owner-gated `permissions` LLM tool: preview/confirm + capability gating."""

import json

import pytest

import tools.permissions_tool as pt
from agent.permissions import (
    Identity,
    PermissionEngine,
    load_policy,
    reset_current_identity,
    reset_engine,
    set_current_identity,
    set_engine,
)
from agent.permissions.tool_policy import required_capability_for_tool


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    yield tmp_path


def _act_as(role, enabled=True):
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "local:owner": {"roles": ["owner"]},
        "tg:m": {"roles": ["member"]},
    }}})
    eng = PermissionEngine(pol, audit=__import__("agent.permissions", fromlist=["AuditLog"]).AuditLog())
    set_engine(eng)
    if role == "owner":
        tok = set_current_identity(Identity(id="local:owner", roles=("owner",)))
    else:
        tok = set_current_identity(Identity(id="tg:m", roles=(role,)))
    return eng, tok


def _td(tok):
    reset_current_identity(tok)
    reset_engine()


def test_tool_is_owner_gated_capability():
    assert required_capability_for_tool("permissions") == "manage.roles"


def test_owner_read_actions(home):
    eng, tok = _act_as("owner")
    try:
        users = json.loads(pt.permissions_tool("users"))
        assert users["success"] is True
        roles = json.loads(pt.permissions_tool("roles"))
        assert any(r["role"] == "mentor" for r in roles["roles"])
        pol = json.loads(pt.permissions_tool("policy"))
        assert pol["success"] is True
    finally:
        _td(tok)


def test_grant_requires_confirmation(home):
    eng, tok = _act_as("owner")
    try:
        prev = json.loads(pt.permissions_tool("grant", identity="tg:x", role="member"))
        assert prev["success"] is False
        assert prev["needs_confirmation"] is True
        # nothing written yet
        assert not (home / "permissions.yaml").exists()
    finally:
        _td(tok)


def test_grant_applies_with_confirm(home):
    eng, tok = _act_as("owner")
    try:
        res = json.loads(pt.permissions_tool("grant", identity="tg:x", role="member", confirm=True))
        assert res["success"] is True
        assert "member" in load_policy(home=home).roles_for_identity("tg:x")
        # mutation audited
        assert len(eng.audit.query(event_type="privileged_mutation")) >= 1
    finally:
        _td(tok)


def test_revoke_then_confirm(home):
    eng, tok = _act_as("owner")
    try:
        pt.permissions_tool("grant", identity="tg:x", role="admin", confirm=True)
        pt.permissions_tool("revoke", identity="tg:x", role="admin", confirm=True)
        assert "admin" not in load_policy(home=home).roles_for_identity("tg:x")
    finally:
        _td(tok)


def test_non_owner_mutation_is_denied_by_admin_layer(home):
    # Defense in depth: even if a non-owner reached the tool, admin.grant_role
    # rejects without manage.roles.
    eng, tok = _act_as("member")
    try:
        res = json.loads(pt.permissions_tool("grant", identity="tg:x", role="owner", confirm=True))
        assert res["success"] is False
        assert "denied" in res.get("error", "").lower() or "permitted" in res.get("error", "").lower()
        assert not (home / "permissions.yaml").exists()
    finally:
        _td(tok)


def test_enable_disable_need_confirm(home):
    eng, tok = _act_as("owner")
    try:
        assert json.loads(pt.permissions_tool("enable"))["needs_confirmation"] is True
        res = json.loads(pt.permissions_tool("enable", confirm=True))
        assert res["success"] is True
        assert load_policy(home=home).enabled is True
    finally:
        _td(tok)
