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

## 1. Feishu app configuration (one-time)

Log into the Feishu Open Platform: <https://open.feishu.cn>.

1. Open the "招聘分析师" app (`cli_aa87c42bb4785bd0` — confirm via
   `lark-cli` or the existing `.env` on the host).
2. Navigate to **应用功能 → 事件订阅 → 事件配置**.
3. Change the **user_id_type** field from `open_id` to `union_id` and save.
4. (Optional) Verify by sending the bot a message and inspecting the
   event log: `sender.sender_id.union_id` should now be populated.

This change is critical — Hermes needs `union_id` to bridge to MiraHire's
`User.feishu_union_id` (different Feishu apps issue different `open_id`s
but share `union_id`s across the same Feishu tenant).

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

## 7. Wire the identity-resolver into the Feishu platform handler

In `gateway/platforms/feishu.py` (or wherever the Feishu inbound message
handler is in your deployment), at the start of each new inbound user
message:

```python
from gateway.hooks.mirahire_identity import bind_identity_for_turn

bind_identity_for_turn(union_id=event.sender.sender_id.union_id)
```

(Adjust attribute path to match the Feishu event SDK version in use.)

If you'd rather not patch the platform handler, an alternative is to
register a hermes hook for `agent:start` and call
`bind_identity_for_turn` there, reading `union_id` from the event
context that hermes provides.

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
