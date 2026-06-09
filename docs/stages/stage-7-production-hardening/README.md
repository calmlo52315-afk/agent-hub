# Stage 7 - Frontend & Runtime Integration

## Overview

This stage integrates the AgentHub frontend with the existing backend architecture (Gateway + Runtime), keeping the Runtime architecture unchanged.

## Goals

- Maintain existing Runtime architecture
- Use existing Gateway for frontend communication
- Implement @claude code / @claude codex functionality
- Build end-to-end minimal working loop
- Schedule layer remains invisible to frontend

---

## 🐛 Bug Fixes & Improvements

### 1. Gateway 超时时间配置

**问题**：Gateway 的任务超时时间只有 3 分钟，开发环境不够用，导致任务经常超时失败。

**解决方案**：修改了 `gateway/internal/app/app.go`，将超时时间从 3 分钟延长到 10 分钟。同时将轮询超时从 90 秒延长到 10 分钟。

**效果**：任务有足够的时间完成，不会再因为超时而失败。

---

### 2. CORS 跨域问题

**问题**：前端无法与 Gateway 通信，浏览器报告 CORS 错误。OPTIONS 请求返回 404。

**解决方案**：在 `gateway/internal/httpapi/router.go` 中添加了 CORS 中间件，正确处理预检请求，允许来自前端的跨域请求。

**效果**：前端可以正常与 Gateway 通信了。

---

### 3. 前端 API 端口配置错误

**问题**：前端配置连接到端口 8000，而 Gateway 实际监听在 8080。

**解决方案**：修改了 `fronted/.env.local`，将端口从 8000 改为 8080。

**效果**：前端可以正常连接到后端了。

---

## ✨ New Features

### 1. @claude code / @claude codex 功能

**问题**：需要支持通过 @ 提及来选择特定的 Agent（Claude Code / Codex）来处理任务。

**解决方案**：
1. **Gateway 修改**：
   - 在 `gateway/internal/runtimeclient/http_client.go` 中扩展了 `RunInstructionRequest`，新增 `MentionedAgent` 字段
   - 在 `gateway/internal/store/store.go` 中的 `Task` 结构中添加了 `MentionedAgent` 字段
   - 在 `gateway/internal/app/app.go` 中新增了 `extractMentionedAgent()` 函数来检测 @ 提及
   - 在 `executeTask` 中正确传递提到的 Agent
2. **Runtime 修改**：
   - 在 `runtime/api.py` 中新增了 `RuntimeTaskRunRequest.mentioned_agent` 字段
   - 在 `runtime/orchestrator/orchestrator.py` 的 `run_task` 中支持 `mentioned_agent`
   - 在编码阶段根据提到的 Agent 选择对应的技能（如 `claude_code`）
3. **调试日志**：在 Gateway 和 Runtime 中添加了详细的调试日志，便于排查问题

**效果**：用户可以在对话中使用 `@claude code` 或 `@claude-code` 来指定使用 Claude Code 技能处理任务。

---

### 2. 单聊/群聊模式 UI

**问题**：需要区分单聊（与单个 Agent 对话）和群聊（可 @ 多个 Agent 协作）两种模式。

**解决方案**：
1. **新建会话菜单** (`fronted/components/layout/NewChatMenu.tsx`)：
   - 提供 "新建群聊" 选项，默认创建 multi_agent 模式的会话
   - 提供 "单聊" 选项，直接创建 Claude Code / Codex 的 single_agent 会话
2. **侧边栏优化** (`fronted/components/layout/SessionSidebar.tsx`)：
   - 点击 Agents 部分的按钮可以直接创建对应的单聊会话
   - 优化了 UI，添加了 Agent Contact 定义
3. **会话模式显示** (`fronted/components/layout/ChatWorkspace.tsx`)：
   - 在顶部栏显示会话模式标签（单聊/群聊）
   - 用不同的渐变色区分：
     - 群聊：蓝色 → 靛蓝色渐变
     - 单聊：紫色 → 粉色渐变
4. **主布局** (`fronted/app/(main)/layout.tsx`)：
   - 新增了 `handleCreateSingleAgentSession` 方法
   - 新增了 AgentContact 类型定义

**效果**：用户可以通过侧边栏快速创建单聊会话，UI 清晰地区分了不同的会话模式。

---

## 🔧 Key Files Modified

### Gateway (Go)
- `gateway/internal/runtimeclient/http_client.go` - 扩展协议，新增 mentioned_agent
- `gateway/internal/app/app.go` - 新增检测逻辑、延长超时、添加日志
- `gateway/internal/httpapi/router.go` - 添加 CORS 支持
- `gateway/internal/store/store.go` - 在 Task 结构中添加字段

### Runtime (Python)
- `runtime/api.py` - 新增 mentioned_agent 字段
- `runtime/orchestrator/orchestrator.py` - 根据提到的 Agent 选择技能、添加调试日志

### Frontend (Next.js)
- `fronted/components/layout/NewChatMenu.tsx` - 新建会话菜单组件
- `fronted/components/layout/SessionSidebar.tsx` - 侧边栏优化
- `fronted/components/layout/ChatWorkspace.tsx` - 会话模式 UI
- `fronted/app/(main)/layout.tsx` - 主布局更新
- `fronted/.env.local` - 修正 API 端口配置

## Architecture

### Frontend ↔ Gateway ↔ Runtime

```
┌─────────────────┐
│   Frontend      │
│  (Next.js)      │
└────────┬────────┘
         │
         │ HTTP / WebSocket
         │
         ▼
┌───────────────────────────────────────┐
│  Gateway (Port 8080)                  │
│  - Session Management                 │
│  - Message Routing                    │
│  - WebSocket Broker                   │
│  - Task Orchestration                 │
└────────┬───────────────────────────────┘
         │
         │ Internal API
         │
         ▼
┌───────────────────────────────────────┐
│  Runtime (Port 8001)                  │
│  - Orchestrator                       │
│  - Agents (coding/review/artifact)    │
│  - Skills System                      │
└───────────────────────────────────────┘
```

## Key Features

### 1. Gateway API Layer

- Session CRUD operations
- Message storage and retrieval
- WebSocket connection management
- Real-time event broadcasting
- Task execution orchestration
- Artifact management

### 2. Runtime Layer

- Orchestrator for task planning
- Coding agent for code generation
- Review agent for code review
- Artifact agent for artifact creation
- Skills system for extended functionality

### 3. Frontend Configuration

File: `fronted/.env.local`

```env
NEXT_PUBLIC_GATEWAY_BASE_URL=http://localhost:8080
NEXT_PUBLIC_FORCE_DIRECT_GATEWAY=1
NEXT_PUBLIC_DEMO_ACCESS_TOKEN=demo-access-token
```

### 4. @claude code / @claude codex Functionality

The system handles instructions through the Gateway and Runtime:
1. User sends message with instruction
2. Gateway receives and processes
3. Task is created and sent to Runtime
4. Runtime's Orchestrator executes pipeline
5. Real-time events streamed back to frontend
6. Artifacts are generated and displayed

## How to Run

### 1. Start Runtime (Port 8001)

```bash
# From project root
cd /Users/macbook/Desktop/important_code/agent_hub
source .venv/bin/activate
python -m uvicorn runtime.api:app --host 0.0.0.0 --port 8001
```

### 2. Start Gateway (Port 8080)

Gateway should already be running (check terminal logs for `gateway listening on :8080`)

### 3. Start Frontend

```bash
cd fronted
npm run dev
```

Frontend runs on `http://localhost:3000`

## API Endpoints

### Session Management

- `POST /api/v1/sessions` - Create session
- `GET /api/v1/sessions` - List sessions
- `GET /api/v1/sessions/{id}` - Get session details
- `GET /api/v1/sessions/{id}/messages` - List messages
- `POST /api/v1/sessions/{id}/messages` - Send message
- `GET /api/v1/sessions/{id}/tasks` - List tasks
- `GET /api/v1/sessions/{id}/artifacts` - List artifacts

### Task Management

- `GET /api/v1/tasks/{id}` - Get task details
- `POST /api/v1/tasks/{id}/retry` - Retry task
- `POST /api/v1/tasks/{id}/cancel` - Cancel task
- `POST /api/v1/tasks/{id}/approvals/{id}` - Submit approval
- `POST /api/v1/tasks/{id}/conflicts/{id}/resolve` - Resolve conflict

### Artifact Management

- `GET /api/v1/artifacts/{id}` - Get artifact details

### WebSocket

- `POST /api/v1/ws-tickets` - Issue WebSocket ticket
- `WS /ws` - WebSocket connection

### Health

- `GET /healthz` - Health check

## Data Flow

### Normal Chat Flow

1. User sends message in frontend
2. Frontend sends via API or WebSocket to Gateway
3. Gateway stores and broadcasts message
4. All connected clients receive message

### @claude code Flow

1. User sends instruction (e.g., `@claude code create a todo app`)
2. Gateway receives message
3. Gateway creates task and sends to Runtime
4. Runtime's Orchestrator executes pipeline:
   - Planner creates task plan
   - Coding agent generates code
   - Review agent reviews code
   - Artifact agent creates artifacts
5. Real-time events streamed back through Gateway
6. Artifacts displayed in frontend UI

### WebSocket Events

- `connection.ready` - Connection established
- `session.snapshot` - Initial state snapshot
- `chat.message` - Chat messages
- `task.created` - New task
- `task.updated` - Task progress
- `task.completed` - Task finished
- `artifact.created` - New artifact
- `approval.required` - Approval needed
- `system.error` - Error occurred

## Demo

1. Ensure all services are running:
   - Runtime on http://localhost:8001
   - Gateway on http://localhost:8080
   - Frontend on http://localhost:3000

2. Refresh frontend page

3. Create new session or use Quick Start

4. Send a message like:
   ```
   @claude code create a simple python hello world script
   ```

5. Watch real-time updates in the chat panel

6. See code changes in the artifacts panel
