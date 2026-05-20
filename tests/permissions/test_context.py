"""Phase 1 (TEA-89) — process engine + current-identity context plumbing.

The integration phases (tool dispatch, skills, memory) need to reach the
permission engine and "who is acting right now" from deep call sites without
threading parameters everywhere, mirroring how approval.py uses a contextvar
for the session key.
"""

from agent.permissions import (
    LOCAL_OWNER_ID,
    Identity,
    PermissionEngine,
    build_engine,
    get_current_identity,
    get_engine,
    reset_engine,
    set_current_identity,
    set_engine,
)


def test_default_current_identity_is_local_owner():
    ident = get_current_identity()
    assert ident.id == LOCAL_OWNER_ID
    assert "owner" in ident.roles


def test_set_and_reset_current_identity():
    token = set_current_identity(Identity(id="tg:1", platform="tg", roles=("member",)))
    try:
        assert get_current_identity().id == "tg:1"
    finally:
        from agent.permissions import reset_current_identity
        reset_current_identity(token)
    assert get_current_identity().id == LOCAL_OWNER_ID


def test_build_engine_from_config_enables_enforcement():
    eng = build_engine(config={"permissions": {"enabled": True}})
    assert isinstance(eng, PermissionEngine)
    assert eng.policy.enabled is True


def test_build_engine_points_audit_log_under_home(tmp_path):
    eng = build_engine(home=tmp_path, config={"permissions": {"enabled": True}})
    assert eng.audit is not None
    assert eng.audit.path == tmp_path / "audit" / "permissions.jsonl"


def test_get_engine_default_is_permissive():
    reset_engine()
    try:
        eng = get_engine()
        # default process engine has enforcement OFF -> allows everything
        anyone = Identity(id="tg:guest", roles=("guest",))
        assert eng.can(anyone, "manage.users") is True
    finally:
        reset_engine()


def test_set_engine_roundtrip():
    custom = build_engine(config={"permissions": {"enabled": True}})
    set_engine(custom)
    try:
        assert get_engine() is custom
    finally:
        reset_engine()
