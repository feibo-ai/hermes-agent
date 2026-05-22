"""Phase 3 (TEA-91) — end-to-end skill mutation gating through the real
tools.skill_manager_tool.skill_manage dispatcher.

Only denial paths exercise skill_manage directly (they return before any disk
write); allow-paths are asserted via the wired permission/governance helpers so
the test never touches the real ~/.hermes/skills tree.
"""

import json

import tools.skill_manager_tool as smt
from agent.permissions import (
    PermissionEngine,
    SkillGovernance,
    SkillState,
    load_policy,
    reset_current_identity,
    reset_engine,
    reset_governance,
    set_current_identity,
    set_engine,
    set_governance,
)


def _setup(role, enabled=True, governance=None):
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "tg:u": {"roles": [role]},
    }}})
    eng = PermissionEngine(pol, audit=__import__("agent.permissions", fromlist=["AuditLog"]).AuditLog())
    set_engine(eng)
    if governance is not None:
        set_governance(governance)
    return eng, set_current_identity(eng.resolve(platform="tg", user_id="u"))


def _teardown(token):
    reset_current_identity(token)
    reset_engine()
    reset_governance()


def test_member_cannot_create_skill():
    eng, token = _setup("member")
    try:
        res = json.loads(smt.skill_manage("create", "evil", content="---\nname: evil\n---\nx"))
        assert res.get("success") is False
        assert "skill.create" in res.get("error", "")
        # denial audited
        assert len(eng.audit.query(decision="deny")) >= 1
    finally:
        _teardown(token)


def test_member_cannot_edit_or_delete_or_install_or_approve():
    eng, token = _setup("member")
    try:
        for action, cap in [("edit", "skill.update"), ("delete", "skill.delete"),
                            ("approve", "skill.approve")]:
            res = json.loads(smt.skill_manage(action, "x", content="---\nname: x\n---\ny"))
            assert res.get("success") is False
            assert cap in res.get("error", ""), f"{action} should require {cap}"
    finally:
        _teardown(token)


def test_owner_and_admin_pass_the_create_gate():
    # Use the wired gate directly so we don't write to the real skills tree.
    eng, token = _setup("owner")
    try:
        assert smt._check_skill_permission("create", "x") is None
        assert smt._check_skill_permission("approve", "x") is None
        assert smt._check_skill_permission("delete", "x") is None
    finally:
        _teardown(token)
    eng, token = _setup("admin")
    try:
        assert smt._check_skill_permission("edit", "x") is None
        assert smt._check_skill_permission("approve", "x") is None
    finally:
        _teardown(token)


def test_disabled_enforcement_allows_member_mutation_gate():
    eng, token = _setup("member", enabled=False)
    try:
        # gate is a no-op -> single-user CLI behaviour preserved
        assert smt._check_skill_permission("create", "x") is None
    finally:
        _teardown(token)


def test_content_mutation_records_pending_review(tmp_path):
    gov = SkillGovernance(path=tmp_path / "skills" / ".governance.json")
    eng, token = _setup("admin", governance=gov)
    try:
        # simulate the post-success governance hook for a content-mutating action
        smt._record_skill_governance("edit", "some-skill")
        assert gov.state("some-skill") == SkillState.PENDING_REVIEW
        assert gov.is_usable("some-skill") is False
        # privileged mutation audited
        assert len(eng.audit.query(event_type="privileged_mutation")) >= 1
    finally:
        _teardown(token)


def test_skills_list_helper_hides_pending_for_member(tmp_path):
    import tools.skills_tool as st
    gov = SkillGovernance(path=tmp_path / "g.json")
    gov.record_mutation("pending", "h", action="create")
    eng, token = _setup("member", governance=gov)
    try:
        out = {s["name"] for s in st._filter_skills_by_governance(
            [{"name": "pending"}, {"name": "bundled"}])}
        assert out == {"bundled"}  # untracked bundled skill stays visible
    finally:
        _teardown(token)


def test_skill_view_blocks_pending_for_member(tmp_path):
    import tools.skills_tool as st
    gov = SkillGovernance(path=tmp_path / "g.json")
    gov.record_mutation("pending", "h", action="create")
    eng, token = _setup("member", governance=gov)
    try:
        block = st._skill_view_governance_block("pending")
        assert block is not None and "pending review" in block
        assert st._skill_view_governance_block("bundled") is None
    finally:
        _teardown(token)


def test_prompt_injection_helper_filters_for_member(tmp_path):
    import agent.prompt_builder as pb
    gov = SkillGovernance(path=tmp_path / "g.json")
    gov.record_mutation("pending", "h", action="create")
    eng, token = _setup("member", governance=gov)
    try:
        out = pb._filter_skills_by_governance(
            {"general": [("pending", "d"), ("bundled", "d")]})
        names = {n for items in out.values() for (n, _) in items}
        assert names == {"bundled"}
    finally:
        _teardown(token)


def test_admin_sees_pending_skills_in_helpers(tmp_path):
    import tools.skills_tool as st
    gov = SkillGovernance(path=tmp_path / "g.json")
    gov.record_mutation("pending", "h", action="create")
    eng, token = _setup("admin", governance=gov)
    try:
        out = {s["name"] for s in st._filter_skills_by_governance([{"name": "pending"}])}
        assert out == {"pending"}  # approvers see everything
    finally:
        _teardown(token)
