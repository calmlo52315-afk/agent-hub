# Task Schema Spec

## 1. 目标

定义 Stage 4 主任务与子任务的统一结构，作为 Orchestrator 拆分任务、构建 DAG、计算优先级、控制超时/重试和回放执行轨迹的基础规范。

## 2. 设计原则

- 任务对象必须结构化，禁止用自然语言段落直接充当运行时任务对象。
- 子任务粒度必须遵循 ADR-007，默认目标文件数不超过 3 个。
- 任务对象必须兼容 ADR-011 的结构化消息协议，能够嵌入 `payload`。
- Schema 既要支持串行链路，也要支持 Stage 4 的 DAG 并行调度。

## 3. Root Task

```json
{
  "task_id": "task-root-001",
  "title": "实现登录页并完成审核归档",
  "instruction": "开发登录页面，完成 review，并生成 artifact",
  "priority": "high",
  "status": "planning",
  "created_at": "2026-06-04T10:00:00Z",
  "subtasks": ["coding-login-001", "review-login-001", "artifact-login-001"],
  "metadata": {
    "source": "chat",
    "explicit_agents": ["coding", "review"]
  }
}
```

字段说明：

- `task_id`：主任务唯一 ID。
- `title`：适合展示与 review 的简短标题。
- `instruction`：原始目标摘要。
- `priority`：主任务优先级，允许 `high|medium|low`。
- `status`：主任务状态，取值见 `dag-execution-spec.md`。
- `subtasks`：子任务 ID 列表。
- `metadata`：来源、会话、用户显式路由等附加信息。

## 4. Subtask Schema

```json
{
  "subtask_id": "coding-login-001",
  "task_id": "task-root-001",
  "title": "实现登录页 UI",
  "summary": "仅负责登录页结构与样式，不含 review 与 artifact",
  "agent": "coding",
  "skill_name": "coding.generate_patch",
  "target_files": ["web/login.tsx", "web/login.css"],
  "dependency_ids": [],
  "priority": "high",
  "timeout_seconds": 120,
  "retry_limit": 2,
  "status": "ready",
  "attempt": 0,
  "input": {
    "instruction": "实现深色风格登录页"
  },
  "output": null
}
```

字段约束：

- `subtask_id`：子任务唯一 ID。
- `task_id`：所属主任务 ID。
- `title` / `summary`：面向执行与 review 的任务说明。
- `agent`：目标角色，仅允许 `coding|review|artifact`。
- `skill_name`：选填；若系统已启用 Skill Runtime，则用于绑定具体能力。
- `target_files`：目标文件列表；Stage 4 原则上不超过 3 个物理文件。
- `dependency_ids`：直接依赖子任务 ID 列表。
- `priority`：优先级，允许 `high|medium|low`。
- `timeout_seconds`：单节点超时，必须大于 0。
- `retry_limit`：单节点允许重试次数，必须大于等于 0。
- `status`：子任务内部状态，见 `dag-execution-spec.md`。
- `attempt`：当前执行尝试次数。
- `input` / `output`：结构化输入输出。

## 5. Dependency Rules

- `dependency_ids` 只描述直接前驱，不应冗余展开全部祖先节点。
- 依赖关系必须形成有向无环图；发现环时，Orchestrator 必须拒绝调度。
- 后继节点只消费前驱节点最近一次成功输出。
- 失败节点若未定义降级输出，则依赖它的强依赖节点不得进入执行。

## 6. Recommended Status Set

主任务推荐状态：

- `created`
- `planning`
- `scheduled`
- `running`
- `success`
- `failed`
- `cancelled`

子任务推荐状态：

- `pending`
- `blocked`
- `ready`
- `running`
- `retrying`
- `success`
- `failed`
- `skipped`

## 7. Validation Rules

- 子任务 `agent` 必须符合 ADR-002 规定的角色边界。
- 子任务 `target_files` 数量必须符合 ADR-007 的粒度约束。
- 所有消息投递时，任务对象必须作为 ADR-011 Message `payload` 的结构化字段传输。
- `timeout_seconds`、`retry_limit`、`priority` 必须在任务创建时确定，不应在 Agent 内部临时篡改。

## 8. References

- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-007-task-granularity.md`
- `docs/specs/ADR/ADR-011-message-protocol.md`
- `docs/specs/contracts/dag-execution-spec.md`
