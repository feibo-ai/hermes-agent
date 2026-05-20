"""Phase 4 (TEA-93) — layered memory path resolution + profile ACL."""

from pathlib import Path

from agent.permissions import Identity, PermissionEngine, load_policy
from agent.permissions.memory_paths import (
    can_read_profile,
    can_write_profile,
    chat_md_path,
    global_memory_path,
    legacy_user_path,
    sanitize_component,
    user_md_path,
)

ROOT = Path("/m")


def test_user_path_is_per_identity_when_enabled():
    assert user_md_path(ROOT, "telegram:123", True) == ROOT / "users" / "telegram_123" / "USER.md"


def test_user_path_is_legacy_when_disabled():
    # single-user CLI default: shared USER.md at the legacy location
    assert user_md_path(ROOT, "telegram:123", False) == ROOT / "USER.md"
    assert user_md_path(ROOT, "telegram:123", False) == legacy_user_path(ROOT)


def test_user_path_is_legacy_when_no_identity():
    assert user_md_path(ROOT, None, True) == ROOT / "USER.md"


def test_two_users_get_distinct_user_paths():
    assert user_md_path(ROOT, "tg:a", True) != user_md_path(ROOT, "tg:b", True)


def test_global_memory_path_is_shared():
    assert global_memory_path(ROOT) == ROOT / "MEMORY.md"


def test_chat_path():
    assert chat_md_path(ROOT, "telegram:c1") == ROOT / "chats" / "telegram_c1" / "CHAT.md"
    assert chat_md_path(ROOT, None) is None


def test_sanitize_makes_filesystem_safe_component():
    assert sanitize_component("a:b/c") == "a_b_c"
    assert sanitize_component("telegram:123") == "telegram_123"


# --- profile ACL ------------------------------------------------------------

def _eng(enabled=True):
    return PermissionEngine(load_policy(config={"permissions": {"enabled": enabled, "users": {
        "tg:m": {"roles": ["member"]},
        "tg:ad": {"roles": ["admin"]},
    }}}))


def test_member_can_only_rw_own_profile():
    eng = _eng()
    m = eng.resolve("tg", "m")
    assert can_read_profile(eng, m, "tg:m") is True
    assert can_write_profile(eng, m, "tg:m") is True
    assert can_read_profile(eng, m, "tg:other") is False
    assert can_write_profile(eng, m, "tg:other") is False


def test_admin_can_rw_other_profiles():
    eng = _eng()
    a = eng.resolve("tg", "ad")
    assert can_read_profile(eng, a, "tg:other") is True
    assert can_write_profile(eng, a, "tg:other") is True


def test_disabled_allows_all_profile_access():
    eng = _eng(enabled=False)
    m = Identity(id="tg:m", roles=("member",))
    assert can_read_profile(eng, m, "tg:other") is True
    assert can_write_profile(eng, m, "tg:other") is True
