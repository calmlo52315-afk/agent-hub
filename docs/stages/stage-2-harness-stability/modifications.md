# 第二阶段变更记录

## 阶段定位

本阶段对应 `stage-2-harness-stability`，目标是让 AgentHub 运行时默认具备“不会崩、可恢复、可诊断、可复现”的能力。

本阶段基于以下输入推进开发：

- 由开发者提供的 ADR：
  - `docs/specs/ADR/ADR-008-replay-storage.md`
  - `docs/specs/ADR/ADR-009-metrics.md`
- 由开发者设计并确认的全局 rules：
  - `docs/specs/rules/**`
- 第一阶段已经完成的最小运行时骨架：
  - `runtime/orchestrator/`
  - `runtime/agents/`
  - `runtime/harness/`

## AI 辅助开发说明

<br />

- 开发者负责确定阶段目标、技术选型（Pydantic-first）、参考 ADR 与规则边界
- AI 根据既有 rules / ADR / 阶段任务文档，补齐运行时模块实现、测试样例与阶段文档
- AI 输出的实现结果继续回写到阶段文档、测试文件与运行时代码中，形成可审计留痕

## 阶段任务描述

本阶段围绕 Harness 稳定性建设，完成了以下任务：

- 建立统一 Schema 校验能力，确保消息与 Agent 输出结构可解析、可验证
- 建立 rules 必需段校验与 Forbidden Actions 运行时限制
- 建立失败分类、重试、降级与结构化失败返回
- 建立状态机驱动执行，约束状态迁移合法性
- 建立 Replay 存储能力，保证任务执行过程可复盘
- 建立 Metrics 事件输出能力，支持任务质量与性能观测
- 建立负向测试与回归验证，保证稳定性能力真正生效

## 输入输出限制

### 输入限制

- 运行时消息必须满足统一 `MessageEnvelope` 结构，至少包含：
  - `task_id`
  - `type`
  - `agent`
  - `timestamp`
  - `payload`
- Agent 输出必须为可解析 JSON，且满足对应 Pydantic Schema
- rules 文件必须具备运行时必需段，缺失或格式非法时应快速失败
- Replay 仅接收结构化 message / event / artifact metadata，不直接依赖业务代码文本作为核心索引
- Metrics 输入来自 Orchestrator / Harness 边界事件，不允许由 Agent 自行直写指标文件

### 输出限制

- 校验输出必须为结构化 `ValidationResult`
- 失败结果必须为结构化 failure 对象，不允许仅返回自然语言错误
- Replay 输出必须写入 SQLite，并受以下策略约束：
  - `retain_days = 30`
  - `max_records = 5000`
- Metrics 输出必须为 JSON Lines，且每条事件至少包含：
  - `task_id`
  - `agent`
  - `metric`
  - `value`
  - `timestamp`
- 本阶段不要求提供完整 dashboard、可视化大盘或复杂 replay 检索，只要求结构化落盘与可验证输出

## 规则与文档补充

- 补充 Metrics 规则文档（对应 ADR-009）：
  - `docs/specs/rules/metrics/metrics.md`
- 补充 Replay 规则文档（对应 ADR-008）：
  - `docs/specs/rules/replay/replay.md`
- 补充 Schema 校验规则文档（Pydantic-first）：
  - `docs/specs/rules/validator/schema-validation.md`
- 补充第二阶段阶段文档：
  - `docs/stages/stage-2-harness-stability/tasks.md`
  - `docs/stages/stage-2-harness-stability/checklist.md`
  - `docs/stages/stage-2-harness-stability/modifications.md`

## 代码实现变更

- 实现运行时 Schema 校验与 Orchestrator 边界校验：
  - `runtime/harness/validator/schemas.py`
  - `runtime/harness/validator/runtime_validator.py`
- 实现 rules schema 校验：
  - `runtime/config/rules_schema.py`
- 实现状态机约束：
  - `runtime/harness/state_machine.py`
- 实现失败分类、重试与结构化降级结果：
  - `runtime/harness/retry/`
- 实现 Replay SQLite 存储与保留策略：
  - `runtime/harness/replay/sqlite_store.py`
- 实现 Metrics JSONL 输出能力（best-effort）：
  - `runtime/harness/metrics/`

## 测试与验证产物

- 新增 Stage 2 单元测试：
  - `tests/unit/test_stage2_validation.py`
  - `tests/unit/test_stage2_retry.py`
  - `tests/unit/test_stage2_forbidden_actions.py`
  - `tests/unit/test_replay_sqlite_store.py`
  - `tests/unit/test_metrics_jsonl.py`
- 本阶段通过：
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `python3 -m runtime.smoke_test`

