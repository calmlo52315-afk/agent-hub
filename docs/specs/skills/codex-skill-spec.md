# Codex Skill Spec

## 1. 目标

定义 Codex（OpenAI Codex CLI）作为 AgentHub 能力单元（Skill）的专属规范，包括 CLI 调用方式、输入输出契约、代码评审模式、自动编辑模式、权限边界与错误处理语义。

Codex 作为**评审智能体（Review Agent）的底层能力实现**，负责源代码评审解析、代码变更 Diff 分析与标准化评审报告输出。

## 2. Skill 元数据

```json
{
  "skill_name": "codex",
  "version": "1.0.0",
  "description": "Codex CLI 评审与自动编辑能力——代码评审、Diff 分析、自动代码编辑",
  "owner": "runtime",
  "entrypoint": "external_cli",
  "timeout_seconds": 180,
  "permission_scope": {
    "read_paths": ["${WORKSPACE_ROOT}/**"],
    "write_paths": ["${WORKSPACE_ROOT}/**"],
    "deny_operations": [
      "network",
      "modify_rules",
      "access_replay_db",
      "access_metrics_db",
      "cross_workspace_access",
      "modify_global_config"
    ]
  }
}
```

## 3. 角色定位

在 AgentHub 的 Coding → Review → Artifact 主链路中，Codex Skill 由 **Review Agent** 调用，承担：

```
Review Agent（编排调度）
    │
    │ 评审任务规划 + 风险分析 + 打分评级
    │
    ▼
CodexSkill（能力执行）
    │
    │ codex "Review this diff" / codex --auto-edit
    │
    ▼
隔离工作区（评审报告产出）
```

约束：

- Codex Skill **不可**直接改写业务源代码（Review 模式），Auto-edit 模式仅为 Coding Agent 执行
- Codex Skill **不可**直接修改 Review Agent 的运行状态
- Codex Skill **不可**文件所有权配置
- Codex Skill **不可**篡改全局调度状态
- 所有评审结论的最终决策（pass/fail/retry）由上层 Review Agent 执行

## 4. CLI 调用规范

### 4.1 两种工作模式

Codex CLI 提供两种工作模式，Skill Runtime 根据调用场景选择：

| 模式 | 命令格式 | 用途 | 调用方 |
|------|----------|------|--------|
| **Review 模式** | `codex "Review this diff"` | 代码评审解析、Diff 分析 | Review Agent |
| **Auto-edit 模式** | `codex --auto-edit` | 自动代码编辑（备选编码能力） | Coding Agent（备选） |

Review 模式为**主要能力**，Auto-edit 模式作为 Coding Agent 的备选编码能力保留。

### 4.2 Review 模式调用示例

```bash
cd /path/to/workspace/task_001 && \
codex "Review this diff:

Files changed:
- src/api/auth.py (+45, -3)
- src/models/user.py (+20, -0)

Diff:
@@ -1,5 +1,47 @@
+ ...
+
Please analyze:
1. Security vulnerabilities
2. Logic errors
3. Style / best practice violations
4. Performance concerns

Output a structured review in JSON format:
{
  \"decision\": \"pass|fail\",
  \"issues\": [...],
  \"score\": { \"value\": N, \"max\": 100 }
}
" \
2>&1
```

### 4.3 Auto-edit 模式调用示例（备选）

```bash
cd /path/to/workspace/task_001 && \
codex --auto-edit <<EOF
Update src/models/user.py: add email field with validation
EOF
```

### 4.4 环境变量

Skill Runtime 在拉起子进程前注入：

```bash
WORKSPACE_ROOT=/path/to/workspace/task_001
TASK_ID=task_001
SKILL_NAME=codex
TRACE_ID=xxxx-xxxx
CODEX_TIMEOUT=180
CODEX_MODE=review           # review | auto_edit
```

Codex 子进程应通过 `WORKSPACE_ROOT` 确定文件操作根目录。

## 5. 输入 Contract

### 5.1 `CodexInput`（Review 模式）

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "codex",
  "version": "1.0.0",
  "invoker": {
    "type": "review_agent",
    "id": "string"
  },
  "payload": {
    "mode": "review",
    "task": {
      "id": "string"
    },
    "changes": [
      {
        "path": "string",
        "action": "create|update|delete",
        "diff": "string"
      }
    ],
    "review_focus": {
      "dimensions": ["security", "logic", "style", "performance"],
      "policies": {
        "execution": {},
        "permission": {},
        "ownership": {},
        "communication": {}
      }
    }
  },
  "constraints": {
    "timeout_seconds": 180,
    "max_retries": 3
  }
}
```

字段说明：

- `payload.mode`：`"review"` 表示代码评审模式
- `payload.changes`：Coding Agent 产出的文件变更列表（含 diff）
- `payload.review_focus.dimensions`：本次评审关注的维度（安全、逻辑、风格、性能）
- `payload.review_focus.policies`：引用的规则策略，用于对齐评审标准

### 5.2 `CodexInput`（Auto-edit 模式，备选）

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "codex",
  "version": "1.0.0",
  "invoker": {
    "type": "coding_agent",
    "id": "string"
  },
  "payload": {
    "mode": "auto_edit",
    "instruction": "string",
    "targets": [
      {
        "path": "string",
        "action": "create|update|delete",
        "description": "string"
      }
    ]
  },
  "constraints": {
    "timeout_seconds": 180,
    "max_retries": 3
  }
}
```

## 6. 输出 Contract

### 6.1 `CodexOutput`（Review 模式）

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "codex",
  "version": "1.0.0",
  "status": "success|failed",
  "payload": {
    "decision": "pass|fail",
    "score": {
      "value": 0,
      "max": 100
    },
    "issues": [
      {
        "id": "string",
        "severity": "high|medium|low",
        "type": "security|logic|style|performance|other",
        "message": "string",
        "paths": ["string"],
        "line_range": {
          "start": 0,
          "end": 0
        },
        "suggestion": "string"
      }
    ],
    "summary": {
      "total_issues": 0,
      "high_severity_count": 0,
      "medium_severity_count": 0,
      "low_severity_count": 0,
      "dimension_breakdown": {
        "security": 0,
        "logic": 0,
        "style": 0,
        "performance": 0,
        "other": 0
      }
    },
    "suggestions": ["string"]
  },
  "error": null,
  "metrics": {
    "latency_ms": 0,
    "token_usage": 0,
    "retry_count": 0,
    "exit_code": 0
  }
}
```

字段说明：

- `payload.decision`：`"pass"` 表示评审通过、`"fail"` 表示评审不通过
- `payload.score`：代码质量评分（0-100）
- `payload.issues`：发现的问题清单，按严重程度与类型分类
- `payload.summary.dimension_breakdown`：按评审维度汇总的问题数量
- `payload.suggestions`：改进建议（自然语言）

### 6.2 `CodexOutput`（Auto-edit 模式，备选）

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "codex",
  "version": "1.0.0",
  "status": "success|failed",
  "payload": {
    "changes": [
      {
        "path": "string",
        "action": "create|update|delete",
        "diff": "string"
      }
    ],
    "self_check": {
      "summary": "string",
      "risks": ["string"]
    }
  },
  "error": null,
  "metrics": {
    "latency_ms": 0,
    "token_usage": 0,
    "retry_count": 0,
    "exit_code": 0
  }
}
```

## 7. Review 决策语义

Review Agent 基于 Codex 输出做最终决策，决策矩阵如下：

| Codex decision | 高风险数 | Review Agent 决策 | 后续动作 |
|---------------|---------|-------------------|----------|
| `pass` | 0 | `review.pass` | 进入 Artifact |
| `pass` | ≥1 | `review.fail.retry` | 回退 Coding Agent 修复 |
| `fail` | 0 | `review.fail.retry` | 回退 Coding Agent 修复 |
| `fail` | ≥3 | `review.fail.hard` | 任务进入 failed 终态 |

约束：

- 高风险（`severity=high`）问题至少一项，即触发 `retry`
- 3 次以上重试仍存在高风险问题，Review Agent 可裁定 `fail.hard`
- Review Agent 保留最终裁定权——Codex 的 `decision` 为建议，非最终判决

## 8. 支持操作集

### 8.1 允许操作

Codex Skill 在 `$WORKSPACE_ROOT` 内**允许**执行：

| 模式 | 操作 | 说明 |
|------|------|------|
| review | `read_files` | 读取变更文件内容 |
| review | `analyze_diff` | 解析 Diff 变更 |
| review | `evaluate_policy` | 对照策略规则评审 |
| review | `generate_report` | 产出结构化评审报告 |
| auto_edit | `file_create` | 创建新文件 |
| auto_edit | `file_update` | 修改已有文件 |

### 8.2 禁止操作

Codex Skill **绝对禁止**（Review 模式额外约束）：

| 禁止操作 | 说明 | 适用模式 |
|----------|------|----------|
| `cross_workspace_access` | 访问 `$WORKSPACE_ROOT` 外的路径 | all |
| `modify_files` | 修改源文件（Review 模式下不可写） | review |
| `modify_ownership` | 修改文件所有权配置 | all |
| `modify_global_state` | 篡改全局调度状态 | all |
| `network_request` | 发起网络请求 | all |
| `access_replay_db` | 访问任务回放数据库 | all |
| `access_metrics_db` | 访问系统指标数据库 | all |
| `modify_rules` | 修改规则配置 | all |

**特别约束**：Review 模式下，Codex 仅具备只读权限——可读取变更文件和策略规则，但**禁止**对源文件做任何修改。

## 9. 错误处理

### 9.1 错误分类映射

| 场景 | error_code | retryable |
|------|-----------|-----------|
| Codex API 调用失败 / 模型返回异常 | `MODEL_ERROR` | 是 |
| 子进程执行超过 timeout_seconds | `TIMEOUT_ERROR` | 是 |
| Codex CLI 进程无法启动或异常退出 | `PROCESS_ERROR` | 视情况 |
| Review 输出 JSON 解析失败 / schema 不满足 | `VALIDATION_ERROR` | 否 |
| Review 模式下尝试写文件 | `PERMISSION_ERROR` | 否 |
| 输出无有效 decision 字段 | `VALIDATION_ERROR` | 否 |

### 9.2 Review 输出校验

Review Agent 在收到 Codex 输出后，必须校验：

1. `decision` 字段存在且为 `"pass"` 或 `"fail"`
2. `score.value` 为 0-100 范围的数字
3. `issues[]` 中每项的 `severity`、`type`、`message` 非空
4. 若 `decision=fail`，`issues[]` 必须至少包含一项

校验失败统一返回 `VALIDATION_ERROR`，不触发重试。

## 10. 超时与资源限制

```yaml
codex:
  timeout:
    max_seconds: 180
    grace_period_seconds: 5

  retry:
    max_attempts: 3
    backoff: exponential
    retryable_errors:
      - MODEL_ERROR
      - TIMEOUT_ERROR

  resource_limits:
    max_memory_mb: 2048
    max_cpu_cores: 2
```

## 11. 审计日志

每次 Codex Skill 调用后，Skill Runtime 必须归档：

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "codex",
  "timestamp": "string",
  "mode": "review|auto_edit",
  "input_changes_count": 0,
  "output_decision": "pass|fail|null",
  "output_issues_count": 0,
  "output_score": 0,
  "exit_code": 0,
  "latency_ms": 0,
  "token_usage": 0,
  "error_code": null
}
```

审计日志进入 Replay 存档。

## 12. 最小集成示例

### 12.1 Review 模式输入

```json
{
  "trace_id": "trace-002",
  "task_id": "task-001",
  "skill_name": "codex",
  "version": "1.0.0",
  "invoker": { "type": "review_agent", "id": "agent-review-01" },
  "payload": {
    "mode": "review",
    "task": { "id": "task-001" },
    "changes": [
      {
        "path": "src/api/auth.py",
        "action": "create",
        "diff": "+ def login(username, password):\n+     query = f\"SELECT * FROM users WHERE name='{username}' AND pass='{password}'\"\n+     ..."
      }
    ],
    "review_focus": {
      "dimensions": ["security", "logic", "style", "performance"]
    }
  },
  "constraints": { "timeout_seconds": 180, "max_retries": 3 }
}
```

### 12.2 CLI 调用

```bash
cd /path/to/workspace/task_001 && \
codex "Review this diff:
...
Please analyze: 1. Security 2. Logic 3. Style 4. Performance
Output structured JSON with decision, issues, score."
```

### 12.3 Review 模式输出

```json
{
  "trace_id": "trace-002",
  "task_id": "task-001",
  "skill_name": "codex",
  "version": "1.0.0",
  "status": "success",
  "payload": {
    "decision": "fail",
    "score": { "value": 35, "max": 100 },
    "issues": [
      {
        "id": "iss-001",
        "severity": "high",
        "type": "security",
        "message": "SQL injection vulnerability: user input directly interpolated in query string",
        "paths": ["src/api/auth.py"],
        "line_range": { "start": 2, "end": 2 },
        "suggestion": "Use parameterized queries with placeholders instead of string formatting"
      },
      {
        "id": "iss-002",
        "severity": "medium",
        "type": "security",
        "message": "Password appears to be stored/comparison in plaintext",
        "paths": ["src/api/auth.py"],
        "line_range": { "start": 2, "end": 2 },
        "suggestion": "Hash passwords with bcrypt before storage and comparison"
      },
      {
        "id": "iss-003",
        "severity": "low",
        "type": "style",
        "message": "Missing docstring for login function",
        "paths": ["src/api/auth.py"],
        "line_range": { "start": 1, "end": 1 },
        "suggestion": "Add a docstring describing parameters and return value"
      }
    ],
    "summary": {
      "total_issues": 3,
      "high_severity_count": 1,
      "medium_severity_count": 1,
      "low_severity_count": 1,
      "dimension_breakdown": {
        "security": 2,
        "logic": 0,
        "style": 1,
        "performance": 0,
        "other": 0
      }
    },
    "suggestions": [
      "Switch to parameterized queries to prevent SQL injection",
      "Implement bcrypt-based password hashing",
      "Add function-level docstrings"
    ]
  },
  "error": null,
  "metrics": {
    "latency_ms": 4200,
    "token_usage": 2400,
    "retry_count": 0,
    "exit_code": 0
  }
}
```

### 12.4 Review Agent 后续决策

根据输出结果：
- `decision=fail`、`high_severity_count=1`
- Review Agent 决策：`review.fail.retry`
- Orchestrator 回退 Coding Agent，附带 Codex 输出的 issues 作为修复指引

## 13. 版本演进规则

| 变更类型 | 版本 | 示例 |
|----------|------|------|
| CLI 参数格式改变、输出字段删除 | Major | `2.0.0`：output schema breaking change |
| 新增可选输出字段、新增评审维度 | Minor | `1.1.0`：新增 `best_practice` 评审维度 |
| Prompt 模板优化、内部实现改进 | Patch | `1.0.1`：优化评审指令模板 |

## 14. 与 Claude Code Skill 的分工边界

| 维度 | Claude Code Skill | Codex Skill |
|------|-------------------|-------------|
| 调用方 | Coding Agent | Review Agent（主）/ Coding Agent（备选） |
| 主要职责 | 代码生成、文件修改、测试执行 | 代码评审、Diff 分析、评审报告 |
| 工作区权限 | 读写 | Review 模式只读 / Auto-edit 模式读写 |
| 输出物 | diff + 测试结果 + 自检 | decision + issues + score |
| 下游消费方 | Review Agent | Artifact Agent（经 Review Agent 裁定） |

## 15. 参考

- [External Agent Contract](../contracts/external-agent-contract.md)
- [ADR-023 外部编码智能体接入方案](../ADR/ADR-023-外部编码智能体接入方案.md)
- [ADR-014 异常错误分类规范](../ADR/ADR-014-error-taxonomy.md)
- [ADR-015 Skill 接口与版本管理](../ADR/ADR-015-skill-interface-versioning.md)
- [ADR-016 工具权限边界](../ADR/ADR-016-tool-permission-boundary.md)
- [Skill Contract Spec](../contracts/skill-contract-spec.md)
- [Agent Spec](../contracts/agent-spec.md)
