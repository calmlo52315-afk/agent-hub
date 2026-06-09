# Context Spec

## 1. 目标

定义 Orchestrator 在投递任务时如何拼装上下文（context），并在 token/长度受限时进行裁剪，保证关键约束与活跃任务信息优先保留。

## 2. Context Model

`context` 作为各 Agent 输入 payload 的一部分，建议结构如下：

```json
{
  "repo_root": "string",
  "pinned": ["string"],
  "active_task": {
    "task_id": "string",
    "targets": ["string"],
    "locks": [
      {
        "path": "string",
        "owner": "string",
        "mode": "read|write"
      }
    ]
  },
  "artifact_summaries": [
    {
      "artifact_id": "string",
      "type": "string",
      "summary": "string",
      "paths": ["string"]
    }
  ],
  "recent_messages": [
    {
      "message_id": "string",
      "kind": "string",
      "sender_id": "string",
      "summary": "string"
    }
  ]
}
```

## 3. 拼装策略（Assembly）

Orchestrator 拼装上下文时应遵循：

- pinned：固定规则与不可变约束（例如全局项目规则、危险操作拒绝项）
- active_task：当前任务的目标文件、锁状态、关键执行参数
- artifact_summaries：历史产物与评审摘要（用于避免重复与回归）
- recent_messages：最近 N 条消息的摘要（用于短期记忆）

## 4. 优先级与裁剪（Trimming）

优先级从高到低（高优先级最后裁剪）：

1. pinned（永不裁剪）
2. active_task（保持完整，不截断关键字段）
3. artifact_summaries
4. recent_messages（最先裁剪）

裁剪规则：

- 达到阈值时，从最低优先级开始逐步裁剪
- 不允许打乱优先级做随机裁剪
- 保留当前任务的完整链路信息（至少包含 targets 与 locks）

## 5. Artifact 摘要规则（Artifact Summary）

artifact 摘要用于在不携带全量文件内容的情况下保留“可回放”的决策依据：

- 必须包含：`artifact_id`、`type`、`summary`、`paths`
- summary 应覆盖：
  - 任务结论（pass/fail）
  - 关键变更范围（文件列表/模块）
  - 高风险问题概览（如有）

## 6. 参考

- [ADR-005-context-management](../../ADR/ADR-005-context-management.md)

