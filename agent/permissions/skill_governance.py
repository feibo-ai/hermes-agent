"""Skill lifecycle + approval governance (TEA-91).

Splits "using" a skill from "mutating" one. Skill-management *actions* map to
distinct capabilities (skill.create / skill.update / skill.delete /
skill.install / skill.approve), and every mutated skill moves through an
approval lifecycle::

    draft -> pending_review -> approved -> active -> disabled

Pre-existing / bundled skills have no governance record and are treated as
*approved* (trusted) so enabling enforcement doesn't hide the shipped skill
library. A skill only enters the lifecycle once it is created or edited
through ``skill_manage``; any content change knocks it back to
``pending_review`` until an approver re-approves it.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, Union

from .context import get_current_identity, get_engine
from .engine import PermissionEngine
from .identity import Identity


class SkillState(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ACTIVE = "active"
    DISABLED = "disabled"


USABLE_STATES = frozenset({SkillState.APPROVED, SkillState.ACTIVE})

_ACTION_CAPABILITY = {
    "create": "skill.create",
    "edit": "skill.update",
    "patch": "skill.update",
    "write_file": "skill.update",
    "remove_file": "skill.update",
    "delete": "skill.delete",
    "install": "skill.install",
    "sync": "skill.install",
    "approve": "skill.approve",
    "disable": "skill.update",
    "enable": "skill.approve",
}

_CONTENT_MUTATING = frozenset({"create", "edit", "patch", "write_file", "remove_file"})


def action_capability(action: str) -> str:
    return _ACTION_CAPABILITY.get(action, "skill.update")


def is_content_mutating(action: str) -> bool:
    return action in _CONTENT_MUTATING


def compute_content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SkillGovernance:
    def __init__(self, path: Optional[Union[Path, str]] = None):
        self.path = Path(path) if path else None
        self._data: dict = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8")) or {}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except Exception:
            pass

    def get(self, name: str) -> Optional[dict]:
        return self._data.get(name)

    def state(self, name: str) -> SkillState:
        rec = self._data.get(name)
        if not rec:
            # untracked (bundled / pre-existing) skills are trusted
            return SkillState.APPROVED
        try:
            return SkillState(rec.get("state", SkillState.APPROVED.value))
        except ValueError:
            return SkillState.APPROVED

    def is_usable(self, name: str) -> bool:
        return self.state(name) in USABLE_STATES

    def record_mutation(self, name: str, content_hash: str, by: str = "", action: str = "edit") -> SkillState:
        prev = self._data.get(name, {})
        self._data[name] = {
            "state": SkillState.PENDING_REVIEW.value,
            "content_hash": content_hash,
            "updated_by": by,
            "updated_at": _now(),
            "last_action": action,
            "approved_by": prev.get("approved_by"),
            "approved_at": prev.get("approved_at"),
        }
        self._save()
        return SkillState.PENDING_REVIEW

    def approve(self, name: str, by: str = "", content_hash: Optional[str] = None) -> None:
        rec = dict(self._data.get(name, {}))
        if content_hash is None:
            content_hash = rec.get("content_hash")
        rec.update({
            "state": SkillState.APPROVED.value,
            "content_hash": content_hash,
            "approved_by": by,
            "approved_at": _now(),
        })
        self._data[name] = rec
        self._save()

    def disable(self, name: str, by: str = "") -> None:
        rec = dict(self._data.get(name, {}))
        rec.update({"state": SkillState.DISABLED.value, "disabled_by": by})
        self._data[name] = rec
        self._save()

    def set_state(self, name: str, state: SkillState, by: str = "") -> None:
        rec = dict(self._data.get(name, {}))
        rec["state"] = SkillState(state).value
        self._data[name] = rec
        self._save()

    def forget(self, name: str) -> None:
        if name in self._data:
            del self._data[name]
            self._save()

    def needs_reapproval(self, name: str, current_hash: str) -> bool:
        rec = self._data.get(name)
        if not rec:
            return False  # untracked => trusted
        if self.state(name) != SkillState.APPROVED:
            return False  # already not approved; not a "re-approval" question
        return rec.get("content_hash") != current_hash

    def all_records(self) -> dict:
        return dict(self._data)


# --- process-level governance accessor -------------------------------------

_process_governance: Optional[SkillGovernance] = None


def _default_governance_path() -> Optional[Path]:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home()) / "skills" / ".governance.json"
    except Exception:
        return None


def get_governance() -> SkillGovernance:
    global _process_governance
    if _process_governance is None:
        _process_governance = SkillGovernance(path=_default_governance_path())
    return _process_governance


def set_governance(gov: SkillGovernance) -> None:
    global _process_governance
    _process_governance = gov


def reset_governance() -> None:
    global _process_governance
    _process_governance = None


def filter_usable_skills(
    names: Iterable[str],
    identity: Optional[Identity] = None,
    engine: Optional[PermissionEngine] = None,
    governance: Optional[SkillGovernance] = None,
) -> list:
    """Return the subset of skill names the identity may see/use.

    Approvers (anyone with ``skill.approve``) see everything so they can review
    pending skills; everyone else sees only usable (approved/active) skills.
    No-op when enforcement is disabled.
    """
    names = list(names)
    eng = engine if engine is not None else get_engine()
    if not eng.policy.enabled:
        return names
    ident = identity if identity is not None else get_current_identity()
    if eng.can(ident, "skill.approve", audit=False):
        return names
    gov = governance if governance is not None else get_governance()
    return [n for n in names if gov.is_usable(n)]
