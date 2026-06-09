# Purpose

定义 Stage 4 多任务并发下的文件锁规则，保证自研 DAG 调度器在内存队列中执行子任务时，能够稳定识别冲突、阻塞、重试和锁释放时机。

# Scope

本 Rule 适用于 Stage 4 中所有对子任务文件读写权限的加锁、续租、冲突检测、等待与释放逻辑。

# Rules

1. 所有文件访问 MUST 先经过锁检查，再进入实际执行。
2. 锁模式仅允许 `read` 与 `write` 两种；其中 `write` 为排他锁。
3. 同一路径上，`read + read` MAY 并存；任何涉及 `write` 的组合 MUST 互斥。
4. 子任务进入 `ready -> running` 前，Orchestrator MUST 一次性申请该子任务的全部必需锁，申请失败则不得启动执行。
5. 锁授予 MUST 与 `task_id`、`subtask_id`、`owner_role` 绑定，禁止无主锁。
6. 锁 SHOULD 带有租期 `lease_seconds`，防止超时任务永久占锁。
7. 子任务成功、失败、取消或超时后，Orchestrator MUST 立即释放其全部锁。
8. 依赖未满足的子任务 MUST 保持无锁状态，避免提前占用写资源。
9. 锁冲突时，调度器 MAY 将子任务标记为 `blocked` 并重新进入等待队列，但 MUST 保留冲突原因。
10. 同一 `task_id` 的返工子任务在旧锁已释放的前提下 MAY 优先重新获得原路径锁。
11. 锁获取与释放 SHOULD 产生回放事件，用于复盘死锁、饥饿与冲突重试。
12. 锁表 MUST 由 Orchestrator 独占维护，Agent MUST NOT 直接改写锁状态。

# Compatibility Matrix

| Existing | Incoming | Allowed | Result |
| --- | --- | --- | --- |
| `read` | `read` | Yes | 共享读 |
| `read` | `write` | No | 写任务阻塞 |
| `write` | `read` | No | 读任务阻塞 |
| `write` | `write` | No | 后到写任务阻塞 |

# Lock Event Model

```json
{
  "event_type": "lock.acquired",
  "task_id": "task-root-001",
  "subtask_id": "review-api-001",
  "path": "runtime/orchestrator/orchestrator.py",
  "mode": "read",
  "owner_role": "review",
  "lease_seconds": 180
}
```

# Conflict Handling

- 依赖未满足：标记为 `blocked`，等待前驱节点成功后重新评估。
- 文件冲突：进入等待队列，直到冲突锁释放或调度器判定超时。
- 锁超时：释放锁并记录 `lock.expired`，相关子任务转为失败或重试。
- 死锁预防：Stage 4 MUST 采用“执行前一次性申请全部锁”的策略，避免运行中逐个拿锁导致循环等待。

# Constraints

- 锁粒度以文件路径为最小单位，当前阶段不支持目录级模糊锁。
- 锁状态 MUST 存在内存单例表中，并可按需快照到 replay。
- Stage 4 锁机制 MUST 兼容 `asyncio + 内存任务队列` 实现，不依赖外部锁服务。
- 锁等待时间 SHOULD 受子任务 `timeout_seconds` 约束，避免无限阻塞。

# Forbidden Actions

- Agent MUST NOT 绕过锁检查直接读写目标文件。
- Orchestrator MUST NOT 在只拿到部分锁的情况下启动子任务执行。
- 锁租期过期后，系统 MUST NOT 继续视其为有效持有。
- 系统 MUST NOT 为未声明目标文件的子任务分配通配锁。

# Examples

- Valid: 两个 Review 子任务并发读取同一个 diff 快照文件。
- Valid: Coding 子任务等待 Review 子任务释放 `write` 锁后再进入运行。
- Invalid: Coding 子任务已拿到 `write` 锁，另一个 Coding 子任务仍然并发写同一路径。
- Invalid: 子任务因为依赖未满足而长时间持有写锁。

# References

- `docs/specs/ADR/ADR-003-file-ownership.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/contracts/dag-execution-spec.md`
