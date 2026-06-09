# 错误与失败路径（比赛提交）

本页用于比赛提交：沉淀运行时的关键错误类型与失败路径，证明系统具备“失败可诊断、不崩溃”的工程化特征。

## 1. 规则/规范加载失败

### 1.1 RulesLoadError（规则加载失败）

- 触发：`/rules/index.json` 缺失、JSON 非法、缺少 policy 字段、policy 文件缺失/字段不完整
- 表现：校验入口返回非 0；或 Orchestrator.load() 失败并输出可诊断信息
- 代码位置：`runtime/config/rules_loader.py`

### 1.2 SpecLoadError（运行时契约入口不兼容）

- 触发：`/spec/index.json` 缺失/JSON 非法/schema_version 不兼容
- 表现：Orchestrator.load() 失败并给出原因
- 代码位置：`runtime/config/spec_loader.py`

## 2. 协议/消息错误

### 2.1 MessageValidationError（Envelope 非法）

- 触发：schema_version 不匹配；字段缺失；payload 非对象等
- 表现：Orchestrator 在发送/接收 envelope 时拒绝并抛出 OrchestratorError（附带原因）
- 代码位置：`runtime/messages.py`

## 3. 权限/Ownership/并发冲突

### 3.1 PermissionDenied（权限拒绝）

- 触发：尝试对不允许路径/动作进行读写删（由 permission-rules 决定）
- 表现：Workspace.apply_change() 抛出可诊断错误，不产生副作用写入
- 代码位置：`runtime/harness/permissions.py`、`runtime/harness/workspace.py`

### 3.2 OwnershipDenied / LockTimeout（所有权拒绝/锁超时）

- 触发：角色无权修改某路径；同文件锁在超时内无法获取
- 表现：Workspace.apply_change() 抛出可诊断错误；不产生并行写冲突
- 代码位置：`runtime/harness/ownership.py`

### 3.3 VersionMismatch（版本基线不一致）

- 触发：提交的 `base_hash` 与当前文件 hash 不一致（典型：旧上下文覆盖新版本）
- 表现：拒绝写入并返回 VersionMismatch（不覆盖、不合并）
- 代码位置：`runtime/harness/workspace.py`

## 4. 评审失败

### 4.1 Review 失败（pass=false）

- 触发：review agent 返回 `pass=false` 或 issues 命中阻断规则
- 表现：Orchestrator 中止 workflow，并返回可诊断失败原因（不会崩溃）
- 代码位置：`runtime/orchestrator/orchestrator.py`、`runtime/agents/review.py`

