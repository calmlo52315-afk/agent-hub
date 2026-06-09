# Purpose

定义 Stage 4 的任务分发规则，约束 Orchestrator 如何根据 `@agent` 指令、任务优先级、依赖关系、并发度和文件冲突情况，把主任务拆成可执行的子任务并路由到合适的 Agent。

# Scope

本 Rule 适用于主任务解析、子任务路由、DAG 节点调度、队列优先级和并发控制，覆盖 Coding / Review / Artifact 三个核心 Agent 的所有任务分发场景。

# Rules

1. 所有任务分发 MUST 由 Orchestrator 执行，Agent MUST NOT 彼此直接派发任务。
2. Orchestrator MUST 在分发前先完成任务拆分，确保单个子任务原则上只覆盖不超过 3 个物理文件。
3. 当用户输入显式包含 `@agent` 时，Orchestrator SHOULD 优先按显式路由解释意图；若显式路由与角色边界冲突，则 MUST 拒绝或改写为合法计划。
4. 未显式指定 `@agent` 时，Orchestrator MUST 根据子任务类型路由到固定角色：代码生成到 Coding、代码审查到 Review、产物收集到 Artifact。
5. 子任务仅在依赖全部满足、锁申请成功、上下文拼装完成后，方可进入待执行队列。
6. 调度器 MUST 先选出 `ready` 节点，再按优先级、创建时间和资源可用性排序。
7. 同优先级节点之间 MAY 并发执行，但并发数 MUST 受全局 `max_parallel_tasks` 和按角色并发上限约束。
8. 若两个 `ready` 节点存在文件写冲突，调度器 MUST 只启动其中一个，另一个进入 `blocked` 或等待队列。
9. 子任务失败后，调度器 MUST 按节点 `retry_limit` 与 `timeout_seconds` 处理重试，不得无限重试。
10. Review 驳回后，Orchestrator SHOULD 生成新的返工 Coding 子任务，而不是直接复用已完成节点的输出。
11. Artifact 阶段 MUST 等待所有必需上游节点完成后再调度，禁止提前归档不稳定产物。
12. 所有分发决策 SHOULD 记录结构化事件，至少包含：`task_id`、`subtask_id`、`route_to`、`priority`、`dependency_state`、`queue_decision`。
13. Stage 4 工作流引擎 MUST 基于 `asyncio + 内存任务队列` 实现，MUST NOT 引入 LangGraph 或其他第三方工作流框架。

# Dispatch Inputs

- 用户原始指令，包括显式 `@agent` 标记
- 主任务与子任务 schema
- 子任务依赖图状态
- 当前文件锁与所有权状态
- 角色边界与权限规则
- 并发度配置与超时/重试配置

# Dispatch Outputs

- `TaskPlan`：主任务拆分结果
- `SubtaskDispatchDecision`：子任务调度决策
- `QueueEvent`：入队、出队、阻塞、重试、取消等事件
- `MessageEnvelope`：投递给目标 Agent 的结构化消息

# Priority Strategy

- `high`：阻塞主链路、用户显式点名或影响多个下游节点的任务
- `medium`：普通编码、普通评审、常规产物收集
- `low`：附属整理、可延后汇总、非阻塞分析
- 当优先级相同，先进入 `ready` 的节点优先。
- 当优先级不同但高优节点与低优节点无文件冲突时，系统 MAY 并发执行。

# Dependency Gate

- 只有全部强依赖成功的节点才能进入 `ready`。
- 只要存在阻塞性依赖处于 `failed`，当前节点 MUST 保持 `blocked` 或进入 `skipped`。
- 节点进入运行前，调度器 MUST 再做一次依赖状态复核，防止并发条件下脏读。

# Constraints

- 分发规则 MUST 遵循 ADR-002 的角色边界，不得把审查任务派给 Coding Agent。
- 分发规则 MUST 遵循 ADR-007 的任务粒度约束，不得生成无边界超大节点。
- 所有路由结果 MUST 使用 ADR-011 规定的结构化消息协议承载。
- Stage 4 调度器 MUST 支持串行与并行混合调度，但并行只能发生在依赖和锁约束都满足时。

# Forbidden Actions

- Orchestrator MUST NOT 生成超过粒度上限的单一子任务继续执行。
- Agent MUST NOT 在返回 payload 中直接派发新任务给其他 Agent。
- 系统 MUST NOT 绕过依赖检查直接把节点推入运行队列。
- 系统 MUST NOT 在文件写冲突未解决时并发执行冲突节点。
- 系统 MUST NOT 使用第三方工作流框架替代本阶段自研 DAG 引擎。

# Examples

- Valid: 用户输入“`@coding` 实现登录页，`@review` 审核表单交互”，系统拆为两个串行节点并按角色路由。
- Valid: 两个无文件冲突的 Coding 子任务都已满足依赖时，调度器并发执行。
- Invalid: 一个节点同时要求实现整个前后端系统，并直接派给单一 Coding Agent。
- Invalid: Review 失败后，系统跳过返工直接进入 Artifact。

# References

- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/ADR/ADR-011-message-protocol.md`
- `docs/specs/contracts/task-schema-spec.md`
- `docs/specs/contracts/dag-execution-spec.md`
