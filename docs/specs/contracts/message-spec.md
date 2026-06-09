# Message Spec

## 1. 目标

定义 AgentHub MVP 的统一消息协议（envelope），保证 Orchestrator 可稳定路由、可回放、可审计。

## 2. 序列化格式

- JSON
- UTF-8

## 3. Envelope Schema

所有跨 Agent 消息必须符合以下结构：

```json
{
  "schema_version": "1.0",
  "message_id": "string",
  "task_id": "string",
  "trace_id": "string",
  "timestamp": "string",
  "sender": {
    "type": "orchestrator|agent",
    "id": "string"
  },
  "receiver": {
    "type": "orchestrator|agent",
    "id": "string"
  },
  "kind": "task|command|event|result|error",
  "status": "pending|running|success|failed",
  "in_reply_to": "string",
  "payload": {}
}
```

字段语义：

- `schema_version`：协议版本；运行时应拒绝不兼容版本
- `message_id`：消息唯一 ID
- `task_id`：工作流任务 ID，全链路透传
- `trace_id`：同一工作流/执行链路的追踪 ID
- `timestamp`：ISO-8601
- `sender` / `receiver`：发送方与接收方身份
- `kind`：消息用途类型
- `status`：消息携带的执行状态
- `in_reply_to`：请求-响应关联（可空）
- `payload`：业务载荷，结构由 Agent Spec 定义

## 4. 消息类型（kind）

最小集合：

- `task`：Orchestrator 投递任务输入给 Agent
- `result`：Agent 返回结构化输出
- `error`：Agent/Orchestrator 产生错误（可带 error payload）
- `event`：可观察事件（状态变化、锁获取/释放等）
- `command`：运行时内部命令（例如重试、取消）

## 5. 时序约束（Sequencing）

- 所有 Agent 间通信必须经由 Orchestrator 中转（见 [communication-rules](../../../rules/communication-rules.json)）
- Orchestrator 必须维护任务状态机（见 [execution-rules](../../../rules/execution-rules.json)）
- `result` 必须携带与输入 `task_id` 一致的 `task_id`
- `status=failed` 的 `error`/`result` 必须携带可诊断的错误信息（见 6.1）

## 6. Error Payload（建议）

### 6.1 `ErrorPayload`

```json
{
  "code": "string",
  "message": "string",
  "details": {},
  "retryable": true
}
```

## 7. 兼容性规则

- 新增字段必须向后兼容（接收方忽略未知字段）
- 删除或改变字段语义必须提升 `schema_version`

## 8. 参考

- [ADR-011-message-protocol](../../ADR/ADR-011-message-protocol.md)

