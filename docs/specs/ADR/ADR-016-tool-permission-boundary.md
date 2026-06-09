ADR-016 工具权限边界

决策
所有 Agent / Skill 的工具调用必须处于统一权限边界内，由 Orchestrator 与规则系统共同裁决；不同角色只能使用与其职责匹配的最小工具集合。

MVP 采用“角色边界 + 文件权限 + 危险操作禁用”的三层控制：
1. 角色边界：不同 Agent / Skill 只能调用各自允许的工具能力。
2. 文件权限：文件读写必须满足 `permission-rules` 与 `ownership-rules`。
3. 危险操作：修改规则、协议、所有权、敏感目录和高危 Shell 行为默认禁止。

背景与选择原因
1. 没有权限边界的 Agent 不是工程化系统，只是带文件系统能力的 Prompt。
2. 代码系统最容易失控的不是“写得不够聪明”，而是“改了不该改的东西”。
3. 当前仓库已经有 `permission-rules`、`ownership-rules`、`runtime-agent-boundary` 等规则基础，应收敛为正式 ADR，避免边界继续散落在各处。

角色级能力边界
1. Coding Agent / Coding Skill
   - 允许：读取工作区、提出代码变更、写入被授权源码路径、读取规则上下文
   - 禁止：修改规则文件、修改协议文件、修改所有权配置、直接归档产物、直接更改任务状态
2. Review Agent / Review Skill
   - 允许：读取工作区、读取 diff、读取规则、输出评审结论与问题列表
   - 禁止：写入源码、修改规则、修改锁状态、直接通过评审后落盘变更
3. Artifact Agent / Artifact Skill
   - 允许：读取工作区快照、读取评审结果、写入归档目录、生成元数据
   - 禁止：修改源码、修改规则、介入评审判定

高危对象保护
1. 默认禁止修改以下内容：
   - `rules/**`
   - `docs/specs/**` 中的协议、规则、归属类文档
   - 所有权与锁配置
   - Orchestrator 协议与路由边界
2. 如确有需要，必须以显式运维/管理员流程单独放行，不能通过常规 Coding Agent 获取。

调用路径决策
1. Agent 不直接拥有“无限工具权限”。
2. 工具权限应先映射为声明式 capability，再由 Orchestrator 按规则实际放行。
3. Skill 即使被多个 Agent 复用，也必须继承调用方上下文内的最小权限，而不是自动获得 Skill 自身定义的最大权限。

为什么 Review 明确禁止写代码
1. 一旦 Review 同时负责审查与修复，就会破坏职责隔离，导致评审结论不可信。
2. 工程化面试中，职责单一、审查可追责，比“让 Review 顺手改完”更具说服力。

影响
1. Skill Contract 应显式声明 `permission_scope` 与 `dangerous_operations`。
2. Permission Rules 需要继续维护白名单目录、禁止路径和危险操作策略。
3. 所有拒绝事件必须生成结构化错误，并纳入 Metrics 与审计日志。

演进路径
1. 后续可将权限边界从 Agent 级细化到 Skill 级。
2. 若未来引入外部 code agent，也必须先映射到本系统能力模型，再执行，不允许旁路文件系统。

参考
- `rules/permission-rules.json`
- `rules/ownership-rules.json`
- `docs/specs/rules/global/runtime-agent-boundary.md`
- `docs/specs/ADR/ADR-002-agent-boundary.md`
- `docs/specs/ADR/ADR-003-file-ownership.md`
