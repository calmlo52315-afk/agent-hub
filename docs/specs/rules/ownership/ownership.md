# Purpose

定义 Stage 4 多子任务协作下的文件所有权规则，确保 Orchestrator 在任务拆解、并发调度和返工重试期间能够稳定判定“谁可以修改哪些文件”。

# Scope

本 Rule 适用于主任务与子任务的文件所有权声明、授予、继承、转移和回收，覆盖 Coding / Review / Artifact 三个核心 Agent 的所有写入行为。

# Rules

1. 文件所有权 MUST 由 Orchestrator 统一分配与回收，Agent MUST NOT 直接声明或篡改文件所有权。
2. 子任务创建时 MUST 显式声明 `target_files`；Orchestrator MUST 依据该列表授予最小写权限。
3. 单个子任务的 `target_files` 原则上 MUST 控制在 3 个物理文件以内，超出范围时 MUST 先拆分任务。
4. Coding 子任务默认拥有其 `target_files` 的写所有权，并可申请直接依赖文件的只读权限。
5. Review 子任务默认只拥有评审范围的只读权限；除微小格式修正外，MUST NOT 获得业务代码写所有权。
6. Artifact 子任务仅可获得产物目录和快照目录的写所有权，MUST NOT 获得业务源码写所有权。
7. 子任务返工时，新的返工子任务 MAY 继承原子任务所有权，但 MUST 重新记录 `owner_subtask_id` 与租期。
8. 同一主任务内，如多个子任务串行处理同一文件，所有权 MUST 显式移交，不得隐式覆盖。
9. 不同主任务争夺同一路径时，Orchestrator MUST 依据优先级、创建时间和锁冲突策略决策，不得让两个写任务同时拥有同一路径。
10. 所有权变更 SHOULD 记录为结构化事件，至少包含：`task_id`、`subtask_id`、`path`、`mode`、`action`、`timestamp`。
11. 子任务结束、失败或超时后，Orchestrator MUST 释放其占有的所有权与关联锁。
12. 若任务进入人工介入或取消状态，所有权 MUST 回收到 Orchestrator，等待下一次明确分配。

# Ownership Model

建议结构如下：

```json
{
  "task_id": "task-root-001",
  "subtask_id": "coding-api-001",
  "owner_role": "coding",
  "files": [
    {
      "path": "runtime/orchestrator/dag_scheduler.py",
      "mode": "write",
      "granted_by": "orchestrator",
      "granted_at": "2026-06-04T10:00:00Z",
      "lease_seconds": 300
    },
    {
      "path": "runtime/orchestrator/models.py",
      "mode": "read",
      "granted_by": "orchestrator",
      "granted_at": "2026-06-04T10:00:00Z",
      "lease_seconds": 300
    }
  ]
}
```

# Conflict Resolution

- 写写冲突：高优先级任务优先；优先级相同则按先到先得；落败方进入 `blocked` 或重排队列。
- 读写冲突：已有写锁时，新读任务不得旁路执行；已有读锁时，写任务进入等待队列。
- 同任务返工：若返工任务与原任务属于同一 `task_id`，可在释放旧租约后快速继承文件所有权。
- Review 驳回返工：返工后的 Coding 子任务重新获得写所有权，Review 侧保留只读权限。

# Constraints

- 所有权授予 MUST 与锁表一致，禁止出现“有所有权无锁”或“有锁无所有权”的分裂状态。
- 所有权记录 MUST 可回放、可查询、可由诊断事件还原。
- 文件所有权 MUST 以相对仓库路径为准，禁止使用模糊目录描述替代具体路径。
- 任何跨任务共享写权限 MUST 被视为违规。

# Forbidden Actions

- Agent MUST NOT 绕过 Orchestrator 直接修改其他子任务拥有的文件。
- Review Agent MUST NOT 申请业务源码的长期写所有权。
- Artifact Agent MUST NOT 持有 `runtime/`、`rules/`、`docs/specs/` 等业务目录写权限。
- Orchestrator MUST NOT 给未声明目标文件的子任务分配通配式写权限。

# Examples

- Valid: Coding 子任务声明修改 `api/todo.py` 和 `tests/test_todo.py`，Orchestrator 只为这两个文件授予写权限。
- Valid: Review 子任务读取 `api/todo.py` 与 diff 快照完成审查，不写入业务文件。
- Invalid: 两个并发 Coding 子任务同时获得 `runtime/orchestrator/orchestrator.py` 的写权限。
- Invalid: Artifact 子任务直接写入 `runtime/agents/coding.py`。

# References

- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-003-file-ownership.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/contracts/task-schema-spec.md`
