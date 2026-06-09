# 第六阶段 — 真实 Agent Runtime 闭环与执行模型定型

## 阶段目标

将 AgentHub 从“可跑通的 Demo Runtime”升级为“具备真实任务规划、真实代码生成、真实评审、真实产物沉淀、真实过程可视化”的比赛可演示主链路版本。

本阶段不再把重点放在“功能看起来像在跑”，而是要求 Runtime 真正具备可解释、可展示、可验证的 Agent 执行闭环。

本阶段核心聚焦六类问题：

- Runtime 不再使用固定 demo/stub 逻辑
- 用户指令能够映射为真实目标文件与真实代码变更
- Agent 执行关系必须被明确定义，避免“谁调谁、谁依赖谁”说不清
- 前端能够看到任务执行过程，而不是仅看到最终完成
- Artifact / Diff / Review 与真实输出一致，具备展示价值
- 模型输出、事件输出、产物输出必须有统一协议，便于后续 Replay、Metrics、WebSocket 与可靠性建设复用

本阶段关键词不是“生产加固”，而是“能力可信化 + 执行模型定型”。

---

## 为什么单独拆出 Stage 6

当前系统已经暴露出明确问题：

- Coding Agent 仍是固定 demo 输出，不能根据用户需求生成真实代码
- Demo 任务计划固定写入 `demo_workspace/hello.txt`，无法根据语言/目标文件生成结果
- Gateway 对 Runtime 采用“提交后轮询直到完成”的聚合模式，前端看不到细粒度执行过程
- Diff / Artifact 虽然有卡片，但内容仍然偏 demo，和真实生成结果不完全对齐
- Planner、Coding、Review、Artifact 之间的职责关系没有被文档化，答辩时很容易被追问

在这些问题未解决前，直接进入“生产级加固与系统可靠性落地”会出现目标错位：

- 加固的是 demo 流程，而不是真实能力
- 可观测看到的是假执行链，而不是真实生成链
- 幂等、回放、重试机制虽然能做，但很难体现比赛价值

因此建议拆分：

- `Stage 6`：先把真实能力链路补齐，并定型 MVP 的 Agent Execution Model
- `Stage 7`：再做生产加固、恢复、幂等、可观测

---

## MVP 执行模型决策

### ADR-024 Agent Execution Model

本阶段必须明确回答：

```text
用户
  ↓
Planner
  ↓
Coding
  ↓
Review
  ↓
Artifact
```

在 MVP 中，系统采用：

```yaml
execution_model: linear_pipeline
```

即：

```text
Planner
  ↓
Coding
  ↓
Review
  ↓
Artifact
```

各阶段关系如下：

- `Planner`：把用户请求转换为结构化 Task Plan
- `Coding`：根据 Task Plan 产出真实 `changes`
- `Review`：基于 `changes` 与目标需求输出审查结论，不负责写代码
- `Artifact`：对已通过的输出做归档、卡片化、版本化，不参与评审

未来扩展方向：

```yaml
execution_model: dag
```

即：

```text
Planner
  ↓
 ├─ Coding-A
 ├─ Coding-B
 └─ Coding-C
        ↓
      Review
        ↓
     Artifact
```

Stage 6 只要求：

- 明确 MVP 是 `linear_pipeline`
- 文档中预留未来 `dag` 演进边界
- 所有协议与事件模型不得阻断将来从线性流切换到 DAG

---

## Planner 策略决策

### ADR-025 Planner Strategy

虽然系统已经有 Planner 概念，但必须明确当前规划策略与兜底逻辑。

MVP 决策如下：

```yaml
planner_strategy:
  primary: llm_planner
  fallback: rule_planner
```

说明：

- `llm_planner`：默认规划器，负责将用户自然语言需求转成结构化 `Task Plan`
- `rule_planner`：回退规划器，在以下情况触发：
  - 模型不可用
  - 模型超时
  - 模型输出不满足 schema
  - 用户需求属于已知模板场景

这样可以回答关键问题：

- 规划错了怎么办
- 模型挂了怎么办
- 演示时如何保证最低可用性

---

## 事件模型决策

### ADR-026 Agent Event Model

本阶段必须把 Runtime 的事件流标准化，后续 WebSocket、Replay、Metrics 全部依赖该事件协议。

MVP 标准事件序列：

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

约束：

- 每个阶段必须遵守 `started -> completed|failed` 的顺序
- 任一阶段失败后，后续阶段不得继续开始
- 所有事件必须可被 Replay、WS 推送、Metrics 复用

---

## Artifact 版本化决策

### ADR-027 Artifact Versioning

Artifact 一旦开始真实化，就必须定义版本语义。

MVP 产物元数据至少包含：

```yaml
artifact:
  task_id:
  version:
  created_at:
```

原因：

- 同一 `task_id` 可能被重试、多次生成或人工批准后继续执行
- 如果没有 `version`，就无法判断哪次产物是最终可用版本
- 前端、下载、回放、复盘都会混乱

Stage 6 要求：

- Artifact 必须支持版本号
- 前端卡片和 Artifact 元数据必须能看到版本
- 重跑场景下不得覆盖旧版本而不留痕

---

## Human Approval 决策

### ADR-028 Human Approval

比赛场景中，人工审批是显著加分项，而且当前前端已具备相关能力入口，因此 Stage 6 必须把审批作为执行链中的标准门控，而不是可有可无的补充功能。

MVP 决策：

- Review 发现高风险问题时，可进入 `approval_required`
- 人工确认后，任务可继续进入下一步或终止
- Approval 记录必须作为事件与回放数据的一部分被存档

说明：

- `ADR-021 Human-in-the-Loop` 负责定义 HITL 原则
- `ADR-028 Human Approval` 负责定义 Stage 6 中的执行门控协议与落地方式

---

## 验收达标标准

系统需全部满足以下能力：

- 能根据用户需求规划真实目标文件，而非固定 `demo_workspace/hello.txt`
- `Planner -> Coding -> Review -> Artifact` 的执行关系被明确建模并有文档支撑
- Runtime 输出的 `changes / diff / artifact` 与实际落盘文件一致
- 前端可看到 `planning -> coding -> review -> artifact` 的阶段进展
- Review 结果不再只是固定规则占位，而要与真实代码内容绑定
- Artifact 卡片可定位到真实产物目录，Diff 卡片可展示真实文件变更摘要
- 模型输出、事件输出、产物输出都已收敛到统一协议

---

## 本阶段不做什么

- 不优先做任务恢复、断点续跑、幂等去重
- 不优先做复杂自治式多 Agent society
- 不展示原始思维链（CoT）；只输出结构化推理摘要
- 不在 Stage 6 落地真正的多分支 DAG 执行器
- 不追求一次性支持任意编程语言与任意复杂工程

---

## 必补 ADR

Stage 6 必须补齐以下架构决策文档：

- `ADR-024 Agent Execution Model`
- `ADR-025 Planner Strategy`
- `ADR-026 Agent Event Model`
- `ADR-027 Artifact Versioning`
- `ADR-028 Human Approval`

这些 ADR 的价值不是“补文档”，而是统一回答以下答辩问题：

- Agent 之间怎么协作
- 为什么当前不是 DAG
- 规划错了如何回退
- 事件如何串联 WS / Replay / Metrics
- 多次生成后的最终 Artifact 如何判定
- 什么时候需要人工介入

---

## 必补 Spec

以下协议文档必须在 Stage 6 定稿：

- `task-plan-spec.md`
- `agent-execution-spec.md`
- `event-spec.md`
- `diff-spec.md`
- `artifact-card-v2-spec.md`

其中：

### `task-plan-spec.md`

定义 Planner 输出协议，至少包含：

```yaml
task_id:
summary:
language:
targets:
artifacts:
risks:
```

### `agent-execution-spec.md`

定义每类 Agent 的输入、输出、状态、事件。

示例：

```yaml
coding_agent:
  input:
    plan:
  output:
    changes:

review_agent:
  input:
    changes:
  output:
    issues:
```

### `event-spec.md`

统一定义：

```yaml
event_id:
task_id:
event_type:
timestamp:
payload:
```

### `diff-spec.md`

统一定义真实变更结构：

```yaml
path:
action:
summary:
```

其中 `action` 仅允许：

- `create`
- `update`
- `delete`

### `artifact-card-v2-spec.md`

前后端统一卡片协议，至少包含：

```yaml
title:
type:
files:
download_url:
summary:
```

---

## 必补 Rules

以下规则文档必须补齐：

- `runtime/agent-execution-rules.md`
- `runtime/event-rules.md`
- `runtime/llm-output-rules.md`

规则目标如下：

### `agent-execution-rules.md`

规定：

- Agent 不得跳步骤
- Planner 必须先执行
- Review 不能修改代码
- Artifact 不能参与评审

### `event-rules.md`

规定：

- `Started` 事件必须先于 `Completed`
- `Failed` 事件必须终止当前阶段
- Approval 与 Retry 事件必须可回放

### `llm-output-rules.md`

规定：

- LLM 输出必须通过 Schema 校验
- 校验失败必须进入重试或 fallback
- Runtime 不得直接消费裸文本输出作为结构化执行结果

---

## 工作项 1：替换 Demo Task Plan 为真实任务规划

### 目标

让 Runtime 能根据 instruction 规划真实目标文件、语言类型、输出方式，而不是固定 demo 目标。

### 当前问题

- `run_demo_task()` 默认只面向 `demo_workspace/hello.txt`
- 即使用户要求生成真实项目，TaskPlan 也不会创建对应目标文件
- Planner 的输出协议与回退策略尚未标准化

### 落地要求

- 引入 `Planner` 结构化输出，遵守 `task-plan-spec.md`
- 默认使用 `llm_planner`，失败时自动回退到 `rule_planner`
- `targets` 必须是明确的真实文件
- `risks`、`artifacts`、`summary` 必须成为标准字段，而不是临时补充字段

### 产出物

- `runtime/planner/` 真实规划实现
- `docs/specs/contracts/task-plan-spec.md`
- `docs/specs/ADR/ADR-025-planner-strategy.md`

---

## 工作项 2：将 Coding Agent 升级为真实代码生成

### 目标

让 Coding Agent 根据规划结果生成真实代码，而不是输出固定字符串模板。

### 当前问题

- 当前 Coding Agent 只会生成 demo 内容
- 与用户输入需求语义基本无关
- 不能生成真实工程文件，也不能产出统一 diff 结构

### 落地要求

- 接入真实模型能力作为最小“大脑”
- 第一版采用“单主模型 + 结构化输出”模式
- 输出必须符合 `diff-spec.md` 与 `agent-execution-spec.md`
- 支持最小文件创建、已有文件更新、失败时结构化错误返回

### 产出物

- `runtime/agents/coding.py` 升级
- `runtime/llm/` 或等价模型适配层
- `docs/specs/contracts/agent-execution-spec.md`
- `docs/specs/contracts/diff-spec.md`

---

## 工作项 3：引入真实 Review Agent

### 目标

让评审结果与真实代码内容绑定，而不是只检查 demo 占位规则。

### 当前问题

- Review Agent 仍以 demo 检查为主
- 不能判断真实代码是否满足需求
- 审批门控与高风险判定未与执行链整合

### 落地要求

- Review 结果至少包含 `pass/issues/summary`
- `issues` 必须关联具体文件
- 高风险问题必须支持进入 `approval_required`
- Review 只做审查与判定，不得修改代码

### 产出物

- `runtime/agents/review.py` 升级
- `docs/specs/ADR/ADR-028-human-approval.md`
- `docs/specs/rules/runtime/agent-execution-rules.md`

---

## 工作项 4：补齐阶段内进度事件与前端过程展示

### 目标

让前端能够看到真实任务过程，而不是只有开始与结束。

### 当前问题

- Gateway 当前只在开始时给 `task.created/task.updated`
- Runtime 中间阶段没有持续透出给前端
- 用户体感是“后端没干活”
- 事件协议没有定型，后续 Replay / Metrics 难以复用

### 落地要求

- 采用统一 `event-spec.md`
- 至少透出标准事件序列：

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

- 前端任务时间线与消息区至少展示：
  - 当前阶段
  - 阶段摘要
  - 成功/失败状态
- 对于长任务，允许显示“正在执行中”的轮询状态

### 产出物

- `gateway` 事件映射增强
- 前端任务时间线增强
- `docs/specs/ADR/ADR-026-agent-event-model.md`
- `docs/specs/contracts/event-spec.md`
- `docs/specs/rules/runtime/event-rules.md`

---

## 工作项 5：修正 Artifact / Diff 的真实产物映射

### 目标

让前端展示的 Diff 与 Artifact 卡片真正反映本次代码输出。

### 当前问题

- Diff 仍然偏示意性质
- Bundle 卡片字段与前端存在契约错位
- Artifact 目前主要是 metadata + snapshot，信息密度偏低
- Artifact 多次生成时缺少版本语义

### 落地要求

- Diff 卡片展示真实文件路径和真实 diff 摘要
- Artifact 卡片至少包含：
  - 真实产物目录
  - 变更文件列表
  - 下载入口或定位入口
  - 版本信息
- 前后端统一 `bundle` 与 `artifact card` 内容字段
- Artifact 元数据必须遵守版本化规则

### 产出物

- Gateway artifact card 契约修正
- Frontend artifact 展示修正
- `docs/specs/ADR/ADR-027-artifact-versioning.md`
- `docs/specs/contracts/artifact-card-v2-spec.md`

---

## 工作项 6：建立最小模型接入边界

### 目标

为后续多模型与路由打基础，但当前只做最小可用实现。

### 落地要求

- 建立统一模型调用边界：

```yaml
provider:
model:
temperature:
timeout:
response_schema:
```

- Stage 6 只要求：
  - 单 provider 可用
  - Planner/Coder 可调用
  - 输出结构化可校验
  - 校验失败可走 retry 或 fallback

### 产出物

- `runtime/llm/`
- `docs/prompts/` 最小目录
- `docs/specs/rules/runtime/llm-output-rules.md`

---

## 工作项 7：比赛演示样例固化

### 目标

沉淀稳定、可重复演示、能体现全链路价值的 benchmark 场景。

### MVP 演示样例

- `Demo 1`：生成 `Go Gin API`
- `Demo 2`：生成 `React Todo 页面`
- `Demo 3`：修改已有代码并新增接口

### 这些样例必须体现

- 创建
- 修改
- Review
- Diff
- Artifact
- 执行过程可视化
- 必要时人工审批

### 每个样例需可展示

- 用户指令
- 规划结果
- 代码生成过程
- Review 结果
- Diff 卡片
- Artifact 卡片
- 最终真实文件

### 产出物

- `docs/demo-cases/stage-6/`
- 录屏脚本或答辩演示脚本

---

## 任务优先级划分

### P0（必做）

- Agent Execution Model 定型
- Planner Strategy 定型
- 真实任务规划
- 真实 Coding Agent
- 真实 Review Agent
- 统一事件模型

### P1（强烈建议）

- Artifact / Diff 真值化
- Artifact 版本化
- Human Approval 门控
- 最小模型接入边界
- 比赛演示样例固化

### P2（优化项）

- 更多语言支持
- 更复杂的多文件规划
- 更细致的 UI 过程打磨
- 为未来 DAG 执行模型预留并行子任务字段

---

## 阶段结项验收标准

满足全部条件即宣告第六阶段完成：

1. 系统已明确采用 `linear_pipeline` 作为 MVP 执行模型，并保留 `dag` 演进路径
2. Planner、Coding、Review、Artifact 的输入输出、状态、事件协议均已文档化
3. 模型输出、事件输出、Artifact 输出已收敛到统一 schema
4. 前端能看到真实阶段过程，而不只是最终完成
5. `Demo 1: Go Gin API` 可稳定生成并展示全过程
6. `Demo 2: React Todo 页面` 可稳定生成并展示全过程
7. `Demo 3: 修改已有代码并新增接口` 可稳定生成并展示全过程
8. Diff / Artifact / Review 与真实输出一致，且代码实际落盘可验证
9. 高风险 Review 结果可触发 Human Approval，并完成继续或终止决策

达成以上条件后，AgentHub 才进入“能力可信、值得继续生产加固”的阶段。
