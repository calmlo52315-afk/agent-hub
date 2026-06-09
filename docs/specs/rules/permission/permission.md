# Purpose

定义 Stage 5 中前端用户通过 Gateway 可以触发哪些动作、哪些动作需要人工确认、哪些动作必须被拒绝，用于约束 IM 群聊与多 Agent 协作中的外部操作边界。

# Scope

本规则适用于：

- 会话创建、查询与订阅
- 聊天消息发送
- 任务取消、重试、审批、冲突处理
- artifact 读取与预览触发
- Gateway 对前端动作的鉴权与准入控制

Agent 与 Skill 的内部工具权限仍由 ADR-016 和既有运行时规则控制；本规则只描述“前端能触发什么”。

# Roles

MVP 最小角色集合：

- `session_member`：会话参与者，默认角色
- `session_approver`：允许做人工确认与冲突裁决的用户
- `system_admin`：保留给运维或比赛演示环境，不作为默认前端能力

MVP 中如果只有单用户模式，`session_member` 与 `session_approver` MAY 映射到同一人，但权限语义仍应保留。

# Rules

1. 所有前端触发动作 MUST 先经过 Gateway 鉴权，再做会话归属与权限校验。
2. `session_member` MUST 被允许创建会话、查看会话列表、查看消息历史、查看任务列表、查看 artifact 卡片。
3. `session_member` MUST 被允许发送普通 `chat.message`，包括 `@agent` 显式路由类消息。
4. `session_member` MAY 请求任务取消与普通重试，但 Gateway MUST 校验任务当前状态是否允许该动作。
5. `session_approver` MUST 被允许处理 `approval.required` 对应的人工决策，包括重试超限、冲突确认、Review 失败后的继续/拒绝。
6. 冲突处理动作 MUST 通过显式接口或命令提交，禁止前端仅靠自然语言文本绕过结构化审批。
7. 会影响任务状态跃迁、锁状态、冲突归并结果的动作 MUST 生成审计记录。
8. Gateway MUST 拒绝来自非会话成员的读取与操作请求。
9. Gateway MUST 拒绝未授权用户对任务做强制继续、强制合并、跳过 Review、跳过 Approval 的请求。
10. 前端对 artifact 的操作默认仅限读取、预览、下载，不得直接修改 artifact 内容。
11. Frontend 触发的任何动作都 MUST 通过 Gateway 转换为结构化命令；Runtime MUST NOT 接收来自前端的裸自由文本控制指令。
12. 涉及高风险变更的继续执行 MUST 遵循 ADR-021 的 Human-in-the-Loop 约束。

# Allowed Actions

`session_member` 默认允许：

- `session.create`
- `session.list`
- `session.get`
- `session.subscribe`
- `session.messages.list`
- `session.tasks.list`
- `task.get`
- `chat.send`
- `artifact.list`
- `artifact.get`
- `artifact.open_preview`
- `artifact.open_diff`
- `artifact.download`
- `heartbeat`

`session_member` 条件允许：

- `task.cancel`
- `task.retry.request`

条件：

- 目标任务属于当前会话
- 任务状态允许该动作
- 未命中额外审批门槛

`session_approver` 额外允许：

- `task.approval.approve`
- `task.approval.reject`
- `task.approval.submit`
- `task.conflict.resolve`
- `conflict.resolution.submit`
- `task.retry.force`

# Approval Gates

以下动作 MUST 进入人工确认门槛：

- Retry 次数已超出系统限制
- 文件冲突无法自动合并
- Review Agent 给出高风险失败结论
- 大文件或大范围修改超过阈值
- 需要恢复被阻塞的高风险任务

审批记录至少包含：

- `approval_id`
- `approver`
- `session_id`
- `task_id`
- `decision`
- `reason`
- `timestamp`

# Forbidden Actions

- 前端 MUST NOT 直接调用 Runtime 或 Agent 内部接口。
- 前端 MUST NOT 直接指定某个 Skill 在 Runtime 内部执行。
- 前端 MUST NOT 直接修改规则文档、协议文档、锁状态或文件所有权状态。
- 前端 MUST NOT 绕过 Review 或 Approval 强制把任务置为完成。
- 前端 MUST NOT 伪造 `session_id`、`task_id`、`approval_id` 冒充其他会话上下文。
- Gateway MUST NOT 因为收到自然语言“我批准了”就跳过结构化审批校验。

# Audit Requirements

- 每个变更类动作 MUST 记录请求人、目标会话、目标任务、动作名、结果和时间戳。
- 每个审批类动作 MUST 记录审批原因。
- 每个权限拒绝事件 SHOULD 记录结构化错误码，便于 Metrics 与回放。

# Examples

- Valid: 会话成员在聊天区发送“`@frontend-agent 做登录页`”，Gateway 受理并进入编排链路。
- Valid: 会话审批人收到 `approval.required` 后，通过结构化接口提交 `approve`，系统继续执行。
- Invalid: 普通会话成员直接强制合并冲突 diff，并跳过人工确认。
- Invalid: 前端构造一个不存在的 `task_id` 直接请求 Runtime 重试。

# References

- `docs/specs/ADR/ADR-016-tool-permission-boundary.md`
- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-021-Human-in-the-Loop`
- `docs/specs/ADR/ADR-022-Gateway-Authentication.md`
- `docs/specs/contracts/session-task-api-spec.md`
