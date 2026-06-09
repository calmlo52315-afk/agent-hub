# ADR-025 Planner Strategy

## 决策

Stage 6 的 Planner 采用双层策略：

```yaml
planner_strategy:
  primary: llm_planner
  fallback: rule_planner
```

---

## 背景

当前系统已有 Planner 概念，但缺乏明确策略定义：

- 默认是否走模型规划
- 模型失败如何处理
- 规划结果是否必须结构化
- 已知模板场景是否需要兜底规划器

如果这些问题不定型，系统在演示或答辩时无法回答“规划错了怎么办”。

---

## 规则

- `llm_planner` 作为默认入口，负责把自然语言需求转换为结构化 `Task Plan`
- `rule_planner` 作为稳定兜底，负责处理模板化或回退场景
- Planner 输出 MUST 满足 `task-plan-spec.md`
- Planner 输出校验失败时，系统 MUST 进入 retry 或 fallback 流程

---

## 触发 fallback 的场景

- 模型超时
- 模型不可用
- 模型返回无法解析
- 模型输出不满足 schema
- 需求命中已知模板，例如预置 Demo Case
