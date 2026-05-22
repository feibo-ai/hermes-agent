"""Phase 3 (TEA-91) — skill lifecycle / approval governance."""

from agent.permissions import (
    Identity,
    PermissionEngine,
    load_policy,
)
from agent.permissions.skill_governance import (
    SkillGovernance,
    SkillState,
    action_capability,
    compute_content_hash,
    filter_usable_skills,
    is_content_mutating,
)


# --- action -> capability ---------------------------------------------------

def test_action_capability_mapping():
    assert action_capability("create") == "skill.create"
    assert action_capability("edit") == "skill.update"
    assert action_capability("patch") == "skill.update"
    assert action_capability("write_file") == "skill.update"
    assert action_capability("delete") == "skill.delete"
    assert action_capability("install") == "skill.install"
    assert action_capability("approve") == "skill.approve"


def test_content_mutating_actions():
    for a in ("create", "edit", "patch", "write_file", "remove_file"):
        assert is_content_mutating(a)
    for a in ("approve", "delete", "disable"):
        assert not is_content_mutating(a)


def test_content_hash_is_deterministic_and_sensitive():
    assert compute_content_hash("abc") == compute_content_hash("abc")
    assert compute_content_hash("abc") != compute_content_hash("abd")


# --- lifecycle state machine ------------------------------------------------

def test_untracked_skill_is_trusted_and_usable():
    gov = SkillGovernance()
    # bundled / pre-existing skills have no record -> treated as approved
    assert gov.state("bundled-skill") == SkillState.APPROVED
    assert gov.is_usable("bundled-skill") is True


def test_create_enters_pending_review_and_is_not_usable():
    gov = SkillGovernance()
    gov.record_mutation("new-skill", compute_content_hash("v1"), by="tg:admin", action="create")
    assert gov.state("new-skill") == SkillState.PENDING_REVIEW
    assert gov.is_usable("new-skill") is False


def test_approve_makes_skill_usable():
    gov = SkillGovernance()
    h = compute_content_hash("v1")
    gov.record_mutation("s", h, by="tg:admin", action="create")
    gov.approve("s", by="local:owner", content_hash=h)
    assert gov.state("s") == SkillState.APPROVED
    assert gov.is_usable("s") is True


def test_content_change_requires_reapproval():
    gov = SkillGovernance()
    h1 = compute_content_hash("v1")
    gov.approve("s", by="owner", content_hash=h1)
    # same content -> no re-approval needed
    assert gov.needs_reapproval("s", h1) is False
    # changed content -> re-approval needed
    h2 = compute_content_hash("v2")
    assert gov.needs_reapproval("s", h2) is True


def test_record_mutation_after_approval_resets_to_pending():
    gov = SkillGovernance()
    h1 = compute_content_hash("v1")
    gov.approve("s", by="owner", content_hash=h1)
    assert gov.is_usable("s") is True
    # editing the approved skill knocks it back to pending_review
    gov.record_mutation("s", compute_content_hash("v2"), by="tg:editor", action="edit")
    assert gov.state("s") == SkillState.PENDING_REVIEW
    assert gov.is_usable("s") is False


def test_disable_and_forget():
    gov = SkillGovernance()
    gov.approve("s", by="owner", content_hash="h")
    gov.disable("s", by="owner")
    assert gov.state("s") == SkillState.DISABLED
    assert gov.is_usable("s") is False
    gov.forget("s")
    assert gov.get("s") is None


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "skills" / ".governance.json"
    gov = SkillGovernance(path=path)
    gov.record_mutation("s", "h1", by="tg:admin", action="create")
    assert path.exists()
    reopened = SkillGovernance(path=path)
    assert reopened.state("s") == SkillState.PENDING_REVIEW


# --- member-visible filtering ----------------------------------------------

def _engine(enabled=True):
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "tg:member": {"roles": ["member"]},
        "tg:admin": {"roles": ["admin"]},
    }}})
    return PermissionEngine(pol)


def test_members_only_see_usable_skills():
    gov = SkillGovernance()
    gov.record_mutation("pending-skill", "h", by="tg:admin", action="create")  # pending
    gov.approve("ok-skill", by="owner", content_hash="h")                       # usable
    eng = _engine()
    member = Identity(id="tg:member", roles=("member",))
    visible = set(filter_usable_skills(
        ["pending-skill", "ok-skill", "bundled"], member, eng, gov))
    assert "ok-skill" in visible
    assert "bundled" in visible        # untracked => approved
    assert "pending-skill" not in visible


def test_admins_see_all_skills_including_pending():
    gov = SkillGovernance()
    gov.record_mutation("pending-skill", "h", by="tg:admin", action="create")
    eng = _engine()
    admin = Identity(id="tg:admin", roles=("admin",))
    visible = set(filter_usable_skills(["pending-skill", "ok"], admin, eng, gov))
    assert visible == {"pending-skill", "ok"}  # approvers see everything


def test_filter_noop_when_disabled():
    gov = SkillGovernance()
    gov.record_mutation("pending-skill", "h", by="x", action="create")
    eng = _engine(enabled=False)
    member = Identity(id="tg:member", roles=("member",))
    visible = set(filter_usable_skills(["pending-skill"], member, eng, gov))
    assert visible == {"pending-skill"}
