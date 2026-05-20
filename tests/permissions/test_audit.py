"""Phase 1 (TEA-89) — audit log unit tests."""

import json

from agent.permissions import AuditEvent, AuditLog, Identity


def _ident(idid="tg:member", role="member"):
    return Identity(id=idid, roles=(role,))


def test_audit_event_to_dict_has_required_shape():
    e = AuditEvent(
        event_type="decision",
        decision="deny",
        identity_id="tg:member",
        capability="skill.create",
        resource="skill:foo",
        reason="not permitted",
    )
    d = e.to_dict()
    for key in ("timestamp", "event_type", "decision", "identity_id",
                "capability", "resource", "reason", "metadata"):
        assert key in d
    assert d["resource"] == "skill:foo"


def test_record_and_query_roundtrip():
    log = AuditLog()
    log.record_decision(_ident(), "skill.view", "allow")
    log.record_decision(_ident(), "skill.create", "deny")
    assert len(log.query()) == 2
    assert len(log.query(decision="deny")) == 1
    assert len(log.query(decision="allow")) == 1


def test_query_filter_by_identity():
    log = AuditLog()
    log.record_decision(_ident("tg:a"), "skill.view", "allow")
    log.record_decision(_ident("tg:b"), "skill.view", "allow")
    assert len(log.query(identity_id="tg:a")) == 1


def test_record_privileged_mutation():
    log = AuditLog()
    log.record_privileged_mutation(_ident("local:owner", "owner"),
                                   action="skill.create",
                                   resource="skill:demo")
    events = log.query(event_type="privileged_mutation")
    assert len(events) == 1
    assert events[0].capability == "skill.create"
    assert events[0].resource == "skill:demo"


def test_query_limit_returns_latest():
    log = AuditLog()
    for i in range(5):
        log.record_decision(_ident(), f"cap.{i}", "allow")
    latest = log.query(limit=2)
    assert len(latest) == 2
    assert latest[-1].capability == "cap.4"


def test_persistence_to_jsonl_and_readback(tmp_path):
    path = tmp_path / "audit" / "permissions.jsonl"
    log = AuditLog(path=path)
    log.record_decision(_ident(), "skill.create", "deny", reason="blocked")
    # written as JSON lines
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["capability"] == "skill.create"
    assert parsed["decision"] == "deny"
    # a fresh log over the same path can read history back
    reopened = AuditLog(path=path)
    assert len(reopened.query(decision="deny")) == 1
