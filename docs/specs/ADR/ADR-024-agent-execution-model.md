# ADR-024 Agent Execution Model

## 决策

AgentHub 在 MVP 阶段采用：

```yaml
execution_model: linear_pipeline
```

标准执行链如下：

```text
User Request
  ↓
Planner
  ↓
Coding
  ↓
Review
  ↓
Artifact
```

未来演进目标为：

```yaml
execution_model: dag
```

但 `dag` 不属于 Stage 6 的必做落地范围。

---

## 背景

当前系统虽然已经具备 Planner、Coding、Review、Artifact 等角色概念，但没有明确说明这些角色的执行关系、依赖方向与阶段边界。

答辩时如果无法明确回答“Agent 之间怎么协作”，会直接影响架构可信度。

---

## MVP 语义

### Planner

负责把用户请求转换成结构化 `Task Plan`。

### Coding

负责根据 `Task Plan` 生成真实代码变更。

### Review

负责基于 `changes` 和需求做审查。

### Artifact

负责基于已完成执行结果做归档、卡片化与版本化。

---

## 约束

- Planner MUST 先于 Coding 执行。
- Review MUST 先于 Artifact 执行。
- Review MUST NOT 修改业务代码。
- Artifact MUST NOT 参与代码评审。
- 任一阶段失败时，后续阶段 MUST NOT 自动继续。

---

## 未来演进

未来允许扩展为 DAG：

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

要求：

- Stage 6 的协议字段必须允许未来增加 `subtask_id`、`parent_task_id`、`dependency_ids`
- 事件模型不得与线性流绑定到无法扩展 DAG
