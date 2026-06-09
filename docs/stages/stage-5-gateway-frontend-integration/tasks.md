# 第五阶段任务清单

## 阶段任务描述

本阶段目标是启动 `Gateway & Frontend 集成（可演示的产品闭环）`。

结合当前开发节奏，本轮只实现 Gateway 侧能力，不进行前端开发；但接口、协议、会话、实时流和 artifact/diff 数据结构需要先落稳，供后续前端直接接入。

本阶段重点围绕以下能力展开：

- Gateway 边界落地
- Session / Task REST API
- WebSocket 连接、ack、replay、消息流
- Gateway 鉴权与 `ws_ticket`
- Runtime FastAPI 内部服务
- Gateway SQLite 持久化存储
- Runtime 异步任务模式
- Task Cancel / Timeout / Poll Timeout
- 比赛留痕文档补齐

## 任务拆解

- [x] 任务 1：补齐 Stage 5 输入与留痕文档
  - [x] 创建 `spec.md` 作为输入参考文档
  - [x] 创建并更新 `tasks.md`
  - [x] 新增 `checklist.md`
  - [x] 新增 `modifications.md`

- [x] 任务 2：建立 Gateway 独立 Go 模块
  - [x] 新建 `gateway/` 目录
  - [x] 初始化 `go.mod`
  - [x] 采用 `Gin + WebSocket` 技术栈

- [x] 任务 3：实现 Gateway 最小存储抽象
  - [x] 定义 `AuthStore / SessionStore / TaskStore / ArtifactStore / ApprovalStore / EventStore`
  - [x] 提供内存版 `MemoryStore`
  - [x] 保留后续切换 SQLite / Postgres / Redis 的接口边界

- [x] 任务 3.1：将 Gateway 默认存储切换为 SQLite
  - [x] 新增 SQLite Store 实现
  - [x] 持久化 Session / Event / Task / Artifact / Approval / Token / WSTicket
  - [x] 保留 `memory` 后端供测试和兜底

- [x] 任务 4：实现鉴权与会话准入
  - [x] 实现 Bearer Token 校验
  - [x] 实现 `ws_ticket` 签发与消费
  - [x] 实现 Session Membership 校验

- [x] 任务 5：实现 REST API 最小闭环
  - [x] 实现 `sessions` 创建、列表、详情、消息历史、任务列表、artifact 列表
  - [x] 实现 `tasks` 查询、取消、重试、审批、冲突处理
  - [x] 实现 `artifacts` 查询
  - [x] 实现 `ws-tickets` 签发

- [x] 任务 6：实现 WebSocket 最小闭环
  - [x] 实现 `/ws` 连接入口
  - [x] 实现 `session.subscribe`
  - [x] 实现 `chat.message`
  - [x] 实现 `ack`
  - [x] 实现基于 `seq` 的基础 replay
  - [x] 实现心跳

- [x] 任务 7：实现 Runtime FastAPI 内部服务与 Gateway HTTP 适配层
  - [x] 新增 Runtime 内部 FastAPI 服务入口
  - [x] 新增 Runtime 内网鉴权 token 校验
  - [x] 将 Runtime Internal API 改为异步任务模式
  - [x] 在 Gateway 中通过 HTTP client 提交任务并轮询结果
  - [x] 把 Runtime 返回结果映射为 `task.* / review.completed / artifact.created / chat.message`

- [x] 任务 7.1：补齐运行时控制边界
  - [x] 补齐 `task cancel`
  - [x] 补齐 `task timeout`
  - [x] 补齐 `poll timeout`
  - [x] 将取消与超时状态写入会话事件流

- [x] 任务 7.2：补充低优先级阶段待办
  - [x] 新增 `todo.workerpool.md`
  - [x] 将 Postgres 与 worker pool 记录为低优先级待办

- [x] 任务 8：补充基础验证
  - [x] 增加 Gateway 单元测试
  - [x] 增加 Runtime FastAPI 单元测试
  - [x] 执行 `go test ./...`
  - [x] 执行 `./.venv/bin/python -m unittest tests.unit.test_runtime_api`
  - [x] 保持现有 Python Runtime 主编排链路不被侵入式改造
