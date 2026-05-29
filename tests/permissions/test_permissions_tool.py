"""Owner-gated `permissions` LLM tool: out-of-band approval + capability gating.

Mutations go through check_all_command_guards -> the runtime approval callback
(the same path the terminal tool uses). The synthetic ``permissions grant ...``
command matches a DANGEROUS_PATTERNS rule, so the human must approve/deny it.
Tests run with HERMES_INTERACTIVE=1 (CLI path) and install a fake approval
callback to simulate the human's approve/deny.
"""

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
from tools.terminal_tool import set_approval_callback


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    # check_all_command_guards only consults the approval callback on the
    # CLI-interactive path; mark this context interactive so the fake callback
    # below stands in for the human's approve/deny decision.
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    yield tmp_path
    set_approval_callback(None)  # reset thread-local approval callback


def _approve():
    set_approval_callback(lambda *a, **k: "once")


def _deny():
    set_approval_callback(lambda *a, **k: "deny")


def _approval_errors():
    def _boom(*a, **k):
        raise RuntimeError("no approval channel")
    set_approval_callback(_boom)


def _act_as(role):
    pol = load_policy(config={"permissions": {"enabled": True, "users": {
        "local:owner": {"roles": ["owner"]},
        "tg:m": {"roles": ["member"]},
    }}})
    eng = PermissionEngine(pol, audit=__import__("agent.permissions", fromlist=["AuditLog"]).AuditLog())
    set_engine(eng)
    ident = Identity(id="local:owner", roles=("owner",)) if role == "owner" else Identity(id="tg:m", roles=(role,))
    return eng, set_current_identity(ident)


def _td(tok):
    reset_current_identity(tok)
    reset_engine()


def test_tool_is_owner_gated_capability():
    assert required_capability_for_tool("permissions") == "manage.roles"


def test_owner_read_actions_need_no_approval(home):
    eng, tok = _act_as("owner")
    try:
        assert json.loads(pt.permissions_tool("users"))["success"] is True
        roles = json.loads(pt.permissions_tool("roles"))
        assert any(r["role"] == "mentor" for r in roles["roles"])
    finally:
        _td(tok)


def test_grant_applies_only_after_human_approval(home):
    eng, tok = _act_as("owner")
    _approve()
    try:
        res = json.loads(pt.permissions_tool("grant", identity="tg:x", role="member"))
        assert res["success"] is True and res["approved"] is True
        assert "member" in load_policy(home=home).roles_for_identity("tg:x")
        assert len(eng.audit.query(event_type="privileged_mutation")) >= 1
    finally:
        _td(tok)


def test_grant_denied_when_human_denies(home):
    eng, tok = _act_as("owner")
    _deny()
    try:
        res = json.loads(pt.permissions_tool("grant", identity="tg:x", role="member"))
        assert res["success"] is False and res.get("approved") is False
        assert not (home / "permissions.yaml").exists()  # nothing written
    finally:
        _td(tok)


def test_fail_closed_when_no_approval_channel(home):
    eng, tok = _act_as("owner")
    _approval_errors()  # approval raises -> treated as deny
    try:
        res = json.loads(pt.permissions_tool("grant", identity="tg:x", role="member"))
        assert res["success"] is False
        assert not (home / "permissions.yaml").exists()
    finally:
        _td(tok)


def test_revoke_after_approval(home):
    eng, tok = _act_as("owner")
    _approve()
    try:
        pt.permissions_tool("grant", identity="tg:x", role="admin")
        pt.permissions_tool("revoke", identity="tg:x", role="admin")
        assert "admin" not in load_policy(home=home).roles_for_identity("tg:x")
    finally:
        _td(tok)


def test_enable_after_approval(home):
    eng, tok = _act_as("owner")
    _approve()
    try:
        res = json.loads(pt.permissions_tool("enable"))
        assert res["success"] is True
        assert load_policy(home=home).enabled is True
    finally:
        _td(tok)


def test_non_owner_denied_by_admin_layer_even_if_approved(home):
    # Defense in depth: even with approval, admin.grant_role rejects a
    # non-owner actor (no manage.roles).
    eng, tok = _act_as("member")
    _approve()
    try:
        res = json.loads(pt.permissions_tool("grant", identity="tg:x", role="owner"))
        assert res["success"] is False
        assert not (home / "permissions.yaml").exists()
    finally:
        _td(tok)
