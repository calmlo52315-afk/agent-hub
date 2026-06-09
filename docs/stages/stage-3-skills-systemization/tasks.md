# 第三阶段任务清单

## 阶段任务描述

本阶段目标是把 AgentHub 运行时从“按 Agent 直接执行”推进到“能力可注册、可复用、可路由”的 Skill 化运行时，重点补齐以下能力：

- Skill Registry 与 Skill Runtime 最小实现
- Skill 与 Agent 的绑定关系
- Skill I/O Contract 与 Prompt 管理规范
- Skill 白名单、调用边界、危险操作约束
- Skill 超时、重试与预算配置
- 阶段文档与测试留痕

## 任务拆解

- [x] 任务 1：补齐 Stage 3 必需规范文档
  - [x] 补充 `prompt-management-spec.md`
  - [x] 复用既有 `skill-contract-spec.md`、`error-code-spec.md`、`task-state-machine-spec.md`
  - [x] 明确 Stage 3 采用的 ADR / Spec / rules 输入边界

- [x] 任务 2：扩展 rules schema 与运行时规则
  - [x] 为 `execution-rules` 增加 Skill 默认超时、按 Skill 超时映射、成本预算
  - [x] 为 `permission-rules` 增加 Skill 白名单、按角色的 Skill 白名单、危险操作拒绝清单
  - [x] 保持规则加载逻辑向后兼容

- [x] 任务 3：实现 Skill Registry 与 Skill Runtime
  - [x] 基于 `runtime/specs/registries/skills.registry.json` 构建最小 Skill Registry
  - [x] 定义 SkillDefinition / SkillInvocationPlan 等运行时对象
  - [x] 在 Skill Runtime 中完成白名单、调用方、超时、预算的计划生成

- [x] 任务 4：让 Orchestrator 经由 Skill 调用现有 Agent
  - [x] 保留既有 Agent 作为底层执行体
  - [x] Stage 3 主流程改为 `Orchestrator -> Skill -> Agent binding`
  - [x] 对每次 Skill 调度生成诊断事件与 replay 事件

- [x] 任务 5：完成测试与验证
  - [x] 新增 Skill Runtime 单元测试
  - [x] 验证运行时能够加载 Skill Registry 与 schema
  - [x] 验证 Demo 任务诊断事件中出现 `skill_dispatch`
