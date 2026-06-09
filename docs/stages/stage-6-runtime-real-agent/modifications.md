# 关键改动记录（Stage 6）

## 1. 阶段目标升级

- 将 Stage 6 从“泛化的真实化目标”升级为“执行模型定型 + 协议定型 + 比赛主链路落地”
- 明确 MVP 执行模型为 `linear_pipeline`
- 明确未来演进模型为 `dag`

## 2. 核心文档补齐

已新增或补齐以下文档：

- `ADR-024 Agent Execution Model`
- `ADR-025 Planner Strategy`
- `ADR-026 Agent Event Model`
- `ADR-027 Artifact Versioning`
- `ADR-028 Human Approval`
- `task-plan-spec.md`
- `agent-execution-spec.md`
- `event-spec.md`
- `diff-spec.md`
- `artifact-card-v2-spec.md`
- `runtime/agent-execution-rules.md`
- `runtime/event-rules.md`
- `runtime/llm-output-rules.md`

## 3. 比赛案例落地

- 新增 `docs/demo-cases/stage-6/`
- 固化 3 个比赛案例：
  - `Go Gin API`
  - `React Todo 页面`
  - `修改已有代码并新增接口`
- 新增本地 case runner 与自动化测试，用于验证当前 runtime 流程可跑通

## 4. 当前开发结论

- 当前主链路仍是 `Stage 4 DAG + demo agents`
- Stage 6 已完成的是”文档和开发基线”
- Stage 6 接下来的核心任务是把这些文档约束真正落到 Runtime 主链路代码上

## 5. LLM Planner 真实模型调用（2026-06-05）

### 新建模块：`runtime/llm/`

- `runtime/llm/__init__.py` — 模块导出
- `runtime/llm/client.py` — OpenAI 兼容的 `LLMClient`，从环境变量读取 `ORCHESTRATOR_BASE_URL` / `ORCHESTRATOR_API_KEY` / `ORCHESTRATOR_MODEL`
- `runtime/llm/prompts.py` — `PLANNER_SYSTEM_PROMPT` 与 `build_planner_user_prompt()`，定义 Task Plan JSON schema 约束

### 修改：`runtime/planner/stage6.py`

- `LLMPlanner.plan()` 从 stub 升级为真实实现：
  - 调用 `LLMClient.from_env()` 连接 SiliconFlow DeepSeek-V4-Pro
  - 构建 system + user prompt → 调用 chat completions API (json_object mode)
  - 解析 JSON 响应 → 清洗 markdown fence → 校验必填字段
  - `base_hash` 计算驱动真实 `action`（覆盖 LLM 输出的 action，避免 `VersionMismatch`）
  - 任何失败抛 `PlannerError` → `Stage6TaskPlanner` 自动 fallback 到 `RulePlanner`
- 自动加载 `.env`：`LLMClient.from_env()` 和 `Orchestrator.load()` 都会调用 `load_dotenv()`

### 验证结果

- `llm_planner` 作为 `primary` 策略正常工作
- 三个 demo case（Go Gin API / React Todo / Modify API）全部走通 LLM 规划
- 模型超时/不可用/输出不合法时自动 fallback 到 `rule_planner`

## 6. Rule Planner 项目结构增强（2026-06-05）

### 修改：`runtime/planner/stage6.py`

- **Go Gin API**: 3 files → 6 files（新增 `router/router.go`, `handlers/health.go`, `handlers/todo.go`）
- **React Todo**: 3 files → 6 files（新增 `components/TodoList.tsx`, `components/TodoItem.tsx`, `styles/index.css`）
- **Modify API**: 2 files → 4 files（新增 `models.py`, `router.py`）

### 修改：`runtime/agents/coding.py`

- 为所有新文件类型添加了 `_render_content` 分支：`router.go`, `health.go`, `todo.go`, `TodoList.tsx`, `TodoItem.tsx`, `index.css`, `models.py`, `router.py`
- 内容从简单占位升级为具备真实语义的骨架代码（如 todo.go 含完整的 ListTodos + CreateTodo + sync.Mutex 并发安全）

### 修改：`runtime/agents/review.py`

- 新增 7 个 shape check 规则覆盖新文件类型
- 修正 `approval_required` 判定逻辑：高风险/修改类任务独立于 `pass/fail` 进入审批门控

## 7. Human Approval 闭环（2026-06-05）

### 修改：`runtime/orchestrator/orchestrator.py`

- `approval_required` 检查独立于 `review.pass`：即使 review pass，高风险任务也会暂停等待审批
- 新增 `resume_stage6_task()` 方法：
  - `approved` → 发射 `approval.approved` → 继续到 artifact 阶段
  - `rejected` → 发射 `approval.denied` → 任务失败
- 审批中间状态通过 `{“status”: “approval_pending”, ...}` 返回值保存 coding/review 快照

### 修改：`runtime/stage6_demo_cases.py`

- 自动检测 `approval_pending` → 调用 `resume_stage6_task` 完成审批闭环
- 报告增加 `status` 字段区分 `completed` / `approval_pending`

### 修改：`tests/unit/test_stage6_demo_cases.py`

- 更新测试支持审批流程：检测 `approval_pending` → 自动调用 `resume_stage6_task(“approved”)` → 验证完整 artifact 输出

### 审批事件序列

```
task.created → planning → coding → review → approval.required → task.paused
→ [人工审批] → approval.approved → review.completed → artifact → task.completed
```

## 8. Diff 卡片真值化（2026-06-05）

### 问题

CodingAgent 的 `example_diff` 字段硬编码为 `"Hello, AgentHub!"` 占位文本。Gateway 的 `buildDiffCard` 取该字段展示 Diff 卡片内容，导致前端看到的代码摘要与实际生成的文件内容无关（即使磁盘上的文件已包含真实代码）。

### 修改：`runtime/orchestrator/orchestrator.py`

- 新增 `_diff_excerpt_create()` / `_diff_excerpt_update()` 两个纯函数，用真实文件内容生成 unified-diff 格式摘要
- `_normalize_stage6_coding_output()` 现在从 `content_samples`（实际落盘内容）生成真实 `example_diff`，覆盖 CodingAgent 的占位值
- 生成的 diff 摘要包含真实代码的前几行，符合验收标准 #3「changes/diff/artifact 与实际落盘文件一致」

### 修改：`runtime/api.py`

- `_execute_job` 将 `run_stage6_task` 的响应适配为 Gateway 期望的 `RunResult` 格式
- `agent_output.changes` 和 `agent_output.example_diff` 提升到 `coding` 顶层供 `buildDiffCard` 消费

### 修改：`runtime/server.py`

- 自动将项目根目录加入 `sys.path`，无需手动设置 `PYTHONPATH`

### 修改：`compose.yaml`

- runtime 服务添加 `ORCHESTRATOR_BASE_URL` / `ORCHESTRATOR_API_KEY` / `ORCHESTRATOR_MODEL` 环境变量
- 添加 `env_file: .env` 自动加载

### 验证

- Diff 卡片中每个文件的 `diff_excerpt` 展示该文件前 5 行的真实代码
- 文件名与 `stage6_workspace/` 磁盘内容一致

## 9. 前端渐进可视化（2026-06-05）

### 问题

Gateway 的 `executeTask` 采用 `SubmitInstruction → WaitForResult` 阻塞轮询模式。
Runtime 内部的所有阶段事件（`planning.started`, `coding.started`, ...）虽然已记录在
`diagnostics` 中，但只在任务结束后一次性返回。前端在整个执行过程中看不到任何变化。

### 修改：`runtime/orchestrator/orchestrator.py`

- `run_stage6_task` 新增 `_shared_diag` 参数：外部传入一个可变 list，`_emit_stage6_event`
  在写入本地 `diagnostics` 时同步写入共享列表
- 共享列表通过实例属性 `_stage6_shared_diag` 桥接，`finally` 块中置 `None`

### 修改：`runtime/api.py`

- 任务创建时初始化 `shared_diag` 列表并存入 `_jobs[task_id]["diagnostics"]`
- `_execute_job` 将 `shared_diag` 传递给 `run_stage6_task`
- 轮询端点 `GET /internal/v1/tasks/{task_id}` 返回当前 `diagnostics` 快照
- `RuntimeTaskStatusResponse` 添加 `diagnostics` 字段

### 修改：`gateway/internal/runtimeclient/http_client.go`

- `taskStatusResponse` 添加 `Diagnostics` 字段
- `Client` 接口新增 `WaitForResultWithProgress` 方法，接收 `onProgress` 回调
- 回调按 `seen` set 去重，每个新事件仅触发一次

### 修改：`gateway/internal/app/app.go`

- `executeTask` 从 `WaitForResult` 切换到 `WaitForResultWithProgress`
- 回调将 Stage 6 事件映射为前端 `task.updated` 事件：
  - `planning.started` → `agent: "planner"`, `progress: {current: 0, total: 4}`
  - `coding.started` → `agent: "coding"`, `progress: {current: 1, total: 4}`
  - `review.started` → `agent: "review"`, `progress: {current: 2, total: 4}`
  - `artifact.started` → `agent: "artifact"`, `progress: {current: 3, total: 4}`
  - `approval.required` → `agent: "approval"`, `progress: {paused: true}`
- 新增 `mapStage6EventToProgress` 映射函数
- 每个中间事件通过 `persistAndBroadcast` 即持久化又推送给前端 WS

### 实时事件数据流

```
Runtime (thread)                Gateway (poll loop)           Frontend (WS)
──────────────                  ───────────────────           ─────────────
planning.started  ──shared_diag─→ poll → diagnostics ──────→ task.updated {agent:"planner",progress:{0/4}}
coding.started    ──shared_diag─→ poll → diagnostics ──────→ task.updated {agent:"coding",progress:{1/4}}
coding.completed  ──shared_diag─→ poll → diagnostics ──────→ task.updated {agent:"coding",progress:{2/4}}
review.started    ──shared_diag─→ poll → diagnostics ──────→ task.updated {agent:"review",progress:{2/4}}
artifact.started  ──shared_diag─→ poll → diagnostics ──────→ task.updated {agent:"artifact",progress:{3/4}}
task.completed    ──返回结果───→ poll → result ─────────────→ task.completed
```
