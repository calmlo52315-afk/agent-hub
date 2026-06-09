# 第五阶段验收清单

- [x] 已建立独立 `gateway/` Go 模块，未侵入式改造现有 Python Runtime 主链路
- [x] 已落地 `Gin + WebSocket` Gateway 服务入口
- [x] 已落地 Runtime 内部 `FastAPI + Pydantic` 服务入口
- [x] Gateway 默认已切换为 SQLite 持久化存储
- [x] 已实现 Bearer Token 与 `ws_ticket` 两级鉴权模型
- [x] 已实现 Session / Task / Artifact 的最小 REST API 闭环
- [x] 已实现 `session.subscribe`、`chat.message`、`ack`、`heartbeat`、基础 replay
- [x] Gateway 已能通过 HTTP client 调用现有 Runtime FastAPI 异步任务接口
- [x] 已补齐 `task cancel`，并支持 Gateway -> Runtime 的 best-effort cancel 联动
- [x] 已补齐 `task timeout`，超时后会落为明确的 `timed_out` 状态与错误码
- [x] 已补齐 `poll timeout`，轮询超时会落为明确的 `poll_timeout` 错误码
- [x] Runtime 执行结果已能映射为 `task.created`、`task.updated`、`task.completed`、`review.completed`、`artifact.created`
- [x] 已生成 diff card 与 artifact bundle card，供后续前端直接消费
- [x] 已保留 `memory` 存储抽象接口，便于后续继续演进到 Postgres / Redis
- [x] 已补齐 Stage 5 文档留痕：输入参考、任务清单、验收清单、变更记录
- [x] 已补充低优先级待办文档 `todo.workerpool.md`
- [x] 已补充基础 Go 单元测试并执行 `go test ./...`
- [x] 已补充 Runtime FastAPI 单元测试并执行 `./.venv/bin/python -m unittest tests.unit.test_runtime_api`
