# Hermes Multi-User Permissions (RBAC)

This document explains the permission system added by Epic TEA-88
(`docs/feibo/hermes-rbac-multitenancy-plan.md`): identities, roles,
capabilities, the default policy, how to enable enforcement safely, the admin
commands, and the audit log.

## TL;DR

- Permission enforcement is **off by default**. Existing single-user CLI
  installs behave exactly as before until you opt in.
- When enabled, every actor is an **identity** with **roles**; roles grant
  **capabilities**; tools, skills, dangerous-command approvals, and per-user
  memory are all gated by capabilities.
- All denials and privileged mutations are written to an **audit log**.

## Model

### Identities

Every actor is an `identity` (`agent/permissions/identity.py`):

```
id = "local:owner" | "telegram:123" | "slack:U123" | ...
```

- Local CLI sessions default to the implicit **local owner** (`local:owner`),
  so the single-user experience is unchanged.
- Gateway sessions map `platform:user_id` to an identity before tool execution.

### Roles & capabilities

Default roles (`agent/permissions/policy.py`, `DEFAULT_ROLES`):

| Role     | Capabilities |
|----------|--------------|
| `owner`  | `*` (everything, including `manage.users` / `manage.roles` / `manage.policy`) |
| `admin`  | `skill.*`, `tool.use.*`, `tool.approve.dangerous`, `memory.*`, `read.audit` |
| `member` | `skill.view`, `skill.use`, `tool.use.safe`, `memory.read.self`, `memory.write.self` |
| `mentor` | member + `skill.create`, `skill.update`, `skill.approve` + `tool.use.shell.workspace` — teaches/maintains skills and gets a **workspace-confined shell**; no full host shell, no delete/install, no user admin |
| `guest`  | `skill.view` |

Capabilities support wildcards: `*`, `skill.*`, `tool.use.*`.

**Only `owner` can manage users/roles/policy by default** — `admin` manages
skills/tools/memory and approves dangerous commands, but cannot change who has
which role.

### What is enforced

- **Tools** — schemas are filtered per identity (members never see admin-only
  tools), and `handle_function_call` re-authorizes before dispatch so the model
  cannot bypass the UI by constructing a tool call directly. Shell/browser/MCP
  tools and skill management require capabilities members lack.
- **Skills** — `skill.view`/`skill.use` for members (approved skills only);
  `skill.create`/`update`/`delete`/`install`/`approve` are admin/owner. New or
  edited skills enter `pending_review` and require approval; any content change
  forces re-approval. Members only see approved skills.
- **Dangerous commands** — durable (`session`/`always`) approvals require
  `tool.approve.dangerous`; others are downgraded to a one-shot `once`.
- **Memory** — `USER.md` becomes per-user (`memories/users/<id>/USER.md`);
  `MEMORY.md` stays global; an optional `memories/chats/<chat-id>/CHAT.md` is
  injected for the current chat. Members read/write only their own profile.

### Scoped (workspace-confined) shell

There are two shell capabilities:

- `tool.use.shell` — **full host shell** (owner via `*`, admin via `tool.use.*`);
  uses the configured terminal backend (e.g. `local`).
- `tool.use.shell.workspace` — a **sandboxed shell** confined to the agent's
  working directory (held by `mentor`).

The `terminal` tool admits either, then `terminal_tool` picks the backend by
capability: a holder of only `tool.use.shell.workspace` is forced into a
**Docker sandbox** with the launch cwd mounted at `/workspace`
(`docker_mount_cwd_to_workspace`, `docker_run_as_host_user`), so the shell
cannot read or modify anything outside the workspace. `process`, `execute_code`,
`computer_use`, and `cronjob` remain full-shell only (not granted to mentors).

Set `HERMES_WORKSPACE_SANDBOX_IMAGE` to choose the sandbox image (default: the
configured Docker terminal image). When Hermes itself runs inside a container,
prefer an in-container confinement (read-only rootfs + writable workspace, or a
low-privilege user) over nested Docker.

## Policy file

Policy lives in `~/.hermes/permissions.yaml` (or a `permissions:` block in
`config.yaml`). Example:

```yaml
enabled: true
default_role: guest
owner_id: local:owner
roles:
  owner:    { capabilities: ["*"] }
  admin:    { capabilities: ["skill.*", "tool.use.*", "tool.approve.dangerous", "memory.*", "read.audit"] }
  member:   { capabilities: ["skill.view", "skill.use", "tool.use.safe", "memory.read.self", "memory.write.self"] }
  guest:    { capabilities: ["skill.view"] }
users:
  "local:owner":   { roles: [owner] }
  "telegram:123":  { roles: [member] }
# optional per-tool capability overrides:
tool_capabilities:
  some_tool: tool.use.shell
```

A missing/empty policy file never breaks startup — enforcement simply stays
off. Defining roles/users for unlisted roles merges over the defaults.

## Safe upgrade path (single-user → multi-user)

1. **Migrate your profile** so the owner keeps existing preferences:
   ```
   hermes memory migrate-user-profile
   ```
   This copies the legacy `memories/USER.md` to
   `memories/users/local:owner/USER.md` (legacy kept as a backup).
2. **Assign roles** to the gateway users you expect:
   ```
   hermes permissions grant telegram:123 member
   hermes permissions grant slack:U999 admin
   ```
3. **Turn on enforcement**:
   ```
   hermes permissions enable
   ```
4. **Verify** with `hermes permissions policy` and `hermes audit list`.

To roll back: `hermes permissions disable` (single-user behaviour returns; the
owner falls back to the legacy `USER.md` automatically).

## Commands

```
hermes permissions users                 # list users + roles
hermes permissions roles                 # list roles + capabilities
hermes permissions policy                # show effective policy
hermes permissions grant <identity> <role>
hermes permissions revoke <identity> <role>
hermes permissions enable | disable      # toggle enforcement (owner only)

hermes audit list [--decision allow|deny] [--privileged] [--limit N]

hermes memory migrate-user-profile [--owner-id local:owner]
```

Role/user mutations and the enable/disable toggle are **owner-only** and are
recorded as privileged mutations in the audit log.

## Audit log

Permission decisions and privileged mutations are appended as JSON lines to
`~/.hermes/audit/permissions.jsonl`. Filter with `hermes audit list`:

- `--decision deny` — blocked actions;
- `--decision allow` — allowed decisions;
- `--privileged` — privileged mutations (grants, approvals, skill changes,
  policy edits).

## Hot updates (no restart, no new session)

Role and policy changes apply to a **running gateway on the next message** —
no restart and no `/new`:

- **Engine auto-refresh** — `get_engine()` fingerprints `permissions.yaml` +
  config (mtime/size, ~2s throttle) and rebuilds when they change, so
  `hermes permissions grant/revoke/enable` take effect process-wide.
- **Per-turn identity re-bind** — the gateway re-resolves the caller's identity
  every turn, so the execution guard enforces the *current* role even for a
  cached per-session agent. **Demotions are enforced immediately** (a removed
  capability is denied on the next message; tool visibility also tightens that
  turn because the schema filter runs per call).
- **Rebuild on role change** — when a session's resolved role changes, the
  cached agent is evicted and rebuilt next turn, so a **promotion** (e.g.
  `member -> owner`) exposes the newly-allowed tools on the next message.

Verified live on Feishu: `owner` (runs shell) -> demote to `member` (terminal
refused, no restart) -> promote back to `owner` (terminal runs again), all in
the same conversation.

## Known limitations

- **Skill index in the system prompt is frozen per session.** Tool *execution*
  and *schema* are re-evaluated per turn, but the skill list embedded in the
  system prompt is built once per cached agent (for prefix-cache stability). A
  role change forces an agent rebuild (above), which refreshes it; absent a
  rebuild it can lag until the session resets. Skill *use* itself is still
  enforced live via the tool layer.
- **Engine refresh is throttled (~2s)** to bound per-call `stat()` cost, so a
  policy edit can take up to a couple of seconds to propagate.
- **One-time prefix-cache reset on role change** for the affected session
  (the rebuilt agent starts a fresh prompt prefix). Role changes are rare, so
  this is an acceptable trade-off.
- **Multi-profile in one process:** the process engine reflects the active
  Hermes home; a single process hot-swapping `HERMES_HOME` across profiles is
  not a supported topology (run one gateway per profile).

## Defaults summary

- Enforcement: **off** until `hermes permissions enable`.
- Unknown gateway users get `default_role` (`guest`).
- Bundled/pre-existing skills are trusted (treated as approved).
- The local CLI owner always resolves to `owner`, so you cannot lock yourself
  out by enabling enforcement.
