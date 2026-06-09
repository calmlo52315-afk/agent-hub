# Purpose

定义 Stage 6 Runtime 的 Agent 执行顺序、角色边界与禁止行为。

# Scope

适用于 Planner、Coding、Review、Artifact 以及调用这些角色的 Runtime 实现。

# Rules

1. 系统在 Stage 6 MUST 使用 `linear_pipeline` 执行顺序。
2. Planner MUST 先于 Coding 执行。
3. Coding MUST 先于 Review 执行。
4. Review MUST 先于 Artifact 执行。
5. Agent MUST NOT 跳过前置阶段直接执行后续阶段。
6. Review MUST NOT 修改业务代码。
7. Artifact MUST NOT 参与代码评审。
8. Planner MUST 输出结构化 `Task Plan` 后，Coding 才能开始。
9. 任一阶段失败后，后续阶段 MUST NOT 自动继续。
10. 高风险 Review MAY 触发人工审批门控。

# Forbidden Actions

- Coding 直接绕过 Planner 生成最终产物。
- Review 直接改代码后再自我通过。
- Artifact 直接判定代码质量或风险等级。
