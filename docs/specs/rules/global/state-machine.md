# Purpose

定义 Stage 4 Orchestrator 的任务状态机与子任务状态机规则，用于约束任务拆分、DAG 调度、依赖满足判定、重试、返工与终态收敛行为。

# Scope

本 Rule 适用于主任务、子任务、调度队列和 Orchestrator 的状态流转控制，覆盖任务创建、拆分、依赖等待、执行、重试、失败和归档全流程。

# Rules

1. 主任务与子任务 MUST 分层建模，禁止只用单一状态描述整个 DAG。
2. 主任务创建后 MUST 先进入 `planning`，完成拆分与依赖图构建后方可进入 `scheduled`。
3. 子任务初始状态 MUST 为 `pending`；当依赖满足且锁可获取时，方可进入 `ready`。
4. 子任务进入 `running` 前，调度器 MUST 完成依赖检查、路由决策和锁申请。
5. 子任务成功后 MUST 进入 `success`，并触发后继节点就绪性重算。
6. 子任务失败后 MAY 按重试策略回到 `ready`；超过重试上限后 MUST 进入 `failed`。
7. 若子任务因依赖失败而不可继续，MUST 进入 `blocked` 或 `skipped`，并保留原因。
8. 主任务仅当所有必需子任务成功后，方可进入 `success`。
9. 任一阻塞性子任务永久失败时，主任务 MUST 进入 `failed`，除非显式声明了降级路径。
10. 只有 Orchestrator 可以驱动状态转移；Agent 只能返回结果和状态建议，不得直接改写状态机。
11. 所有状态转移 SHOULD 产出结构化事件，供 replay、metrics 和 review 使用。
12. 消息协议中的 `status` 字段 MUST 继续使用 ADR-011 规定的 `pending/running/success/failed`，不得与内部丰富状态机混淆。

# Main Task States

- `created`：任务已创建但尚未解析。
- `planning`：Orchestrator 正在拆分任务、构建 DAG、分配路由。
- `scheduled`：DAG 已生成，节点进入调度队列。
- `running`：至少一个子任务正在执行。
- `success`：所有必需子任务已成功完成。
- `failed`：阻塞性子任务失败且无可行降级路径。
- `cancelled`：任务被人工或系统取消。

# Subtask States

- `pending`：节点已创建，尚未进入就绪判定。
- `blocked`：依赖未满足或锁冲突，暂不可执行。
- `ready`：依赖满足、资源可用、可被调度。
- `running`：节点正在执行。
- `retrying`：节点失败后等待按策略重试。
- `success`：节点成功完成。
- `failed`：节点永久失败。
- `skipped`：由于依赖失败或策略跳过，不再执行。

# Transition Rules

- 主任务：`created -> planning -> scheduled -> running -> success|failed|cancelled`
- 子任务：`pending -> blocked|ready -> running -> success|retrying|failed`
- 重试：`retrying -> ready`
- 依赖失败：`blocked -> skipped|failed`
- 非法转移 MUST 记录 `illegal_transition` 诊断事件并终止当前转移。

# Dependency Semantics

- 子任务进入 `ready` 的前提是：所有 `dependency_ids` 对应节点均为 `success`。
- 若存在可选依赖，必须在节点定义中显式标记，否则默认视为强依赖。
- 后继节点读取前驱结果时 MUST 读取前驱最近一次成功输出。
- 前驱节点 `failed` 且无降级输出时，后继节点 MUST NOT 进入 `ready`。

# Constraints

- Stage 4 状态机 MUST 兼容内存版工业级 DAG 执行器，不依赖第三方工作流框架。
- 状态机 MUST 支持并发节点，但并发不应绕过依赖和锁约束。
- 调度层 MUST 以结构化事件驱动状态推进，避免隐式状态漂移。
- 主任务与子任务状态 SHOULD 可分别回放，便于比赛答辩展示协作链路。

# Forbidden Actions

- Agent MUST NOT 自行推进主任务或子任务状态。
- 系统 MUST NOT 在依赖未满足时强行运行后继节点。
- 系统 MUST NOT 用消息 `status` 代替 DAG 节点内部状态。
- 系统 MUST NOT 在永久失败节点后继续触发依赖它的强依赖节点。

# Examples

- Valid: 设计子任务成功后，两个互不冲突的 Coding 子任务同时进入 `ready` 并并发执行。
- Valid: Review 子任务失败后进入 `retrying`，补充反馈后重新回到 `ready`。
- Invalid: 子任务依赖未完成却直接从 `pending` 跳到 `running`。
- Invalid: 主任务中一个阻塞性子任务失败，但系统仍将主任务标记为 `success`。

# References

- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/ADR/ADR-011-message-protocol.md`
- `docs/specs/ADR/ADR-012-task-state-machine.md`
- `docs/specs/contracts/task-state-machine-spec.md`
- `docs/specs/contracts/task-schema-spec.md`
- `docs/specs/contracts/dag-execution-spec.md`
