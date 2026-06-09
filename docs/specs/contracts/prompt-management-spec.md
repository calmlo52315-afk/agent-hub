# Prompt Management Spec

## 1. 目标

定义 AgentHub Stage 3 的 Prompt 存放、版本、启用与回滚策略。

本 Spec 的核心目的不是让 Prompt 成为“魔法文件”，而是让 Prompt 成为可治理的实现资源，并与 Skill Contract 解耦。

## 2. 设计原则

- Prompt 不是 Skill 身份标识
- Skill 版本归 Skill Contract 管
- Prompt 版本归 Prompt Registry 管
- Prompt 切换必须可回滚
- Prompt 文件必须可审计、可留痕、可复现

## 3. 推荐目录结构

推荐在仓库中建立如下目录：

```text
docs/prompts/
  coding/
    generate_patch/
      v1.md
      v2.md
  review/
    analyze_changes/
      v1.md
  artifact/
    package_result/
      v1.md
  active.json
```

说明：

- 一级目录按能力域划分，如 `coding`、`review`、`artifact`
- 二级目录按 Skill 名称划分
- Prompt 文件采用显式版本命名
- `active.json` 用于声明当前启用版本

## 4. Prompt 标识

每份 Prompt 建议至少具备以下元数据：

```json
{
  "prompt_id": "coding.generate_patch.v1",
  "skill_name": "coding.generate_patch",
  "prompt_version": "v1",
  "status": "active"
}
```

字段说明：

- `prompt_id`：Prompt 唯一标识
- `skill_name`：绑定的 Skill 名称
- `prompt_version`：Prompt 资源版本
- `status`：当前状态，如 `active`、`deprecated`、`disabled`

## 5. 启用配置

建议通过集中配置声明当前启用版本：

```json
{
  "coding.generate_patch": "v1",
  "review.analyze_changes": "v1",
  "artifact.package_result": "v1"
}
```

这样切换版本时只需改配置，不需要改业务代码。

## 6. 版本规则

Prompt 版本与 Skill Contract 版本不是一回事：

- Prompt 优化但不改输入输出 Contract：
  - 只升 Prompt 版本
- Prompt 变化导致输出结构或字段语义变化：
  - 必须同步提升 Skill Contract 版本

推荐做法：

- `Skill 1.0.0` 可以绑定 `Prompt v1`、`Prompt v2`
- 只有 Contract 变化才需要升到 `Skill 1.1.0` 或 `2.0.0`

## 7. 回滚策略

Prompt 发布必须支持快速回滚：

- 新版本先进入灰度或开发态
- 通过配置切换 `active` 版本
- 如出现稳定性回退，直接回滚到上一版本

回滚要求：

- 不修改 Skill 名称
- 不直接覆盖历史 Prompt 文件
- 保留版本记录与变更原因

## 8. 文件内容建议

单个 Prompt 文件建议包含以下结构：

```md
# coding.generate_patch v1

## Role
你是 Coding Skill 的实现提示词。

## Goal
根据输入任务生成最小变更集。

## Input Contract
- task
- context
- constraints

## Output Contract
- plan
- changes
- example_diff

## Guardrails
- 禁止修改 rules
- 禁止修改 ownership
- 禁止非结构化输出
```

## 9. 治理要求

- Prompt 变更必须记录修改原因
- Prompt 必须和 Stage 文档、AI 协作留痕保持可追踪关系
- Prompt 不得直接替代 Rules；权限与危险操作约束必须仍由 Rules 执行

## 10. 与运行时的关系

- 当前 Stage 3 可以先只落文档与目录规范
- 后续若引入 Prompt Registry，可让 Skill Registry 通过 `prompt_ref` 指向当前启用 Prompt
- Prompt Registry 不应直接控制状态机、权限与重试策略

## 11. 参考

- `docs/specs/ADR/ADR-015-skill-interface-versioning.md`
- `docs/specs/contracts/skill-contract-spec.md`
- `runtime/specs/registries/skills.registry.json`
