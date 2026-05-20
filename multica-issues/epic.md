# Epic: Hermes 多用户权限、Skill 治理和用户偏好隔离

## 背景

Hermes 当前已经具备 CLI/TUI、Gateway、多工具、Skill、Memory、Cron/Subagent 等能力，但权限边界仍接近单用户本地助手：入口授权、平台 allowlist、toolset 开关和危险命令审批都有基础，但还没有统一的用户/角色/功能权限模型。

我们要把 Hermes 改造成可被团队安全使用的多用户 Agent runtime：

- 每个真实用户有身份；
- 不同角色可以访问不同功能；
- Skill 更新/安装/删除只能由管理员操作；
- 普通成员只能使用已批准 Skill；
- 用户偏好变成多用户隔离；
- 工具执行和危险审批走统一权限；
- 关键权限决策有审计记录。

## 仓库

GitHub: https://github.com/feibo-ai/hermes-agent

计划文档：

- `docs/feibo/hermes-rbac-multitenancy-plan.md`
- `docs/feibo/hermes-oss-project-reports.md`

## 推荐实施顺序

1. Permission Core：身份、角色、capability、policy loader、audit。
2. Tool/Command Enforcement：工具可见性过滤 + 执行前鉴权 + 危险审批权限。
3. Skill Governance：Skill lifecycle 和 admin-only mutation。
4. Multi-user Preferences：`USER.md` 从 profile-global 改为 user-scoped。
5. Admin UX/Migration：用户/角色管理命令、审计查看、旧 memory 迁移。

## 验收

- owner/admin/member/guest 四类角色可配置；
- member 无法创建/更新/安装/删除 Skill；
- member 可以使用已批准 Skill；
- 两个 gateway 用户的 `USER.md` 偏好互不串；
- 未授权工具调用在执行前被拒绝；
- 危险命令的持久批准只能由 admin/owner 做；
- 所有拒绝和 privileged mutation 都写 audit log；
- 现有单用户 CLI 默认行为兼容。
