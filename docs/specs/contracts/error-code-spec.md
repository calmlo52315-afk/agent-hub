# Error Code Spec

## 1. 目标

定义 AgentHub Runtime 的统一错误字段和错误码集合，使失败结果可以被稳定地记录、检索、聚合和重试判定。

本 Spec 与 `ADR-014` 配套，采用“运行时类别 + 业务错误码”的双层表达。

## 2. 标准错误对象

推荐的统一错误结构如下：

```json
{
  "category": "timeout",
  "error_code": "TIMEOUT_ERROR",
  "message": "agent timeout: coding (600s)",
  "stage": "coding",
  "retryable": true,
  "attempts": 2,
  "retry_limit": 2,
  "exception_type": "AgentTimeoutError",
  "details": {}
}
```

字段说明：

- `category`：运行时归一化类别，用于流程控制
- `error_code`：稳定业务错误码，用于日志检索与跨模块对齐
- `message`：人类可读错误描述
- `stage`：发生失败的阶段，如 `coding`、`review`、`artifact`
- `retryable`：是否允许上层重试
- `attempts`：实际执行次数
- `retry_limit`：重试上限
- `exception_type`：底层异常类型
- `details`：补充信息

## 3. 运行时类别

MVP 统一类别如下：

- `schema_invalid`
- `review_failed`
- `timeout`
- `permission_denied`
- `unknown`

后续可扩展类别：

- `ownership_conflict`
- `model_error`
- `system_error`

## 4. 业务错误码

P0/P1 推荐保留以下稳定错误码：

| error_code | 含义 | 默认 retryable |
| --- | --- | --- |
| `SYSTEM_ERROR` | Runtime 内部错误 | 否 |
| `MODEL_ERROR` | 模型或 Provider 调用错误 | 视子类而定 |
| `VALIDATION_ERROR` | 输入输出校验失败 | 否 |
| `TIMEOUT_ERROR` | 阶段执行超时 | 是 |
| `PERMISSION_ERROR` | 权限拒绝或危险操作被拦截 | 否 |
| `OWNERSHIP_ERROR` | 文件归属、锁或版本冲突 | 否 |
| `REVIEW_REJECTED` | Review 判定不通过 | 否 |
| `UNKNOWN_ERROR` | 未知错误 | 视策略而定 |

## 5. 推荐映射

| category | error_code |
| --- | --- |
| `schema_invalid` | `VALIDATION_ERROR` |
| `review_failed` | `REVIEW_REJECTED` |
| `timeout` | `TIMEOUT_ERROR` |
| `permission_denied` | `PERMISSION_ERROR` |
| `unknown` | `UNKNOWN_ERROR` |

补充说明：

- 当前 MVP 若无法提供 `error_code`，至少必须提供 `category`
- 后续 Ownership 与模型错误稳定后，应补充更细映射

## 6. Retry 规则对齐

默认规则建议如下：

- `TIMEOUT_ERROR`：可重试
- `UNKNOWN_ERROR`：可重试，但应受上限控制
- `VALIDATION_ERROR`：不可重试
- `PERMISSION_ERROR`：不可重试
- `OWNERSHIP_ERROR`：不可重试
- `REVIEW_REJECTED`：不可重试

说明：

- “不可重试”指不应通过通用技术重试解决
- Review 返工属于工作流回退，不属于技术重试

## 7. 产物与日志要求

失败事件至少应写入以下信息：

- 任务结果摘要
- Replay 事件
- 错误制品文件
- Metrics 标签

建议日志标签：

```json
{
  "category": "timeout",
  "error_code": "TIMEOUT_ERROR",
  "stage": "coding",
  "retryable": true
}
```

## 8. 向后兼容

- 新增 `error_code` 不应破坏既有 `category`
- 已发布错误码不得随意改名
- 如需废弃错误码，应先标记 deprecated，再在下一 Major 移除

## 9. 示例

### 9.1 超时失败

```json
{
  "category": "timeout",
  "error_code": "TIMEOUT_ERROR",
  "message": "agent timeout: review (300s)",
  "stage": "review",
  "retryable": true,
  "attempts": 2,
  "retry_limit": 2,
  "exception_type": "AgentTimeoutError",
  "details": {}
}
```

### 9.2 Review 不通过

```json
{
  "category": "review_failed",
  "error_code": "REVIEW_REJECTED",
  "message": "review reported issues that require rework",
  "stage": "review",
  "retryable": false,
  "attempts": 1,
  "retry_limit": 1,
  "exception_type": null,
  "details": {
    "severity": "high"
  }
}
```

## 10. 参考

- `docs/specs/ADR/ADR-013-retry-policy.md`
- `docs/specs/ADR/ADR-014-error-taxonomy.md`
- `runtime/harness/retry/__init__.py`
