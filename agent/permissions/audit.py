"""Structured audit log for permission decisions and privileged mutations.

Audit events are appended as JSON lines to ``<home>/audit/permissions.jsonl``
(or kept purely in memory when no path is given, which is handy for tests).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from .identity import Identity


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identity_id(identity: Union[Identity, str]) -> str:
    return identity.id if isinstance(identity, Identity) else str(identity)


@dataclass
class AuditEvent:
    event_type: str = "decision"  # "decision" | "privileged_mutation"
    decision: str = ""            # "allow" | "deny" | ""
    identity_id: str = ""
    capability: str = ""
    resource: Optional[str] = None
    reason: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "decision": self.decision,
            "identity_id": self.identity_id,
            "capability": self.capability,
            "resource": self.resource,
            "reason": self.reason,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AuditEvent":
        return cls(
            event_type=d.get("event_type", "decision"),
            decision=d.get("decision", ""),
            identity_id=d.get("identity_id", ""),
            capability=d.get("capability", ""),
            resource=d.get("resource"),
            reason=d.get("reason", ""),
            metadata=d.get("metadata") or {},
            timestamp=d.get("timestamp", "") or _now_iso(),
        )


class AuditLog:
    def __init__(self, path: Optional[Union[Path, str]] = None):
        self.path = Path(path) if path else None
        self._events: list[AuditEvent] = []
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self._events.append(AuditEvent.from_dict(json.loads(line)))
            except Exception:
                continue

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(event.to_json() + "\n")
            except Exception:
                # Auditing must never break the agent; in-memory copy stays.
                pass

    def record_decision(
        self,
        identity: Union[Identity, str],
        capability: str,
        decision: str,
        resource: Optional[str] = None,
        reason: str = "",
    ) -> None:
        self.record(AuditEvent(
            event_type="decision",
            decision=decision,
            identity_id=_identity_id(identity),
            capability=capability,
            resource=resource,
            reason=reason,
        ))

    def record_privileged_mutation(
        self,
        identity: Union[Identity, str],
        action: str,
        resource: Optional[str] = None,
        metadata: Optional[dict] = None,
        reason: str = "",
    ) -> None:
        self.record(AuditEvent(
            event_type="privileged_mutation",
            decision="",  # distinct from allow/deny decisions so the three audit filters are disjoint
            identity_id=_identity_id(identity),
            capability=action,
            resource=resource,
            reason=reason,
            metadata=metadata or {},
        ))

    def query(
        self,
        decision: Optional[str] = None,
        event_type: Optional[str] = None,
        identity_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[AuditEvent]:
        out: list[AuditEvent] = self._events
        if decision is not None:
            out = [e for e in out if e.decision == decision]
        if event_type is not None:
            out = [e for e in out if e.event_type == event_type]
        if identity_id is not None:
            out = [e for e in out if e.identity_id == identity_id]
        if limit is not None:
            out = out[-limit:]
        return list(out)
