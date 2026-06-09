# 第三阶段变更记录

## 阶段定位

本阶段对应 `stage-3-skills-systemization`，目标是让 AgentHub 从“以 Agent 为中心的执行方式”升级为“以 Skill 为中心的可扩展能力架构”。

本阶段强调的不是新增更多 Agent，而是把能力抽象为可注册、可版本化、可治理的 Skill，并让 Orchestrator 成为唯一编排入口。

## 输入依据

### ADR

- `docs/specs/ADR/ADR-015-skill-interface-versioning.md`
- `docs/specs/ADR/ADR-016-tool-permission-boundary.md`
- `docs/specs/ADR/ADR-017-skill-composition-model.md`
- `docs/specs/ADR/ADR-012-task-state-machine.md`
- `docs/specs/ADR/ADR-013-retry-policy.md`

### Spec

- `docs/specs/contracts/skill-contract-spec.md`
- `docs/specs/contracts/prompt-management-spec.md`
- `docs/specs/contracts/error-code-spec.md`
- `docs/specs/contracts/task-state-machine-spec.md`

### Rules

- `rules/execution-rules.json`
- `rules/permission-rules.json`
- `rules/ownership-rules.json`
- `rules/communication-rules.json`

## 本阶段完成内容

- 扩展 `execution-rules`，增加 Skill 默认超时、按 Skill 超时、成本预算配置
- 扩展 `permission-rules`，增加 Skill 白名单与按角色白名单
- 实现最小 `SkillRegistry` 与 `SkillRuntime`
- 让 Orchestrator 主流程通过 Skill 调用现有 Agent
- 为每次 Skill 调度补充诊断事件与 replay 事件
- 补齐 Prompt 管理规范文档
- 增加 Stage 3 单元测试

## 代码实现变更

- 新增 Skill 基础协议与调用计划：
  - `runtime/skills/base.py`
- 新增 Skill Registry：
  - `runtime/skills/registry.py`
- 新增 Skill Runtime：
  - `runtime/skills/runtime.py`
- 更新 Skill 模块导出：
  - `runtime/skills/__init__.py`
- 更新规则 schema：
  - `runtime/config/rules_schema.py`
- 更新运行时规则：
  - `rules/execution-rules.json`
  - `rules/permission-rules.json`
- 更新 Orchestrator：
  - `runtime/orchestrator/orchestrator.py`
- 补充 Prompt 管理规范：
  - `docs/specs/contracts/prompt-management-spec.md`

## 运行时设计说明

### Skill 与 Agent 的关系

- Skill 是可编排的能力单元
- Agent 是当前阶段的底层执行容器
- Stage 3 采用 `agent-backed skill` 形式：
  - `coding.generate_patch -> coding agent`
  - `review.analyze_changes -> review agent`
  - `artifact.package_result -> artifact agent`

### 为什么这样做

- 避免一开始就重写全部 Agent
- 保留 Stage 2 已验证的执行稳定性
- 先完成“能力解耦与统一入口”，再逐步把 Skill 与具体模型/Prompt/工具完全分离

## 输出限制

- 本阶段不实现复杂 DAG 编排
- 本阶段不实现 Prompt Registry 真正加载与热切换
- 本阶段不实现真实 cost 统计，仅预留预算配置与运行时计划字段
- 本阶段不替换既有 Pydantic-first 校验链路

## 测试与验证产物

- `tests/unit/test_runtime_spec_loader.py`
- `tests/unit/test_stage3_skill_runtime.py`

建议验证命令：

```bash
python3 -m unittest tests.unit.test_runtime_spec_loader tests.unit.test_stage3_skill_runtime
python3 -m runtime.smoke_test
```

## 剩余缺口与延期处理

本阶段主体验收已通过，以下事项不再插入当前开发，统一归档到根目录 `todo.md`：

- Prompt 物理目录落地，以及 `prompt_ref` 真实挂载到 Skill
- 多模型底层 LLM 工厂接入，并按 Skill 路由模型
- 统一错误码的全量落地
- 全链路 cost 预算拦截
- `RuntimeValidator` 的 `Pydantic + JSON Schema` 混合改造
- 全规则消费改造

处理原则：

- 当前立即停止无限制补全
- 剩余事项延后到 `Stage 3` 收尾小迭代或 `Stage 7` 可观测 / 平台化阶段
- 当前优先进入 review、答辩材料整理和比赛提交阶段
