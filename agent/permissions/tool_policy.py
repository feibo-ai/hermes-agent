"""Map a tool name to the capability required to use it (TEA-90).

Defaults are conservative-but-usable: most tools need only ``tool.use.safe``
(which members have), while shell/browser/mcp tools and skill *management*
require stronger capabilities that members lack by default. Operators can
override any tool via ``permissions.tool_capabilities`` in config.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_TOOL_CAPABILITY = "tool.use.safe"

# Exact tool-name -> required capability.
#
# Host-access tools (shell, code execution, desktop control, and filesystem
# read/write) require capabilities members do NOT hold by default — otherwise
# a member could run arbitrary code or touch the host FS via the default
# ``tool.use.safe`` fall-through. Genuinely safe tools (web_search, vision,
# memory, skill view/list, etc.) intentionally fall through to tool.use.safe.
_BUILTIN_TOOL_CAPABILITIES: dict[str, str] = {
    # shell / process / code execution / desktop control
    "terminal": "tool.use.shell",
    "process": "tool.use.shell",
    "execute_code": "tool.use.shell",
    "computer_use": "tool.use.shell",
    # autonomous scheduling: a member must not be able to schedule a job that
    # later runs with the agent's full tool set (privilege escalation).
    "cronjob": "tool.use.shell",
    # filesystem access (read + write)
    "write_file": "tool.use.filesystem",
    "patch": "tool.use.filesystem",
    "read_file": "tool.use.filesystem",
    "search_files": "tool.use.filesystem",
    # skills: discovery/view are member-safe, management is an admin mutation
    "skills_list": "skill.view",
    "skill_view": "skill.view",
    "skill_manage": "skill.update",
}

# Prefix rules, checked when there is no exact match.
_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("browser_", "tool.use.browser"),
    ("mcp__", "tool.use.mcp"),
    ("mcp_", "tool.use.mcp"),
)


def required_capability_for_tool(
    tool_name: str,
    overrides: Optional[dict] = None,
) -> str:
    if overrides and tool_name in overrides:
        return overrides[tool_name]
    if tool_name in _BUILTIN_TOOL_CAPABILITIES:
        return _BUILTIN_TOOL_CAPABILITIES[tool_name]
    for prefix, cap in _PREFIX_RULES:
        if tool_name.startswith(prefix):
            return cap
    return DEFAULT_TOOL_CAPABILITY
