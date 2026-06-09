# Purpose

定义 Stage 4 多任务并行场景下的上下文拼装规则，确保 Orchestrator 在任务拆分、依赖调度和多 Agent 协作过程中始终向执行单元提供可控、可裁剪、可回放的上下文。

# Scope

本 Rule 适用于 Stage 4 中所有由 Orchestrator 生成、拼装、裁剪和传递的任务上下文，覆盖主任务、子任务、重试任务、返工任务和 Artifact 汇总任务。

- 多子任务 DAG 调度前的上下文装配
- Coding / Review / Artifact Agent 的输入上下文构建
- Review 返工后的增量上下文回灌
- 并发执行下的 token budget 控制与摘要生成

# Rules

1. 上下文 MUST 由 Orchestrator 统一拼装，Agent MUST NOT 自行拼接跨任务全量历史。
2. 每个子任务的上下文 MUST 以“当前任务最小充分信息”为目标，禁止无边界注入整仓库内容。
3. 上下文 MUST 至少包含以下区域：`system_rules`、`task_brief`、`dependency_outputs`、`workspace_locks`、`recent_events`。
4. `system_rules` MUST 优先包含 ADR-002、ADR-007、ADR-011 以及本阶段关键 rules 的摘要，不得裁剪掉硬约束。
5. `task_brief` MUST 明确当前子任务的目标、目标文件、依赖子任务、超时、重试和期望输出。
6. `dependency_outputs` MUST 仅注入直接依赖节点的结构化输出，禁止跨层级无选择扩散。
7. `workspace_locks` MUST 反映当前子任务可读写文件范围，防止 Agent 在未知锁状态下修改文件。
8. `recent_events` SHOULD 仅保留与当前子任务直接相关的最近事件摘要，用于支持追踪与重试。
9. 多任务并发时，Orchestrator MUST 为每个子任务单独计算 token budget，并在预算不足时优先保留硬约束和当前任务摘要。
10. 上下文裁剪 MUST 按优先级执行，优先级从高到低为：`system_rules` > `task_brief` > `dependency_outputs` > `workspace_locks` > `recent_events`。
11. 当依赖输出过长时，Orchestrator MUST 先生成结构化摘要，再决定是否附带原始片段。
12. 摘要内容 MUST 保留结论、风险、文件范围和后续动作，MUST NOT 只保留自然语言结论而丢失结构化字段。
13. Review 返工场景 MUST 额外注入上轮 review 的阻塞问题与建议修复范围。
14. Artifact 汇总场景 MUST 读取已完成子任务的结构化结果，而不是重新扫描整个消息历史。

# Context Model

建议上下文结构如下：

```json
{
  "task_id": "task-root-001",
  "subtask_id": "coding-ui-001",
  "system_rules": [
    "ADR-007: 单个任务目标文件原则上不超过 3 个",
    "ADR-011: Agent 间通信统一使用结构化 JSON message"
  ],
  "task_brief": {
    "title": "实现登录页表单布局",
    "agent": "coding",
    "target_files": ["web/login.tsx", "web/login.css"],
    "priority": "high",
    "timeout_seconds": 120,
    "retry_limit": 2
  },
  "dependency_outputs": [
    {
      "subtask_id": "design-login-001",
      "summary": "已确定深色风格与表单字段结构",
      "payload": {
        "tokens": ["dark-theme", "email", "password"]
      }
    }
  ],
  "workspace_locks": [
    {
      "path": "web/login.tsx",
      "mode": "write",
      "owner_task_id": "task-root-001",
      "owner_subtask_id": "coding-ui-001"
    }
  ],
  "recent_events": [
    {
      "type": "review.fail.retry",
      "summary": "按钮缺少禁用态，需要补充 loading 反馈"
    }
  ]
}
```

# Summary Rules

- 摘要 MUST 使用结构化对象表达，至少包含：`summary`、`affected_files`、`risks`、`next_actions`。
- 摘要 SHOULD 控制在单个依赖节点 200~400 tokens 的规模内，超过预算时先压缩示例与长文本。
- 摘要 MUST 标明来源节点 `subtask_id` 与版本时间，避免重试时消费旧结果。
- 摘要生成失败时，Orchestrator MUST 回退为最小字段集合，而不是中断整个 DAG 调度。

# Constraints

- 上下文 MUST 与当前子任务直接相关，禁止将无关任务的文件、消息或产物混入。
- 单个子任务上下文中，目标文件数量 MUST 遵循 ADR-007 的粒度上限。
- 上下文 MUST 使用结构化 JSON 载荷嵌入消息协议，不得绕开统一 Message Protocol。
- 同一子任务的上下文快照 SHOULD 可回放，用于诊断调度错误与摘要失真。
- Stage 4 上下文管理 MUST 兼容内存版 DAG 调度，不依赖外部工作流框架。

# Forbidden Actions

- Orchestrator MUST NOT 将完整仓库内容作为默认上下文广播给所有子任务。
- Agent MUST NOT 直接拉取其他子任务的原始上下文对象。
- 上下文裁剪 MUST NOT 删除硬约束、锁状态和当前任务目标文件。
- 摘要模块 MUST NOT 输出无法追溯来源的自由文本片段。
- Artifact 汇总 MUST NOT 依赖未完成或已失败节点的非稳定输出。

# Examples

- Valid: Coding 子任务只接收目标文件、直接依赖的设计摘要和当前锁信息，然后在预算内执行。
- Valid: Review 子任务在返工后只注入阻塞问题摘要与最新代码片段，而不是附带全部历史消息。
- Invalid: 为所有并发子任务统一注入全量聊天记录和全部产物快照。
- Invalid: 在预算不足时裁掉 ADR 约束，却保留大量无关历史对话。

# References

- `docs/specs/ADR/ADR-005-context-management.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/ADR/ADR-011-message-protocol.md`
- `docs/specs/contracts/context-spec.md`
- `docs/specs/contracts/task-schema-spec.md`
- `docs/specs/contracts/dag-execution-spec.md`
