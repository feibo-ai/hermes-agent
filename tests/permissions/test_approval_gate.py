"""Phase 2 (TEA-90) — durable dangerous-command approval is gated by
``tool.approve.dangerous`` via the real tools.approval helper."""

import tools.approval as approval
from agent.permissions import (
    PermissionEngine,
    load_policy,
    reset_current_identity,
    reset_engine,
    set_current_identity,
    set_engine,
)


def _setup(role, enabled=True):
    pol = load_policy(config={"permissions": {"enabled": enabled, "users": {
        "tg:u": {"roles": [role]},
    }}})
    eng = PermissionEngine(pol)
    set_engine(eng)
    return set_current_identity(eng.resolve(platform="tg", user_id="u"))


def _teardown(token):
    reset_current_identity(token)
    reset_engine()


def test_member_durable_approval_downgraded_to_once():
    token = _setup("member")
    try:
        assert approval._enforce_approval_choice("always") == "once"
        assert approval._enforce_approval_choice("session") == "once"
        # non-durable choices pass through untouched
        assert approval._enforce_approval_choice("once") == "once"
        assert approval._enforce_approval_choice("deny") == "deny"
    finally:
        _teardown(token)


def test_guest_durable_approval_downgraded():
    token = _setup("guest")
    try:
        assert approval._enforce_approval_choice("session") == "once"
    finally:
        _teardown(token)


def test_owner_durable_approval_preserved():
    token = _setup("owner")
    try:
        assert approval._enforce_approval_choice("always") == "always"
        assert approval._enforce_approval_choice("session") == "session"
    finally:
        _teardown(token)


def test_admin_durable_approval_preserved():
    token = _setup("admin")
    try:
        assert approval._enforce_approval_choice("always") == "always"
    finally:
        _teardown(token)


def test_disabled_enforcement_preserves_durable_approval():
    token = _setup("member", enabled=False)
    try:
        assert approval._enforce_approval_choice("always") == "always"
    finally:
        _teardown(token)
