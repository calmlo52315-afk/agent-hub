# 第四阶段变更记录

## 阶段定位

本阶段对应 `stage-4-orchestrator-upgrade`，目标是让 AgentHub 从“单任务串行执行”升级为“任务可拆分、依赖可表达、调度可并行”的多 Agent 协作系统。

Stage 4 不是新增更多核心 Agent，而是在继续遵守 ADR-002 的前提下，升级 Orchestrator 的任务建模与调度能力。

## 输入依据

### ADR

- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/ADR/ADR-011-message-protocol.md`

### Spec

- `docs/specs/contracts/task-schema-spec.md`
- `docs/specs/contracts/dag-execution-spec.md`
- `docs/specs/contracts/task-state-machine-spec.md`
- `docs/specs/contracts/context-spec.md`
- `docs/specs/contracts/message-spec.md`

### Rules

- `docs/specs/rules/dispatch/dispatch.md`
- `docs/specs/rules/context/context.md`
- `docs/specs/rules/ownership/ownership.md`
- `docs/specs/rules/ownership/lock.md`
- `docs/specs/rules/global/state-machine.md`
- `docs/specs/rules/global/runtime-agent-boundary.md`
- `docs/specs/rules/global/protocol.md`

## 本次完成内容

- 新增 Stage 4 所需的 Task Schema 与 DAG 执行语义 Spec
- 补齐 dispatch / context / ownership / lock / state-machine 五类规则文档
- 实现 `TaskPlan` / `Subtask` / `TaskPlanner`，补齐 DAG 运行时对象、依赖校验、就绪判定与冲突检测
- 实现通用 `TaskPlanner`，支持从指令解析 `@agent`、文件路径、优先级、依赖与自动补齐 review/artifact 节点
- 把 `run_demo_task()` 从固定串行链路升级为基于 `TaskPlan` 的内存 DAG 调度链路
- 在 `OwnershipManager` 中补充调度级锁租约，支持子任务运行前申请、结束后释放
- 为调度租约加入 `lease_seconds` 与过期清理，并支持 blocked 节点在资源释放后重试唤醒
- 在 Orchestrator 中补充 context budget 裁剪与依赖摘要压缩，使上下文真正受预算约束
- 为核心编排层代码补充类说明和关键函数说明，降低后续 DAG 改造成本
- 建立第四阶段任务清单、验收清单和变更记录，便于比赛提交与 review

## 新增与更新文档

- 新增 Task Schema Spec：
  - `docs/specs/contracts/task-schema-spec.md`
- 新增 DAG Execution Spec：
  - `docs/specs/contracts/dag-execution-spec.md`
- 新增 Dispatch Rules：
  - `docs/specs/rules/dispatch/dispatch.md`
- 补充 Context Rules：
  - `docs/specs/rules/context/context.md`
- 补充 Ownership / Lock Rules：
  - `docs/specs/rules/ownership/ownership.md`
  - `docs/specs/rules/ownership/lock.md`
- 补充 State Machine Rules：
  - `docs/specs/rules/global/state-machine.md`
- 新增第四阶段文档：
  - `docs/stages/stage-4-orchestrator-upgrade/tasks.md`
  - `docs/stages/stage-4-orchestrator-upgrade/checklist.md`
  - `docs/stages/stage-4-orchestrator-upgrade/modifications.md`

## 代码可读性补充

- 为 `runtime/orchestrator/orchestrator.py` 的核心类与关键函数补充职责说明
- 新增 `runtime/orchestrator/task_graph.py`，承载 Stage 4 任务建模与 DAG 调度基础结构
- 为 `runtime/agents/coding.py`、`runtime/agents/review.py`、`runtime/agents/artifact.py` 补充类说明与 `handle()` 说明
- 为 `runtime/messages.py` 与 `runtime/harness/state_machine.py` 补充结构与函数说明

## 代码实现变更

- 新增 Stage 4 DAG 运行时对象：
  - `runtime/orchestrator/task_graph.py`
- 升级锁与所有权运行时：
  - `runtime/harness/ownership.py`
- 升级 Orchestrator 主链路：
  - `runtime/orchestrator/orchestrator.py`
- 新增 Stage 4 单元测试：
  - `tests/unit/test_stage4_dag_runtime.py`

## 运行时目标约束

- Stage 4 工作流引擎采用自研 DAG（内存版工业级实现）
- 并发模型采用 `asyncio + 内存任务队列`
- 不引入 LangGraph 或任何第三方工作流框架
- 继续保持三个核心 Agent：Coding / Review / Artifact
- 所有 Agent 间通信继续使用 ADR-011 规定的结构化 JSON Message Protocol

## 当前未完成项

- Review 与 Artifact 仍采用单 fan-in 节点，尚未扩展为更复杂的多层 DAG 形态
- 当前 context budget 以序列化字节预算做轻量裁剪，尚未接入更精细的 token 估算器
- 调度租约已支持过期清理、基础等待队列与 age-based 防饥饿，但尚未引入更完整的队列治理与持久化调度策略

## 建议的下一步实现顺序

1. 继续增强等待队列治理，补齐更明确的公平策略、持久化恢复与更丰富的冲突事件。
2. 把字节预算升级为更贴近模型调用的 token budget 估算与硬拦截。
3. 继续扩展 Task Split 规则，把当前启发式 planner 提升到更强的任务语义理解能力。
4. 继续补多层 DAG、返工回路和更细粒度 metrics / replay 事件。

## 测试与验证

本阶段已通过以下验证：

```bash
python3 -m unittest tests.unit.test_stage4_dag_runtime
python3 -m unittest tests.unit.test_stage3_skill_runtime
python3 -m runtime.smoke_test
```
