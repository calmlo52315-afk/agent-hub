# 第二阶段任务清单

## 阶段任务描述

本阶段目标是把 AgentHub 运行时从“能跑通最小闭环”推进到“默认具备稳定性保障”的状态，重点补齐以下能力：
- 结构化输入输出校验
- 运行时规则校验
- 失败分类与重试降级
- 状态机驱动执行
- 回放存储与保留策略
- 指标采集与非阻塞输出

## 任务拆解

- [x] 任务 1：实现 Schema 校验能力（Pydantic-first）
  - [x] 定义运行时 Pydantic Schema，覆盖消息信封与核心 Agent 输出
  - [x] 在 Harness 中提供统一 validator 入口，并在 Orchestrator 边界强制执行
  - [x] 将校验失败结果结构化落盘，供诊断与回放使用

- [x] 任务 2：实现 Rules 校验能力（运行时规则合规）
  - [x] 校验必需规则段是否存在且可解析
  - [x] 在运行时边界执行 Forbidden Actions 限制（MVP 阶段采用 best-effort）

- [x] 任务 3：实现失败分类与 Retry/Fallback 管线
  - [x] 定义失败类别：`schema_invalid`、`review_failed`、`timeout`、`permission_denied`、`unknown`
  - [x] 实现基于 `retry_limit` 的重试策略与最小 backoff
  - [x] 在重试耗尽后返回结构化失败结果，作为阶段内 fallback 形态

- [x] 任务 4：实现状态机驱动执行
  - [x] 在统一位置定义任务状态与允许迁移关系
  - [x] 阻止非法状态迁移，并输出诊断事件

- [x] 任务 5：实现 Replay 存储（对应 ADR-008）(回放存储)
  - [x] 使用 SQLite 落地回放存储，并实现 `retain_days` / `max_records` 保留策略（保留天数，最大保留条数）
  - [x] 持久化 message / event / artifact metadata 三类时间线记录

- [x] 任务 6：实现 Metrics 输出（对应 ADR-009）
  - [x] 按必需指标清单输出 JSON Lines 格式指标事件
  - [x] 所有指标按 `task_id` 与 `agent` 维度打标签
  - [x] 指标输出不得阻塞主流程，失败时按 best-effort 降级

- [x] 任务 7：完成测试与验证
  - [x] 增加 schema 非法输出的负向测试
  - [x] 增加 replay 保留策略测试
  - [x] 增加 metrics 输出及必需标签测试
