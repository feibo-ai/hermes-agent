"""Shell `hermes permissions` mutations are dangerous commands (TEA-88).

Defense-in-depth: a shell-capable agent that bypasses the gated `permissions`
tool by running the CLI directly still trips the out-of-band approval.
"""

from tools.approval import detect_dangerous_command


def _is_dangerous(cmd: str) -> bool:
    return bool(detect_dangerous_command(cmd)[0])


def test_permissions_grant_via_shell_is_dangerous():
    assert _is_dangerous("hermes permissions grant telegram:5 member")
    assert _is_dangerous("hermes permissions revoke tg:1 owner")
    assert _is_dangerous("hermes permissions enable")
    assert _is_dangerous("hermes permissions disable")


def test_cross_profile_hermes_home_bypass_is_dangerous():
    # the exact bypass the live test exhibited
    assert _is_dangerous("HERMES_HOME=/x/profiles/teama hermes permissions grant telegram:55555 member")


def test_module_form_is_dangerous():
    assert _is_dangerous("python -m hermes_cli.main permissions grant tg:1 admin")


def test_permission_reads_are_not_dangerous():
    assert not _is_dangerous("hermes permissions users")
    assert not _is_dangerous("hermes permissions policy")
    assert not _is_dangerous("hermes audit list")
