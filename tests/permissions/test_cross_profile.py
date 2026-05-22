"""Cross-profile central management via the permissions tool (Epic TEA-88)."""

import json

import pytest

import tools.permissions_tool as pt
from agent.permissions import (
    Identity,
    PermissionEngine,
    AuditLog,
    load_policy,
    reset_current_identity,
    reset_engine,
    set_current_identity,
    set_engine,
)
from tools.terminal_tool import set_approval_callback


@pytest.fixture
def env(tmp_path, monkeypatch):
    central = tmp_path / "central"; central.mkdir()
    team_a = tmp_path / "teamA"; team_a.mkdir()
    reg = tmp_path / "global-permissions.yaml"
    monkeypatch.setenv("HERMES_GLOBAL_PERMISSIONS", str(reg))
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: central)
    monkeypatch.setattr("agent.permissions.profiles.current_profile_home", lambda: central)
    monkeypatch.setattr("agent.permissions.profiles.current_profile_name", lambda: "central")
    monkeypatch.setattr("agent.permissions.profiles.resolve_profile_home",
                        lambda name: team_a if name == "teamA" else None)
    monkeypatch.setattr("agent.permissions.profiles.list_profiles",
                        lambda: [{"name": "central", "home": str(central)},
                                 {"name": "teamA", "home": str(team_a)}])
    # central profile engine: local:owner is owner here
    pol = load_policy(config={"permissions": {"enabled": True, "users": {"local:owner": {"roles": ["owner"]}}}})
    eng = PermissionEngine(pol, audit=AuditLog())
    set_engine(eng)
    tok = set_current_identity(Identity(id="local:owner", roles=("owner",)))
    set_approval_callback(lambda *a, **k: "once")  # human approves
    yield {"central": central, "teamA": team_a, "reg": reg, "eng": eng}
    reset_current_identity(tok)
    reset_engine()
    set_approval_callback(None)


def _super_admin_for(reg, profiles_list):
    reg.write_text(f'super_admins:\n  "local:owner": {{ profiles: {json.dumps(profiles_list)} }}\n',
                   encoding="utf-8")


def test_cross_profile_grant_applies_to_target_when_super_admin(env):
    _super_admin_for(env["reg"], ["teamA"])
    res = json.loads(pt.permissions_tool("grant", identity="telegram:7", role="member",
                                         target_profile="teamA"))
    assert res["success"] is True and res["approved"] is True
    assert res["profile"] == "teamA"
    # landed in teamA's permissions.yaml, NOT central
    assert "member" in load_policy(home=env["teamA"]).roles_for_identity("telegram:7")
    assert not (env["central"] / "permissions.yaml").exists()
    # dual audit: central engine audit + target profile audit file
    assert len(env["eng"].audit.query(event_type="privileged_mutation")) >= 1
    assert (env["teamA"] / "audit" / "permissions.jsonl").exists()


def test_cross_profile_denied_when_not_super_admin(env):
    _super_admin_for(env["reg"], ["teamB"])  # authorized for teamB only, not teamA
    res = json.loads(pt.permissions_tool("grant", identity="telegram:7", role="member",
                                         target_profile="teamA"))
    assert res["success"] is False
    assert not (env["teamA"] / "permissions.yaml").exists()  # nothing changed
    assert len(env["eng"].audit.query(decision="deny")) >= 1


def test_cross_profile_denied_when_no_registry(env):
    # registry file absent -> fail-closed
    res = json.loads(pt.permissions_tool("grant", identity="telegram:7", role="member",
                                         target_profile="teamA"))
    assert res["success"] is False
    assert not (env["teamA"] / "permissions.yaml").exists()


def test_unknown_target_profile_errors(env):
    _super_admin_for(env["reg"], ["*"])
    res = json.loads(pt.permissions_tool("grant", identity="telegram:7", role="member",
                                         target_profile="ghost"))
    assert res["success"] is False
    assert "Unknown profile" in res.get("error", "")


def test_cross_profile_read_users_when_super_admin(env):
    _super_admin_for(env["reg"], ["*"])
    # seed teamA with a user
    (env["teamA"] / "permissions.yaml").write_text(
        'enabled: true\nusers:\n  "tg:a": {roles: [member]}\n', encoding="utf-8")
    res = json.loads(pt.permissions_tool("users", target_profile="teamA"))
    assert res["success"] is True and res["profile"] == "teamA"
    assert any(u["identity"] == "tg:a" for u in res["users"])


def test_local_action_unchanged_without_target(env):
    res = json.loads(pt.permissions_tool("grant", identity="tg:local", role="member"))
    assert res["success"] is True and res["profile"] == "central"
    assert "member" in load_policy(home=env["central"]).roles_for_identity("tg:local")
