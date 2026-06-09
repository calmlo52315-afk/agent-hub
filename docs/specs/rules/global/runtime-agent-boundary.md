# Purpose

定义 AgentHub MVP 阶段运行时与 Agent 边界的强制执行规则。

# Scope

本 Rule 适用于 Orchestrator、Coding Agent、Review Agent、Artifact Agent，以及实现或调用 MVP 流程的开发人员。

# Rules

1. MVP 阶段系统 MUST 运行在单 Runtime、单进程、单入口形态下。
2. 所有 Agent MUST 由主入口统一启动，并运行在同一进程内。
3. 文件锁、文件所有权、状态表 MUST 作为运行时内的全局单例资源维护。
4. 所有 Agent 间交互 MUST 通过 Orchestrator 路由。
5. 所有 Agent 间通信 MUST 使用统一 Message Protocol。
6. 任一 Agent MUST NOT 直接调用、修改或绕过其他 Agent。
7. MVP 主流程 MUST 固定使用且仅使用三个核心 Agent：Coding Agent、Review Agent、Artifact Agent。
8. Coding Agent MUST 负责需求理解、任务规划、业务代码生成、单元测试生成、Diff 生成和自检。
9. Review Agent MUST 负责代码审查、语法与逻辑检查、风格检查、接口合规性审查、问题归类、风险分级、质量评分、修复建议和冲突合并处理。
10. Artifact Agent MUST 负责产物收集、完整性校验、文件快照、版本归档、元数据生成、预览卡片生成和工程打包输出。
11. 跨角色操作 MUST 经由 Orchestrator 提交，并遵守对应角色边界。
12. 细分角色 MAY 仅作为可选扩展存在，MUST NOT 替代或改变三个核心 Agent 的 MVP 主流程。

# Inputs

- MVP 流程任务请求。
- 经由 Orchestrator 传递的结构化消息。
- 共享运行时状态，包括文件锁、文件所有权和状态表。
- 当前角色执行所需的源文件、Diff、测试、评审项和产物数据。

# Outputs

- Coding Agent 输出任务计划、代码变更、单元测试、Diff 和自检结果。
- Review Agent 输出审查问题、问题分类、风险等级、质量评分和修复建议。
- Artifact Agent 输出已校验产物、文件快照、归档版本、元数据、预览卡片和打包结果。
- Orchestrator 输出任务路由结果、角色间消息和流程状态流转结果。

# Constraints

- MVP MUST NOT 使用微服务、多进程部署、跨主机部署、消息队列或 Worker Pool。
- MVP MUST NOT 为任一 Agent 分配独立进程或独立端口。
- 运行时 MUST 保持所有 Agent 在本地内存中执行，并使用本地方法调用通信。
- Review Agent MAY 仅执行微小格式修正，MUST NOT 新增或重构业务代码。
- 如启用细分角色，其 MUST 保持为可选扩展，且 MUST NOT 侵入 MVP 核心流程。

# Forbidden Actions

- Coding Agent MUST NOT 执行代码审查或质量评分。
- Coding Agent MUST NOT 修改全局规则、文件规范或接口契约。
- Coding Agent MUST NOT 篡改原始任务需求或规格文档。
- Review Agent MUST NOT 直接新增或重构业务代码，微小格式修正除外。
- Review Agent MUST NOT 分配任务或修改文件所有权、锁状态。
- Artifact Agent MUST NOT 生成或修改业务代码、单元测试。
- Artifact Agent MUST NOT 参与代码评审或风险判定。
- 任一 Agent MUST NOT 直接调用其他 Agent，或执行超出自身角色边界的操作。
- 系统 MUST NOT 在 MVP 主流程中引入额外核心 Agent。

# Examples

- Valid: Orchestrator 将编码任务发送给 Coding Agent，再将生成的 Diff 转交 Review Agent，最后把通过审查的结果交给 Artifact Agent 打包归档。
- Valid: Review Agent 输出风险等级、问题列表和修复建议，但不修改业务逻辑。
- Valid: Artifact Agent 基于已批准文件生成快照、元数据和打包结果，但不编辑源代码。
- Invalid: Coding Agent 修改全局 Rule 文件或重写需求文档。
- Invalid: Review Agent 直接修改文件所有权或重写业务服务实现。
- Invalid: Artifact Agent 新增单元测试或参与评审风险判断。
- Invalid: 开发人员在 MVP 阶段将 Coding Agent 与 Review Agent 部署为独立进程或独立服务。

# References

- ADR-001
- ADR-002
