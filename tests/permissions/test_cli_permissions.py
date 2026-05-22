"""Phase 5 (TEA-92) — `hermes permissions` / `audit` / `memory migrate`
CLI handlers exercised through hermes_cli.permissions_cli."""

import argparse

import pytest

from agent.permissions import reset_engine


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr("hermes_cli.permissions_cli.get_hermes_home", lambda: tmp_path)
    # start each test with a permissive (disabled) engine derived from config
    monkeypatch.setattr("hermes_cli.config.load_config_readonly", lambda: {})
    reset_engine()
    yield tmp_path
    reset_engine()


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_grant_then_users_list(home, capsys):
    from hermes_cli.permissions_cli import permissions_command

    permissions_command(_ns(permissions_command="grant", identity="telegram:42", role="member"))
    reset_engine()  # rebuild engine so it reads the freshly written permissions.yaml
    permissions_command(_ns(permissions_command="users"))
    out = capsys.readouterr().out
    assert "telegram:42" in out
    assert "member" in out
    # persisted to permissions.yaml
    assert (home / "permissions.yaml").exists()


def test_roles_list(home, capsys):
    from hermes_cli.permissions_cli import permissions_command

    permissions_command(_ns(permissions_command="roles"))
    out = capsys.readouterr().out
    assert "owner" in out and "member" in out and "guest" in out


def test_policy_show(home, capsys):
    from hermes_cli.permissions_cli import permissions_command

    permissions_command(_ns(permissions_command="policy"))
    out = capsys.readouterr().out
    assert '"enabled"' in out and '"roles"' in out


def test_enable_disable(home, capsys):
    from hermes_cli.permissions_cli import permissions_command
    from agent.permissions import load_policy

    permissions_command(_ns(permissions_command="enable"))
    assert load_policy(home=home).enabled is True
    permissions_command(_ns(permissions_command="disable"))
    assert load_policy(home=home).enabled is False


def test_revoke(home, capsys):
    from hermes_cli.permissions_cli import permissions_command
    from agent.permissions import load_policy

    permissions_command(_ns(permissions_command="grant", identity="tg:x", role="admin"))
    reset_engine()
    permissions_command(_ns(permissions_command="revoke", identity="tg:x", role="admin"))
    assert "admin" not in load_policy(home=home).roles_for_identity("tg:x")


def test_audit_list(home, capsys):
    from agent.permissions import AuditLog, Identity
    from hermes_cli.permissions_cli import audit_command

    # seed an audit log at the expected location
    log = AuditLog(path=home / "audit" / "permissions.jsonl")
    log.record_decision(Identity(id="tg:m", roles=("member",)), "skill.create", "deny")
    audit_command(_ns(decision="deny", privileged=False, limit=None))
    out = capsys.readouterr().out
    assert "skill.create" in out and "tg:m" in out


def test_migrate_user_profile_cli(home, capsys):
    from hermes_cli.permissions_cli import migrate_user_profile_command

    mem = home / "memories"
    mem.mkdir(parents=True)
    (mem / "USER.md").write_text("owner prefs", encoding="utf-8")
    migrate_user_profile_command(_ns(owner_id="local:owner"))
    out = capsys.readouterr().out
    assert "Migrated" in out
    assert (mem / "users" / "local_owner" / "USER.md").exists()
