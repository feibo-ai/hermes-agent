"""Process-wide engine + current-identity context.

These helpers let deep call sites (tool dispatch, skill management, memory
injection) reach the permission engine and the active identity without
threading them through every function signature.
"""

from __future__ import annotations

import contextvars
import os
import time
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
# True when the engine was injected via set_engine() (e.g. tests) — such an
# engine is authoritative and is never auto-refreshed from disk.
_engine_explicit: bool = False
# Fingerprint of the policy inputs (permissions.yaml + config) the lazily-built
# engine was derived from, so we can rebuild when an operator edits the policy
# (e.g. `hermes permissions grant`) without restarting a running gateway.
_engine_fingerprint: Optional[tuple] = None
_engine_last_check: float = 0.0
# Stat the policy files at most this often to bound the per-call overhead.
_ENGINE_RECHECK_INTERVAL: float = 2.0


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
    global _process_engine, _engine_explicit
    _process_engine = engine
    _engine_explicit = True


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


def _stat_fp(path) -> tuple:
    try:
        st = os.stat(path)
        return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(path), 0, 0)


def _policy_fingerprint() -> Optional[tuple]:
    """Fingerprint the policy inputs so we can detect operator edits."""
    try:
        from hermes_constants import get_hermes_home

        parts = [_stat_fp(Path(get_hermes_home()) / "permissions.yaml")]
        try:
            from hermes_cli.config import get_config_path

            parts.append(_stat_fp(get_config_path()))
        except Exception:
            pass
        return tuple(parts)
    except Exception:
        return None


def get_engine() -> PermissionEngine:
    """Return the process permission engine, rebuilding it when the policy
    files change on disk (so role/policy edits apply to a running gateway
    without a restart). An engine injected via set_engine() is never refreshed."""
    global _process_engine, _engine_fingerprint, _engine_last_check
    if _engine_explicit:
        return _process_engine
    if _process_engine is None:
        _process_engine = _build_engine_from_live_config()
        _engine_fingerprint = _policy_fingerprint()
        _engine_last_check = time.monotonic()
        return _process_engine
    now = time.monotonic()
    if now - _engine_last_check >= _ENGINE_RECHECK_INTERVAL:
        _engine_last_check = now
        fp = _policy_fingerprint()
        if fp != _engine_fingerprint:
            _process_engine = _build_engine_from_live_config()
            _engine_fingerprint = fp
    return _process_engine


def reset_engine() -> None:
    global _process_engine, _engine_explicit, _engine_fingerprint, _engine_last_check
    _process_engine = None
    _engine_explicit = False
    _engine_fingerprint = None
    _engine_last_check = 0.0
