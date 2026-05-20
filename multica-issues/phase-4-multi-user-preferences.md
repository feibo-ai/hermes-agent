# Phase 4: 用户偏好改成多用户隔离

## 目标

把当前 profile-global 的 `USER.md` 改造成 per-user profile，Gateway 多用户场景下只注入当前用户自己的偏好。

## 建议目录

```text
~/.hermes/memories/
  global/MEMORY.md
  users/<identity-id>/USER.md
  chats/<platform-chat-id>/CHAT.md
```

## 注入规则

- 注入 global memory。
- 注入当前 user 的 `USER.md`。
- 如存在 chat/team profile，注入当前 chat 的 `CHAT.md`。
- 不注入其他用户 profile，除非具备 `memory.read.any`。

## 验收

- 两个 gateway 用户得到不同 `USER.md` snapshot。
- member 只能读写自己 profile。
- admin/owner 可管理其他用户 profile。
- 旧单用户 `USER.md` 可迁移到 owner profile。
