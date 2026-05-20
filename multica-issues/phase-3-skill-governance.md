# Phase 3: Skill 生命周期和管理员更新权限

## 目标

把 Skill 的“使用”和“修改”拆开：普通用户可以使用已批准 Skill，但创建、更新、安装、删除、同步、批准都必须是 admin/owner。

## 建议能力点

- `skill.view`
- `skill.use`
- `skill.create`
- `skill.update`
- `skill.delete`
- `skill.install`
- `skill.approve`

## 建议生命周期

```text
draft -> pending_review -> approved -> active -> disabled
```

## 验收

- member 可以 list/view/use approved skill。
- member 不能 create/update/install/delete skill。
- admin/owner 可以修改和批准 skill。
- skill 内容变化后需要重新 approval 或进入 pending_review。
- 所有 skill mutation 写 audit log。
