# AgentHub

AI 多智能体协作开发平台 — 通过 Claude Code、Codex 和内置 LLM 的智能编排，实现从编码到审查的完整自动化工作流。

## ✨ 项目特色

- **多 Agent 智能分流** — 根据任务复杂度自动选择 Claude Code（大项目深度审查）、Codex（快速开发）、内置 LLM（简单任务）
- **实时协作管道** — WebSocket 驱动的 Coding → Review → Package 全流程，前端实时渲染每个阶段的状态和耗时
- **用户自定义 Agent** — 通过侧边栏创建专属 Agent，支持从第三方 URL 导入 Skills/Tools 配置
- **全栈可观测** — 编码耗时、审查耗时、streaming 内容实时渲染、Markdown 预览
- **一键 Docker 部署** — 三服务编排（Gateway / Runtime / Fronted），健康检查自动恢复

## 🚀 Docker 一键启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 MODEL_API_KEY

# 2. 构建并启动
docker compose up -d --build

# 3. 打开浏览器
open http://localhost:3000
```

> 仅需 Docker Desktop。首次构建约 2-3 分钟，后续启动秒级。

| 服务 | 端口 | 技术栈 |
|---|---|---|
| Fronted | 3000 | Next.js 16 + TypeScript + TailwindCSS |
| Gateway | 8080 | Go + Gin + WebSocket |
| Runtime | 8001 | Python FastAPI + LLM Client |
| Postgres | 5432 | PostgreSQL 16 (数据持久化)

## 💻 本地开发（不使用 Docker）

### 前置要求

- **Go** 1.25+ · **Python** 3.14+ · **Node.js** 24+

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 MODEL_API_KEY
# 本地开发需确保以下配置：
#   RUNTIME_BASE_URL=http://127.0.0.1:8001
#   GATEWAY_STORE_BACKEND=sqlite
#   GATEWAY_SQLITE_PATH=data/gateway.db
```

### 2. 启动 Runtime（Python）

```bash
cd runtime
pip install -r requirements.txt
python -m server
# 监听 http://127.0.0.1:8001
```

### 3. 启动 Gateway（Go）

```bash
cd gateway
go run ./cmd/server
# 监听 http://0.0.0.0:8080，连接 Runtime 8001
# 启动后自动创建 demo 令牌: demo-access-token
```

### 4. 启动前端（Next.js）

```bash
cd fronted
npm install
npm run dev
# 监听 http://localhost:3000，自动代理 /api/* → Gateway 8080
```

### 5. 打开浏览器

访问 `http://localhost:3000`，无需输入令牌（已内置 demo 令牌）。

### 可选：启动 PostgreSQL

仅在使用 `GATEWAY_STORE_BACKEND=postgres` 时需要。SQLite 模式无需额外操作。

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `MODEL_API_KEY` | LLM API Key（必填） | — |
| `MODEL_BASE_URL` | LLM API 地址 | `https://ark.cn-beijing.volces.com/api/v3` |
| `CODING_MODEL` | 编码模型 | `doubao-seed-code-preview-251028` |
| `PLANNER_MODEL` | 规划模型 | `doubao-seed-2-0-mini-260428` |
| `RUNTIME_BASE_URL` | Runtime 地址 | `http://127.0.0.1:8001` |
| `GATEWAY_STORE_BACKEND` | 存储后端 | `sqlite`（可选 memory / postgres） |
| `GATEWAY_PORT` | Gateway 端口 | `8080` |

## 📖 用法

### 在对话中输入 `@Agent名称` 即可调用对应 Agent：

| Agent | 说明 |
|---|---|
| `@Claude Code` | 复杂项目开发，深度代码审查 |
| `@Codex` | 项目快速开发 |
| `@Test Agent` | 测试生成 |
| `@Doc Agent` | 文档生成 |

### 自定义 Agent

点击侧边栏 **创建 Agent**，填写：
- 名称、描述、System Prompt
- 选择 Skills/Tools
- 可选：填入第三方 URL 自动导入 Skills 配置

### 工作流

```
用户输入任务
  → Planner 分析 → 选择编码 Skill (Codex / Claude Code / 内置 LLM)
    → 代码生成 → 前端渲染代码
      → SkillRouter 选择审查 Skill
        → Review 结果 → 前端显示评分和问题列表
```

## 💡 项目亮点

### 多 Agent 协作编排

不是简单的单 Agent 对话，而是 **Planner → Coding → Review → Artifact** 多阶段流水线。Gateway 作为中心调度器，协调 Runtime 中的 5 个内置 Agent（coding、review、artifact、testing、documentation），每个阶段独立执行、独立重试，实现真正的多智能体协作。

### 外部 CLI 集成

支持在对话中 `@Claude Code` 或 `@Codex`，Runtime 会 fork 对应 CLI 进程来执行编码/审查任务。这使得 Agent Hub 既能使用内置 LLM 处理简单任务，又能借助 Claude Code、Codex 等专业工具应对复杂项目。

### 实时 WebSocket 流式推送

从任务创建到编码进度、审查结果、产物生成，全流程通过 WebSocket 实时推送到前端。支持 streaming 消息块、连接心跳、断线状态管理，用户体验流畅。

### 零配置 Demo 令牌

开箱即用 — 首次启动 Gateway 时自动创建 `demo-access-token`，前端默认填入，用户无需关心认证配置即可体验完整功能。

### 灵活的存储后端

支持 memory / SQLite / PostgreSQL 三种存储后端，通过 `GATEWAY_STORE_BACKEND` 环境变量一键切换。开发测试用内存或 SQLite，生产环境用 PostgreSQL。

## 🔧 技术难点

### 异步任务轮询与进度上报

Gateway 向 Runtime 提交任务后，采用轮询模式获取执行状态。难点在于：Runtime 的执行可能持续数十秒甚至数分钟，Gateway 需要在轮询间隔中解析 Runtime 返回的 diagnostics 事件，将其转换为前端可识别的进度消息（planning → coding → review → artifact），同时处理好超时和取消场景。

### 多 Agent 输出规范化

不同 Agent（Claude Code、Codex、内置 LLM）输出格式各异 — Claude Code 输出 JSON 流、Codex 输出纯文本 diff、内置 LLM 输出自由文本。Runtime 通过 `normalizers.py` 统一提取 diff 内容，确保 artifact 打包的一致性和代码卡片的正确渲染。

### WebSocket 连接生命周期管理

每个会话的 WebSocket 连接需经历：Ticket 签发（5分钟 TTL、单次使用）→ 升级连接 → 订阅会话 → 重连恢复（resume_from_seq）→ 心跳维护 → 断线清理。Gateway 的 Hub 模块管理多会话并发连接，确保消息不丢失、不重复。

### 工作区懒加载与文件索引

工作区文件树通过懒加载机制：前端先获取目录结构，仅当用户点击文件时才请求具体内容。Gateway 负责路径安全校验（防遍历攻击），Runtime 负责文件系统读取和内容缓存。

## 📁 项目结构

```
agent_hub/
├── fronted/          # Next.js 16 前端
│   ├── app/          # App Router 页面
│   ├── components/   # UI 组件（chat / layout / artifact / task）
│   ├── stores/       # Zustand 状态管理
│   ├── lib/          # API 客户端、WebSocket 管理
│   └── types/        # TypeScript 类型定义
├── gateway/          # Go 网关
│   ├── cmd/server/   # 入口
│   └── internal/     # 核心逻辑（app / auth / ws / store / protocol）
├── runtime/          # Python 运行时
│   ├── agents/       # Agent 定义（coding / review / doc / persona）
│   ├── orchestrator/ # 任务编排核心
│   ├── skills/       # 技能执行器（含 external CLI 调用）
│   ├── specs/        # 技能注册表、Agent 注册表
│   └── llm/          # LLM 客户端
├── rules/            # 规则配置（通信/执行/权限/Ownership）
├── docs/             # 设计文档、Context Pack、Stage 规格
├── tests/            # 单元 + 端到端测试
├── docker-compose.yml
├── Dockerfile        # 各服务独立 Dockerfile
└── .env.example      # 环境变量模板
```
