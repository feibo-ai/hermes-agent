"""Admin operations for the permission system (TEA-92, Phase 5).

Pure-ish functions backing the ``hermes permissions`` / ``hermes audit`` /
``hermes memory migrate-user-profile`` CLI surfaces. Mutations require the
acting identity to hold ``manage.roles`` (owner-only by default) and are
written to ``<home>/permissions.yaml`` + recorded in the audit log.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

import yaml

from .audit import AuditLog
from .engine import PermissionDenied, PermissionEngine
from .identity import Identity
from .memory_paths import sanitize_component
from .policy import Policy

PERMISSIONS_FILENAME = "permissions.yaml"


def _permissions_file(home) -> Path:
    return Path(home) / PERMISSIONS_FILENAME


def _read_raw(home) -> dict:
    p = _permissions_file(home)
    if p.exists():
        try:
            loaded = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            return {}
    return {}


def _write_raw(home, raw: dict) -> None:
    p = _permissions_file(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(raw, sort_keys=True, allow_unicode=True), encoding="utf-8")
    os.replace(tmp, p)


def _entry_roles(entry) -> List[str]:
    if isinstance(entry, dict):
        if "roles" in entry:
            return list(entry["roles"] or [])
        if "role" in entry:
            return [entry["role"]]
        return []
    if isinstance(entry, (list, tuple)):
        return list(entry)
    if entry:
        return [entry]
    return []


def _require_manage_roles(actor: Identity, engine: PermissionEngine, resource: str) -> None:
    if not engine.policy.enabled:
        return
    if engine.can(actor, "manage.roles", audit=False):
        return
    if engine.audit is not None:
        engine.audit.record_decision(actor, "manage.roles", "deny", resource=resource,
                                     reason="privileged admin operation")
    raise PermissionDenied(actor.id, "manage.roles", resource)


# --- read-only views --------------------------------------------------------

def list_users(policy: Policy) -> List[dict]:
    return [{"identity": uid, "roles": list(roles)} for uid, roles in sorted(policy.users.items())]


def list_roles(policy: Policy) -> List[dict]:
    return [{"role": r, "capabilities": list(caps)} for r, caps in sorted(policy.roles.items())]


def show_policy(policy: Policy) -> dict:
    return {
        "enabled": policy.enabled,
        "default_role": policy.default_role,
        "owner_id": policy.owner_id,
        "roles": {r: list(c) for r, c in policy.roles.items()},
        "users": {u: list(rs) for u, rs in policy.users.items()},
    }


# --- mutations --------------------------------------------------------------

def grant_role(home, identity_id: str, role: str, actor: Identity, engine: PermissionEngine) -> dict:
    _require_manage_roles(actor, engine, f"user:{identity_id}")
    raw = _read_raw(home)
    raw.setdefault("enabled", engine.policy.enabled)
    users = raw.setdefault("users", {})
    roles = _entry_roles(users.get(identity_id))
    if role not in roles:
        roles.append(role)
    users[identity_id] = {"roles": roles}
    _write_raw(home, raw)
    if engine.audit is not None:
        engine.audit.record_privileged_mutation(actor, "manage.roles.grant",
                                                resource=f"user:{identity_id}",
                                                metadata={"role": role})
    return {"success": True, "identity": identity_id, "roles": roles}


def revoke_role(home, identity_id: str, role: str, actor: Identity, engine: PermissionEngine) -> dict:
    _require_manage_roles(actor, engine, f"user:{identity_id}")
    raw = _read_raw(home)
    raw.setdefault("enabled", engine.policy.enabled)
    users = raw.setdefault("users", {})
    roles = [r for r in _entry_roles(users.get(identity_id)) if r != role]
    users[identity_id] = {"roles": roles}
    _write_raw(home, raw)
    if engine.audit is not None:
        engine.audit.record_privileged_mutation(actor, "manage.roles.revoke",
                                                resource=f"user:{identity_id}",
                                                metadata={"role": role})
    return {"success": True, "identity": identity_id, "roles": roles}


def set_enabled(home, enabled: bool, actor: Identity, engine: PermissionEngine) -> dict:
    _require_manage_roles(actor, engine, "policy:enabled")
    raw = _read_raw(home)
    raw["enabled"] = bool(enabled)
    _write_raw(home, raw)
    if engine.audit is not None:
        engine.audit.record_privileged_mutation(actor, "manage.policy.enabled",
                                                resource="policy", metadata={"enabled": bool(enabled)})
    return {"success": True, "enabled": bool(enabled)}


# --- audit ------------------------------------------------------------------

def audit_list(home, decision: Optional[str] = None, event_type: Optional[str] = None,
               identity_id: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    log = AuditLog(path=Path(home) / "audit" / "permissions.jsonl")
    return [e.to_dict() for e in log.query(decision=decision, event_type=event_type,
                                           identity_id=identity_id, limit=limit)]


# --- migration --------------------------------------------------------------

def migrate_user_profile(home, owner_id: str = "local:owner") -> dict:
    """Copy the legacy shared ``memories/USER.md`` into the owner's per-user
    profile. Non-destructive (legacy file is kept as a backup) and idempotent."""
    mem = Path(home) / "memories"
    legacy = mem / "USER.md"
    if not legacy.exists():
        return {"success": False, "message": "No legacy USER.md to migrate."}
    dest = mem / "users" / sanitize_component(owner_id) / "USER.md"
    if dest.exists():
        return {"success": False, "message": f"Destination already exists: {dest}"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, dest)
    return {"success": True, "from": str(legacy), "to": str(dest)}
