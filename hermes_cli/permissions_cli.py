"""CLI handlers for `hermes permissions`, `hermes audit`, and
`hermes memory migrate-user-profile` (Epic TEA-88 / Phase 5)."""

from __future__ import annotations

import json

from hermes_constants import get_hermes_home


def _engine_and_actor():
    from agent.permissions import build_engine
    from hermes_cli.config import load_config_readonly

    home = get_hermes_home()
    try:
        cfg = load_config_readonly()
    except Exception:
        cfg = {}
    eng = build_engine(config=cfg, home=home)
    actor = eng.resolve(platform="cli")  # local owner identity
    return home, eng, actor


def permissions_command(args) -> None:
    from agent.permissions import admin

    sub = getattr(args, "permissions_command", None)
    home, eng, actor = _engine_and_actor()
    policy = eng.policy

    if sub == "users":
        users = admin.list_users(policy)
        if not users:
            print("  (no users configured — default role applies to everyone)")
        for u in users:
            print(f"  {u['identity']}: {', '.join(u['roles']) or '(none)'}")
        print(f"\n  enforcement: {'on' if policy.enabled else 'off'} | default role: {policy.default_role}")
    elif sub == "roles":
        for r in admin.list_roles(policy):
            print(f"  {r['role']}: {', '.join(r['capabilities'])}")
    elif sub == "policy":
        print(json.dumps(admin.show_policy(policy), indent=2, ensure_ascii=False))
    elif sub == "grant":
        try:
            res = admin.grant_role(home, args.identity, args.role, actor, eng)
            print(f"  ✓ {args.identity} now has roles: {', '.join(res['roles'])}")
        except Exception as e:
            print(f"  ✗ {e}")
    elif sub == "revoke":
        try:
            res = admin.revoke_role(home, args.identity, args.role, actor, eng)
            print(f"  ✓ {args.identity} roles: {', '.join(res['roles']) or '(none)'}")
        except Exception as e:
            print(f"  ✗ {e}")
    elif sub in ("enable", "disable"):
        try:
            admin.set_enabled(home, sub == "enable", actor, eng)
            print(f"  ✓ permission enforcement {'enabled' if sub == 'enable' else 'disabled'}")
        except Exception as e:
            print(f"  ✗ {e}")
    else:
        print(
            "Usage: hermes permissions {users|roles|policy|"
            "grant <identity> <role>|revoke <identity> <role>|enable|disable}"
        )


def audit_command(args) -> None:
    from agent.permissions import admin

    home = get_hermes_home()
    decision = getattr(args, "decision", None)
    event_type = "privileged_mutation" if getattr(args, "privileged", False) else None
    limit = getattr(args, "limit", None)
    events = admin.audit_list(home, decision=decision, event_type=event_type, limit=limit)
    if not events:
        print("  (no audit events)")
        return
    for e in events:
        kind = e["event_type"] if e["event_type"] == "privileged_mutation" else (e["decision"] or "-")
        print(f"  {e['timestamp']}  {kind:18}  {e['identity_id']:20}  "
              f"{e['capability']}  {e.get('resource') or ''}")


def migrate_user_profile_command(args) -> None:
    from agent.permissions import admin

    home = get_hermes_home()
    owner_id = getattr(args, "owner_id", None) or "local:owner"
    res = admin.migrate_user_profile(home, owner_id=owner_id)
    if res.get("success"):
        print(f"  ✓ Migrated legacy USER.md -> {res['to']}")
        print(f"    (legacy {res['from']} kept as backup)")
    else:
        print(f"  • {res.get('message', 'nothing to do')}")
