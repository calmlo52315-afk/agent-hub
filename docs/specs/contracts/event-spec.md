# Event Spec

## 1. 目标

定义 Runtime、Gateway、WebSocket、Replay、Metrics 共用的统一事件协议。

## 2. 最小 Schema

```yaml
event_id: string
task_id: string
event_type: string
timestamp: string
payload: object
```

## 3. 推荐附加字段

```yaml
session_id: string
agent: string
stage: string
status: string
attempt: integer
```

## 4. MVP 标准事件

- `task.created`
- `planning.started`
- `planning.completed`
- `coding.started`
- `coding.completed`
- `review.started`
- `review.completed`
- `artifact.started`
- `artifact.completed`
- `task.completed`
- `task.failed`

## 5. 规则

- `event_id` MUST 全局唯一
- `timestamp` MUST 使用统一时间格式
- `payload` MUST 为结构化对象
- 事件命名 SHOULD 稳定且可枚举
