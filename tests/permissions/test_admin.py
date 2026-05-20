"""Phase 5 (TEA-92) — admin commands: grant/revoke, list, policy, audit, migrate."""

from pathlib import Path

import pytest

from agent.permissions import AuditLog, Identity, PermissionEngine, load_policy
from agent.permissions import admin

OWNER = Identity(id="local:owner", roles=("owner",))
MEMBER = Identity(id="tg:m", roles=("member",))


def _engine(home, enabled=True):
    pol = load_policy(home=Path(home), config={"permissions": {"enabled": enabled, "users": {
        "local:owner": {"roles": ["owner"]},
        "tg:m": {"roles": ["member"]},
    }}})
    return PermissionEngine(pol, audit=AuditLog(path=Path(home) / "audit" / "permissions.jsonl"))


def test_list_users_and_roles():
    pol = load_policy(config={"permissions": {"enabled": True, "users": {"tg:m": {"roles": ["member"]}}}})
    users = admin.list_users(pol)
    assert {"identity": "tg:m", "roles": ["member"]} in users
    roles = {r["role"] for r in admin.list_roles(pol)}
    assert {"owner", "admin", "member", "guest"} <= roles


def test_show_policy():
    pol = load_policy(config={"permissions": {"enabled": True}})
    snap = admin.show_policy(pol)
    assert snap["enabled"] is True
    assert "owner" in snap["roles"]


def test_owner_can_grant_role_and_it_persists(tmp_path):
    eng = _engine(tmp_path)
    res = admin.grant_role(tmp_path, "tg:new", "member", OWNER, eng)
    assert res["success"] is True
    reloaded = load_policy(home=tmp_path)
    assert "member" in reloaded.roles_for_identity("tg:new")
    assert len(eng.audit.query(event_type="privileged_mutation")) >= 1


def test_non_owner_cannot_grant_role(tmp_path):
    eng = _engine(tmp_path)
    with pytest.raises(Exception):
        admin.grant_role(tmp_path, "tg:new", "member", MEMBER, eng)
    # nothing was written
    reloaded = load_policy(home=tmp_path)
    assert reloaded.roles_for_identity("tg:new") == ["guest"]
    assert len(eng.audit.query(decision="deny")) >= 1


def test_owner_can_revoke_role(tmp_path):
    eng = _engine(tmp_path)
    admin.grant_role(tmp_path, "tg:x", "admin", OWNER, eng)
    admin.grant_role(tmp_path, "tg:x", "member", OWNER, eng)
    admin.revoke_role(tmp_path, "tg:x", "admin", OWNER, eng)
    roles = load_policy(home=tmp_path).roles_for_identity("tg:x")
    assert "member" in roles and "admin" not in roles


def test_non_owner_cannot_revoke(tmp_path):
    eng = _engine(tmp_path)
    admin.grant_role(tmp_path, "tg:x", "admin", OWNER, eng)
    with pytest.raises(Exception):
        admin.revoke_role(tmp_path, "tg:x", "admin", MEMBER, eng)


def test_audit_list_filtering(tmp_path):
    audit = AuditLog(path=Path(tmp_path) / "audit" / "permissions.jsonl")
    audit.record_decision(MEMBER, "skill.create", "deny")
    audit.record_decision(OWNER, "skill.view", "allow")
    audit.record_privileged_mutation(OWNER, "skill.create", resource="skill:x")
    assert len(admin.audit_list(tmp_path, decision="deny")) == 1
    assert len(admin.audit_list(tmp_path, decision="allow")) == 1
    assert len(admin.audit_list(tmp_path, event_type="privileged_mutation")) == 1
    assert len(admin.audit_list(tmp_path)) == 3


def test_migrate_user_profile_copies_legacy_to_owner(tmp_path):
    mem = Path(tmp_path) / "memories"
    mem.mkdir(parents=True)
    (mem / "USER.md").write_text("owner likes tea", encoding="utf-8")
    res = admin.migrate_user_profile(tmp_path, owner_id="local:owner")
    assert res["success"] is True
    dest = mem / "users" / "local_owner" / "USER.md"
    assert dest.exists()
    assert "owner likes tea" in dest.read_text(encoding="utf-8")
    # legacy preserved so single-user CLI (enforcement off) stays compatible
    assert (mem / "USER.md").exists()


def test_migrate_is_idempotent(tmp_path):
    mem = Path(tmp_path) / "memories"
    mem.mkdir(parents=True)
    (mem / "USER.md").write_text("prefs", encoding="utf-8")
    assert admin.migrate_user_profile(tmp_path, owner_id="local:owner")["success"] is True
    # second run does not clobber
    assert admin.migrate_user_profile(tmp_path, owner_id="local:owner")["success"] is False


def test_migrate_without_legacy_is_noop(tmp_path):
    assert admin.migrate_user_profile(tmp_path, owner_id="local:owner")["success"] is False


def test_set_enabled_persists(tmp_path):
    eng = _engine(tmp_path, enabled=False)
    admin.set_enabled(tmp_path, True, OWNER, eng)
    assert load_policy(home=tmp_path).enabled is True
    admin.set_enabled(tmp_path, False, OWNER, eng)
    assert load_policy(home=tmp_path).enabled is False
