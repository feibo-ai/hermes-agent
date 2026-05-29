"""Phase 1 (TEA-89) — permission engine unit tests.

Covers the acceptance criteria: owner/admin/member/guest behaviour,
wildcard capabilities, deny cases, default-local-owner, and that the
engine is a no-op when enforcement is disabled (single-user compat).
"""

import pytest

from agent.permissions import (
    AuditLog,
    Identity,
    PermissionDenied,
    PermissionEngine,
    Policy,
    load_policy,
)


def _enabled_engine(audit=None):
    """Engine backed by the default roles, with enforcement turned on."""
    pol = load_policy(config={"permissions": {"enabled": True, "users": {
        "local:owner": {"roles": ["owner"]},
        "tg:admin": {"roles": ["admin"]},
        "tg:member": {"roles": ["member"]},
        "tg:guest": {"roles": ["guest"]},
    }}})
    return PermissionEngine(pol, audit=audit)


def _ident(idid, role):
    return Identity(id=idid, roles=(role,))


# --- role coverage ----------------------------------------------------------

def test_owner_can_do_everything():
    eng = _enabled_engine()
    owner = _ident("local:owner", "owner")
    for cap in ("skill.create", "tool.approve.dangerous", "manage.users",
                "manage.roles", "memory.write.any", "anything.custom"):
        assert eng.can(owner, cap), cap


def test_admin_capabilities():
    eng = _enabled_engine()
    admin = _ident("tg:admin", "admin")
    assert eng.can(admin, "skill.create")          # via skill.*
    assert eng.can(admin, "skill.approve")
    assert eng.can(admin, "tool.use.shell")        # via tool.use.*
    assert eng.can(admin, "tool.approve.dangerous")
    assert eng.can(admin, "memory.write.any")      # admin manages others
    assert eng.can(admin, "read.audit")
    # admin is NOT owner: cannot manage users/roles by default (Phase 5)
    assert not eng.can(admin, "manage.users")
    assert not eng.can(admin, "manage.roles")


def test_member_capabilities():
    eng = _enabled_engine()
    member = _ident("tg:member", "member")
    assert eng.can(member, "skill.view")
    assert eng.can(member, "skill.use")
    assert eng.can(member, "tool.use.safe")
    assert eng.can(member, "memory.read.self")
    assert eng.can(member, "memory.write.self")
    # denied: mutation + privileged + other-user memory
    assert not eng.can(member, "skill.create")
    assert not eng.can(member, "skill.update")
    assert not eng.can(member, "skill.install")
    assert not eng.can(member, "tool.use.shell")
    assert not eng.can(member, "tool.approve.dangerous")
    assert not eng.can(member, "memory.read.any")
    assert not eng.can(member, "manage.users")


def test_mentor_role_can_author_and_approve_skills_only():
    # A "skill mentor": teaches/maintains skills (create/update/approve) and
    # uses the agent like a member, but has no host tools / user admin.
    pol = load_policy(config={"permissions": {"enabled": True, "users": {
        "tg:mentor": {"roles": ["mentor"]},
    }}})
    eng = PermissionEngine(pol)
    mentor = Identity(id="tg:mentor", roles=("mentor",))
    # skill authoring + approval
    for cap in ("skill.view", "skill.use", "skill.create", "skill.update", "skill.approve"):
        assert eng.can(mentor, cap), cap
    # member-level base so they can actually use the agent
    assert eng.can(mentor, "tool.use.safe")
    assert eng.can(mentor, "memory.read.self")
    assert eng.can(mentor, "memory.write.self")
    # a workspace-confined shell (sandboxed), but NOT full host shell
    assert eng.can(mentor, "tool.use.shell.workspace")
    assert not eng.can(mentor, "tool.use.shell")
    # but NOT destructive skill ops, other users' memory, or admin
    assert not eng.can(mentor, "skill.delete")
    assert not eng.can(mentor, "skill.install")
    assert not eng.can(mentor, "memory.read.any")
    assert not eng.can(mentor, "manage.users")
    assert not eng.can(mentor, "manage.roles")


def test_guest_capabilities():
    eng = _enabled_engine()
    guest = _ident("tg:guest", "guest")
    assert eng.can(guest, "skill.view")
    assert not eng.can(guest, "skill.use")
    assert not eng.can(guest, "tool.use.safe")
    assert not eng.can(guest, "memory.write.self")


# --- deny + require ---------------------------------------------------------

def test_require_raises_on_denied_capability():
    eng = _enabled_engine()
    member = _ident("tg:member", "member")
    with pytest.raises(PermissionDenied) as exc:
        eng.require(member, "skill.create")
    assert exc.value.capability == "skill.create"
    assert exc.value.identity_id == "tg:member"


def test_require_returns_none_when_allowed():
    eng = _enabled_engine()
    owner = _ident("local:owner", "owner")
    assert eng.require(owner, "skill.create") is None


# --- enforcement disabled = backward compatible -----------------------------

def test_disabled_policy_allows_everything_and_does_not_audit():
    audit = AuditLog()  # in-memory
    pol = load_policy(config={"permissions": {"enabled": False}})
    eng = PermissionEngine(pol, audit=audit)
    guest = _ident("tg:guest", "guest")
    # everything allowed when enforcement is off (single-user CLI default)
    assert eng.can(guest, "manage.users")
    assert eng.can(guest, "skill.delete")
    eng.require(guest, "tool.approve.dangerous")  # must not raise
    assert audit.query() == []  # no noise when disabled


# --- identity resolution ----------------------------------------------------

def test_resolve_cli_default_is_owner():
    eng = _enabled_engine()
    ident = eng.resolve(platform="cli")
    assert ident.id == "local:owner"
    assert "owner" in ident.roles
    assert eng.can(ident, "manage.users")


def test_resolve_known_gateway_user_gets_configured_roles():
    eng = _enabled_engine()
    ident = eng.resolve(platform="tg", user_id="member")
    assert ident.id == "tg:member"
    assert ident.roles == ("member",)


def test_resolve_unknown_user_gets_default_role():
    pol = load_policy(config={"permissions": {"enabled": True, "default_role": "guest"}})
    eng = PermissionEngine(pol)
    ident = eng.resolve(platform="tg", user_id="stranger")
    assert ident.roles == ("guest",)
    assert eng.can(ident, "skill.view")
    assert not eng.can(ident, "skill.use")


# --- audit shape ------------------------------------------------------------

def test_can_records_allow_and_deny_decisions():
    audit = AuditLog()
    eng = _enabled_engine(audit=audit)
    member = _ident("tg:member", "member")
    eng.can(member, "skill.view")     # allow
    eng.can(member, "skill.create")   # deny
    events = audit.query()
    assert len(events) == 2
    allow = audit.query(decision="allow")
    deny = audit.query(decision="deny")
    assert len(allow) == 1 and len(deny) == 1
    e = deny[0]
    # audit event shape
    assert e.identity_id == "tg:member"
    assert e.capability == "skill.create"
    assert e.decision == "deny"
    assert e.event_type == "decision"
    assert e.timestamp  # ISO timestamp present
    d = e.to_dict()
    assert set(["timestamp", "event_type", "decision", "identity_id",
                "capability", "resource", "reason"]).issubset(d.keys())


def test_require_denial_is_audited():
    audit = AuditLog()
    eng = _enabled_engine(audit=audit)
    member = _ident("tg:member", "member")
    with pytest.raises(PermissionDenied):
        eng.require(member, "manage.users")
    deny = audit.query(decision="deny")
    assert len(deny) == 1
    assert deny[0].capability == "manage.users"
