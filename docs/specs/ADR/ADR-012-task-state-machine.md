ADR-012 任务状态机

决策
为 AgentHub Runtime 定义唯一的任务状态机，并要求所有主流程推进、失败终止、回放记录、指标统计都以状态转移为准。

MVP 采用当前运行时已经落地的固定工作流状态机：

- `created`
- `coding`
- `reviewing`
- `artifacting`
- `done`
- `failed`

其中 `done` 与 `failed` 为终态，所有状态流转必须由 Orchestrator 触发，Agent 不得自行修改任务状态。

背景与选择原因
1. 没有统一状态机，`Replay`、`Metrics`、诊断事件和错误恢复都无法围绕同一事实源工作。
2. 当前代码已经在 `execution-rules.json`、`WorkflowStateMachine` 与 Orchestrator 主流程中实现了 MVP 状态流转，应该先将其收敛为正式架构决策，而不是继续口头约定。
3. 面向工程化演示，固定主流程比“自由推理状态”更容易验证、回放、审计，也更利于后续接入多模型与 Skill 编排。

状态定义
1. `created`
   - 任务已创建，尚未进入执行链路。
2. `coding`
   - Coding 执行阶段，负责产出变更候选、差异、自检结果。
3. `reviewing`
   - Review 执行阶段，负责审查变更并给出通过/不通过结论。
4. `artifacting`
   - Artifact 执行阶段，负责对通过评审的产物进行归档、打包和元数据生成。
5. `done`
   - 主流程成功结束，任务可被视为完成。
6. `failed`
   - 主流程不可继续推进，任务以结构化失败结束。

MVP 转移规则
1. `created --start--> coding`
2. `coding --coding.success--> reviewing`
3. `coding --coding.failed--> failed`
4. `reviewing --review.pass--> artifacting`
5. `reviewing --review.fail.retry--> coding`
6. `reviewing --review.fail.hard--> failed`
7. `artifacting --artifact.success--> done`
8. `artifacting --artifact.failed--> failed`

边界约束
1. 状态机的唯一执行者是 Orchestrator；Agent 只能返回结构化结果，不得直接声明任务完成。
2. `done`、`failed` 为终态；进入终态后禁止再次转移。
3. 非法转移必须被记录为诊断事件，并作为运行时错误处理，而不是静默忽略。
4. 状态字段是 Replay、Metrics、错误制品、任务汇总的统一事实来源，不允许各模块维护私有状态枚举。

为什么当前不引入 `planned` / `packaging` / `review_failed`
1. 当前运行时代码尚未将 Planning 作为独立执行节点持久化，若强行引入 `planned` 会造成文档与代码分叉。
2. 当前产物阶段的真实实现名称为 `artifacting`，其职责已经覆盖归档与打包；在打包步骤独立化前，不额外拆出 `packaging`。
3. 当前 Review 不通过使用事件区分两类语义：
   - `review.fail.retry`：回退到 `coding`
   - `review.fail.hard`：直接失败
   对 MVP 来说，这比新增中间失败状态更贴近现有实现，也更利于保持状态机简单。

扩展预留
1. 当 Planning 被持久化并形成独立输入输出时，可在 `created` 与 `coding` 之间引入 `planned`。
2. 当归档与打包分离时，可将 `artifacting` 拆分为 `archiving` 与 `packaging`。
3. 当需要记录返工轮次、人工介入或暂停恢复时，可引入 `paused`、`awaiting_input`、`cancelled` 等非成功终态。

影响
1. `execution-rules` 必须声明状态集合、合法转移与终态。
2. Replay 事件必须记录 `from`、`to`、`event`。
3. Metrics 必须能够基于状态转移统计任务成功率、失败率、返工率、平均阶段耗时。

参考
- `rules/execution-rules.json`
- `runtime/harness/state_machine.py`
- `runtime/orchestrator/orchestrator.py`
