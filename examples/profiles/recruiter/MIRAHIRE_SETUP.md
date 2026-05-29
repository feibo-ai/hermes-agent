# Recruiter Profile · MiraHire Integration Setup

End-to-end deployment notes for wiring the recruiter profile's
`mirahire_create_requirement` tool to a live MiraHire backend.

This document describes **deployment-time** steps only; the code lives in
`tools/mirahire_tool.py` + `gateway/hooks/mirahire_identity.py` of this
branch.

Spec source of truth:
`docs/superpowers/specs/2026-05-28-requirements-mining-agent-mirahire-integration-design.md`
on the MiraHire repo.

---

## 1. Feishu app configuration — NO CHANGE NEEDED (verified 2026-05-29)

The "招聘业务需求分析师" app (`cli_aa87c42bb4785bd0`) runs in
**long-connection (websocket) mode** — confirmed in the developer
console at 事件与回调 → 事件配置: "订阅方式 = 使用长连接接收事件".

In long-connection mode there is **no `user_id_type` console toggle** for
events (that knob only exists for webhook-callback mode). The event
payload's `sender.sender_id` already includes `union_id` by default for
the developer's own apps — this is exactly why `gateway/platforms/feishu.py`
already extracts `union_id` (see its module docstring: "Session-key
participant isolation prefers union_id ... over open_id"). The recruiter
bot has been receiving `union_id` all along.

**Therefore: nothing to change in the Feishu console.** Subscribed events
(verified present): `im.message.receive_v1` + reaction/read events, all
under 应用身份.

The only runtime check worth doing once deployed: tail the agent log on
the first inbound message and confirm the identity resolver got a
non-empty union_id (the hook logs a warning if union_id is missing).

## 2. MiraHire backend prep (already done in MiraHire repo)

The following commits on the MiraHire repo's `dev` branch must be deployed:

- `37b418d` — RBAC: integration role + REQUIREMENT_* permissions
- `394f402` — User.is_service_account field
- `674a155` — Requirement.source field
- `d07bca1` — requirement_versions snapshot table
- `5c5e8d0` — RequirementVersion snapshot on every mutation
- `bc69bd5` — partial unique on users.feishu_union_id
- `15602f8` — by-feishu-union endpoint + require_integration_role
- `12458fa` — mint-service-token CLI
- `b4f45a4` — seed_service_accounts script

## 3. Seed service-account users (per tenant)

On the MiraHire backend host:

```bash
python -m scripts.seed_service_accounts --print
```

This creates one User per active tenant with `is_service_account=true`
and `TenantMembership(role="integration")`. The `--print` flag prints
the exact `mint-service-token` command for each seeded row.

## 4. Mint a long-TTL JWT per tenant

For each tenant whose HR will use Hermes:

```bash
python -m scripts.mint_service_token \
    --tenant-id <tenant-uuid> \
    --user-id   <bot-user-uuid> \
    --ttl-days  90
```

Save the printed token securely. You'll paste it into the Hermes profile
env in step 5.

## 5. Profile .env on Hermes host

SSH into the Hermes host (e.g. `root@10.0.5.51`) and append to
`/data/agents/<profile-root>/profiles/recruiter/.env`:

```env
MIRAHIRE_BASE_URL=https://interview.feibo.cn/v2
MIRAHIRE_API_TOKEN=<paste-the-token-from-step-4>
```

If you run Hermes for multiple Feishu/MiraHire tenants from the same
profile, deploy one container instance per tenant with distinct env
files — a single recruiter profile process binds to one
`MIRAHIRE_API_TOKEN` at a time.

## 6. Drop in permissions.yaml

```bash
cp permissions.yaml /data/agents/<profile-root>/profiles/recruiter/permissions.yaml
```

(Or scp from your local clone of this branch.)

## 7. Identity-resolver wiring (already done in this branch)

The identity binding is **already wired** in
`gateway/platforms/feishu.py::_handle_message_event_data` — right after
admission, it calls `bind_identity_for_turn_async(union_id=...)` reading
the sender's `union_id`. The call is a no-op unless `MIRAHIRE_API_TOKEN`
is set, so it's safe for all deployments.

No manual patching needed. Just make sure:
  - The Feishu app event subscription sends `user_id_type=union_id`
    (step 1) so `sender.sender_id.union_id` is populated.
  - `MIRAHIRE_API_TOKEN` + `MIRAHIRE_BASE_URL` are in the profile `.env`
    (step 5).

The binding uses `asyncio.to_thread` for the MiraHire HTTP call so it
never stalls the gateway event loop, and sets a contextvar that the
`mirahire_create_requirement` tool reads via `current_identity()`.

**Runtime-validation note:** the contextvar propagates to tools that run
in the same async task. If a future Hermes version dispatches tool calls
in a detached executor thread, the binding may need to switch to a
session-keyed store (mirroring `tools/approval.py`'s session-key
pattern). Verify in the smoke test (step 9) that the tool resolves the
HR identity correctly.

## 8. Rebuild + deploy the image

```bash
# On your build host:
docker build -t hermes-agent-recruiter:fork-$(date +%Y%m%d) .
docker save hermes-agent-recruiter:fork-$(date +%Y%m%d) | \
    gzip > /tmp/hermes-recruiter.tar.gz
scp /tmp/hermes-recruiter.tar.gz root@10.0.5.51:/tmp/

# On the Hermes host:
ssh root@10.0.5.51 <<'EOF'
gunzip -c /tmp/hermes-recruiter.tar.gz | docker load
docker run -d \
    --name hermes-assis-recruiter-new \
    -v /data/agents/hermes-assis:/opt/data \
    --env-file /data/agents/hermes-assis/profiles/recruiter/.env \
    --restart unless-stopped \
    hermes-agent-recruiter:fork-$(date +%Y%m%d) \
    hermes -p recruiter gateway run

# Verify logs for 30s then cut over:
sleep 30
docker logs --tail 50 hermes-assis-recruiter-new
docker stop hermes-assis-recruiter
docker rm hermes-assis-recruiter
docker rename hermes-assis-recruiter-new hermes-assis-recruiter
EOF
```

## 9. Smoke test in Feishu

1. As a real HR user who's bound their Feishu in MiraHire (e.g. 陈小娇),
   DM the "招聘分析师" bot: 「我想招一个 AI 全栈工程师」
2. The bot should ask 5 followups (业务/阶段/团队/预算/地点).
3. After giving complete answers, the bot should propose a structured
   summary and (under PR#3's OOB approval gate) a Feishu card with
   `[✅ 确认这版]`/`[✏️ 还要调整]` buttons.
4. Click `[✅ 确认这版]`.
5. The bot should reply with a platform URL like
   `https://interview.feibo.cn/v2/integration/recruit/requirements?openExisting=1&id=...`
6. Open the URL in browser → MiraHire shows the new Requirement with
   `status=draft`, `source=hermes`.

## 10. Verify the audit trail

On the MiraHire backend, run:

```bash
psql -d mirahire -c "
SELECT
  rv.version,
  rv.change_kind,
  rv.changed_by_id,
  u.is_service_account,
  rv.changed_at
FROM requirement_versions rv
JOIN users u ON rv.changed_by_id = u.id
WHERE rv.requirement_id = '<id-from-step-9>'
ORDER BY rv.version
"
```

You should see at least `v=1, change_kind=create, is_service_account=true`
— that's the bot writing the snapshot. After the HR edits in the UI you
should see `v=2, change_kind=update, is_service_account=false`.

---

## Troubleshooting

**Bot replies but never proposes the structured card**
- The SOUL.md prompt may need the "写入工具使用" appendix from spec §6.5;
  paste it onto the end of `/data/agents/.../profiles/recruiter/SOUL.md`.

**Tool returns 401 from MiraHire**
- Token expired. Regenerate with `mint_service_token.py` and update
  the profile `.env`.

**Tool returns 403 INTEGRATION_ROLE_REQUIRED**
- The service-account User's TenantMembership is not `role="integration"`.
  Re-check via the platform's `psql` shell.

**Tool returns "Cannot determine MiraHire user identity"**
- The identity-resolver hook wasn't called for this turn. Verify the
  Feishu platform handler patch in step 7 is deployed.

**Tool returns 404 USER_NOT_FOUND_BY_UNION_ID for the right HR user**
- HR user hasn't bound their Feishu in MiraHire (one-time onboarding
  via `/api/v1/auth/feishu/bind`). The bot should reply with a friendly
  prompt to do so — that's tracked as an out-of-scope item in the spec.
