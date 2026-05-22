"""Global super-admin registry for cross-profile management (Epic TEA-88)."""

import textwrap

from agent.permissions import global_admin as ga


def _write(tmp_path, body):
    p = tmp_path / "global-permissions.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_wildcard_super_admin_manages_any_profile(tmp_path):
    p = _write(tmp_path, """
        super_admins:
          "local:owner": { profiles: ["*"] }
    """)
    assert ga.can_manage_profile("local:owner", "teamA", path=p)
    assert ga.can_manage_profile("local:owner", "teamB", path=p)
    assert ga.is_super_admin("local:owner", path=p)


def test_scoped_super_admin_only_manages_listed_profiles(tmp_path):
    p = _write(tmp_path, """
        super_admins:
          "feishu:ou_X": { profiles: ["teamA"] }
    """)
    assert ga.can_manage_profile("feishu:ou_X", "teamA", path=p)
    assert not ga.can_manage_profile("feishu:ou_X", "teamB", path=p)


def test_unknown_actor_is_not_super_admin(tmp_path):
    p = _write(tmp_path, """
        super_admins:
          "local:owner": { profiles: ["*"] }
    """)
    assert not ga.can_manage_profile("telegram:stranger", "teamA", path=p)
    assert not ga.is_super_admin("telegram:stranger", path=p)


def test_profile_match_is_case_insensitive(tmp_path):
    # registry lists 'teamA'; resolved profile dirs are normalized to 'teama'
    p = _write(tmp_path, """
        super_admins:
          "local:owner": { profiles: ["teamA"] }
    """)
    assert ga.can_manage_profile("local:owner", "teamA", path=p)
    assert ga.can_manage_profile("local:owner", "teama", path=p)


def test_missing_registry_is_fail_closed(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert ga.load_global_policy(path=missing) == {}
    assert ga.can_manage_profile("local:owner", "teamA", path=missing) is False
