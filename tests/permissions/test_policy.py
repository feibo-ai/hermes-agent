"""Phase 1 (TEA-89) — policy loading and capability matching unit tests."""

import textwrap

from agent.permissions import Policy, capability_matches, load_policy


# --- wildcard capability matching ------------------------------------------

def test_exact_capability_matches():
    assert capability_matches("skill.view", "skill.view")
    assert not capability_matches("skill.view", "skill.create")


def test_star_matches_everything():
    assert capability_matches("*", "skill.create")
    assert capability_matches("*", "tool.approve.dangerous")
    assert capability_matches("*", "anything.at.all")


def test_prefix_wildcard_matches_children():
    assert capability_matches("skill.*", "skill.view")
    assert capability_matches("skill.*", "skill.create")
    assert capability_matches("tool.use.*", "tool.use.shell")
    assert capability_matches("tool.use.*", "tool.use.filesystem")


def test_prefix_wildcard_matches_bare_prefix():
    # "skill.*" should also cover the bare "skill" node
    assert capability_matches("skill.*", "skill")


def test_prefix_wildcard_respects_dot_boundary():
    # "tool.use.*" must not leak into a sibling namespace
    assert not capability_matches("tool.use.*", "tool.approve.dangerous")
    # must not match an unrelated prefix-sharing string
    assert not capability_matches("skill.*", "skillset.view")


# --- default roles ----------------------------------------------------------

def test_default_policy_has_four_roles():
    pol = load_policy()
    for role in ("owner", "admin", "member", "guest"):
        assert role in pol.roles, f"missing default role {role}"


def test_owner_role_has_global_wildcard():
    pol = load_policy()
    assert "*" in pol.roles["owner"]


def test_member_role_cannot_mutate_skills_by_default():
    pol = load_policy()
    caps = set(pol.roles["member"])
    assert "skill.use" in caps
    assert "skill.view" in caps
    # no skill mutation capabilities for members
    for forbidden in ("skill.create", "skill.update", "skill.delete", "skill.install", "skill.*"):
        assert forbidden not in caps


def test_manage_roles_is_owner_only_by_default():
    pol = load_policy()
    # non-owner roles must not be able to manage users/roles (Phase 5 acceptance)
    for role in ("admin", "member", "guest"):
        caps = set(pol.roles[role])
        assert "manage.users" not in caps
        assert "manage.roles" not in caps
        assert "*" not in caps


# --- identity -> roles -> capabilities -------------------------------------

def test_roles_for_identity_uses_configured_roles():
    pol = Policy(
        enabled=True,
        roles={"owner": ["*"], "member": ["skill.use"]},
        users={"telegram:1": ["member"]},
        default_role="guest",
        owner_id="local:owner",
    )
    assert pol.roles_for_identity("telegram:1") == ["member"]


def test_roles_for_identity_falls_back_to_default_role():
    pol = Policy(
        enabled=True,
        roles={"owner": ["*"], "guest": ["skill.view"]},
        users={},
        default_role="guest",
        owner_id="local:owner",
    )
    assert pol.roles_for_identity("telegram:unknown") == ["guest"]


def test_capabilities_for_roles_unions():
    pol = Policy(
        enabled=True,
        roles={"a": ["skill.view"], "b": ["tool.use.safe"]},
        users={},
        default_role="guest",
        owner_id="local:owner",
    )
    caps = pol.capabilities_for_roles(["a", "b"])
    assert caps == {"skill.view", "tool.use.safe"}


# --- loading behaviour ------------------------------------------------------

def test_load_policy_without_file_does_not_raise_and_is_disabled(tmp_path):
    # TEA-89 acceptance: CLI must start without a policy file present.
    pol = load_policy(home=tmp_path)
    assert pol.enabled is False  # no enforcement when nothing configured
    assert "owner" in pol.roles


def test_load_policy_from_config_section():
    cfg = {
        "permissions": {
            "enabled": True,
            "users": {"telegram:1": {"roles": ["member"]}},
        }
    }
    pol = load_policy(config=cfg)
    assert pol.enabled is True
    assert pol.roles_for_identity("telegram:1") == ["member"]


def test_load_policy_from_permissions_yaml_file(tmp_path):
    (tmp_path / "permissions.yaml").write_text(
        textwrap.dedent(
            """
            enabled: true
            roles:
              owner:
                capabilities: ["*"]
              member:
                capabilities: ["skill.use"]
            users:
              "slack:U1":
                roles: [member]
            """
        )
    )
    pol = load_policy(home=tmp_path)
    assert pol.enabled is True
    assert "skill.use" in pol.roles["member"]
    assert pol.roles_for_identity("slack:U1") == ["member"]


def test_explicit_config_overrides_enabled_flag():
    cfg = {"permissions": {"enabled": False, "users": {}}}
    pol = load_policy(config=cfg)
    assert pol.enabled is False
