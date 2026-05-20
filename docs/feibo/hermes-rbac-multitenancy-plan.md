# Hermes RBAC, Skill Governance, and Multi-User Memory Plan

Date: 2026-05-20
Owner org: feibo-ai
Source fork: https://github.com/feibo-ai/hermes-agent
Upstream: https://github.com/NousResearch/hermes-agent

## Goal

Turn Hermes from a mostly single-user/local-agent runtime into a controllable multi-user agent platform while preserving the existing CLI, gateway, tool, skill, memory, and local execution model.

The first delivery should prove:

- real user identity is available across CLI/gateway/tool execution paths;
- user roles can control feature access;
- skill creation/update/install/delete is admin-only;
- normal users can use approved skills without mutating them;
- user preferences are isolated per user and injected only for the active user;
- dangerous tool approvals can be restricted to owner/admin users;
- denied actions and privileged mutations are audit logged.

## Current Hermes Baseline

Hermes already has useful foundations:

- gateway source context carries platform, user, chat, thread, and session metadata;
- pairing and allowlist logic gate some messaging-platform access;
- platform toolsets can enable/disable broad tool groups;
- dangerous terminal command approval already exists;
- skills are discovered and injected through prompt builder/tooling paths;
- built-in memory uses `MEMORY.md` and `USER.md`;
- external memory providers already receive user/chat/platform context.

Current gaps:

- no unified role/capability permission engine;
- no per-user feature permissions;
- no resource ACL for skills, tools, MCP servers, projects, or memories;
- skill mutation is not separated from skill usage at policy level;
- built-in `USER.md` is profile-global, not multi-user scoped;
- gateway pairing/session isolation is not a host-admin authorization boundary;
- audit logging for permission decisions is not first-class.

## Target Model

### Identities

Represent every actor as:

```text
identity = {
  id: "telegram:123456" | "slack:U123" | "local:xmfb" | ...,
  display_name: string,
  platform: string,
  roles: string[],
  groups: string[],
  tenant_id?: string
}
```

CLI sessions should default to a local owner identity unless explicitly configured otherwise.

Gateway sessions should map platform user ids into Hermes users before tool execution.

### Roles

Initial roles:

- `owner`: all capabilities, can manage roles/users.
- `admin`: manage skills/tools/memory for a workspace, approve dangerous actions.
- `member`: use approved skills and safe tools, manage own user preferences.
- `guest`: limited read/use capability only.

### Capabilities

Core capabilities:

```text
skill.view
skill.use
skill.create
skill.update
skill.delete
skill.install
skill.approve

tool.use.safe
tool.use.shell
tool.use.filesystem
tool.use.browser
tool.use.mcp
tool.approve.dangerous

memory.read.self
memory.write.self
memory.read.any
memory.write.any
memory.admin

manage.users
manage.roles
manage.policy
read.audit
```

Capabilities should support wildcards, for example `skill.*` and `tool.use.*`.

### Resource ACL

Add optional ACLs for high-value resources:

```text
skill:<skill_id> -> viewer/editor/owner
mcp_server:<server_id> -> viewer/editor/owner
memory_scope:<user_id> -> self/admin
project:<project_id> -> viewer/editor/owner
```

The MVP can start with role/capability checks and add resource ACL in Phase 2.

## Proposed Implementation Phases

### Phase 1: Permission Core

Add a small central permission package:

```text
agent/permissions/
  __init__.py
  identity.py
  policy.py
  engine.py
  audit.py
```

Responsibilities:

- load policy from Hermes config/home;
- resolve identity from agent/gateway/CLI context;
- evaluate `can(identity, capability, resource=None)`;
- emit structured audit events for allow/deny and privileged mutations.

Acceptance:

- unit tests cover role inheritance, wildcard capabilities, denied access, and audit event shape;
- no tool behavior changes yet except identity resolution tests.

### Phase 2: Tool and Slash Command Enforcement

Wire permission checks into:

- tool schema filtering before LLM calls;
- tool execution guard before `handle_function_call`;
- CLI/gateway slash command dispatch for privileged commands;
- dangerous command approval so only owner/admin can grant durable approval.

Acceptance:

- member identity cannot see or call admin-only tools;
- direct tool-call bypass attempts are rejected before execution;
- terminal dangerous approvals require `tool.approve.dangerous`;
- audit logs include denied tool calls.

### Phase 3: Skill Governance

Split skill permissions by action:

- view/list/use: available to members for approved skills;
- create/update/delete/install/sync/approve: admin-only;
- new or changed skills enter `pending_review` or `disabled` state until approved.

Suggested lifecycle:

```text
draft -> pending_review -> approved -> active -> disabled
```

Acceptance:

- member can list/view/use approved skills;
- member cannot update skill content or install new skills;
- admin can update/approve skills;
- updated skills require re-approval when content changes;
- privileged mutations are audited.

### Phase 4: Multi-User User Preferences

Replace profile-global user memory injection with layered memory:

```text
~/.hermes/memories/
  global/MEMORY.md
  users/<identity-id>/USER.md
  chats/<platform-chat-id>/CHAT.md
```

Prompt injection should include:

- global memory;
- current user's `USER.md`;
- current chat/team profile when available;
- never another user's profile unless `memory.read.any` is granted.

Acceptance:

- two gateway users receive different `USER.md` profile snapshots;
- one user cannot read/write another user's profile as member;
- owner/admin can inspect or migrate profiles with explicit capability.

### Phase 5: Admin UX and Migration

Add command/config surfaces:

- list users/roles;
- grant/revoke role;
- inspect policy;
- view audit log;
- migrate existing `USER.md` into owner profile.

Acceptance:

- existing single-user users keep working;
- migration creates owner identity and preserves old preferences;
- docs explain safe defaults and upgrade path.

## Policy MVP Example

```yaml
permissions:
  users:
    local:xmfb:
      roles: [owner]
  roles:
    owner:
      capabilities: ["*"]
    admin:
      capabilities:
        - "skill.*"
        - "tool.use.*"
        - "tool.approve.dangerous"
        - "memory.*"
        - "manage.users"
        - "manage.roles"
        - "read.audit"
    member:
      capabilities:
        - "skill.view"
        - "skill.use"
        - "tool.use.safe"
        - "memory.read.self"
        - "memory.write.self"
    guest:
      capabilities:
        - "skill.view"
```

## Test Strategy

- Unit tests for permission engine, identity mapping, policy loading, and wildcard matching.
- Tool-dispatch tests proving direct unauthorized tool calls are denied.
- Skill-management tests for create/update/install approval gates.
- Gateway tests with two users to prove profile isolation.
- Regression tests for existing single-user memory behavior after migration.

## Open Decisions

1. Should policy live in `~/.hermes/config.yaml`, a separate `permissions.yaml`, or both?
2. Should resource ACL ship in MVP or Phase 2?
3. Should skill approval be required for local CLI owner changes, or only gateway/multi-user mode?
4. Should `member` have browser/file read access by default, or should all host tools be admin-granted?
5. What should the default identity be for local CLI in CI and batch mode?

## References

- Detailed OSS comparison: `docs/feibo/hermes-oss-project-reports.md`
- Permission model inspirations: LibreChat access control, Open WebUI RBAC, Moxxy capability allowlists, AtlasClaw provider execution context.
