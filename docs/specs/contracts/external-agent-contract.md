# External Agent Contract

## 1. 目标

定义外置编码智能体（External Coding Agent）接入 AgentHub 的统一契约规范，使 Claude Code、Codex 等第三方编码 CLI 工具能够作为**标准化可调度能力单元（Skill）**接入系统，而非作为系统内置智能体。

本 Spec 是面向人类阅读的契约说明；后续如需机器校验，应在 `runtime/specs/` 落对应 schema。

## 2. 术语

| 术语 | 定义 |
|------|------|
| External Coding Agent | 以独立进程方式运行、通过 CLI 接口调用的第三方编码工具（如 Claude Code、Codex） |
| Skill Runtime | AgentHub 的能力运行时层，负责拉起、管控、回收外部智能体进程 |
| Workspace | 按任务隔离的工作目录，外部智能体的文件操作仅允许在分配的工作区内进行 |
| Agent Binding | 系统内置智能体（Coding Agent / Review Agent）与外部能力实例的绑定映射关系 |

## 3. 设计原则

- 外置编码智能体**不作为系统内置 Agent**，而是作为 Skill 接入，统一由 Orchestrator 通过 Skill Runtime 调度
- 外部智能体以**子进程方式拉起**，不与 AgentHub 主进程共享内存空间
- 每次能力调用分配**独立隔离工作区**，避免跨任务文件访问
- 所有调用必须遵循统一的超时、重试、错误分类规范
- 外部智能体**不得直接修改**智能体运行状态、任务运行状态、全局配置

## 4. 架构定位

```
用户
 │
 ▼
网关层 (Gateway)
 │
 ▼
调度中心 (Orchestrator)
 │
 ▼
能力运行时 (Skill Runtime)
 │
 ├───────────────┐
 │               │
 ▼               ▼
ClaudeCode能力实例  Codex能力实例
 │               │
 ▼               ▼
Claude命令行工具   Codex命令行工具
 │               │
 ▼               ▼
隔离工作区 (Workspace)
```

外置编码智能体处于架构最底层，仅接收 Skill Runtime 的调用指令并在隔离工作区内执行操作，不向上层暴露内部实现细节。

## 5. 进程调用规范

### 5.1 通用调用模型

Skill Runtime 通过**子进程方式**调用外部智能体 CLI，模型如下：

```json
{
  "invocation": {
    "skill_name": "string",
    "command": "string",
    "args": ["string"],
    "cwd": "string",
    "env": {},
    "timeout_seconds": 180
  }
}
```

字段说明：

- `skill_name`：对应 Skill Registry 中的唯一能力名
- `command`：外部智能体的 CLI 入口命令（如 `claude`、`codex`）
- `args`：传递给 CLI 的参数列表
- `cwd`：分配给本次调用的工作区绝对路径
- `env`：注入到子进程的环境变量（如 `WORKSPACE_ROOT`、`TASK_ID`）
- `timeout_seconds`：子进程最大存活时间

### 5.2 进程生命周期

```
skill_runtime.launch()
    │
    ├─ spawn subprocess
    │     │
    │     ├─ stdout/stderr stream → log capture
    │     │
    │     └─ on_exit(code, signal) → result classification
    │
    └─ return SkillResult
```

约束：

- 子进程 exit code = 0 视为成功
- 子进程 exit code ≠ 0 视为执行失败，需结合 stderr 归类错误码
- 超时后 Skill Runtime 发送 SIGTERM，等待 5s 后若未退出则发送 SIGKILL
- 子进程退出后，Skill Runtime 负责清理临时资源并归档日志

## 6. 工作区隔离约束

### 6.1 目录分配规则

每次能力调用分配独立隔离工作目录：

```
workspace/
 ├─ task_001/
 ├─ task_002/
 └─ task_003/
```

### 6.2 强制约束

外部智能体**仅允许**在被分配的 `cwd` 目录内进行文件操作，**禁止**：

- 跨任务目录访问文件
- 访问 `cwd` 父级目录之外的任意路径
- 创建指向 `cwd` 外部的符号链接

### 6.3 环境变量注入

Skill Runtime 向子进程注入以下环境变量以确保隔离：

```bash
WORKSPACE_ROOT=/path/to/workspace/task_001
TASK_ID=task_001
SKILL_NAME=claude_code
TRACE_ID=xxxx-xxxx
```

外部智能体实现必须通过 `WORKSPACE_ROOT` 确定自身操作边界。

## 7. 通用输入 Envelope

所有外部智能体 Skill 调用统一使用如下输入结构：

```json
{
  "trace_id": "string",
  "task_id": "string",
  "skill_name": "string",
  "version": "string",
  "invoker": {
    "type": "coding_agent|review_agent",
    "id": "string"
  },
  "payload": {
    "instruction": "string",
    "targets": [
      {
        "path": "string",
        "action": "create|update|delete|review"
      }
    ],
    "context": {
      "repo_root": "string",
      "pinned": ["string"],
      "recent_messages": ["string"]
    }
  },
  "constraints": {
    "timeout_seconds": 180,
    "max_retries": 3
  }
}
```

说明：

- `invoker.type` 标明调用来源为 `coding_agent` 或 `review_agent`
- `payload.instruction` 为自然语言指令，由上层智能体拼装
- `payload.targets` 为本次调用涉及的文件路径与预期操作
- `constraints` 承接超时与重试配置

## 8. 通用输出 Envelope

所有外部智能体 Skill 执行结果统一为如下结构：

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
    "retry_count": 0,
    "exit_code": 0
  }
}
```

约束：

- `status=success` 时，`payload` 必须满足对应 Skill 的输出 schema
- `status=failed` 时，`error` 必须非空且包含稳定错误码
- `metrics` 需包含本次调用的退出码与 token 消耗（若 CLI 工具支持返回）

## 9. 安全约束规则

### 9.1 强制禁止行为

外置编码智能体**绝对禁止**：

- 访问任务回放数据库（Replay DB）
- 访问系统指标数据库（Metrics DB）
- 修改资源所有权规则（Ownership Rules）
- 修改运行时全局配置
- 绕过 AgentHub 直接发起网络请求
- 在分配的工作区之外创建或修改任何文件

### 9.2 强制遵守规则

外置编码智能体**必须**：

- 限定在所属工作目录（`$WORKSPACE_ROOT`）内操作
- 遵从目录所有权管控规则
- 遵从全局文件锁调度约束
- 遵从调用超时时间限制
- 将全部 stdout/stderr 输出至标准流以供 Skill Runtime 捕获

## 10. 错误分类体系

所有外部智能体调用异常统一归类为四类错误码，与 ADR-014 对齐：

| 错误码 | 类别 | 含义 | 可重试 |
|--------|------|------|--------|
| `MODEL_ERROR` | 模型侧异常 | Provider、模型调用、推理服务异常 | 是 |
| `TIMEOUT_ERROR` | 调用超时异常 | 子进程执行超过 timeout_seconds | 是 |
| `PROCESS_ERROR` | 进程启动/运行异常 | 子进程无法启动、异常崩溃、非零退出 | 视情况 |
| `VALIDATION_ERROR` | 返回结果校验失败 | 输出不满足约定的 schema | 否 |

Error 结构：

```json
{
  "category": "timeout|model|process|validation",
  "error_code": "MODEL_ERROR|TIMEOUT_ERROR|PROCESS_ERROR|VALIDATION_ERROR",
  "message": "string",
  "retryable": true,
  "details": {
    "exit_code": -1,
    "signal": null,
    "stderr_tail": "string"
  }
}
```

## 11. 超时与重试策略

由 Skill Runtime 统一管控：

```yaml
timeout:
  max_seconds: 180

retry:
  max_attempts: 3
  backoff: exponential
  retryable_errors:
    - MODEL_ERROR
    - TIMEOUT_ERROR
```

约束：

- 重试仅对 `retryable=true` 的错误码生效
- 重试采用指数退避策略，避免瞬时过载
- 3 次重试全部失败后，任务进入 `failed` 终态

## 12. 能力注册配置规范

### 12.1 Skill 注册格式

```yaml
skills:
  claude_code:
    enabled: true
    command: claude
    timeout_seconds: 180
    version: "1.0.0"
    entrypoint: external_cli
    permission_scope:
      read_paths: ["${WORKSPACE_ROOT}/**"]
      write_paths: ["${WORKSPACE_ROOT}/**"]
      deny_operations:
        - network
        - modify_rules
        - access_replay_db
        - access_metrics_db

  codex:
    enabled: true
    command: codex
    timeout_seconds: 180
    version: "1.0.0"
    entrypoint: external_cli
    permission_scope:
      read_paths: ["${WORKSPACE_ROOT}/**"]
      write_paths: ["${WORKSPACE_ROOT}/**"]
      deny_operations:
        - network
        - modify_rules
        - access_replay_db
        - access_metrics_db
```

### 12.2 智能体与能力绑定

```yaml
agent_bindings:
  coding_agent:
    skills:
      - claude_code

  review_agent:
    skills:
      - codex
```

上层智能体（Coding Agent、Review Agent）通过此绑定配置确定应调用的外部能力实例，实现**业务逻辑与厂商模型解耦**。

## 13. 架构演进路径

### 13.1 当前落地形态（单机子进程）

```
AgentHub
    ↓
系统子进程调用
    ↓
Claude Code / Codex CLI
```

### 13.2 未来演进形态（分布式）

```
AgentHub
    ↓
能力运行时 (Skill Runtime)
    ↓
远端工作节点资源池
    ↓
Claude远端工作实例
    ↓
Codex远端工作实例
```

架构升级仅需修改 Skill Runtime 的进程拉起实现（本地子进程 → 远端节点调度），**上层业务代码无需改动**。

## 14. 合规检查清单

接入新的外置编码智能体前，必须逐项确认：

- [ ] CLI 命令可通过子进程方式调用
- [ ] 支持从标准输入或命令行参数接收指令
- [ ] 退出码语义明确（0 = 成功，非0 = 失败）
- [ ] 文件操作可限定在 `$WORKSPACE_ROOT` 内
- [ ] 支持超时终止（响应 SIGTERM）
- [ ] stdout/stderr 可被外部捕获归档
- [ ] 单个实例不依赖持久化状态（无状态/自包含）
- [ ] 已注册 Skill 元数据并绑定到对应上层智能体

## 15. 参考

- [ADR-023 外部编码智能体接入方案](../ADR/ADR-023-外部编码智能体接入方案.md)
- [ADR-001 运行时整体架构](../ADR/ADR-001-runtime-architecture.md)
- [ADR-002 智能体权责划分](../ADR/ADR-002-agent-boundary.md)
- [ADR-003 资源所有权规则](../ADR/ADR-003-file-ownership.md)
- [ADR-011 消息通信协议](../ADR/ADR-011-message-protocol.md)
- [ADR-012 状态机设计](../ADR/ADR-012-task-state-machine.md)
- [ADR-013 重试策略规范](../ADR/ADR-013-retry-policy.md)
- [ADR-014 异常错误分类规范](../ADR/ADR-014-error-taxonomy.md)
- [ADR-015 Skill 接口与版本管理](../ADR/ADR-015-skill-interface-versioning.md)
- [ADR-016 工具权限边界](../ADR/ADR-016-tool-permission-boundary.md)
- [ADR-017 Skill 组合模型](../ADR/ADR-017-skill-composition-model.md)
- [Skill Contract Spec](skill-contract-spec.md)
- [Agent Spec](agent-spec.md)
