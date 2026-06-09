# 第五阶段输入参考文档

本文件只记录 Stage 5 `Gateway & Frontend 集成（可演示的产品闭环）` 的输入依据，供后续实现时引用。

## 阶段目标

IM 形态的多 Agent 群聊、流式消息、artifact 展示、diff 展示、会话管理。

## ADR 输入

- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-019-Session-Model.md`
- `docs/specs/ADR/ADR-020-WebSocket Protocol`
- `docs/specs/ADR/ADR-021-Human-in-the-Loop`
- `docs/specs/ADR/ADR-022-Gateway-Authentication.md`

## Contract / Spec 输入

- `docs/specs/contracts/message-spec.md`
- `docs/specs/contracts/websocket-message-spec.md`
- `docs/specs/contracts/session-task-api-spec.md`
- `docs/specs/contracts/artifact-card-schema-spec.md`

## Rules 输入

- `docs/specs/rules/global/protocol.md`
- `docs/specs/rules/global/project.md`
- `docs/specs/rules/global/runtime-agent-boundary.md`
- `docs/specs/rules/communication/communication.md`
- `docs/specs/rules/permission/permission.md`
- `docs/specs/rules/context/context.md`
- `docs/specs/rules/dispatch/dispatch.md`
- `docs/specs/rules/ownership/ownership.md`
- `docs/specs/rules/ownership/lock.md`

## 需求输入

- `docs/specs/需求文档.md`

## 当前约束

- 当前实现范围只覆盖 Gateway 侧，不包含前端开发。
- Runtime 与 Gateway 的内部对接方式已收敛为 `Go HTTP Client -> FastAPI Runtime Internal API`。
- Gateway 默认持久化方案已收敛为 `SQLite`。
- Runtime Internal API 已收敛为“提交任务 + 查询状态”的异步模式。
- Gateway 当前已补齐 `task cancel / task timeout / poll timeout`。
- 本阶段的任务拆解、验收清单与变更记录已分别沉淀到 `tasks.md`、`checklist.md`、`modifications.md`。
