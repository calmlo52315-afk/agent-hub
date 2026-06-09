# 第二阶段验收清单

- [x] Schema 校验能够拦截非法 Agent 输出，并阻断后续下游步骤
- [x] 校验失败能够返回结构化 `ValidationResult`，并持久化用于诊断与回放
- [x] Runtime rules 可解析，必需规则段缺失或非法时能够快速失败
- [x] 失败分类已统一应用到校验失败、Review 失败、超时、权限拒绝等场景
- [x] Retry 行为遵循执行规则中的 `retry_limit`，重试耗尽后返回确定性失败结果
- [x] 状态机能够阻止非法状态迁移，并记录诊断事件
- [x] Replay 记录已存入 SQLite，并满足 ADR-008 规定的保留策略
- [x] Metrics 事件已按 JSON Lines 输出，并包含 ADR-009 要求的指标项与标签
- [x] Harness 在 sink / storage 写入失败时不会拖垮主流程，能够按 best-effort 降级
