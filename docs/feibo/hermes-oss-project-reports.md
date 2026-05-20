# Hermes 多用户权限/Skill/偏好能力开源项目调研报告

日期：2026-05-20

## 结论先行

如果目标是“在 Hermes 上补齐多用户、权限、Skill 管理、用户偏好”，最值得借鉴的是：

1. **LibreChat**：权限模型最完整，尤其是“功能权限 + 资源 ACL + 系统管理权限”三层结构，适合直接参考设计。
2. **Open WebUI**：产品化 Admin/RBAC 做得成熟，尤其对工具/Skill 这种高危能力有明确的权限警告。
3. **AtlasClaw**：理念和你的 Hermes 需求最接近，主打企业多用户、RBAC、Skill、Provider、Webhook，但项目还年轻。
4. **Moxxy**：Agent runtime 方向很像 Hermes，Skill、memory、vault、allowlist、审计都有，适合作为 Hermes 安全执行层参考。
5. **OpenAgent**：更偏“自托管 Agent 平台”，有 SSO、多租户、审计、工具管理，适合看工程化平台壳。
6. **AnythingLLM**：适合知识库/RAG/工作区类场景，多用户和角色简单，但对“Skill 管理权限”不够细。
7. **OpenClaw**：和 Hermes/OpenClaw 类个人 Agent 血缘最接近，Gateway/Skill/Memory 很有参考价值，但官方明确说它不是强多租户 host 权限边界。

综合建议：**不要直接迁移到某个项目；更适合把 Hermes 做成：LibreChat/Open WebUI 式权限模型 + Moxxy/OpenClaw 式 Agent runtime 安全执行 + AtlasClaw 式 Provider/Skill 企业集成。**

## 对比矩阵

| 项目 | 多用户 | RBAC/ACL | Skill/工具权限 | 用户偏好/记忆 | Gateway/多渠道 | 和 Hermes 相似度 | 适合作用 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AtlasClaw | 强 | 强，强调用户权限继承 | 强，Provider + Skill | 有 Session/Memory | Web/UI/Webhook/IM | 高 | 企业版 Hermes 目标架构参考 |
| LibreChat | 强 | 很强，三层权限 | 强，Agent/MCP/Prompt 资源 ACL | 强，Memory 权限 | Web 为主 | 中 | 权限模型蓝本 |
| Open WebUI | 强 | 强，Admin + Group 权限 | 强，Tools/Skills 独立权限 | 强，Memories | Web 为主 | 中 | Admin/RBAC 产品实现参考 |
| OpenAgent | 强 | 中强，SSO/RBAC/审计 | 中强，工具管理/MCP | 中强，RAG/知识库 | Telegram/Discord/WeCom | 中高 | 自托管 Agent 平台参考 |
| AnythingLLM | 中 | 中，Admin/Manager/Default | 中，Agent Skills 但权限粒度粗 | 强，Memories | Telegram 等有限 | 中 | RAG/工作区/普通企业聊天参考 |
| Moxxy | 中强 | 中强，allowlist/capability | 强，Skill quarantine/approval | 强，agent 私有 memory | CLI/TUI/API/Telegram/Discord | 高 | 安全执行层和 Agent runtime 参考 |
| OpenClaw | 中 | 弱到中，pairing/allowlist/session isolation | 中强，Skill 安全扫描/安装警告 | 中强 | 很强，多 IM Gateway | 很高 | Gateway/Skill/Memory 机制参考，不适合作 RBAC 终态 |

## 1. AtlasClaw

项目链接：
- 官网：[atlasclaw.ai](https://atlasclaw.ai/en/)
- GitHub：[CloudChef/atlasclaw](https://github.com/CloudChef/atlasclaw)

### 项目定位

AtlasClaw 是一个企业 AI Agent 框架，目标不是个人助手，而是“一个部署服务多个企业用户”。官网明确主打 multi-user deployment、SSO、RBAC、Skill-based system integration、provider-based integrations、webhook AI integration 和企业批准的模型供应商。

它的核心叙事非常贴近你的需求：员工通过一个对话式 AI 入口访问 CRM、ITSM、监控、HR、财务、OA、Jira 等系统，Agent 执行动作时继承真实用户权限，不绕过原系统授权和审计。

### 架构

官方 README 里给出的结构是“薄核心 + 丰富 Provider”：

- `API Layer`：REST、SSE、WebSocket、Webhook。
- `Agent Engine`：路由、prompt building、tool selection、execution orchestration。
- `Session & Memory`：会话上下文、持久化、检索。
- `Tools & Skills`：可复用执行单元。
- `Provider Registry`：企业系统集成发现和注册。
- `Execution Context`：注入 auth、tenant、runtime scope。

仓库结构也很清楚：

- `app/atlasclaw/api`
- `app/atlasclaw/agent`
- `app/atlasclaw/channels`
- `app/atlasclaw/core`
- `app/atlasclaw/memory`
- `app/atlasclaw/session`
- `app/atlasclaw/skills`
- `app/atlasclaw/tools`
- `app/atlasclaw/workflow`

### 对你需求的覆盖

权限管理：覆盖度高。它把“权限继承”作为核心原则：Agent 不应绕过 RBAC，不应提升权限，企业系统仍然是授权和审计源。

功能级权限：有基础，但需要看具体 Provider 实现。核心仓库强调 Provider 封装认证、skills、scripts；具体企业系统 provider 可能在 sibling repo。

Skill 更新仅管理员：理念支持，但要确认当前实现有没有现成 UI/API。它的 Skill/Provider 结构天然适合加 `skill.create/update/delete/install` 权限。

多用户偏好：有 Session & Memory 模块；企业多用户定位决定它应当支持 user/tenant scope。但要落地前需要审代码确认 memory 是否已按 tenant/user/chat 分层。

### 优点

- 和你的 Hermes 目标最像：不是纯 Chat UI，而是企业 Agent runtime。
- 权限理念非常正确：不让 Agent 成为越权入口，而是继承真实用户权限。
- Provider 模型适合企业系统集成，避免把所有工具硬塞到 Agent core。
- Apache-2.0，适合参考和二次开发。

### 风险

- GitHub 星数很少，当前看到约 30 stars，项目还年轻。
- 核心仓库说明“concrete providers are not implemented in this repository”，真实集成能力可能分散在 provider 仓库。
- 需要代码级验证 RBAC 是否只是架构声明，还是已经贯穿 API、工具执行、Skill 管理。

### 对 Hermes 的借鉴建议

Hermes 可以借鉴 AtlasClaw 的 **ExecutionContext** 思路：

```text
request -> identity -> tenant -> role -> capability -> provider credential/context -> tool/skill execution
```

尤其是把工具执行从“Agent 有什么权限”改成“当前用户在当前平台/项目/系统有什么权限”。这比简单做一个 admin/member 字段更长期正确。

## 2. LibreChat

项目链接：
- 文档：[Access Control](https://www.librechat.ai/docs/features/access_control)
- 文档：[Agents](https://www.librechat.ai/docs/features/agents)
- 文档：[MCP](https://www.librechat.ai/docs/features/mcp)

### 项目定位

LibreChat 是一个自托管 ChatGPT/Agent 平台，重点是多模型、Agents、MCP、代码执行、Artifacts、Memory、Web Search、企业认证。它不是 Hermes 这种本地执行型 CLI/Gateway Agent，但它的权限系统是这批项目里最成熟、最可直接参考的。

### 权限架构

LibreChat 的权限模型是三层组合：

1. **Feature Permissions**：按角色控制某类功能能不能 use/create/share/public share，例如 agents、prompts、MCP servers、memories、web search。
2. **Resource ACLs**：每个具体资源有自己的 ACL，例如某个 agent、prompt、MCP server、file、project 可以授权给 user/group/role/public。
3. **System Grants**：平台级管理权限，例如 `manage:users`、`manage:roles`、`read:usage`。

主体类型包括：

- User
- Group
- Role
- Public

资源权限预设包括 Viewer、Editor、Owner 这样的角色，适合终端用户理解。

### 对你需求的覆盖

权限管理：覆盖度很高。它已经不是简单 RBAC，而是 RBAC + resource ACL + system grant。

各功能管理：覆盖度很高。Feature Permissions 可控制 agent、prompt、MCP server、memory、web search、code run 等功能。

Skill 更新仅管理员：LibreChat 没有 Hermes/OpenClaw 那种 SKILL.md runtime，但它有 Agent、Prompt、MCP Server 的 create/edit/share ACL，完全可以映射成 Hermes Skill 权限。

用户偏好多用户化：覆盖度高。Memory 是 feature permission 的一部分，文档里也明确支持 persistent context。

### 优点

- 权限模型可直接抄作 Hermes 的目标模型。
- 适合企业：支持 group、role、自定义 role、resource ACL、admin panel。
- MCP server 也纳入 ACL，这点对 Hermes 很关键，因为 MCP/Tool/Skill 本质都是高危能力。
- 支持角色/组级配置 override，可给不同团队不同模型、工具、递归限制。

### 风险

- 主要是 Web Chat/Agent 平台，不是本地 CLI/Gateway 执行框架。
- 如果想迁移 Hermes 的“终端、文件、浏览器、Gateway 消息平台”体验，需要额外改很多。
- 它更适合作权限系统参考，不适合作 Hermes 替代品。

### 对 Hermes 的借鉴建议

Hermes 应该直接采用类似三层模型：

```text
Feature Permissions:
  skill.use / skill.create / skill.update / skill.delete / tool.use / memory.read / memory.write

Resource ACL:
  skill:<id> -> viewer/editor/owner
  mcp_server:<id> -> viewer/editor/owner
  memory_scope:<id> -> self/admin

System Grants:
  manage:users / manage:roles / manage:skills / manage:tools / read:audit
```

这可以避免后面权限逻辑散落在 slash command、tool registry、gateway handler 里。

## 3. Open WebUI

项目链接：
- 文档：[RBAC Permissions](https://docs.openwebui.com/features/authentication-access/rbac/permissions/)
- 文档：[Groups](https://docs.openwebui.com/features/authentication-access/rbac/groups/)
- 文档：[Tools](https://docs.openwebui.com/features/extensibility/plugin/tools/)

### 项目定位

Open WebUI 是成熟的自托管 AI Web 平台，支持用户、组、角色、模型、知识库、工具、Prompt、Memory、自动化等。它的定位比 Hermes 更偏 Web UI，但多用户和管理后台做得很扎实。

### 权限架构

Open WebUI 的 RBAC 主要通过 Admin Panel 配置：

- Default Permissions：全局默认权限。
- Group Permissions：组级权限覆盖。
- 用户角色：Pending、Admin、User。
- 权限合并：加法合并，用户在多个组里时取所有授予权限的并集。

它明确列出了：

- Models Access / Import / Export
- Knowledge Access
- Prompts Access / Import / Export
- Tools Access / Import / Export
- Skills Access
- Memories Access
- Automations
- Direct Tool Servers

非常重要的一点：文档明确警告 **Tools Access 接近 root 权限**，因为 Tools/Functions 会执行任意 Python 代码。这和 Hermes Skill 更新/工具安装的风险本质一样。

### 对你需求的覆盖

权限管理：覆盖度高。Admin panel、group permission、default permission 都成熟。

各功能管理：覆盖度高。模型、知识库、Prompt、Tools、Skills、Memory、Automation 都能分别控。

Skill 更新仅管理员：覆盖度高。它有 Skills Access 和 Tools Access 权限概念；不过具体是否能拆成 create/update/delete 要看实现细节。

用户偏好多用户化：覆盖度高。Memories 是独立 feature permission。

### 优点

- 管理后台成熟，适合参考 UI/产品交互。
- 权限项覆盖了你关心的 Tool/Skill/Memory/Automation。
- 对高危工具权限的安全边界讲得很清楚，适合写进 Hermes 管理后台。
- OAuth group sync 等企业身份集成比较现实。

### 风险

- Open WebUI 权限是“加法合并”，没有 deny，复杂企业场景可能需要小心设计默认权限。
- 更偏 Web 平台，不是 Hermes 那种 CLI/Gateway/agent runtime。
- Tool/Function 执行模型和 Hermes 的 SKILL.md/工具注册机制不同。

### 对 Hermes 的借鉴建议

Hermes 的权限 UI 可以学 Open WebUI：

- 默认权限最小化。
- 用 Group 授权高级能力。
- 把 `skill.update`、`tool.install`、`mcp.add` 标为“高危/管理员级”。
- 对任何可执行代码/可改 prompt 的能力显示安全提示。

## 4. OpenAgent

项目链接：
- 官网：[openagentai.org](https://www.openagentai.org/)
- GitHub：[the-open-agent/openagent](https://github.com/the-open-agent/openagent)

### 项目定位

OpenAgent 是一个自托管 Agent 平台，单二进制部署，支持多模型、RAG、agent loops、computer-use、browser-use、coding agent、MCP、工作流、审计和管理面板。

它更像“把 Agent 做成一个完整平台产品”，而不是像 Hermes 那样首先是 CLI/本地智能体。

### 架构/功能

从 README 和官网看，核心能力包括：

- 30+ model providers。
- Browser-use、web search/fetch、shell execution、office automation、MCP integration。
- RAG/Knowledge Base，隔离知识库。
- Workflow automation，BPMN 风格 workflow builder，定时任务。
- OIDC/OAuth2/LDAP/SAML SSO。
- Multi-tenancy。
- Audit logs。
- Tool management。
- Telegram、Discord、WeCom 等 gateway/channel。

GitHub 当前显示约 4.8k stars、Apache-2.0、Go + TypeScript。

### 对你需求的覆盖

权限管理：覆盖度中高。官网/README 声称有 SSO、RBAC、多租户、审计，但需要进一步看 authz 模块细节。

各功能管理：覆盖度中高。有 Tool Management、MCP、workflow、knowledge base，但具体权限粒度要验证。

Skill 更新仅管理员：中等。它有 `skills` 目录和工具管理，但不确定是否像 Open WebUI 那样把 Skills Access 独立出来。

用户偏好多用户化：中高。多租户、知识库隔离、用户/组织 workspace 方向明确。

### 优点

- 更接近“企业 Agent 平台”而非纯 Chat UI。
- 单二进制部署很友好。
- Gateway/channel + MCP + shell/browser/code/office automation 组合接近 Hermes 能力面。
- 有审计和管理面板，适合看平台化实现。

### 风险

- 官网声称“20+ messaging channels”，但当前页面明确列出的通道主要是 Telegram、Discord、WeCom，README 也列 3 个，需要以代码为准。
- 权限粒度未必达到 LibreChat/Open WebUI 的成熟程度。
- 项目功能面大，迁移成本较高。

### 对 Hermes 的借鉴建议

OpenAgent 最值得参考的是平台壳：

- 单服务/单二进制部署思路。
- Admin dashboard：usage、activity、tool management、request logs。
- SSO + audit + tool management 做成一条线。

如果 Hermes 要变成企业内部服务，OpenAgent 是值得进一步代码级拆解的对象。

## 5. AnythingLLM

项目链接：
- 文档首页：[AnythingLLM Docs](https://docs.anythingllm.com/)
- 文档：[Security and Access](https://docs.anythingllm.com/features/security-and-access)
- 文档：[AI Agents](https://docs.anythingllm.com/features/ai-agents)
- 文档：[Memories & Personalization](https://docs.anythingllm.com/features/memories)
- 文档：[Custom Agent Skills](https://docs.anythingllm.com/agent/custom/introduction)

### 项目定位

AnythingLLM 是一个成熟的自托管 AI workspace/RAG/Agent 平台。它很适合团队知识库、文档问答、工作区聊天、Agent Skills、MCP、定时任务等场景。

### 权限架构

AnythingLLM Docker 版本支持 single-user 和 multi-user mode。多用户模式下有三类角色：

- Admin：完整系统权限。
- Manager：可查看所有 workspace，管理大部分属性，但不能改 LLM/Embedder/Vector DB 设置。
- Default：只能向明确加入的 workspace 发送聊天，不能看或改 workspace/system settings。

官方文档提醒：一旦切到 multi-user mode，不能退回 single-user mode。

### 对你需求的覆盖

权限管理：中等。角色清晰但粒度不如 LibreChat/Open WebUI。

各功能管理：中等。Workspace 权限较好，但功能级权限不够细。

Skill 更新仅管理员：中等偏弱。支持 built-in skills/custom skills，但公开文档里没有看到非常细的 per-skill ACL/RBAC。

用户偏好多用户化：强。Memories & Personalization 是明确功能，工作区和用户也天然分离。

### 优点

- 成熟、易部署、文档完善。
- RAG/Workspace/文档知识库能力很强。
- 内置多种 Agent Skills，如 RAG Search、Web Browsing、SQL Agent、File System Agent、Gmail/Calendar/Outlook 等。
- 对普通企业知识助手足够实用。

### 风险

- RBAC 粒度偏粗：Admin/Manager/Default 三档不够支撑你说的“每个功能管理、Skill 更新仅管理员”。
- 更偏知识库和工作区，不是 Hermes 类本地执行/Gateway Agent。
- 如果你要的是“多渠道消息入口 + 本地工具执行 + skill 生命周期治理”，AnythingLLM 只能参考一部分。

### 对 Hermes 的借鉴建议

可以借鉴它的 Workspace 模型：

```text
workspace -> members -> role -> allowed agents/tools/docs/memories
```

但 Hermes 权限不应只做三档角色，至少要 capability-based。

## 6. Moxxy

项目链接：
- 文档：[docs.moxxy.ai](https://docs.moxxy.ai/)
- GitHub：[moxxy-ai/moxxy](https://github.com/moxxy-ai/moxxy)

### 项目定位

Moxxy 是一个自托管 autonomous AI agents runtime。它和 Hermes 的相似度很高：Agent 有自己的 workspace、memory、vault secrets，可以使用文件系统、git、shell、HTTP、浏览器、Playwright、MCP、skills、cron、webhooks 和多 agent 编排。

### 架构/功能

官方 README 强调：

- 每个 agent 有 isolated workspace、private memory、scoped secrets。
- 85 built-in primitives：filesystem、git、shell、HTTP、browsing、headless browser、memory、webhooks、vault、MCP、skills 等。
- Agents 只能使用 allowlist 明确授权的 primitives。
- Skills 是带 YAML frontmatter 的 Markdown 文件，可定义能力和权限。
- Skills 初始 quarantine，必须显式 approve 才能使用。
- WASI plugin system，capability-based permissions。
- cron heartbeat。
- SSE 事件流和 audit logging。

### 对你需求的覆盖

权限管理：中强。它不一定是传统企业 RBAC，但 capability/allowlist 很强。

各功能管理：强。Primitive allowlist 可以控制文件、shell、HTTP、browser、memory、MCP、skills 等。

Skill 更新仅管理员：强。Skill quarantine + approval 机制非常贴合你的需求。

用户偏好多用户化：中强。每个 agent 有私有 memory；但用户级/组织级多用户权限需要进一步看 auth 模块。

### 优点

- 和 Hermes runtime 很像，尤其是工具执行、sub-agent、cron、memory、skills。
- 安全执行模型比传统 Chat 平台更贴 Agent：allowlist、vault、domain-gated networking、secret redaction、audit events。
- Skill 生命周期治理更接近你关心的“管理员才能更新/批准”。
- MIT license。

### 风险

- 当前更像 agent runtime，不一定有成熟企业用户/RBAC UI。
- 需要确认多用户身份体系是否足够产品化。
- 项目仍偏新，生产成熟度需要压测和代码审查。

### 对 Hermes 的借鉴建议

Hermes 可以重点借鉴 Moxxy 的两件事：

1. **Capability allowlist**：角色不要直接控制“工具名字”，而是控制 capability，例如 `filesystem.read.project`、`shell.run.safe`、`http.fetch.public`。
2. **Skill quarantine**：新安装/更新 Skill 默认隔离，管理员审批后才进入可用状态。

## 7. OpenClaw

项目链接：
- Gateway Security 文档：[openclaw/docs/gateway/security](https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md)
- Gateway Configuration 文档：[configuration-reference](https://github.com/openclaw/openclaw/blob/main/docs/gateway/configuration-reference.md)

### 项目定位

OpenClaw 是自托管个人 AI Agent/Gateway，特点是多消息渠道、Skill、Memory、MCP、工具执行和本地自动化。它和 Hermes 这类 Agent 的血缘/形态最接近。

### 多用户与安全边界

OpenClaw 的官方安全文档有一个关键判断：它不是 hostile multi-tenant security boundary。换句话说，它可以做消息会话隔离、DM pairing、allowlist，但不能把“多个互不信任用户共享一个工具型 Agent”变成严格 host 权限隔离。

它支持：

- DM policy：pairing、allowlist、open、disabled。
- pairing code，有过期和 pending 上限。
- DM session isolation：`per-channel-peer` 或 `per-peer`。
- Gateway skill dependency install 的 dangerous/suspicious 分类。
- 对 hook payload/prompt injection 的安全提醒。

### 对你需求的覆盖

权限管理：中等偏弱。入口授权和 session 隔离有，但不是完整 RBAC。

各功能管理：中等。可通过 tool profile/skills/gateway config 控制，但不等价于企业 feature permission。

Skill 更新仅管理员：部分支持。安全文档有 skill install 风险和阻断机制，但完整管理员审批/资源 ACL 需要补。

用户偏好多用户化：中等。DM session isolation 可减少用户上下文串扰，但官方明确说这不是 host-admin 权限边界。

### 优点

- Gateway、多 IM 平台、Skill、Memory 形态很适合 Hermes 借鉴。
- 对 prompt injection、skill install、DM pairing 的安全风险认识清楚。
- session isolation 机制能作为 Hermes 多用户偏好第一阶段参考。

### 风险

- 不适合直接作为企业 RBAC 终态。
- 共享 Agent 权限集时，任何被允许发消息的人都可能驱动同一组 host/tool 权限。
- Skill 生态安全风险高，必须有签名/扫描/审批/隔离/审计。

### 对 Hermes 的借鉴建议

OpenClaw 对 Hermes 的价值不是“拿来当权限系统”，而是提醒你不要犯一个错：

```text
多用户 session isolation != 多用户权限隔离
```

Hermes 要做企业多用户，必须在 tool execution 前检查当前用户 capability，而不能只靠不同 session/memory 文件夹。

## 推荐路线

### 如果继续改 Hermes

建议做四层：

1. **Identity**
   - platform user id：telegram/slack/discord/feishu/wecom/local。
   - user mapping：绑定到 Hermes 内部 user。
   - group/team/tenant。

2. **Capability**
   - `skill.view`
   - `skill.use`
   - `skill.create`
   - `skill.update`
   - `skill.delete`
   - `skill.install`
   - `tool.use.shell`
   - `tool.use.filesystem`
   - `tool.use.browser`
   - `memory.read.self`
   - `memory.write.self`
   - `memory.read.any`
   - `memory.write.any`
   - `manage.users`
   - `manage.roles`
   - `read.audit`

3. **Resource ACL**
   - 某个 Skill 谁能 view/use/edit/owner。
   - 某个 MCP server 谁能 use/edit。
   - 某个 project/workspace 谁能访问。

4. **Runtime Enforcement**
   - gateway ingress 检查用户身份。
   - slash command 注册时过滤命令。
   - tool registry 根据 capability 过滤可见工具。
   - tool execution 前二次鉴权。
   - skill_manage/memory/tool install 走管理员权限。
   - 危险命令 approval 只能 admin/owner approve。
   - 所有拒绝/执行写 audit log。

### 最小 MVP

1. `users.yaml`

```yaml
users:
  "local:xmfb":
    role: owner
  "telegram:123456":
    role: member
roles:
  owner:
    capabilities: ["*"]
  admin:
    capabilities:
      - "skill.*"
      - "tool.use.*"
      - "memory.*"
      - "manage.users"
      - "read.audit"
  member:
    capabilities:
      - "skill.view"
      - "skill.use"
      - "memory.read.self"
      - "memory.write.self"
      - "tool.use.safe"
  guest:
    capabilities:
      - "skill.view"
```

2. Skill 生命周期：

```text
draft -> pending_review -> approved -> active -> disabled
```

3. 用户偏好目录：

```text
~/.hermes/memories/
  global/MEMORY.md
  users/<user-id>/USER.md
  chats/<platform-chat-id>/CHAT.md
```

4. 执行鉴权：

```text
before_tool_call(ctx, tool, action, resource):
  identity = ctx.user
  required = policy.required_capability(tool, action)
  assert permission_engine.can(identity, required, resource)
```

### 如果要参考/二次开发一个项目

优先级：

1. **LibreChat**：抄权限模型。
2. **Open WebUI**：抄 Admin/RBAC 产品化。
3. **Moxxy**：抄 runtime capability/skill quarantine/audit。
4. **AtlasClaw**：抄 Provider/ExecutionContext 企业集成架构。
5. **OpenAgent**：抄单服务平台和管理面板。
6. **AnythingLLM**：抄 workspace/RAG/memory 产品体验。
7. **OpenClaw**：抄 Gateway/session/skill 安全提醒，但不要抄成最终 RBAC。

## 最终判断

目前没有一个项目 100% 完整覆盖你对 Hermes 的全部需求：

- 多用户；
- 每个功能可管；
- 用户/角色权限划分；
- Skill 更新仅管理员；
- 用户偏好多用户隔离；
- 同时保持 Hermes 的 CLI/TUI/Gateway/local tool execution 形态。

最接近的是 **AtlasClaw + Moxxy** 的方向，但最成熟的权限设计在 **LibreChat + Open WebUI**。所以最佳路线不是换项目，而是在 Hermes 上做一个统一权限层，并把 Skill/Memory/Gateway/Tool 都接进去。

## Sources

- [AtlasClaw 官网](https://atlasclaw.ai/en/)
- [CloudChef/atlasclaw GitHub](https://github.com/CloudChef/atlasclaw)
- [LibreChat Access Control](https://www.librechat.ai/docs/features/access_control)
- [LibreChat Agents](https://www.librechat.ai/docs/features/agents)
- [LibreChat MCP](https://www.librechat.ai/docs/features/mcp)
- [Open WebUI RBAC Permissions](https://docs.openwebui.com/features/authentication-access/rbac/permissions/)
- [Open WebUI Groups](https://docs.openwebui.com/features/authentication-access/rbac/groups/)
- [Open WebUI Tools](https://docs.openwebui.com/features/extensibility/plugin/tools/)
- [OpenAgent 官网](https://www.openagentai.org/)
- [the-open-agent/openagent GitHub](https://github.com/the-open-agent/openagent)
- [AnythingLLM Docs](https://docs.anythingllm.com/)
- [AnythingLLM Security and Access](https://docs.anythingllm.com/features/security-and-access)
- [AnythingLLM AI Agents](https://docs.anythingllm.com/features/ai-agents)
- [AnythingLLM Memories](https://docs.anythingllm.com/features/memories)
- [Moxxy Docs](https://docs.moxxy.ai/)
- [moxxy-ai/moxxy GitHub](https://github.com/moxxy-ai/moxxy)
- [OpenClaw Gateway Security](https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md)
- [OpenClaw Gateway Configuration](https://github.com/openclaw/openclaw/blob/main/docs/gateway/configuration-reference.md)
