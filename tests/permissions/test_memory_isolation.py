"""Phase 4 (TEA-93) — per-user USER.md isolation through the real MemoryStore."""

import pytest

from tools.memory_tool import MemoryStore


@pytest.fixture
def mem_root(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path)
    return tmp_path


def _store(identity_id, *, enabled=True, is_owner=False, chat_id=None):
    s = MemoryStore()
    s.bind_context(identity_id=identity_id, chat_id=chat_id, enabled=enabled, is_owner=is_owner)
    s.load_from_disk()
    return s


def test_two_gateway_users_get_isolated_user_profiles(mem_root):
    a = _store("telegram:A")
    b = _store("telegram:B")
    a.add("user", "I prefer Python")
    b.add("user", "I prefer Rust")
    a.load_from_disk()
    b.load_from_disk()
    assert a.user_entries == ["I prefer Python"]
    assert b.user_entries == ["I prefer Rust"]
    # distinct files on disk
    assert (mem_root / "users" / "telegram_A" / "USER.md").exists()
    assert (mem_root / "users" / "telegram_B" / "USER.md").exists()


def test_user_profile_snapshots_differ_between_users(mem_root):
    a = _store("telegram:A")
    a.add("user", "call me Alice")
    b = _store("telegram:B")
    b.add("user", "call me Bob")
    a.load_from_disk()
    b.load_from_disk()
    snap_a = a.format_for_system_prompt("user")
    snap_b = b.format_for_system_prompt("user")
    assert "Alice" in snap_a and "Bob" not in snap_a
    assert "Bob" in snap_b and "Alice" not in snap_b


def test_global_memory_is_shared_across_users(mem_root):
    a = _store("telegram:A")
    a.add("memory", "the company is called Feibo")
    b = _store("telegram:B")
    assert any("Feibo" in e for e in b.memory_entries)


def test_disabled_uses_legacy_shared_user_file(mem_root):
    s = _store("telegram:A", enabled=False)
    s.add("user", "shared preference")
    assert (mem_root / "USER.md").exists()
    assert not (mem_root / "users").exists()


def test_owner_falls_back_to_legacy_user_md(mem_root):
    (mem_root / "USER.md").write_text("legacy owner preference", encoding="utf-8")
    s = _store("local:owner", enabled=True, is_owner=True)
    assert s.user_entries == ["legacy owner preference"]


def test_member_does_not_inherit_owner_legacy_profile(mem_root):
    (mem_root / "USER.md").write_text("legacy owner preference", encoding="utf-8")
    s = _store("telegram:M", enabled=True, is_owner=False)
    assert s.user_entries == []  # isolation: members never see the owner's legacy profile


def test_chat_md_injected_when_present(mem_root):
    chat_dir = mem_root / "chats" / "telegram_c1"
    chat_dir.mkdir(parents=True)
    (chat_dir / "CHAT.md").write_text("this team uses metric units", encoding="utf-8")
    s = _store("telegram:A", chat_id="telegram:c1")
    block = s.format_for_system_prompt("chat")
    assert block is not None and "metric units" in block
