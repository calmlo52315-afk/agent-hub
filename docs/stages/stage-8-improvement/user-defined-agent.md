# Stage 8 — User-Defined Agent 实现

## 设计依据

ADR-029 定义了两种 Agent 形态和三层分离架构。本次实现覆盖了 ADR 的 Phase 1 + Phase 2。

## 实现内容

### 1. Gateway 侧：Agent Definition 存储

**新增接口**：`gateway/internal/store/store.go`

```go
type AgentDefinitionStore interface {
    CreateAgentDefinition(record AgentDefinitionRecord) error
    GetAgentDefinition(id string) (AgentDefinitionRecord, error)
    ListAgentDefinitions(ownerID string) []AgentDefinitionRecord
    ListPublicAgentDefinitions() []AgentDefinitionRecord
    UpdateAgentDefinition(record AgentDefinitionRecord) error
    DeleteAgentDefinition(id string) error
}
```

**SQLite 实现**：`gateway/internal/store/sqlite.go` — 新增 `agent_definitions` 表

```sql
CREATE TABLE IF NOT EXISTS agent_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar TEXT DEFAULT '',
    description TEXT DEFAULT '',
    system_prompt TEXT NOT NULL,
    allowed_skills_json TEXT DEFAULT '[]',
    preferred_provider TEXT DEFAULT 'claude_code',
    visibility TEXT DEFAULT 'private',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**Memory 实现**：`gateway/internal/store/store.go` — 新增 `agentDefs map[string]AgentDefinitionRecord`

### 2. Gateway 侧：CRUD API

**路由**：`gateway/internal/httpapi/router.go`

```
POST   /api/v1/agents               — 创建 Agent Definition
GET    /api/v1/agents               — 列出我的 Agent
GET    /api/v1/agents/marketplace   — 浏览公开 Agent (Marketplace)
GET    /api/v1/agents/:agent_id     — 获取单个 Agent
PUT    /api/v1/agents/:agent_id     — 更新 Agent
DELETE /api/v1/agents/:agent_id     — 删除 Agent
```

**业务逻辑**：`gateway/internal/app/app.go`

- 创建时自动生成 ID（`agent_<uuid>`）
- 更新时校验所有权（只能修改自己创建的）
- 删除时允许删除 `created_by=system` 的 Agent（内置）
- 默认值：`visibility=private`、`preferred_provider=claude_code`

### 3. Python 侧：Persona 模块

**文件**：`runtime/agents/persona.py`

**PersonaLoader**：
```python
loader = PersonaLoader()
agent_def = loader.resolve("@Backend Architect")  # 去掉@，匹配内置
agent_def = loader.resolve("backend_architect")     # 直接匹配 id
agent_def = loader.resolve(None)                    # → None，使用默认
```

加载优先级：
1. 内置 5 个 Agent（硬编码在 `_BUILTIN_AGENTS` 字典中）
2. Gateway API（future）

**AgentPromptBuilder**：
```python
prompt = AgentPromptBuilder.build_coding_prompt(
    agent_def=backend_architect_def,
    instruction="写一个 Gin 登录接口",
    targets=[{"action": "create", "path": "demo_workspace/login.go"}],
)
# → System Prompt (from agent) + instruction + targets + output format
```

**Skill 白名单检查**：
```python
AgentPromptBuilder.check_skill_allowed(qa_engineer_def, "coding")  # → False
AgentPromptBuilder.check_skill_allowed(qa_engineer_def, "review")  # → True
AgentPromptBuilder.check_skill_allowed(None, "coding")             # → True (默认)
```

### 4. 内置 5 个 Agent

| ID | Name | Skills | 定位 |
|---|---|---|---|
| `backend_architect` | Backend Architect | coding, review, read_file, write_file | Go 后端架构，Gin + GORM |
| `frontend_engineer` | Frontend Engineer | coding, review, read_file, write_file | React 前端，Next.js + TailwindCSS |
| `devops_engineer` | DevOps Engineer | coding, run_command, git_diff, read_file, write_file | Docker, K8s, CI/CD |
| `qa_engineer` | QA Engineer | review, read_file, search_code | 测试用例生成，代码审查 |
| `security_reviewer` | Security Reviewer | review, read_file, search_code | OWASP, 安全审查 |

### 5. Orchestrator 集成

在 `run_task()` 中的改动（~15 行）：

```
① 解析 mentioned_agent → AgentDefinition (persona)
② 若 Agent 的 preferred_provider = claude_code → coding_skill = "claude_code"
③ 白名单检查 → skill 必须在 allowed_skills 中
④ Persona Prompt 注入 → coding_payload["persona"] + 改写 instruction
⑤ Review 阶段同样注入 persona 到 review_payload
```

### 6. 运行时效果

用户输入：
```
@Backend Architect 帮我写一个 Gin 登录接口
```

系统执行链：
```
① PersonaLoader.resolve("Backend Architect")
   → AgentDefinition(id="backend_architect", system_prompt="你是一名资深 Go 后端架构师...")

② AgentPromptBuilder.build_coding_prompt()
   → "你是一名资深 Go 后端架构师。\n你擅长：...\n\nWrite a Gin login endpoint\n..."

③ Skill whitelist check
   → "coding" in ["coding", "review", "read_file", "write_file"] → ✅

④ preferred_provider = "claude_code"
   → coding_skill_name = "claude_code"

⑤ claude -p "<persona prompt>" --permission-mode bypassPermissions
```

## 文件变更清单

| 文件 | 变更 | 说明 |
|---|---|---|
| `gateway/internal/store/store.go` | 修改 | 新增 AgentDefinitionRecord + AgentDefinitionStore + MemoryStore 实现 |
| `gateway/internal/store/sqlite.go` | 修改 | 新增 agent_definitions 表 + CRUD |
| `gateway/internal/store/factory.go` | 修改 | Backend 接口加入 AgentDefinitionStore |
| `gateway/internal/httpapi/router.go` | 修改 | 新增 6 个 Agent API 路由 |
| `gateway/internal/app/app.go` | 修改 | 新增 5 个 GatewayApp 方法 |
| `runtime/agents/persona.py` | **新增** | PersonaLoader + AgentPromptBuilder + 5 内置 Agent |
| `runtime/orchestrator/orchestrator.py` | 修改 | run_task() 集成 persona 加载 + prompt 注入 |
| `docs/specs/ADR/ADR-029-user-defined-agent.md` | **新增** | ADR 设计文档 |
| `docs/stages/stage-8-improvement/user-defined-agent.md` | **新增** | 本文档 |

## 后续扩展

- [ ] **前端 Marketplace 页面**：浏览 + 复制 + 创建 Agent
- [ ] **Gateway API 加载**：PersonaLoader 支持从 Gateway API 加载用户自定义 Agent
- [ ] **多 Agent 群聊**：Session 关联多个 Agent，Orchestrator 按 Agent 分发任务
- [ ] **工具集分层**：L0-L3 工具分级，Agent 创建界面勾选
