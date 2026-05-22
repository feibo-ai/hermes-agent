"""Policy model + loader for the Hermes permission core (TEA-89).

The policy maps identities -> roles -> capabilities. Capabilities support
wildcards (``skill.*``, ``tool.use.*``, ``*``). The default role grants align
with the Epic acceptance criteria:

- ``owner`` can do everything (``*``) and is the only role that can manage
  users/roles/policy;
- ``admin`` manages skills/tools/memory and approves dangerous actions;
- ``member`` uses approved skills + safe tools and manages only their own memory;
- ``guest`` can only view.

Loading is intentionally fault-tolerant: a missing policy file never raises, so
``hermes`` keeps starting for existing single-user installs (enforcement stays
*off* until a policy is configured).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

DEFAULT_OWNER_ID = "local:owner"

DEFAULT_ROLES: dict[str, list[str]] = {
    "owner": ["*"],
    "admin": [
        "skill.*",
        "tool.use.*",
        "tool.approve.dangerous",
        "memory.*",
        "read.audit",
    ],
    "member": [
        "skill.view",
        "skill.use",
        "tool.use.safe",
        "memory.read.self",
        "memory.write.self",
    ],
    # A skill mentor: a member who also teaches/maintains skills — can author
    # (create/update) and approve skills, but has no host tools, no destructive
    # skill ops (delete/install), and no user/role administration.
    "mentor": [
        "skill.view",
        "skill.use",
        "skill.create",
        "skill.update",
        "skill.approve",
        "tool.use.safe",
        # a workspace-confined shell (runs in a sandbox limited to the agent's
        # working directory) — distinct from full host shell (tool.use.shell)
        "tool.use.shell.workspace",
        "memory.read.self",
        "memory.write.self",
    ],
    "guest": [
        "skill.view",
    ],
}


def capability_matches(granted: str, required: str) -> bool:
    """Return True if a *granted* capability pattern covers a *required* one."""
    if granted == "*":
        return True
    if granted == required:
        return True
    if granted.endswith(".*"):
        prefix = granted[:-2]  # "skill.*" -> "skill"
        return required == prefix or required.startswith(prefix + ".")
    return False


@dataclass
class Policy:
    enabled: bool = False
    roles: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_ROLES.items()})
    users: dict[str, list[str]] = field(default_factory=dict)  # identity_id -> [role names]
    default_role: str = "guest"
    owner_id: str = DEFAULT_OWNER_ID
    tool_capabilities: dict[str, str] = field(default_factory=dict)  # tool name -> capability override

    def roles_for_identity(self, identity_id: str) -> list[str]:
        if identity_id in self.users:
            return list(self.users[identity_id])
        # The implicit local owner is always an owner even when not listed,
        # so a freshly-enabled policy never locks the operator out.
        if identity_id == self.owner_id:
            return ["owner"]
        return [self.default_role]

    def capabilities_for_roles(self, roles: Iterable[str]) -> set[str]:
        caps: set[str] = set()
        for role in roles:
            caps.update(self.roles.get(role, []))
        return caps


def _coerce_user_roles(spec: Any) -> list[str]:
    if isinstance(spec, dict):
        if "roles" in spec:
            return list(spec["roles"] or [])
        if "role" in spec:
            return [spec["role"]]
        return []
    if isinstance(spec, (list, tuple)):
        return list(spec)
    if spec:
        return [spec]
    return []


def _policy_from_raw(raw: dict) -> Policy:
    pol = Policy()
    # A present permissions block enables enforcement unless told otherwise.
    pol.enabled = bool(raw.get("enabled", True))

    roles = {k: list(v) for k, v in DEFAULT_ROLES.items()}
    for name, spec in (raw.get("roles") or {}).items():
        if isinstance(spec, dict):
            roles[name] = list(spec.get("capabilities", []) or [])
        else:
            roles[name] = list(spec or [])
    pol.roles = roles

    pol.users = {
        uid: _coerce_user_roles(spec)
        for uid, spec in (raw.get("users") or {}).items()
    }
    pol.default_role = raw.get("default_role", "guest")
    pol.owner_id = raw.get("owner_id", DEFAULT_OWNER_ID)
    tool_caps = raw.get("tool_capabilities") or {}
    if isinstance(tool_caps, dict):
        pol.tool_capabilities = {str(k): str(v) for k, v in tool_caps.items()}
    return pol


def load_policy(home: Optional[Path] = None, config: Optional[dict] = None) -> Policy:
    """Load a :class:`Policy` from a config dict and/or the Hermes home dir.

    Resolution order:
      1. ``config["permissions"]`` if present;
      2. ``<home>/permissions.yaml`` if present;
      3. a safe default with enforcement disabled.
    """
    raw: Optional[dict] = None

    if config is not None and isinstance(config.get("permissions"), dict):
        raw = dict(config["permissions"])
    elif home is not None:
        pfile = Path(home) / "permissions.yaml"
        if pfile.exists():
            try:
                loaded = yaml.safe_load(pfile.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded
            except Exception:
                raw = None

    if raw is None:
        return Policy(enabled=False)
    return _policy_from_raw(raw)
