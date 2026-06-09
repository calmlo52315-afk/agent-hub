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
# 1. 克隆项目
git clone <repo-url> && cd agent_hub

# 2. 配置 LLM API Key（必需）
cp .env.example .env
# 编辑 .env，填入你的 MODEL_API_KEY

# 3. 启动
docker compose up -d
```

启动后访问 http://localhost:3000

| 服务 | 端口 | 技术栈 |
|---|---|---|
| Fronted | 3000 | Next.js 16 + TypeScript + TailwindCSS |
| Gateway | 8080 | Go + Gin + WebSocket |
| Runtime | 8001 | Python FastAPI + LLM Client |

## ⚙️ 环境变量

复制 `.env.example` 为 `.env`，按需修改：

```bash
cp .env.example .env
```

### 核心配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `MODEL_API_KEY` | LLM API Key（必填） | — |
| `MODEL_BASE_URL` | LLM API 地址 | `https://ark.cn-beijing.volces.com/api/v3` |
| `CODING_MODEL` | 编码模型 | `doubao-seed-code-preview-251028` |
| `PLANNER_MODEL` | 规划模型 | `doubao-seed-2-0-mini-260428` |

### 本地开发

```bash
# Runtime (Python 3.14+)
cd runtime && pip install -r requirements.txt && python -m runtime.server

# Gateway (Go 1.25+)
cd gateway && go run ./cmd/server

# Fronted (Node.js 24+)
cd fronted && npm install && npm run dev
```

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
│   └── data/         # SQLite 数据
├── runtime/          # Python 运行时
│   ├── agents/       # Agent 定义（coding / review / doc / persona）
│   ├── orchestrator/ # 任务编排核心
│   ├── skills/       # 技能执行器（含 external CLI 调用）
│   ├── specs/        # 技能注册表、Agent 注册表
│   └── llm/          # LLM 客户端
├── rules/            # 规则配置
├── docker-compose.yml
├── Dockerfile        # 三服务各自的 Dockerfile
└── .env.example      # 环境变量模板
```
