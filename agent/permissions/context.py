"""Process-wide engine + current-identity context.

These helpers let deep call sites (tool dispatch, skill management, memory
injection) reach the permission engine and the active identity without
threading them through every function signature.
"""

from __future__ import annotations

import contextvars
from pathlib import Path
from typing import Optional, Union

from .audit import AuditLog
from .engine import PermissionEngine
from .identity import Identity, default_local_identity
from .policy import load_policy

_current_identity: contextvars.ContextVar[Optional[Identity]] = contextvars.ContextVar(
    "hermes_current_identity", default=None
)

_process_engine: Optional[PermissionEngine] = None


def get_current_identity() -> Identity:
    ident = _current_identity.get()
    if ident is None:
        return default_local_identity()
    return ident


def set_current_identity(identity: Identity) -> contextvars.Token:
    return _current_identity.set(identity)


def reset_current_identity(token: contextvars.Token) -> None:
    _current_identity.reset(token)


def build_engine(
    config: Optional[dict] = None,
    home: Optional[Union[Path, str]] = None,
    audit_path: Optional[Union[Path, str]] = None,
) -> PermissionEngine:
    policy = load_policy(home=Path(home) if home else None, config=config)
    if audit_path is None and home is not None:
        audit_path = Path(home) / "audit" / "permissions.jsonl"
    audit = AuditLog(path=audit_path)
    return PermissionEngine(policy, audit=audit)


def set_engine(engine: PermissionEngine) -> None:
    global _process_engine
    _process_engine = engine


def _build_engine_from_live_config() -> PermissionEngine:
    """Best-effort engine built from the running Hermes config + home.

    Falls back to a disabled (permissive) engine on any error so that the
    permission layer can never prevent the agent from starting.
    """
    try:
        from hermes_cli.config import load_config_readonly
        from hermes_constants import get_hermes_home

        cfg = load_config_readonly()
        home = get_hermes_home()
        return build_engine(config=cfg, home=home)
    except Exception:
        return PermissionEngine(load_policy(), AuditLog())


def get_engine() -> PermissionEngine:
    global _process_engine
    if _process_engine is None:
        _process_engine = _build_engine_from_live_config()
    return _process_engine


def reset_engine() -> None:
    global _process_engine
    _process_engine = None
