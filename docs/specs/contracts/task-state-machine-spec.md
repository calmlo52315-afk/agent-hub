# Task State Machine Spec

## 1. 目标

定义 AgentHub 任务状态机的可读规范，作为运行时执行、回放、诊断和指标统计的统一依据。

本 Spec 对齐当前 MVP 实现，供人类评审使用；如需机器校验，应在 `runtime/specs/` 中生成对应 schema。

## 2. 状态集合

MVP 规范状态如下：

- `created`
- `coding`
- `reviewing`
- `artifacting`
- `done`
- `failed`

说明：

- `done`、`failed` 为终态
- 状态名统一使用小写 snake-free 字符串，与当前运行时实现保持一致

## 3. 事件集合

MVP 标准事件如下：

- `start`
- `coding.success`
- `coding.failed`
- `review.pass`
- `review.fail.retry`
- `review.fail.hard`
- `artifact.success`
- `artifact.failed`

## 4. 转移表

| From | Event | To | 语义 |
| --- | --- | --- | --- |
| `created` | `start` | `coding` | 启动任务执行 |
| `coding` | `coding.success` | `reviewing` | 代码产出成功 |
| `coding` | `coding.failed` | `failed` | 编码阶段失败且不可继续 |
| `reviewing` | `review.pass` | `artifacting` | 评审通过 |
| `reviewing` | `review.fail.retry` | `coding` | 评审要求返工 |
| `reviewing` | `review.fail.hard` | `failed` | 评审判定任务失败 |
| `artifacting` | `artifact.success` | `done` | 归档完成 |
| `artifacting` | `artifact.failed` | `failed` | 归档失败 |

## 5. 执行约束

- 只有 Orchestrator 可以触发状态转移
- Agent 与 Skill 只能返回结果和事件，不能直接改写任务状态
- 进入终态后禁止继续转移
- 非法转移必须抛出运行时错误，并追加诊断事件

## 6. 诊断事件格式

状态机至少应输出以下两类诊断事件：

### 6.1 合法转移事件

```json
{
  "kind": "transition",
  "from": "reviewing",
  "to": "coding",
  "event": "review.fail.retry"
}
```

### 6.2 非法转移事件

```json
{
  "kind": "illegal_transition",
  "reason": "no_rule",
  "from": "artifacting",
  "event": "review.pass",
  "allowed_events": ["artifact.success", "artifact.failed"]
}
```

其中 `reason` 建议取值：

- `no_rule`
- `terminal_state`

## 7. Replay 要求

Replay 层应至少记录：

- `task_id`
- `trace_id`
- `event_type`
- `from`
- `to`
- `event`
- `timestamp`

建议的状态转移回放事件：

```json
{
  "kind": "transition",
  "from": "coding",
  "to": "reviewing",
  "event": "coding.success"
}
```

## 8. Metrics 要求

Metrics 至少应支持围绕状态机计算：

- 任务成功率
- 各阶段失败率
- Review 回退率
- 平均任务时长
- 平均阶段时长

## 9. 扩展预留

以下状态目前不进入 MVP 标准集合，但允许未来扩展：

- `planned`
- `paused`
- `awaiting_input`
- `cancelled`
- `packaging`

原则：

- 扩展状态必须先更新 ADR 与运行时规则
- 扩展状态不得破坏现有终态语义

## 10. 参考

- `docs/specs/ADR/ADR-012-task-state-machine.md`
- `rules/execution-rules.json`
- `runtime/harness/state_machine.py`
