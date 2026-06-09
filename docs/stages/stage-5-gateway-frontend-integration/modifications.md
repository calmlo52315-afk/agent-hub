# 第五阶段变更记录

## 阶段定位

本阶段对应 `stage-5-gateway-frontend-integration`，目标是把 Stage 4 已具备的 Python Runtime 编排能力接到一个可演示的 Gateway 外部入口上，并按需求文档把 Runtime 内部服务正式落为 `FastAPI + Pydantic`，为后续 IM 前端接入提供稳定的 REST / WebSocket 边界。

结合当前开发范围，本次只实现 Gateway 侧与 Runtime 适配，不进行前端开发。

## 输入依据

### ADR

- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-019-Session-Model.md`
- `docs/specs/ADR/ADR-020-WebSocket Protocol`
- `docs/specs/ADR/ADR-021-Human-in-the-Loop`
- `docs/specs/ADR/ADR-022-Gateway-Authentication.md`

### Spec

- `docs/specs/contracts/message-spec.md`
- `docs/specs/contracts/websocket-message-spec.md`
- `docs/specs/contracts/session-task-api-spec.md`
- `docs/specs/contracts/artifact-card-schema-spec.md`

### Rules

- `docs/specs/rules/global/protocol.md`
- `docs/specs/rules/global/project.md`
- `docs/specs/rules/global/runtime-agent-boundary.md`
- `docs/specs/rules/communication/communication.md`
- `docs/specs/rules/permission/permission.md`
- `docs/specs/rules/context/context.md`
- `docs/specs/rules/dispatch/dispatch.md`
- `docs/specs/rules/ownership/ownership.md`
- `docs/specs/rules/ownership/lock.md`

### 需求

- `docs/specs/需求文档.md`

## 本次完成内容

- 新建独立 `gateway/` Go 模块，使用 `Gin + WebSocket`
- 实现 Gateway 存储抽象，并将默认后端切换为 SQLite
- 保留内存版存储作为测试与兜底实现
- 实现 Bearer Token 与 `ws_ticket` 模型
- 实现 Session / Task / Artifact 的最小 REST API
- 实现 `/ws` WebSocket 入口，以及 `session.subscribe`、`chat.message`、`ack`、`heartbeat`、基础 replay
- 新增 Runtime 内部 `FastAPI + Pydantic` 服务入口，并提供内网鉴权 token
- 将 Runtime Internal API 升级为异步任务模式
- 在 Gateway 中通过 HTTP client 提交 Runtime 任务并轮询结果
- 补齐 `task cancel / task timeout / poll timeout`
- 将 Runtime 返回的 `coding / review / artifact / task_plan` 结果映射为 Stage 5 所需的外部事件
- 自动生成 diff card 与 artifact bundle card，供后续前端展示
- 补充 Stage 5 过程文档，满足比赛留痕提交需要

## 新增与更新文档

- Stage 5 输入参考文档：
  - `docs/stages/stage-5-gateway-frontend-integration/spec.md`
- Stage 5 任务清单：
  - `docs/stages/stage-5-gateway-frontend-integration/tasks.md`
- Stage 5 验收清单：
  - `docs/stages/stage-5-gateway-frontend-integration/checklist.md`
- Stage 5 变更记录：
  - `docs/stages/stage-5-gateway-frontend-integration/modifications.md`
- Stage 5 低优先级待办：
  - `docs/stages/stage-5-gateway-frontend-integration/todo.workerpool.md`
- Stage 5 前端设计文档：
  - `docs/stages/stage-5-gateway-frontend-integration/frontend-design.md`
- Claude Code 使用版文档：
  - `docs/cc-used/frontend-design-for-claudecode.md`

## 代码实现变更

- 新增 Gateway Go 模块：
  - `gateway/go.mod`
- 新增 Gateway 启动入口：
  - `gateway/cmd/server/main.go`
- 新增 Gateway 应用层：
  - `gateway/internal/app/app.go`
- 新增鉴权服务：
  - `gateway/internal/auth/service.go`
- 新增 REST 路由层：
  - `gateway/internal/httpapi/router.go`
- 新增 WebSocket 协议模型：
  - `gateway/internal/protocol/types.go`
- 新增 Runtime 适配层：
  - `gateway/internal/runtimeclient/http_client.go`
  - `gateway/internal/runtimeclient/http_client_test.go`
- 新增存储实现：
  - `gateway/internal/store/store.go`
  - `gateway/internal/store/sqlite.go`
  - `gateway/internal/store/factory.go`
- 新增 WebSocket Hub：
  - `gateway/internal/ws/hub.go`
- 新增 Runtime Internal API：
  - `runtime/api.py`
  - `runtime/server.py`
  - `runtime/requirements.txt`
- 新增 Gateway 单元测试：
  - `gateway/internal/app/app_test.go`
  - `gateway/internal/httpapi/router_test.go`
- 新增 Runtime 单元测试：
  - `tests/unit/test_runtime_api.py`

## 运行时约束

- Gateway 作为唯一外部入口，继续遵循 ADR-018
- Runtime 仍保持现有单进程 Python 编排主链路，但新增内部 FastAPI 服务供 Gateway 调用
- Runtime Internal API 只允许内网 token 调用，不直接暴露给前端
- Runtime Internal API 当前采用“提交任务 + 查询状态”的异步模式
- Gateway 当前通过 HTTP client 调用 Runtime FastAPI 异步接口，属于贴合需求文档的工业级接线方案
- Gateway 当前默认存储为 SQLite，接口仍保留可替换边界
- `task cancel` 当前为 Gateway 发起、Runtime best-effort 接收的取消模式
- `task timeout` 由 Gateway 执行上下文控制
- `poll timeout` 由 Runtime HTTP client 独立控制并显式分类
- 当前只实现 Gateway 侧，不包含任何前端页面开发

## 当前未完成项

- 尚未实现前端页面与 UI 联调
- Runtime 与 Gateway 之间当前为异步 HTTP 轮询模式，尚未升级为消息队列 / worker pool / 推送式回调
- Runtime 侧取消仍为 best-effort，尚未做到真正的执行中断
- Postgres / Redis 版本的持久化后端尚未实现
- 当前 artifact card 以 diff / bundle 为主，尚未提供真实 preview card

## 建议的下一步实现顺序

1. 为 Gateway 增加 Postgres / Redis 存储实现。
2. 把 Runtime Internal API 从 HTTP 轮询升级为更稳定的 worker pool 或事件驱动模式。
3. 接入前端聊天页、会话列表、artifact panel、diff viewer。
4. 增强 replay、approval、conflict resolution 的完整链路。

## 外部编码智能体接入（Claude Code / Codex）

本阶段新增对外部编码智能体 Claude Code、Codex 的子进程接入支持，将 ADR-023 的设计落地为实际可运行的代码。

### 输入依据

- `docs/specs/ADR/ADR-023-外部编码智能体接入方案.md`
- `docs/specs/contracts/external-agent-contract.md`
- `docs/specs/skills/claude-code-skill-spec.md`
- `docs/specs/skills/codex-skill-spec.md`

### 新增文件

- 外部 CLI 子进程执行器：
  - `runtime/skills/external_cli.py`

### 代码修改

- `runtime/skills/base.py` — SkillDefinition 新增 `command`、`args_template` 字段，支持配置外部 CLI 路径与参数模板
- `runtime/skills/registry.py` — SkillRegistry 新增 `command`/`args_template` 解析，`resolve_stage` 新增 `prefer_entrypoint` 多技能自动选择（external_cli > agent）
- `runtime/skills/__init__.py` — 导出 ExternalCLIExecutor 及相关异常类
- `runtime/orchestrator/orchestrator.py` — 新增 `_resolve_preferred_skill_name`（自动升级到外部 CLI）、`_call_external_skill`（外部 CLI 执行 + 回退）、`_call_skill` 分支路由；`_classify_failure` 支持 ExternalCLIError 分类
- `runtime/specs/registries/skills.registry.json` — 新增 `claude_code@1.0.0`、`codex@1.0.0` 外部 CLI Skill 注册
- `runtime/specs/registries/agents.registry.json` — coding/review agent 的 allowed_skills 纳入 claude_code/codex
- `rules/execution-rules.json` — 新增 claude_code、codex 的 skill_timeouts
- `rules/permission-rules.json` — allowed_skills 与 role_skill_whitelist 纳入 claude_code、codex

### 架构设计要点

1. **入口分流**：`SkillDefinition.entrypoint` 字段控制路由——`"agent"` 走内置 Agent，`"external_cli"` 走子进程执行器
2. **自动升级**：当 CLI 工具可用时，`_resolve_preferred_skill_name` 自动将 `coding.generate_patch` → `claude_code`、`review.analyze_changes` → `codex`
3. **优雅降级**：CLI 不可用时自动回退到内置 Agent 实现，保证系统始终可运行
4. **错误映射**：`ExternalCLIError` 子类→`FailureCategory`→`error_code` 三级映射，与 ADR-014 对齐
5. **输出兼容**：ExternalCLIExecutor 产出与 Agent.handle() 相同格式的 payload，`_normalize_coding_output`/`_normalize_review_output` 无需修改

### 调用链路

```
Coding Agent (编排)
    │
    ▼
_resolve_preferred_skill_name → "claude_code"
    │
    ▼
SkillRuntime.plan_invocation("claude_code")
    │
    ▼
_call_external_skill:
  ├─ ExternalCLIExecutor.execute()
  │     ├─ 创建隔离工作区 workspaces/task_XXX/
  │     ├─ 注入 $WORKSPACE_ROOT, $TASK_ID, $TRACE_ID
  │     ├─ subprocess: claude -p "..."  (cwd=repo_root, 与 Orchestrator 路径对齐)
  │     ├─ 超时管控 (SIGTERM → SIGKILL, grace=5s)
  │     └─ 解析 stdout JSON → agent 兼容格式
  │
  └─ [fallback] CodingAgent.handle()  (CLI 不可用时)
```

### 测试开关

设置 `AGENTHUB_DISABLE_EXTERNAL_CLI=1` 环境变量可强制走内置 Agent 路径，供测试套件使用：

| 模式 | 环境变量 | Coding 实现 | 典型耗时 |
|------|----------|-------------|----------|
| 外部 CLI | 默认（不设） | Claude Code 子进程 | ~60-90s |
| 内置 Agent | `AGENTHUB_DISABLE_EXTERNAL_CLI=1` | CodingAgent.handle() | ~10ms |

### 当前限制

- Claude Code / Codex CLI 需要在运行环境中预先安装
- 子进程输出解析依赖 JSON 围栏提取，纯文本输出降级为保守兼容格式
- 工作区隔离通过 `$WORKSPACE_ROOT` 环境变量实现，依赖 CLI 工具自觉遵守
- CLI 当前在 repo_root 运行（非物理隔离工作区），物理隔离留待后续阶段
- 尚未实现远端工作节点调度（当前仅支持本地子进程）

## 测试与验证

### 快速测试（内置 Agent，毫秒级）

```bash
AGENTHUB_DISABLE_EXTERNAL_CLI=1 .venv/bin/python -m unittest discover -s tests -v
```

**结果**（36 项，0 新增失败）：

```
Ran 36 tests in 0.226s

PASS (31):
  test_best_effort_sink_failure_does_not_raise
  test_jsonl_sink_writes_one_event_per_line
  test_max_records_eviction_keeps_newest_by_timestamp
  test_retain_days_eviction_by_time
  test_cancel_queued_runtime_task
  test_healthz
  test_submit_task_and_poll_result
  test_submit_task_requires_internal_token
  test_load_spec_reads_schemas_and_registries
  test_retry_applies_limit_and_min_backoff_then_succeeds
  test_retry_exhaustion_returns_structured_failure
  test_agent_output_schema_invalid_persists_error
  test_envelope_schema_invalid_raises
  test_rules_required_sections_missing_raises
  test_state_machine_illegal_transition_emits_diagnostic
  test_orchestrator_run_demo_task_records_skill_dispatch
  test_skill_runtime_plans_invocation_from_rules_and_registry
  test_skill_runtime_rejects_skill_for_wrong_role
  test_blocked_subtask_can_be_requeued_after_release
  test_context_budget_trims_recent_events_and_dependency_summaries
  test_orchestrator_run_demo_task_uses_stage4_task_plan
  test_scheduler_level_lock_reservations_conflict_and_release
  test_scheduler_level_lock_reservations_expire
  test_task_plan_ready_semantics_and_conflict_detection
  test_task_plan_rejects_cycle
  test_task_planner_auto_appends_review_and_artifact
  test_task_planner_builds_plan_with_explicit_agent_clauses
  test_task_planner_chunks_files_by_adr007_limit
  test_task_planner_detects_fanout_parallel_hint
  test_wait_queue_age_based_ordering
  test_workerpool_task_cancel_and_timeout_signals

FAIL (5, 全部为预存失败):
  test_orchestrator_emits_required_metrics      ← review_pass_rate 指标未实现
  test_cross_ownership_write_denied             ← 临时目录无 spec 文件
  test_deny_shell_flag_blocks_dangerous         ← 临时目录无 spec 文件
  test_forbidden_action_error_contains_violations ← 临时目录无 spec 文件
  test_forbidden_delete_denied_at_runtime       ← 临时目录无 spec 文件
```

### 真实验证（Claude Code 全链路）

```bash
# 清理旧文件后运行完整 Demo
rm -f demo_workspace/hello.txt
.venv/bin/python -m runtime.demo
```

**结果**（全链路闭环通过）：

```
Coding  (Claude Code, ~70s): 生成 demo_workspace/hello.txt
Review  (内置 Agent):        pass=true, issues=[]
Artifact (内置 Agent):       归档至 artifacts/{task_id}/

输出文件内容: "Hello, world! This is a minimal reviewable change."
```

### 其他验证

```bash
# Smoke Test
AGENTHUB_DISABLE_EXTERNAL_CLI=1 .venv/bin/python -m runtime.smoke_test
# → Ran 1 test in 0.023s OK

# Rules 合法性
.venv/bin/python -m runtime.harness.validator.validate_rules
# → 全部规则文件通过 schema 校验

# Gateway 测试
cd gateway && go test ./... && cd ..
# → 全部通过
```
