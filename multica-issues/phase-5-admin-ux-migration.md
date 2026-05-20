# Phase 5: 管理命令、审计和迁移

## 目标

给管理员最小可用 UX：能看 policy、管用户/角色、看 audit，并安全迁移已有单用户 memory。

## 建议命令

- `hermes permissions users list`
- `hermes permissions roles list`
- `hermes permissions grant <identity> <role>`
- `hermes permissions revoke <identity> <role>`
- `hermes permissions policy show`
- `hermes audit list`
- `hermes memory migrate-user-profile`

## 验收

- owner 可以授予/撤销角色。
- 非 owner 不能修改 roles/users。
- audit log 可按 denied/allowed/privileged mutation 过滤。
- 旧 `USER.md` 迁移后 CLI 行为保持兼容。
- 文档解释默认策略和安全升级路径。
