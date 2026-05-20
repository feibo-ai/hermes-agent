# Phase 1: 建立 Hermes Permission Core

## 目标

新增一个统一权限核心，先不大规模改变业务行为，只把身份、角色、capability、policy 解析、鉴权和审计事件结构打稳。

## 建议改动

- 新增 `agent/permissions/identity.py`
- 新增 `agent/permissions/policy.py`
- 新增 `agent/permissions/engine.py`
- 新增 `agent/permissions/audit.py`
- 支持从 Hermes home/config 读取 policy。
- 支持 wildcard capability，例如 `skill.*`、`tool.use.*`、`*`。
- 支持默认 local owner identity，避免破坏单用户 CLI。

## 验收

- 单测覆盖 owner/admin/member/guest。
- 单测覆盖 wildcard capability。
- 单测覆盖 deny case。
- 单测覆盖 audit event shape。
- 现有 CLI 启动不因缺少 policy 文件失败。
