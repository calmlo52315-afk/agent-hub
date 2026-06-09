ADR-017 Skill 组合模型

决策
Stage 3 的 Skill 组合模型采用受 Orchestrator 控制的固定 Workflow，而不是允许 Agent 自主调用其他 Agent 或 Skill 形成自由网络。

MVP 决策如下：
1. 主链路为固定顺序：
   - `coding`
   - `review`
   - `artifact`
2. 所有调度、分支、重试、回退都由 Orchestrator 统一执行。
3. 禁止 Agent 自主调用其他 Agent。
4. 禁止 Skill 在运行时自行发起新的工作流。

背景与选择原因
1. 当前系统正在从 Agent Prompt 走向 Skill 体系，如果此时同时开放自由组合，复杂度会远超当前阶段承受能力。
2. 固定 Workflow 更利于：
   - 回放
   - 指标统计
   - 权限收口
   - 成本预算
3. 从工程化面试视角看，“先把编排权收归 Orchestrator”比“Agent 自由自治”更成熟，也更像真正可运营的平台。

MVP 组合规则
1. Coding 负责生成候选变更。
2. Review 负责审查并决定：
   - `review.pass`：进入 Artifact
   - `review.fail.retry`：回退到 Coding
   - `review.fail.hard`：任务失败
3. Artifact 只处理通过评审的产物。

允许的组合能力
1. 串行组合
   - 主流程固定串行。
2. 条件分支
   - 基于 Review 结论决定进入下一阶段或回退。
3. 受控重试
   - 由 Retry Policy 在阶段内进行。

当前不做的事情
1. 不做 Agent 自主发现并调用其他 Agent。
2. 不做开放式 DAG 编辑器。
3. 不做多层嵌套工作流。
4. 不做“模型自己决定下一个 Skill”的自治编排。

为什么当前不直接上 DAG
1. 当前任务规模小、角色固定、状态机已经落地，DAG 的收益远低于其治理成本。
2. 一旦允许自由 DAG，状态机、可观测性、权限校验、失败恢复都会指数级复杂化。
3. MVP 阶段先验证 Skill 的接口、权限、版本和执行规则，优先级高于图编排。

影响
1. Orchestrator 是唯一编排入口。
2. Skill Registry 只负责声明能力，不负责调度决策。
3. Replay 与 Metrics 可以围绕固定阶段做稳定统计。

演进路径
1. 当 Skill 数量显著增长且已具备稳定 I/O Contract 后，可从固定 Workflow 演进到受限 DAG。
2. 即使将来支持 DAG，也应保留“所有边必须经过 Orchestrator 校验”的原则。

参考
- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-012-task-state-machine.md`
- `rules/execution-rules.json`
