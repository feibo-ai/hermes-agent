# Phase 2: 工具和命令执行前鉴权

## 目标

把权限核心接到工具和 slash command 执行路径，避免“LLM 直接构造 tool call”绕过 UI/命令层权限。

## 建议改动

- tool schema 暴露前按 identity capability 过滤。
- `handle_function_call` 执行前做二次鉴权。
- CLI/gateway slash command 对 privileged command 做权限检查。
- dangerous command approval 要求 `tool.approve.dangerous`。
- 权限拒绝写 audit log。

## 验收

- member 看不到 admin-only tool schema。
- member 直接构造 admin-only tool call 会被拒绝。
- guest/member 不能做 durable dangerous approval。
- owner/admin 可以按策略批准危险命令。
- audit log 能追踪 denied tool call。
