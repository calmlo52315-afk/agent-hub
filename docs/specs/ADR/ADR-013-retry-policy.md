ADR-013 重试策略

决策
AgentHub Runtime 对所有可重试失败采用统一 Retry Policy，由 Orchestrator 按执行规则驱动，禁止 Agent 在内部自行无限重试。

MVP 决策如下：
1. 重试上限与 backoff 由 `execution-rules` 配置。
2. 重试判断由运行时失败分类驱动，而不是由单个 Agent 自行决定。
3. 重试耗尽后必须返回结构化失败结果，作为当前阶段的 fallback 形态。
4. 重试仅覆盖瞬时性失败，不覆盖权限、归属、协议违约等确定性失败。

背景与选择原因
1. LLM 与外部工具调用本质上是不稳定系统，超时、瞬时异常、模型过载、短暂 I/O 异常无法完全避免。
2. 如果没有统一重试入口，重试逻辑会散落在各 Agent、Provider 适配器和工具层，导致行为不可预测、成本不可控。
3. 现有代码已经实现了基于 `RetryPolicy`、`FailureCategory` 和最小 backoff 的通用重试器，需要上升为正式架构决策。

MVP 策略
1. 默认由 Orchestrator 包裹 `coding`、`review`、`artifact` 三类阶段调用。
2. 重试配置读取自 `rules/execution-rules.json`：
   - `max_attempts`
   - `backoff_seconds`
3. MVP 默认可重试失败类别为：
   - `timeout`
   - `unknown`
4. MVP 默认不可重试失败类别为：
   - `schema_invalid`
   - `permission_denied`
   - `review_failed`

重试判定原则
1. 可重试：失败原因具有瞬时性，二次执行有明确恢复可能。
2. 不可重试：失败原因具有确定性，重复执行只会增加成本和风险。

典型分类
1. 应重试
   - Agent 超时
   - 临时性未知异常
   - 未来接入模型后可映射为 `MODEL_OVERLOADED`、`TRANSIENT_IO` 等瞬时错误
2. 不应重试
   - Schema 校验失败
   - 权限拒绝
   - 文件所有权冲突
   - Review 明确判定不通过
   - 非法状态转移

Fallback 语义
1. 当前 MVP 的 fallback 不是“切换到另一个 Agent 继续干”，而是“输出结构化失败，停止主流程”。
2. 结构化失败必须至少包含：
   - `category`
   - `stage`
   - `message`
   - `attempts`
   - `retry_limit`
   - `exception_type`
3. 失败结构必须可直接写入 Replay、Metrics、错误制品与任务结果摘要。

为什么当前不做更复杂的多级 fallback
1. 现阶段尚未完成多 Provider / 多 Agent 接入，过早引入“主模型失败后切备用模型”的复杂策略，会让执行链路和可观测性急剧复杂化。
2. 面试与工程化视角下，先把“什么时候重试、什么时候快速失败”讲清楚，比堆多套 fallback 更有说服力。

扩展预留
1. 允许未来将 `retryable_error_codes` 从预留字段升级为真实判定输入，用于承接 Provider 返回的标准错误码。
2. 允许按阶段定义差异化重试策略：
   - Coding 容忍较高重试次数
   - Review 重试次数更低
   - Artifact 更偏向快速失败
3. 允许后续增加 fallback 路由：
   - 模型降级
   - 切换备选 Skill
   - 人工接管

边界约束
1. 禁止在 Agent Prompt 内声明“如果失败就一直重试”。
2. 禁止绕过 Orchestrator 直接在工具层吞错重试。
3. 重试行为必须计入 Metrics 的 `retry_count`，并纳入成本统计。

参考
- `rules/execution-rules.json`
- `runtime/harness/retry/__init__.py`
- `runtime/orchestrator/orchestrator.py`
