"""Phase 2 (TEA-90) — tool -> required-capability mapping."""

from agent.permissions.tool_policy import (
    DEFAULT_TOOL_CAPABILITY,
    required_capability_for_tool,
)


def test_default_tool_requires_safe_use():
    assert required_capability_for_tool("web_search") == "tool.use.safe"
    assert required_capability_for_tool("read_file") == DEFAULT_TOOL_CAPABILITY


def test_shell_tools_require_shell_capability():
    assert required_capability_for_tool("terminal") == "tool.use.shell"
    assert required_capability_for_tool("process") == "tool.use.shell"


def test_browser_tools_require_browser_capability():
    assert required_capability_for_tool("browser_navigate") == "tool.use.browser"
    assert required_capability_for_tool("browser_click") == "tool.use.browser"


def test_mcp_tools_require_mcp_capability():
    assert required_capability_for_tool("mcp__server__do") == "tool.use.mcp"


def test_skill_tools_mapping():
    # discovery/view are member-safe; management is an admin mutation
    assert required_capability_for_tool("skills_list") == "skill.view"
    assert required_capability_for_tool("skill_view") == "skill.view"
    assert required_capability_for_tool("skill_manage") == "skill.update"


def test_config_overrides_win():
    overrides = {"web_search": "tool.use.shell"}
    assert required_capability_for_tool("web_search", overrides) == "tool.use.shell"
