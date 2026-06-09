# Claude Code Skill Spec

## 1. 目标

定义 Claude Code 作为 AgentHub 能力单元（Skill）的专属规范，包括 CLI 调用方式、输入输出契约、支持操作集、权限边界与错误处理语义。

Claude Code 作为**编码智能体（Coding Agent）的底层能力实现**，负责代码生成、文件修改、单元测试执行与已授权的 Shell 指令执行。

## 2. Skill 元数据

```json
{
  "skill_name": "claude_code",
  "version": "1.0.0",
  "description": "Claude Code CLI 编码能力——代码生成、文件修改、单元测试、Shell 执行",
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

在 AgentHub 的 Coding → Review → Artifact 主链路中，Claude Code Skill 由 **Coding Agent** 调用，承担：

```
Coding Agent（编排调度）
    │
    │ 子任务拆分 + Prompt 组装
    │
    ▼
ClaudeCodeSkill（能力执行）
    │
    │ claude -p "..."
    │
    ▼
隔离工作区（文件变更落盘）
```

约束：

- Claude Code Skill **不可**直接修改 Coding Agent 的运行状态
- Claude Code Skill **不可**直接变更任务运行状态
- 所有编排决策（重试、回退、分支）由上层 Coding Agent / Orchestrator 执行

## 4. CLI 调用规范

### 4.1 基础调用格式

```bash
claude -p "<instruction>"
```

其中 `-p`（print mode）以 SDK 风格传入指令，Claude Code 在非交互模式下执行并输出结果。

### 4.2 Skill Runtime 组装示例

```bash
cd /path/to/workspace/task_001 && \
claude -p "
Implement login API.

Requirements:
- POST /api/auth/login
- Accept { username, password }
- Return { token, expires_at }
- Validate input, hash password with bcrypt
- Write unit tests

Files to modify:
- src/api/auth.py (create)
- tests/test_auth.py (create)
" \
2>&1
```

### 4.3 环境变量

Skill Runtime 在拉起子进程前注入：

```bash
WORKSPACE_ROOT=/path/to/workspace/task_001
TASK_ID=task_001
SKILL_NAME=claude_code
TRACE_ID=xxxx-xxxx
CLAUDE_CODE_TIMEOUT=180
```

Claude Code 子进程应通过 `WORKSPACE_ROOT` 确定文件操作根目录。

## 5. 输入 Contract

### 5.1 `ClaudeCodeInput`

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "claude_code",
  "version": "1.0.0",
  "invoker": {
    "type": "coding_agent",
    "id": "string"
  },
  "payload": {
    "instruction": "string",
    "task": {
      "id": "string",
      "title": "string",
      "description": "string",
      "acceptance_criteria": ["string"]
    },
    "targets": [
      {
        "path": "string",
        "action": "create|update|delete",
        "description": "string"
      }
    ],
    "context": {
      "repo_root": "string",
      "pinned": ["string"],
      "recent_messages": ["string"],
      "artifacts": [
        {
          "id": "string",
          "type": "string",
          "summary": "string",
          "path": "string"
        }
      ]
    }
  },
  "constraints": {
    "timeout_seconds": 180,
    "max_retries": 3
  }
}
```

字段说明：

- `payload.instruction`：由 Coding Agent 拼装的完整自然语言指令，包含需求、目标文件、约束
- `payload.task`：当前任务的结构化描述
- `payload.targets`：预期变更的文件路径与操作类型
- `payload.context`：来自 Orchestrator 的上下文信息

### 5.2 Prompt 组装规则

Coding Agent 负责将 `ClaudeCodeInput.payload` 拼装为传给 `claude -p` 的自然语言 Prompt，拼装需包含：

1. 任务目标与验收标准
2. 目标文件路径与预期操作
3. 上下文信息（pinned 文件内容摘要）
4. 显式的输出格式要求（diff、变更文件列表、自检结果）

## 6. 输出 Contract

### 6.1 `ClaudeCodeOutput`

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "claude_code",
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
    "test_results": {
      "total": 0,
      "passed": 0,
      "failed": 0,
      "failures": [
        {
          "test_name": "string",
          "message": "string"
        }
      ]
    },
    "self_check": {
      "summary": "string",
      "risks": ["string"],
      "coverage_gaps": ["string"]
    },
    "shell_commands_executed": [
      {
        "command": "string",
        "exit_code": 0,
        "output_summary": "string"
      }
    ]
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

- `payload.changes`：实际产生的文件变更列表
- `payload.test_results`：单元测试执行汇总
- `payload.self_check`：Claude Code 自检摘要——风险点与覆盖盲区
- `payload.shell_commands_executed`：执行过的 Shell 命令审计记录
- `status=failed` 时，`error` 必须非空

## 7. 支持操作集

### 7.1 允许操作

Claude Code Skill 在 `$WORKSPACE_ROOT` 内**允许**执行：

| 操作 | 说明 | 示例 |
|------|------|------|
| `file_create` | 创建新文件 | `src/api/auth.py` |
| `file_update` | 修改已有文件 | `src/api/routes.py` |
| `file_delete` | 删除文件 | `src/deprecated.py` |
| `test_run` | 执行单元测试 | `pytest tests/` |
| `shell_exec` | 执行已授权 Shell 指令 | `pip install dep`, `git diff` |

### 7.2 禁止操作

Claude Code Skill **绝对禁止**：

| 禁止操作 | 说明 |
|----------|------|
| `cross_workspace_access` | 访问 `$WORKSPACE_ROOT` 外的任意路径 |
| `network_request` | 发起网络请求（下载外部依赖需由 AgentHub 预先准备） |
| `modify_rules` | 修改所有权规则、权限规则、执行规则 |
| `access_replay_db` | 访问任务回放数据库 |
| `access_metrics_db` | 访问系统指标数据库 |
| `modify_global_config` | 修改 AgentHub 运行时全局配置 |
| `modify_agent_state` | 修改智能体运行状态 |
| `modify_task_state` | 变更任务运行状态 |

## 8. 错误处理

### 8.1 错误分类映射

| 场景 | error_code | retryable |
|------|-----------|-----------|
| Claude API 调用失败 / 模型返回异常 | `MODEL_ERROR` | 是 |
| 子进程执行超过 timeout_seconds | `TIMEOUT_ERROR` | 是 |
| Claude CLI 进程无法启动或异常退出 | `PROCESS_ERROR` | 视 exit code |
| 输出 JSON 解析失败 / 结构不满足 schema | `VALIDATION_ERROR` | 否 |
| 操作越权（访问工作区外路径） | `PERMISSION_ERROR` | 否 |

### 8.2 stderr 解析规则

Skill Runtime 从子进程 stderr 中提取错误信息：

```
MODEL_ERROR    ← "Rate limit exceeded", "Model overloaded", "API error"
TIMEOUT_ERROR  ← "Operation timed out"、SIGTERM 触发
PROCESS_ERROR  ← spawn failure、非零退出且无上述特征
VALIDATION_ERROR ← Coding Agent 校验输出时发现结构不符
```

## 9. 超时与资源限制

```yaml
claude_code:
  timeout:
    max_seconds: 180
    grace_period_seconds: 5   # SIGTERM 后等待时间

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

## 10. 审计日志

每次 Claude Code Skill 调用后，Skill Runtime 必须归档以下审计信息：

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "claude_code",
  "timestamp": "string",
  "input_instruction_hash": "sha256",
  "changes_summary": ["path", "action"],
  "shell_commands": ["string"],
  "exit_code": 0,
  "latency_ms": 0,
  "token_usage": 0,
  "error_code": null
}
```

审计日志进入 Replay 存档，供回放与合规审查。

## 11. 最小集成示例

### 11.1 输入

```json
{
  "trace_id": "trace-001",
  "task_id": "task-001",
  "skill_name": "claude_code",
  "version": "1.0.0",
  "invoker": { "type": "coding_agent", "id": "agent-coding-01" },
  "payload": {
    "instruction": "Add a /health endpoint that returns { status: ok }",
    "targets": [
      { "path": "src/api/health.py", "action": "create" }
    ]
  },
  "constraints": { "timeout_seconds": 180, "max_retries": 3 }
}
```

### 11.2 CLI 调用

```bash
cd /path/to/workspace/task_001 && \
claude -p "
Add a /health endpoint that returns { status: ok }.

Create file: src/api/health.py
"
```

### 11.3 输出

```json
{
  "trace_id": "trace-001",
  "task_id": "task-001",
  "skill_name": "claude_code",
  "version": "1.0.0",
  "status": "success",
  "payload": {
    "changes": [
      {
        "path": "src/api/health.py",
        "action": "create",
        "diff": "+ from flask import Blueprint\n+ ...\n+ @health.route('/health')\n+ def health():\n+     return {'status': 'ok'}\n"
      }
    ],
    "test_results": { "total": 1, "passed": 1, "failed": 0, "failures": [] },
    "self_check": {
      "summary": "Simple health endpoint added. No risks identified.",
      "risks": [],
      "coverage_gaps": []
    },
    "shell_commands_executed": []
  },
  "error": null,
  "metrics": {
    "latency_ms": 8500,
    "token_usage": 1200,
    "retry_count": 0,
    "exit_code": 0
  }
}
```

## 12. 版本演进规则

| 变更类型 | 版本 | 示例 |
|----------|------|------|
| CLI 参数格式改变、输出字段删除 | Major | `2.0.0`：`-p` 改为 `--prompt` |
| 新增可选输出字段、扩展支持操作 | Minor | `1.1.0`：输出中新增 `token_cost` 字段 |
| Prompt 模板优化、内部实现改进 | Patch | `1.0.1`：优化指令拼装模板 |

## 13. 参考

- [External Agent Contract](../contracts/external-agent-contract.md)
- [ADR-023 外部编码智能体接入方案](../ADR/ADR-023-外部编码智能体接入方案.md)
- [ADR-015 Skill 接口与版本管理](../ADR/ADR-015-skill-interface-versioning.md)
- [ADR-016 工具权限边界](../ADR/ADR-016-tool-permission-boundary.md)
- [ADR-014 异常错误分类规范](../ADR/ADR-014-error-taxonomy.md)
- [Skill Contract Spec](../contracts/skill-contract-spec.md)
- [Agent Spec](../contracts/agent-spec.md)
