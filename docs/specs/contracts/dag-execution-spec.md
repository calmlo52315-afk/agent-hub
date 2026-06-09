# DAG Execution Spec

## 1. 目标

定义 Stage 4 自研 DAG 执行器的表示方式与执行语义，确保任务拆分后的子任务能够在 `asyncio + 内存任务队列` 模型下稳定执行、可并行、可串行、可回放。

## 2. 非目标

本阶段明确不引入以下方案：

- LangGraph
- 任何第三方工作流框架
- 外部消息队列驱动的分布式 Worker Pool

## 3. DAG Model

建议的 DAG 结构如下：

```json
{
  "task_id": "task-root-001",
  "nodes": [
    {
      "subtask_id": "coding-ui-001",
      "agent": "coding",
      "priority": "high",
      "status": "ready"
    },
    {
      "subtask_id": "review-ui-001",
      "agent": "review",
      "priority": "high",
      "status": "blocked"
    }
  ],
  "edges": [
    {
      "from": "coding-ui-001",
      "to": "review-ui-001",
      "type": "hard"
    }
  ]
}
```

说明：

- `nodes`：子任务节点集合。
- `edges`：依赖边集合。
- `type=hard`：强依赖，前驱失败时后继不得运行。
- 当前阶段推荐只支持 `hard` 依赖；若后续增加弱依赖，必须先补规则和验证逻辑。

## 4. Ready 语义

节点进入 `ready` 必须同时满足：

1. 所有强依赖节点状态为 `success`。
2. 节点本身未超过 `retry_limit`。
3. 目标文件锁可全部获取。
4. 目标 Agent 可用且路由合法。
5. 上下文拼装完成，且预算检查通过。

只要任一条件不满足，节点不得进入执行队列。

## 5. Scheduling Semantics

- 调度器必须维护 `pending`、`ready`、`running`、`blocked` 四类运行中节点集合。
- 每轮调度先扫描可运行节点，再根据优先级和资源约束决定是否并发。
- 节点无依赖冲突且无文件写冲突时，可以并行执行。
- 节点执行完成后，调度器必须立即重算其直接后继节点的就绪条件。
- 调度器应尽量保持 deterministic 行为：同一输入下优先得到相同的节点选择顺序。

## 6. Retry / Timeout 语义

- 每个节点独立维护 `attempt` 计数。
- 节点超时或可重试错误时，状态进入 `retrying`，随后回到 `ready`。
- 重试次数超过 `retry_limit` 后，节点进入 `failed`。
- 非可重试错误可直接进入 `failed`。
- 节点失败后，调度器必须重新评估后继节点是否应进入 `blocked` 或 `skipped`。

## 7. Main Task Completion

主任务收敛规则：

- 所有必需节点 `success`：主任务进入 `success`。
- 任一阻塞性节点永久 `failed` 且无降级路径：主任务进入 `failed`。
- 用户取消或系统显式终止：主任务进入 `cancelled`。

## 8. Event Model

调度器至少应记录以下事件：

- `task.planned`
- `task.scheduled`
- `subtask.ready`
- `subtask.dispatched`
- `subtask.blocked`
- `subtask.retrying`
- `subtask.success`
- `subtask.failed`
- `task.success`
- `task.failed`

推荐事件结构：

```json
{
  "event_type": "subtask.dispatched",
  "task_id": "task-root-001",
  "subtask_id": "coding-ui-001",
  "agent": "coding",
  "priority": "high",
  "timestamp": "2026-06-04T10:05:00Z"
}
```

## 9. Runtime Constraints

- Stage 4 DAG 执行器必须基于内存实现，适合比赛演示与本地 review。
- 并发调度必须基于 `asyncio` 与内存任务队列，不得偷换成串行伪并发描述。
- DAG 执行器必须能输出可审计的结构化事件，用于 replay 和答辩演示。
- DAG 执行器必须兼容现有三核心 Agent 边界，不得绕过 Orchestrator。

## 10. References

- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/ADR/ADR-011-message-protocol.md`
- `docs/specs/contracts/task-schema-spec.md`
