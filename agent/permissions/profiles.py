"""Profile addressing for cross-profile central management (Epic TEA-88).

Thin adapter over Hermes' existing profile system (``hermes_cli.profiles``):
profiles live under ``~/.hermes/profiles/<name>/`` (the ``default`` profile is
``~/.hermes`` itself). Cross-profile permission management resolves a target
profile *name* to its home directory so the admin functions can write that
profile's ``permissions.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def list_profiles() -> List[dict]:
    """Return ``[{"name", "home"}]`` for every profile on this machine."""
    try:
        from hermes_cli.profiles import list_profiles as _lp
        return [{"name": p.name, "home": str(p.path)} for p in _lp()]
    except Exception:
        return []


def profile_exists(name: str) -> bool:
    try:
        from hermes_cli.profiles import normalize_profile_name, profile_exists as _pe
        return _pe(normalize_profile_name(name))
    except Exception:
        return False


def resolve_profile_home(name: str) -> Optional[Path]:
    """Resolve a profile name to its home directory, or None if it doesn't exist."""
    try:
        from hermes_cli.profiles import (
            get_profile_dir,
            normalize_profile_name,
            profile_exists as _pe,
        )
        canon = normalize_profile_name(name)
        if not _pe(canon):
            return None
        return Path(get_profile_dir(canon))
    except Exception:
        return None


def current_profile_home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def current_profile_name() -> str:
    """Name of the profile this process is running as ('' if not a known profile)."""
    try:
        cur = current_profile_home().resolve()
    except Exception:
        return ""
    for p in list_profiles():
        try:
            if Path(p["home"]).resolve() == cur:
                return p["name"]
        except Exception:
            continue
    return ""
