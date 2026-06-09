# ADR-029 用户自定义 Agent 设计

## 一、决策结论

**Agent = Definition（数据），Agent ≠ Runtime Class（代码）。**

用户自建 Agent 的本质是创建一个 **Agent Definition** 配置记录，包含 System Prompt、工具绑定、路由策略。运行时通过统一的 `PromptBuilder → SkillRouter → Provider` 管线执行，不动态生成 Agent 类。

与之配套的 Provider / Skill / Agent 三层彻底分离，解决当前 `claude_code` 既像 Agent 又像 Skill 的概念混乱。

---

## 二、背景

### 当前问题

1. **概念混乱**：`claude_code` 在 `agents.registry.json` 中是 Agent，在 `skills.registry.json` 中是 Skill，在 `.env` 中是 Provider。同一实体跨三层定义，新人无法理解。
2. **用户无法扩展**：Agent 硬编码在 `runtime/agents/` 目录下，用户想加一个 "Backend Architect" 需要写 Python 类。
3. **比赛要求**：支持用户自建 Agent（对话式创建，设定 System Prompt + 工具集），支持多 Agent 群聊协作。

### 设计原则

```
❌ Agent = Python Class  (AutoGPT 模式 — 太重，不安全)
✅ Agent = Definition   (配置驱动 — 轻量，可审计，可市场)
```

### Agent 的两类形态

AgentHub 中 Agent 存在两种形态，二者职责不同、存储方式不同、生命周期不同：

```
┌──────────────────────────────────────────────────────┐
│                   RuntimeAgent                        │
│  (Python dataclass — 系统内置，不可被用户删除)          │
│                                                      │
│  CodingAgent     — 生成代码变更                        │
│  ReviewAgent     — 审查代码质量                        │
│  TestAgent       — 生成测试用例                        │
│  DocAgent        — 生成文档                            │
│  PlannerAgent    — 拆解任务计划                        │
│  ArtifactAgent   — 归档产物                            │
│                                                      │
│  特点：固定角色、固定 handle() 方法、绑定 workflow_stage │
│  存储：runtime/agents/*.py (Python 代码)               │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│                 UserDefinedAgent                      │
│  (数据库记录 — 用户创建，可复制/修改/删除)               │
│                                                      │
│  Backend Architect  — Go 后端架构专家                  │
│  Frontend Engineer  — React 前端工程师                 │
│  DevOps Engineer    — 部署运维专家                     │
│  QA Engineer        — 质量保证工程师                   │
│  Security Reviewer  — 安全审查专家                     │
│  Java Interview Coach — 用户自定义的面试教练            │
│                                                      │
│  特点：Agent Definition = 数据，Persona + Tools + Route │
│  存储：agent_definitions 表 (SQLite / PostgreSQL)      │
└──────────────────────────────────────────────────────┘
```

**关键**：

- **RuntimeAgent** 是系统骨架——定义了 pipeline 中必需的 6 个角色，每个有明确的 stage 绑定
- **UserDefinedAgent** 是用户皮肤——在 RuntimeAgent 之上叠加 Persona + 工具白名单 + Provider 偏好
- UserDefinedAgent **不替代** RuntimeAgent，而是**穿在 RuntimeAgent 外面**：用户选 Backend Architect 执行 coding 时，底层的 RuntimeAgent 仍是 CodingAgent，但 System Prompt 来自 Backend Architect 的 persona

---

## 三、三层分离架构

```
┌─────────────────────────────────────────────┐
│                  AGENT                       │
│  Backend Architect · Security Reviewer · ... │
│  (Persona + System Prompt + 允许哪些 Skill)   │
└──────────────────┬──────────────────────────┘
                   │ allowed_skills
                   ▼
┌─────────────────────────────────────────────┐
│                  SKILL                       │
│  coding · review · read_file · write_file ·  │
│  search_code · run_command · git_diff · ...  │
│  (能力抽象 — 与 Agent 和 Provider 解耦)       │
└──────────────────┬──────────────────────────┘
                   │ preferred_provider
                   ▼
┌─────────────────────────────────────────────┐
│                PROVIDER                      │
│  Claude Code · Codex · OpenAI · Gemini · ... │
│  (底层执行引擎 — 可无感知替换)                 │
└─────────────────────────────────────────────┘
```

**关系链**：

```
Agent ──允许调用──▶ Skill ──路由到──▶ Provider
  1:N               1:N               1:1 (每次调用)
```

示例：

```yaml
Backend Architect:
  allowed_skills: [coding, review, read_file, write_file]
  preferred_provider: claude_code

Security Reviewer:
  allowed_skills: [review, read_file, search_code]
  preferred_provider: claude_code
```

---

## 四、Agent Definition 数据模型

### 4.1 核心字段

```yaml
id: backend_architect                    # 唯一标识
name: Backend Architect                  # 显示名
avatar: backend.png                      # 头像
description: Go 后端架构专家，擅长 Gin + GORM  # 一句话描述

system_prompt: |                         # 核心 Persona
  你是一名资深 Go 后端架构师。
  你擅长：
  - Gin 框架的 API 设计
  - GORM 数据模型设计
  - 微服务架构
  - 代码审查
  你的代码风格偏好：
  - 清晰的分层架构（handler → service → repository）
  - 完善的错误处理
  - 有意义的变量命名

allowed_skills:                          # 允许调用的 Skill
  - coding
  - review
  - read_file
  - write_file

preferred_provider: claude_code          # 首选执行引擎

visibility: public                       # public | private | unlisted

created_by: user_xxx                     # 创建者
created_at: 2026-06-08T10:00:00Z
updated_at: 2026-06-08T10:00:00Z
```

### 4.2 存储

```sql
CREATE TABLE agent_definitions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    avatar      TEXT DEFAULT '',
    description TEXT DEFAULT '',
    system_prompt TEXT NOT NULL,
    allowed_skills TEXT NOT NULL,          -- JSON array: ["coding", "review"]
    preferred_provider TEXT DEFAULT 'claude_code',
    visibility  TEXT DEFAULT 'private',    -- public | private | unlisted
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

Gateway 侧新增 `AgentDefinitionStore` 接口，SQLite 先行，后续迁移到 PostgreSQL。

### 4.3 内置预置 Agent

系统内置 5 个 Agent，存入 `agent_definitions` 表，`created_by = 'system'`，`visibility = 'public'`：

| ID | Name | Skills | Provider |
|---|---|---|---|
| `backend_architect` | Backend Architect | coding, review, read_file, write_file | claude_code |
| `frontend_engineer` | Frontend Engineer | coding, review, read_file, write_file | claude_code |
| `devops_engineer` | DevOps Engineer | coding, run_command, git_diff | claude_code |
| `qa_engineer` | QA Engineer | review, read_file | claude_code |
| `security_reviewer` | Security Reviewer | review, read_file, search_code | claude_code |

---

## 五、运行时管线

### 5.1 用户视角

用户在对话中输入：

```
@Backend Architect 帮我写一个 Gin 登录接口
```

### 5.2 系统执行链

```
① Gateway 解析 @mention → 查找 agent_definitions
                          │
                          ▼
② Prompt Builder 组装上下文
   ┌─────────────────────────────────────────┐
   │ System Prompt (from Agent Definition)    │
   │ + Task Instruction (user input)          │
   │ + Context (files, dependencies, etc.)    │
   │ + Output Format (JSON schema)            │
   └─────────────────────────────────────────┘
                          │
                          ▼
③ Skill Router 决策
   "coding" stage → 选 coding skill
   根据 preferred_provider → 选 claude_code
                          │
                          ▼
④ Provider 执行
   claude -p "<assembled prompt>" --permission-mode bypassPermissions
                          │
                          ▼
⑤ 结果归一化 → 返回用户
```

**关键**：Agent Definition 本身不包含任何执行逻辑。它只是 Prompt 的输入源 + Skill 的白名单。

### 5.3 Prompt Builder

```python
def build_agent_prompt(agent_def: AgentDefinition, task: TaskContext) -> str:
    return f"""{agent_def.system_prompt}

## 当前任务
{task.instruction}

## 目标文件
{task.target_files}

## 约束
- 你可以使用以下能力：{', '.join(agent_def.allowed_skills)}
- 输出格式：JSON
"""
```

---

## 六、工具集分级设计

不开放任意工具。工具按风险分层，Agent 创建时勾选：

### L0 — 只读（默认开放）
```
☑ read_file      — 读取文件
☑ search_code    — 搜索代码
☑ list_files     — 列出目录
```

### L1 — 安全写入
```
☐ write_file     — 写入文件
☐ create_dir     — 创建目录
```

### L2 — 执行命令（需确认）
```
☐ run_command    — 执行 Shell 命令
☐ git_diff       — 查看 Git 差异
☐ git_status     — 查看 Git 状态
```

### L3 — 高风险（默认禁止）
```
☐ deploy         — 部署
☐ browser        — 浏览器操作
☐ web_search     — 网络搜索
```

Agent 创建界面上，用户看到的是勾选框，不是代码编辑器。

---

## 七、Agent Marketplace

### 7.1 功能

```
┌─────────────────────────────────────────────┐
│               Agent Marketplace              │
│                                             │
│  🔍 搜索: [                    ]            │
│                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │ Backend  │ │ Frontend │ │ DevOps  │       │
│  │ Architect│ │ Engineer │ │ Engineer│       │
│  │ 🏗️       │ │ 🎨       │ │ 🚀      │       │
│  │ public   │ │ public   │ │ public  │       │
│  └─────────┘ └─────────┘ └─────────┘       │
│  ┌─────────┐ ┌─────────┐                    │
│  │ QA       │ │ Security │                   │
│  │ Engineer │ │ Reviewer │                   │
│  │ 🧪       │ │ 🔒       │                   │
│  │ public   │ │ public   │                   │
│  └─────────┘ └─────────┘                    │
│                                             │
│  [+ 创建我的 Agent]   [📋 从已有复制]        │
└─────────────────────────────────────────────┘
```

### 7.2 用户操作

| 操作 | 说明 |
|---|---|
| 浏览 | 查看所有 `visibility=public` 的 Agent |
| 复制 | 基于已有 Agent 创建副本，修改后成为自己的 |
| 创建 | 填表：名称、描述、System Prompt、勾选 Skills |
| 编辑 | 修改自己的 Agent |
| 删除 | 删除自己的 Agent |
| 导出/导入 | JSON 文件导出，可分享给其他人导入 |

---

## 八、多 Agent 群聊

### 8.1 群聊模型

一个 Session 可以关联多个 Agent：

```yaml
session:
  id: sess_abc
  agents:
    - backend_architect
    - qa_engineer
    - security_reviewer
```

### 8.2 消息路由

用户发消息时：

```
User: "帮我写一个用户注册系统"
        │
        ▼
  Orchestrator 拆解任务
        │
        ├──▶ Task 1: coding → Backend Architect → Claude Code
        ├──▶ Task 2: review  → QA Engineer        → Claude Code
        └──▶ Task 3: review  → Security Reviewer  → Claude Code
        │
        ▼
  汇总结果 → 返回群聊
```

### 8.3 对话可见性

每个 Agent 只看到：
- 自己的 System Prompt
- 当前任务指令
- 依赖任务的输出摘要（不暴露其他 Agent 的 System Prompt）

---

## 九、与现有架构的整合

### 9.1 需要废弃的概念

| 旧 | 新 | 原因 |
|---|---|---|
| `agents.registry.json` 中的 coding/review/artifact | 保留为角色（role），不再叫 Agent | Agent 现在是用户可创建的 |
| `claude_code` 同时出现在 agents 和 skills 中 | `claude_code` 归入 Provider 层 | 三层分离 |

### 9.2 需要新增的模块

```
runtime/
├── agents/
│   └── persona.py          ← NEW: Agent Definition 加载 + Prompt Builder
├── skills/
│   └── ... (已有，不变)
├── gateway/internal/
│   ├── store/
│   │   └── agent_def_store.go  ← NEW: Agent Definition CRUD
│   └── httpapi/
│       └── agent_handler.go    ← NEW: Marketplace API
```

### 9.3 不变的部分

- **Skill Runtime** — 不变，Agent 的 `allowed_skills` 只是 Skill 调用的前置白名单检查
- **Orchestrator** — 不变，仍然负责拆解任务、调度执行、汇总结果
- **External CLI** — 不变，仍然是 Provider 的执行实现

### 9.4 改动最小化

```
现有: orchestrator.run_task(instruction, mentioned_agent="claude_code")
                                    │
                                    ▼
新增: orchestrator.run_task(instruction, mentioned_agent="backend_architect")
                                    │
                                    ▼
      ① 查 agent_definitions → 拿到 system_prompt + allowed_skills
      ② Prompt Builder 拼装 system_prompt 进入 payload
      ③ Skill Router 的 skill_name_for_stage 不变（仍是 coding/review/artifact）
      ④ 但执行前加一个白名单检查：skill 必须在 allowed_skills 中
```

---

## 十、实施路线

### Phase 1 — 数据落地 (P0)

- [ ] 创建 `agent_definitions` 表
- [ ] 实现 Gateway CRUD API (`POST/GET/PUT/DELETE /api/agents`)
- [ ] 预置 5 个内置 Agent
- [ ] 前端 Marketplace 页面（浏览 + 复制）

### Phase 2 — 运行时集成 (P0)

- [ ] `PersonaLoader` 模块：根据 `mentioned_agent` 加载 Agent Definition
- [ ] `PromptBuilder` 将 System Prompt 注入 payload
- [ ] Skill 白名单检查：执行前验证 `skill_name in allowed_skills`

### Phase 3 — 多 Agent 群聊 (P1)

- [ ] Session 关联多个 Agent
- [ ] Orchestrator 根据 Agent 角色分发任务
- [ ] 不同 Agent 的消息隔离

---

## 十一、与相关 ADR 的关系

| ADR | 关系 |
|---|---|
| ADR-002 Agent Boundary | 本 ADR 重新定义 Agent 边界：从 Python 类变为数据定义 |
| ADR-006 Agent Spec | 补充 Agent 的配置式定义方式 |
| ADR-010 Model Routing | Agent 的 `preferred_provider` 复用路由策略 |
| ADR-015 Skill Interface | Agent 的 `allowed_skills` 是 Skill 调用的前置白名单 |
| ADR-023 外部编码智能体接入 | Provider 层统一对接外部 CLI |
| ADR-025 Planner Strategy | 多 Agent 群聊的任务拆分复用 Planner |
