# Skill Contract Spec

## 1. 目标

定义 Stage 3 Skill 体系的统一输入输出契约，使 Skill 可以被注册、复用、版本化、审计和编排。

本 Spec 是面向人类阅读的契约说明；后续如需机器校验，应在 `runtime/specs/` 落对应 schema。

## 2. 设计原则

- Skill 是可复用能力单元，不等同于 Agent
- Skill 的身份由 `skill_name + version` 唯一确定
- Skill 的输入输出必须结构化，不能只依赖自然语言约定
- Skill 的权限、超时、错误语义必须显式声明

## 3. Skill 元数据

每个 Skill 至少包含以下元数据：

```json
{
  "skill_name": "coding.generate_patch",
  "version": "1.0.0",
  "description": "Generate workspace changes for a coding task",
  "owner": "runtime",
  "entrypoint": "agent|tool|workflow",
  "timeout_seconds": 600,
  "permission_scope": {
    "read_paths": ["runtime/**", "docs/**"],
    "write_paths": ["demo_workspace/**"],
    "deny_operations": ["network", "modify_rules"]
  }
}
```

字段说明：

- `skill_name`：全局唯一能力名，推荐使用命名空间风格
- `version`：语义化版本号，绑定 Skill Contract
- `entrypoint`：Skill 的实现入口类型
- `timeout_seconds`：默认超时设置
- `permission_scope`：Skill 级权限边界

## 4. 通用输入 Envelope

所有 Skill 执行请求建议统一为如下结构：

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "string",
  "version": "string",
  "invoker": {
    "type": "orchestrator|agent|workflow",
    "id": "string"
  },
  "context": {
    "workflow_state": "string",
    "shared_state_keys": ["string"]
  },
  "payload": {},
  "constraints": {
    "timeout_seconds": 600,
    "budget_tokens": 0,
    "budget_cost_usd": 0
  }
}
```

说明：

- `trace_id`、`task_id` 为必填追踪字段
- `payload` 为具体 Skill 自定义输入
- `constraints` 用于承接执行规则、预算和超时

## 5. 通用输出 Envelope

所有 Skill 执行结果建议统一为如下结构：

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "string",
  "version": "string",
  "status": "success|failed",
  "payload": {},
  "error": null,
  "metrics": {
    "latency_ms": 0,
    "token_usage": 0,
    "retry_count": 0
  }
}
```

约束：

- `status=success` 时，`payload` 必须满足该 Skill 的输出 schema
- `status=failed` 时，`error` 必须非空
- `metrics` 建议保留，即使部分字段暂不可用

## 6. Error 结构

Skill 失败时建议统一返回：

```json
{
  "category": "timeout",
  "error_code": "TIMEOUT_ERROR",
  "message": "agent timeout: coding (600s)",
  "retryable": true,
  "details": {}
}
```

字段要求：

- `category`：运行时失败类别
- `error_code`：稳定业务错误码
- `retryable`：是否允许上层重试
- `details`：附加调试信息

## 7. 版本规则

语义化版本规则如下：

- Major：不兼容变更
- Minor：向后兼容新增
- Patch：不改变 Contract 的实现优化

示例：

- `1.0.0 -> 1.0.1`：Prompt 优化
- `1.0.1 -> 1.1.0`：新增可选字段
- `1.1.0 -> 2.0.0`：删除字段或改变字段语义

## 8. Prompt 与 Skill 的关系

- Prompt 是 Skill 的实现资源，不是版本源头
- Prompt 可独立维护版本与启用关系
- Prompt 升级若不影响 Contract，不必提升 Major / Minor

## 9. 最小 Skill 示例

### 9.1 Coding Skill

```json
{
  "skill_name": "coding.generate_patch",
  "version": "1.0.0",
  "payload": {
    "instruction": "Add hello endpoint",
    "targets": [
      {
        "path": "runtime/demo.py",
        "action": "update"
      }
    ]
  }
}
```

### 9.2 Review Skill

```json
{
  "skill_name": "review.analyze_diff",
  "version": "1.0.0",
  "payload": {
    "changes": [
      {
        "path": "runtime/demo.py",
        "action": "update",
        "diff": "..."
      }
    ]
  }
}
```

## 10. 注册与寻址

Skill Registry 至少需要支持以下索引键：

- `skill_name`
- `version`
- `entrypoint`
- `owner`
- `status`

其中 `status` 建议取值：

- `active`
- `deprecated`
- `disabled`

## 11. 与规则系统的关系

- 权限边界由 `permission-rules` 与 `ownership-rules` 共同裁决
- 超时、重试、预算由 `execution-rules` 驱动
- Skill Contract 不替代规则系统，只负责定义接口与声明式元数据

## 12. 参考

- `docs/specs/ADR/ADR-015-skill-interface-versioning.md`
- `docs/specs/ADR/ADR-016-tool-permission-boundary.md`
- `docs/specs/ADR/ADR-017-skill-composition-model.md`
