"""Layered, per-user memory path resolution + profile ACL (TEA-93).

Layout under the memories root (``~/.hermes/memories``)::

    MEMORY.md                      # global, shared (legacy location)
    USER.md                        # legacy single-user profile (enforcement off)
    users/<identity-id>/USER.md    # per-user profile (enforcement on)
    chats/<platform-chat-id>/CHAT.md

When enforcement is disabled the user profile stays at the legacy shared
``USER.md`` so existing single-user installs are byte-for-byte unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .engine import PermissionEngine
from .identity import Identity

_UNSAFE = re.compile(r"[^A-Za-z0-9_.@-]")


def sanitize_component(component: str) -> str:
    """Make an identity/chat id safe to use as a single path component."""
    return _UNSAFE.sub("_", component or "")


def legacy_user_path(mem_root: Path) -> Path:
    return Path(mem_root) / "USER.md"


def global_memory_path(mem_root: Path) -> Path:
    return Path(mem_root) / "MEMORY.md"


def user_md_path(mem_root: Path, identity_id: Optional[str], enabled: bool) -> Path:
    if not enabled or not identity_id:
        return legacy_user_path(mem_root)
    return Path(mem_root) / "users" / sanitize_component(identity_id) / "USER.md"


def chat_md_path(mem_root: Path, chat_id: Optional[str]) -> Optional[Path]:
    if not chat_id:
        return None
    return Path(mem_root) / "chats" / sanitize_component(chat_id) / "CHAT.md"


def can_read_profile(engine: PermissionEngine, identity: Identity, target_identity_id: str) -> bool:
    if not engine.policy.enabled:
        return True
    if identity.id == target_identity_id:
        return engine.can(identity, "memory.read.self", audit=False)
    return engine.can(identity, "memory.read.any", audit=False)


def can_write_profile(engine: PermissionEngine, identity: Identity, target_identity_id: str) -> bool:
    if not engine.policy.enabled:
        return True
    if identity.id == target_identity_id:
        return engine.can(identity, "memory.write.self", audit=False)
    return engine.can(identity, "memory.write.any", audit=False)
