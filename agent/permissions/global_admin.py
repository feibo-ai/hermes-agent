"""Global super-admin registry for cross-profile management (Epic TEA-88).

Lives at a fixed path OUTSIDE any profile home (``~/.config/hermes/
global-permissions.yaml``, overridable via ``HERMES_GLOBAL_PERMISSIONS``), so a
profile can never escalate itself by editing its own ``permissions.yaml``. It is
read-only from the agent's perspective — only host operators edit it.

Format::

    super_admins:
      "local:owner":   { profiles: ["*"] }            # may manage every profile
      "feishu:ou_X":   { profiles: ["teamA", "teamB"] }  # scoped to named profiles

A super-admin may manage a target profile only if their entry lists ``"*"`` or
the target's name. Missing/empty registry => nobody is a super-admin
(fail-closed).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Union

import yaml


def global_registry_path() -> Path:
    override = os.environ.get("HERMES_GLOBAL_PERMISSIONS", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base) if base else (Path.home() / ".config")
    return root / "hermes" / "global-permissions.yaml"


def load_global_policy(path: Optional[Union[Path, str]] = None) -> dict:
    """Load the global registry. Returns ``{}`` (no super-admins) on any error."""
    p = Path(path) if path is not None else global_registry_path()
    if not p.exists():
        return {}
    try:
        loaded = yaml.safe_load(p.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _norm(name: str) -> str:
    """Normalize a profile name the same way Hermes does (case-insensitive),
    so a registry entry 'teamA' matches a resolved profile dir 'teama'."""
    try:
        from hermes_cli.profiles import normalize_profile_name
        return normalize_profile_name(name)
    except Exception:
        return (name or "").strip().lower()


def _managed_profiles(policy: dict, actor_id: str) -> List[str]:
    entry = (policy.get("super_admins") or {}).get(actor_id)
    if entry is None:
        return []
    if isinstance(entry, dict):
        scope = entry.get("profiles", [])
    elif isinstance(entry, (list, tuple)):
        scope = list(entry)
    else:
        scope = [scope] if (scope := entry) else []
    return [str(s) for s in (scope or [])]


def is_super_admin(actor_id: str, path: Optional[Union[Path, str]] = None) -> bool:
    return bool(_managed_profiles(load_global_policy(path), actor_id))


def can_manage_profile(
    actor_id: str,
    target_profile: str,
    path: Optional[Union[Path, str]] = None,
) -> bool:
    """True if ``actor_id`` is a super-admin authorized for ``target_profile``.
    Fail-closed: unknown actor / missing registry / out-of-scope => False."""
    scope = _managed_profiles(load_global_policy(path), actor_id)
    if not scope:
        return False
    if "*" in scope:
        return True
    tnorm = _norm(target_profile)
    return any(_norm(s) == tnorm for s in scope)
