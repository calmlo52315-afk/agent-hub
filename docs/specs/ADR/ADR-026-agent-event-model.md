# ADR-026 Agent Event Model

## 决策

Stage 6 引入统一 Agent Event Model，作为 Runtime、Gateway、WebSocket、Replay、Metrics 的共用事件协议。

MVP 事件主序列固定为：

```text
task.created
planning.started
planning.completed
coding.started
coding.completed
review.started
review.completed
artifact.started
artifact.completed
task.completed
task.failed
```

---

## 背景

目前系统已经出现阶段事件，但没有事件标准：

- 事件名不稳定
- 字段未定型
- 无法保证前后端、Replay、Metrics、WS 使用同一协议

因此必须把事件模型前置为架构决策，而不是实现细节。

---

## 事件原则

- 所有事件 MUST 具备统一包络
- 每个阶段 MUST 遵守 `started -> completed|failed`
- `task.completed` 与 `task.failed` 只能由任务总控发出
- Approval、Retry、Fallback 相关事件 SHOULD 与主事件模型兼容
