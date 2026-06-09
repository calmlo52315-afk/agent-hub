ADR-014 错误分类体系

决策
为 AgentHub Runtime 建立统一错误分类体系，要求所有失败都至少归一化到稳定的错误类别，并为后续错误码、重试策略、指标聚合和告警系统提供一致语义。

MVP 采用“两层表示”：
1. 运行时类别：用于流程控制、重试与指标聚合。
2. 业务错误码：用于对外暴露、日志检索、跨模块对齐。

背景与选择原因
1. 如果只有“Task Failed”这类粗粒度结果，Replay、Metrics、告警与回归分析都无法使用。
2. 重试策略本质上依赖错误分类；没有分类，就无法判断是否应该重试。
3. 当前代码已经实现了 `schema_invalid`、`review_failed`、`timeout`、`permission_denied`、`unknown` 的 MVP 分类，需要正式固化下来，并为后续 Provider 错误与 Ownership 错误预留扩展槽位。

MVP 运行时类别
1. `schema_invalid`
   - 输入或输出不满足约定 schema。
2. `review_failed`
   - Review 阶段对产物作出明确拒绝结论。
3. `timeout`
   - Agent 执行超时。
4. `permission_denied`
   - 权限规则、危险操作拦截或文件访问越权。
5. `unknown`
   - 未能归类的兜底异常。

标准错误码族
1. `SYSTEM_ERROR`
   - Runtime 内部逻辑、状态机、I/O、存储等系统错误。
2. `MODEL_ERROR`
   - Provider、模型调用、推理服务异常。
3. `VALIDATION_ERROR`
   - 输入输出 schema 不合法、协议字段缺失。
4. `TIMEOUT_ERROR`
   - 执行超时。
5. `PERMISSION_ERROR`
   - 权限拒绝、危险操作禁止、沙箱越权。
6. `OWNERSHIP_ERROR`
   - 文件归属冲突、锁获取失败、版本检查不通过。
7. `REVIEW_REJECTED`
   - Review 业务判定不通过。
8. `UNKNOWN_ERROR`
   - 无法进一步归类的兜底错误。

两层映射原则
1. 运行时必须至少产出一个稳定 `category`，保证流程可继续判断。
2. 若能识别更细语义，则同时产出 `error_code`。
3. `category` 用于执行控制，`error_code` 用于对外契约与可观测性，不要求两者一一同名。

推荐映射
1. `schema_invalid` -> `VALIDATION_ERROR`
2. `review_failed` -> `REVIEW_REJECTED`
3. `timeout` -> `TIMEOUT_ERROR`
4. `permission_denied` -> `PERMISSION_ERROR`
5. `unknown` -> `UNKNOWN_ERROR`

为什么现在不强制一次性实现全量错误码
1. 当前 Provider 层尚未完全接入，`MODEL_ERROR` 等细分类还缺少稳定来源。
2. 当前 ownership 冲突在规则与工作空间层已存在，但尚未在失败对象中形成完整错误码收敛。
3. MVP 先要求“类别稳定”，再逐步扩展“错误码精细化”，能避免文档先于代码过度复杂化。

边界约束
1. 禁止直接抛出原始异常字符串作为唯一失败语义。
2. 禁止不同模块为同一类失败创造多个近义名字。
3. 所有错误事件必须可被 Replay 存档，并可被 Metrics 聚合。

影响
1. Retry Policy 基于错误类别判断是否重试。
2. Error Spec 应定义统一字段与错误码列表。
3. Metrics 与告警系统应能按 `category` 和 `error_code` 双维度聚合。

演进路径
1. 接入外部模型后，将 Provider 错误统一映射到 `MODEL_ERROR` 子类。
2. 将 ownership / lock / version mismatch 归并到 `OWNERSHIP_ERROR`。
3. 未来如需对外开放 API，可基于该体系派生 HTTP / RPC 错误语义。

参考
- `runtime/harness/retry/__init__.py`
- `runtime/orchestrator/orchestrator.py`
- `docs/specs/系统架构设计.md`
