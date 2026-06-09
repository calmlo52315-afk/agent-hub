# Purpose

定义 Stage 6 Runtime 的事件顺序、终止语义与回放约束。

# Scope

适用于 Runtime 事件发射、Gateway 事件转发、WebSocket 推送、Replay 存储与 Metrics 消费。

# Rules

1. 每个阶段的 `started` 事件 MUST 先于对应的 `completed` 或 `failed` 事件。
2. 同一阶段 MUST NOT 同时发出 `completed` 与 `failed`。
3. `task.completed` 与 `task.failed` MUST 作为任务终结事件。
4. 阶段 `failed` 事件出现后，当前阶段 MUST 终止。
5. 任务终结后，后续业务阶段事件 MUST NOT 再继续发出。
6. Approval、Retry、Fallback 相关事件 SHOULD 复用统一事件包络。
7. 所有事件 MUST 可被 Replay 与 Metrics 复用。
