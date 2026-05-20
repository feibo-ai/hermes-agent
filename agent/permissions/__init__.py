"""Hermes permission core (Epic TEA-88 / Phase 1 TEA-89).

A small, central RBAC layer: identities -> roles -> capabilities, a wildcard
capability matcher, a fault-tolerant policy loader, and a structured audit log.

Enforcement is opt-in: with no policy configured the engine allows everything
and records nothing, so existing single-user CLI installs are unaffected.
"""

from __future__ import annotations

from .audit import AuditEvent, AuditLog
from .context import (
    build_engine,
    get_current_identity,
    get_engine,
    reset_current_identity,
    reset_engine,
    set_current_identity,
    set_engine,
)
from .engine import PermissionDenied, PermissionEngine
from .identity import (
    LOCAL_OWNER_ID,
    Identity,
    default_local_identity,
    make_identity_id,
)
from .policy import (
    DEFAULT_OWNER_ID,
    DEFAULT_ROLES,
    Policy,
    capability_matches,
    load_policy,
)
from .skill_governance import (
    SkillGovernance,
    SkillState,
    action_capability,
    compute_content_hash,
    filter_usable_skills,
    get_governance,
    is_content_mutating,
    reset_governance,
    set_governance,
)

__all__ = [
    "AuditEvent",
    "AuditLog",
    "PermissionDenied",
    "PermissionEngine",
    "Identity",
    "LOCAL_OWNER_ID",
    "default_local_identity",
    "make_identity_id",
    "Policy",
    "DEFAULT_ROLES",
    "DEFAULT_OWNER_ID",
    "capability_matches",
    "load_policy",
    "build_engine",
    "get_engine",
    "set_engine",
    "reset_engine",
    "get_current_identity",
    "set_current_identity",
    "reset_current_identity",
    "SkillGovernance",
    "SkillState",
    "action_capability",
    "is_content_mutating",
    "compute_content_hash",
    "filter_usable_skills",
    "get_governance",
    "set_governance",
    "reset_governance",
]
