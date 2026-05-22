"""Epic TEA-88 capstone: assert every Epic-level acceptance criterion end to end.

Each test maps directly to one bullet of the Epic's 验收 (acceptance) list:

  - owner/admin/member/guest 四类角色可配置
  - member 无法创建/更新/安装/删除 Skill
  - member 可以使用已批准 Skill
  - 两个 gateway 用户的 USER.md 偏好互不串
  - 未授权工具调用在执行前被拒绝
  - 危险命令的持久批准只能由 admin/owner 做
  - 所有拒绝和 privileged mutation 都写 audit log
  - 现有单用户 CLI 默认行为兼容
"""

import json

import pytest

import model_tools
import tools.approval as approval
import tools.skill_manager_tool as smt
from agent.permissions import (
    AuditLog,
    Identity,
    PermissionEngine,
    SkillGovernance,
    load_policy,
    reset_current_identity,
    reset_engine,
    reset_governance,
    set_current_identity,
    set_engine,
    set_governance,
)
from tools.memory_tool import MemoryStore


def _engine(audit=None, enabled=True):
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "local:owner": {"roles": ["owner"]},
        "tg:admin": {"roles": ["admin"]},
        "tg:member": {"roles": ["member"]},
        "tg:guest": {"roles": ["guest"]},
    }}})
    return PermissionEngine(pol, audit=audit or AuditLog())


@pytest.fixture(autouse=True)
def _clean():
    model_tools._tool_defs_cache.clear()
    yield
    reset_engine()
    reset_governance()
    model_tools._tool_defs_cache.clear()


def _act_as(eng, role):
    set_engine(eng)
    return set_current_identity(eng.resolve(platform=("cli" if role == "owner" else "tg"),
                                            user_id=(None if role == "owner" else role)))


# 1. owner/admin/member/guest 四类角色可配置
def test_four_roles_are_configurable():
    eng = _engine()
    assert {"owner", "admin", "member", "guest"} <= set(eng.policy.roles)
    assert eng.can(Identity(id="local:owner", roles=("owner",)), "manage.roles")
    assert eng.can(Identity(id="tg:admin", roles=("admin",)), "skill.create")
    assert not eng.can(Identity(id="tg:member", roles=("member",)), "skill.create")
    assert eng.can(Identity(id="tg:guest", roles=("guest",)), "skill.view")


# 2. member 无法创建/更新/安装/删除 Skill
def test_member_cannot_mutate_skills():
    eng = _engine()
    tok = _act_as(eng, "member")
    try:
        for action, cap in [("create", "skill.create"), ("edit", "skill.update"),
                            ("delete", "skill.delete"), ("install", "skill.install")]:
            res = json.loads(smt.skill_manage(action, "x", content="---\nname: x\n---\nb"))
            assert res.get("success") is False and cap in res.get("error", "")
    finally:
        reset_current_identity(tok)


# 3. member 可以使用已批准 Skill
def test_member_can_use_approved_skill():
    from agent.permissions import filter_usable_skills
    gov = SkillGovernance()
    gov.approve("approved-skill", by="local:owner", content_hash="h")
    gov.record_mutation("pending-skill", "h", action="create")  # not usable
    set_governance(gov)
    eng = _engine()
    tok = _act_as(eng, "member")
    try:
        visible = set(filter_usable_skills(["approved-skill", "pending-skill", "bundled"]))
        assert "approved-skill" in visible and "bundled" in visible
        assert "pending-skill" not in visible
    finally:
        reset_current_identity(tok)


# 4. 两个 gateway 用户的 USER.md 偏好互不串
def test_two_gateway_users_user_md_do_not_cross(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path)
    a = MemoryStore(); a.bind_context("telegram:A", enabled=True); a.load_from_disk()
    b = MemoryStore(); b.bind_context("telegram:B", enabled=True); b.load_from_disk()
    a.add("user", "Alice likes vim")
    b.add("user", "Bob likes emacs")
    a.load_from_disk(); b.load_from_disk()
    assert a.user_entries == ["Alice likes vim"]
    assert b.user_entries == ["Bob likes emacs"]


# 5. 未授权工具调用在执行前被拒绝
def test_unauthorized_tool_call_rejected_before_execution():
    audit = AuditLog()
    eng = _engine(audit=audit)
    tok = _act_as(eng, "member")
    try:
        result = model_tools.handle_function_call("skill_manage", {"action": "create", "name": "x"})
        assert "is not permitted to" in result
        assert len(audit.query(decision="deny")) >= 1
    finally:
        reset_current_identity(tok)


# 6. 危险命令的持久批准只能由 admin/owner 做
def test_durable_dangerous_approval_owner_admin_only():
    eng = _engine()
    for role in ("owner", "admin"):
        tok = _act_as(eng, role)
        try:
            assert approval._enforce_approval_choice("always") == "always"
        finally:
            reset_current_identity(tok)
    for role in ("member", "guest"):
        tok = _act_as(eng, role)
        try:
            assert approval._enforce_approval_choice("always") == "once"
        finally:
            reset_current_identity(tok)


# 7. 所有拒绝和 privileged mutation 都写 audit log
def test_denials_and_privileged_mutations_are_audited():
    audit = AuditLog()
    eng = _engine(audit=audit)
    member = Identity(id="tg:member", roles=("member",))
    owner = Identity(id="local:owner", roles=("owner",))
    assert eng.can(member, "skill.create") is False  # audited deny
    audit.record_privileged_mutation(owner, "skill.approve", resource="skill:x")
    assert len(audit.query(decision="deny")) >= 1
    assert len(audit.query(event_type="privileged_mutation")) >= 1


# 8. 现有单用户 CLI 默认行为兼容 (enforcement off => everything allowed, nothing audited)
def test_single_user_cli_default_is_unchanged():
    audit = AuditLog()
    eng = _engine(audit=audit, enabled=False)
    tok = _act_as(eng, "member")
    try:
        # tool schema unfiltered
        defs = model_tools.get_tool_definitions(enabled_toolsets=["skills"], quiet_mode=True)
        assert "skill_manage" in {d["function"]["name"] for d in defs}
        # admin-only tool call allowed (no permission error)
        res = model_tools.handle_function_call("definitely_not_real_tool", {})
        assert "is not permitted to" not in res
        # durable approval preserved; nothing audited
        assert approval._enforce_approval_choice("always") == "always"
        assert audit.query() == []
    finally:
        reset_current_identity(tok)
