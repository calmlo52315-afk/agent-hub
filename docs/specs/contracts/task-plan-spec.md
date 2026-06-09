# Task Plan Spec

## 1. 目标

定义 Planner 输出的统一结构化协议，供 Runtime、Gateway、Replay、Metrics 与后续多模型策略复用。

## 2. 最小 Schema

```yaml
task_id: string
summary: string
language: string | null
targets:
  - path: string
    action: create | update | delete
    reason: string
artifacts:
  - type: diff | bundle | preview | review
    title: string
risks:
  - severity: high | medium | low
    summary: string
```

## 3. 规则

- Planner 输出 MUST 为结构化对象
- `targets` MUST 为显式文件目标，不得仅给抽象描述
- `action` 仅允许 `create|update|delete`
- `summary` MUST 为用户可读摘要
- `risks` MAY 为空，但字段 SHOULD 存在

## 4. 扩展字段

未来允许增加：

- `subtasks`
- `dependency_ids`
- `parent_task_id`
- `acceptance_checks`
