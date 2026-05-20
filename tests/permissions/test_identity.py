"""Phase 1 (TEA-89) — identity model unit tests."""

from agent.permissions import (
    Identity,
    default_local_identity,
    make_identity_id,
)


def test_make_identity_id_combines_platform_and_user():
    assert make_identity_id("telegram", "123456") == "telegram:123456"
    assert make_identity_id("slack", "U123") == "slack:U123"


def test_default_local_identity_is_cli_owner():
    ident = default_local_identity()
    assert ident.platform == "cli"
    assert "owner" in ident.roles
    # default local identity must be stable so single-user CLI keeps working
    assert ident.id == "local:owner"


def test_identity_is_immutable_and_hashable():
    ident = Identity(id="local:owner", platform="cli", roles=("owner",))
    # frozen dataclass -> hashable, usable as dict key / set member
    {ident}
    assert hash(ident) == hash(Identity(id="local:owner", platform="cli", roles=("owner",)))


def test_identity_with_roles_returns_new_identity():
    base = Identity(id="telegram:1", platform="telegram")
    granted = base.with_roles(["member"])
    assert granted.roles == ("member",)
    # original is untouched
    assert base.roles == ()
    assert granted.id == base.id


def test_identity_defaults():
    ident = Identity(id="local:owner")
    assert ident.platform == "cli"
    assert ident.roles == ()
    assert ident.groups == ()
    assert ident.tenant_id is None
