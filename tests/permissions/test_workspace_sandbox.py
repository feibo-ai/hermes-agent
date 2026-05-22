"""Mentor scoped shell -> workspace-confined Docker sandbox (Epic TEA-88)."""

import tools.terminal_tool as tt
from agent.permissions import (
    Identity,
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


_BASE = {"env_type": "local", "cwd": ".", "docker_image": "x",
         "docker_mount_cwd_to_workspace": False, "host_cwd": None}


def test_mentor_shell_is_forced_into_workspace_docker(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_CWD", str(tmp_path))
    token = _setup("mentor")
    try:
        out = tt._apply_workspace_sandbox(dict(_BASE))
        assert out["env_type"] == "docker"
        assert out["docker_mount_cwd_to_workspace"] is True
        assert out["cwd"] == "/workspace"
        assert out["host_cwd"] == str(tmp_path)        # launch cwd mounted at /workspace
        assert out["docker_run_as_host_user"] is True
    finally:
        _teardown(token)


def test_owner_shell_is_not_sandboxed():
    token = _setup("owner")
    try:
        out = tt._apply_workspace_sandbox(dict(_BASE))
        assert out["env_type"] == "local"             # full host shell, unchanged
        assert out["docker_mount_cwd_to_workspace"] is False
    finally:
        _teardown(token)


def test_disabled_enforcement_leaves_config_unchanged():
    token = _setup("mentor", enabled=False)
    try:
        out = tt._apply_workspace_sandbox(dict(_BASE))
        assert out["env_type"] == "local"
    finally:
        _teardown(token)


def test_custom_sandbox_image_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_CWD", str(tmp_path))
    monkeypatch.setenv("HERMES_WORKSPACE_SANDBOX_IMAGE", "debian:bookworm-slim")
    token = _setup("mentor")
    try:
        out = tt._apply_workspace_sandbox(dict(_BASE))
        assert out["docker_image"] == "debian:bookworm-slim"
    finally:
        _teardown(token)
