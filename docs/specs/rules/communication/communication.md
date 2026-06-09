# Purpose

定义 Stage 5 Frontend <-> Gateway 的实时通信规则，覆盖消息类型、连接顺序、ack 语义、断线重连与事件重放，支撑 IM 形态的多 Agent 群聊闭环。

# Scope

本规则适用于：

- 前端与 Gateway 的 WebSocket 连接
- 会话初始化后的消息订阅与流式渲染
- 聊天消息、任务状态、评审结果、artifact 卡片事件
- 断线重连、ack、replay 与 snapshot 回补

Runtime 内部消息协议继续由 `message-spec.md` 约束；本规则只描述外部边界上的通信行为。

# Rules

1. Frontend 与 Gateway 的所有实时通信 MUST 使用 `websocket-message-spec.md` 定义的统一 JSON envelope。
2. Frontend MUST 先完成 HTTP 鉴权与 `ws_ticket` 获取，再发起 WebSocket 连接。
3. WebSocket 建连成功后，客户端 MUST 先发送 `session.subscribe`，Gateway MUST 回复 `connection.ready` 或 `system.error`。
4. 所有带状态变更语义的客户端命令 SHOULD 开启 `ack.required=true`。
5. Gateway 在收到合法命令后 MUST 先发送 `ack_mode=received`，完成业务受理后 MUST 再发送 `ack_mode=processed`。
6. Gateway MUST 为每个 `session_id` 分配严格递增的 `seq`，前端 MUST 按 `seq` 渲染同一会话内的事件顺序；客户端上行命令 MAY 不携带 `seq`。
7. 前端断线重连时 MUST 带上最近已确认的 `resume_from_seq`，Gateway SHOULD 尝试重放缺失事件。
8. 若 Gateway 无法安全重放指定区间，MUST 返回 `session.snapshot`，并从新的 `seq` 继续流式推送。
9. `chat.message` 的流式分片 MUST 共享同一业务消息标识，并通过 `status=streaming|success|failed` 表示流结束状态。
10. `task.created`、`task.updated`、`task.completed` MUST 保留一致的 `task_id`，禁止用不同任务 ID 表示同一执行单元。
11. `artifact.created` 事件中的卡片数据 MUST 符合 `artifact-card-schema-spec.md`。
12. 心跳消息 SHOULD 周期性发送；连续多个心跳超时后，前端 SHOULD 触发重连，Gateway MAY 主动关闭失活连接。
13. 所有通信错误 MUST 标准化为 `system.error` 事件，禁止回传裸文本错误。
14. Frontend MUST NOT 直接与 Runtime 建立连接，所有外部消息都 MUST 经过 Gateway。

# Message Type Catalog

客户端允许发送的最小集合：

- `session.subscribe`
- `chat.message`
- `task.retry.request`
- `task.cancel.request`
- `task.approval.submit`
- `conflict.resolution.submit`
- `heartbeat`

服务端允许推送的最小集合：

- `connection.ready`
- `session.snapshot`
- `chat.message`
- `task.created`
- `task.updated`
- `task.completed`
- `review.completed`
- `artifact.created`
- `approval.required`
- `ack`
- `system.error`
- `heartbeat`

# Ordering

- `seq` 是前端渲染顺序与 replay 光标的唯一依据。
- `timestamp` 用于审计、跨系统对齐与调试，不作为重放游标。
- 同一 `task_id` 的事件 SHOULD 保持逻辑顺序：`task.created` -> `task.updated*` -> `task.completed|system.error`。
- 流式 `chat.message` 分片 MAY 与 `task.updated` 交错出现，但每种事件都必须保持其各自 `seq` 顺序稳定。

# Ack Model

- `received` 表示 Gateway 已完成 envelope 校验、鉴权、会话绑定与基础权限检查。
- `processed` 表示 Gateway 已将命令成功受理，或已给出明确拒绝结果。
- 若命令被拒绝，`processed` ack MUST 标记 `accepted=false` 并附带拒绝原因。
- 需要人工确认的命令在进入审批前 MAY 先返回 `processed` ack，然后再下发 `approval.required`。

# Replay Model

- Gateway SHOULD 为每个会话维护最近一段事件缓冲与可持久化游标。
- 重连 replay MUST 以 `resume_from_seq` 为起点，不得以客户端本地时间戳估算。
- 被重放的事件 SHOULD 使用 `status=replayed` 或在 `payload` 中标记 replay 来源。
- 若缓冲已过期、会话已迁移或游标非法，Gateway MUST 发 `session.snapshot` 而不是静默丢事件。

# Constraints

- 所有实时消息 MUST 为 UTF-8 JSON。
- 所有实时消息 MUST 带 `session_id`。
- 所有任务相关消息 MUST 带 `task_id`。
- 所有变更类命令 MUST 经过鉴权和权限校验。
- Gateway MUST 作为唯一外部通信边界；Runtime 内部细节 MUST NOT 直接暴露给前端。

# Forbidden Actions

- Frontend MUST NOT 直接调用 Runtime 内部 API。
- Gateway MUST NOT 向前端发送未包裹 envelope 的裸字符串。
- 客户端 MUST NOT 跳过 `session.subscribe` 就直接发送业务命令。
- Gateway MUST NOT 接受缺少有效会话绑定的变更命令。
- 系统 MUST NOT 使用 `timestamp` 代替 `seq` 做断线续传。

# Examples

- Valid: 前端完成 REST 鉴权后申请 `ws_ticket`，连接成功后发送 `session.subscribe`，随后收到 `connection.ready`、`chat.message` 与 `task.updated` 流。
- Valid: 前端断线后以 `resume_from_seq=124` 重连，Gateway 回放 125-130 的事件，再继续推送最新流。
- Invalid: 前端通过 HTTP 直接长轮询 Runtime 获取任务流式输出。
- Invalid: Gateway 直接把内部异常字符串写进 WebSocket，而不发 `system.error` envelope。

# References

- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-020-WebSocket Protocol`
- `docs/specs/ADR/ADR-022-Gateway-Authentication.md`
- `docs/specs/contracts/websocket-message-spec.md`
- `docs/specs/contracts/artifact-card-schema-spec.md`
