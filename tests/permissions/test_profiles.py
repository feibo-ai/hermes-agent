"""Profile addressing adapter (Epic TEA-88)."""

from pathlib import Path

from agent.permissions import profiles


def test_list_profiles_returns_name_home_dicts():
    out = profiles.list_profiles()
    assert isinstance(out, list)
    for p in out:
        assert "name" in p and "home" in p


def test_resolve_unknown_profile_is_none():
    assert profiles.resolve_profile_home("definitely-not-a-real-profile-xyz") is None


def test_profile_exists_false_for_unknown():
    assert profiles.profile_exists("definitely-not-a-real-profile-xyz") is False


def test_current_profile_home_is_a_path():
    assert isinstance(profiles.current_profile_home(), Path)
