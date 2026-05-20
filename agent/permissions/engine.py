"""Permission engine: evaluate ``can(identity, capability, resource)``.

The engine is the single decision point. When the policy is *disabled* it is a
pure no-op that allows everything and records nothing, which preserves the
existing single-user CLI behaviour until an operator opts in.
"""

from __future__ import annotations

from typing import Optional, Union

from .audit import AuditLog
from .identity import Identity, default_local_identity, make_identity_id
from .policy import Policy, capability_matches


class PermissionDenied(Exception):
    def __init__(self, identity_id: str, capability: str, resource: Optional[str] = None, reason: str = ""):
        self.identity_id = identity_id
        self.capability = capability
        self.resource = resource
        self.reason = reason or "permission denied"
        msg = f"{identity_id} is not permitted to '{capability}'"
        if resource:
            msg += f" on {resource}"
        super().__init__(msg)


class PermissionEngine:
    def __init__(self, policy: Policy, audit: Optional[AuditLog] = None):
        self.policy = policy
        self.audit = audit

    def effective_roles(self, identity: Identity) -> list[str]:
        roles = set(identity.roles)
        roles.update(self.policy.roles_for_identity(identity.id))
        return sorted(roles)

    def effective_capabilities(self, identity: Identity) -> set[str]:
        return self.policy.capabilities_for_roles(self.effective_roles(identity))

    def can(
        self,
        identity: Identity,
        capability: str,
        resource: Optional[str] = None,
        *,
        audit: bool = True,
    ) -> bool:
        if not self.policy.enabled:
            return True
        caps = self.effective_capabilities(identity)
        allowed = any(capability_matches(granted, capability) for granted in caps)
        if audit and self.audit is not None:
            self.audit.record_decision(
                identity, capability, "allow" if allowed else "deny", resource=resource
            )
        return allowed

    def require(self, identity: Identity, capability: str, resource: Optional[str] = None) -> None:
        if self.can(identity, capability, resource=resource):
            return
        raise PermissionDenied(identity.id, capability, resource)

    def resolve(
        self,
        platform: str,
        user_id: Optional[str] = None,
        display_name: str = "",
    ) -> Identity:
        """Resolve a concrete :class:`Identity` from runtime context.

        Local CLI sessions with no explicit user default to the local owner.
        """
        if not user_id:
            if platform in ("cli", "", None):
                base = default_local_identity()
                return base.with_roles(self.policy.roles_for_identity(base.id))
            idid = make_identity_id(platform, "anonymous")
        else:
            idid = make_identity_id(platform, user_id)
        roles = self.policy.roles_for_identity(idid)
        return Identity(id=idid, display_name=display_name, platform=platform, roles=tuple(roles))
