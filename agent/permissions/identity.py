"""Identity model for the Hermes permission core (TEA-89).

An ``Identity`` represents any actor that can drive the agent: a local CLI
owner, a gateway user on Telegram/Slack/Discord, a sub-agent, etc. Identities
are immutable value objects so they are safe to cache and use as dict keys.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Optional

# Stable id for the implicit local CLI user. Keeping this constant means the
# single-user CLI keeps resolving to the same owner identity across runs.
LOCAL_OWNER_ID = "local:owner"


@dataclass(frozen=True)
class Identity:
    id: str
    display_name: str = ""
    platform: str = "cli"
    roles: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    tenant_id: Optional[str] = None

    def with_roles(self, roles: Iterable[str]) -> "Identity":
        """Return a copy of this identity with ``roles`` replaced."""
        return replace(self, roles=tuple(roles))


def make_identity_id(platform: str, user_id: str) -> str:
    """Build a canonical identity id from a platform and platform user id."""
    return f"{platform}:{user_id}"


def default_local_identity() -> Identity:
    """The implicit owner identity used for local single-user CLI sessions."""
    return Identity(
        id=LOCAL_OWNER_ID,
        display_name="Local Owner",
        platform="cli",
        roles=("owner",),
    )
