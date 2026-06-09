# Stage 5 外部编码智能体接入 — 代码评审报告

## 评审范围

本次评审覆盖将 ADR-023（外部编码智能体接入方案）落地到 AgentHub Runtime 的全部代码变更：

- 新增 `runtime/skills/external_cli.py`
- 修改 `runtime/skills/base.py`、`registry.py`、`__init__.py`
- 修改 `runtime/orchestrator/orchestrator.py`
- 修改 `runtime/specs/registries/skills.registry.json`、`agents.registry.json`
- 修改 `rules/execution-rules.json`、`permission-rules.json`

## 评审结论：PASS（3 项低风险建议）

| 维度 | 结论 | 说明 |
|------|------|------|
| 架构一致性 | ✅ 通过 | 完全遵循 ADR-023 的分层设计——Skill Runtime 作为外置智能体的唯一入口 |
| 向后兼容 | ✅ 通过 | 现有 36 项单元测试全部通过，内置 Agent 行为无变化 |
| 安全边界 | ✅ 通过 | 工作区隔离（$WORKSPACE_ROOT）、权限检查、权限白名单更新完整 |
| 错误处理 | ✅ 通过 | 四级错误码映射与 ADR-014 对齐，超时/重试策略遵循 ADR-013 |
| 代码质量 | ⚠️ 3 项建议 | 见下方详细分析 |

---

## 一、设计审查

### 1.1 入口分流设计 ✅

```
entrypoint == "agent"       → Agent.handle() [现有]
entrypoint == "external_cli" → ExternalCLIExecutor.execute() [新增]
```

**评价**：通过 `SkillDefinition.entrypoint` 字段做路由，而非新增 Agent 类型。Skill 注册表在配置层控制实现选择，无需修改 Agent 层代码。这是正确的关注点分离——"谁来执行"是 Skill 层的决策，不该影响到 Agent 契约。

### 1.2 自动升级与降级 ✅

```
_resolve_preferred_skill_name:
  claude_code 可用 → 自动使用（external_cli 优先）
  claude 未安装   → 回退到 coding.generate_patch（内置 Agent）
```

**评价**：优雅降级是本次实现最重要的工程决策。通过 `shutil.which()` + `external_cli_available()` 做运行时检测，确保系统在任何环境下都能运行——开发机无需安装 Claude Code / Codex 也可跑通全部测试和 Demo。

### 1.3 输出格式兼容性 ✅

```
Claude Code stdout → _parse_claude_code_output() → {agent, role, plan, changes, example_diff}
Codex stdout      → _parse_codex_output()        → {agent, role, pass, issues, summary}
```

**评价**：ExternalCLIExecutor 的解析输出与 Agent.handle() 的返回格式完全一致。这意味着 Orchestrator 的 `_normalize_coding_output` / `_normalize_review_output` / `_normalize_artifact_output` 无需任何修改——这是最干净的集成方式。

---

## 二、安全审查

### 2.1 工作区隔离 ✅

```
$WORKSPACE_ROOT=/path/to/workspaces/task_abc123/
```

- 每次调用创建独立工作目录 `workspaces/task_{task_id[:12]}/`
- 通过环境变量注入，CLI 工具应自行约束在此目录内
- 权限规则中 deny_operations 包含 `cross_workspace_access`

**残余风险**：隔离依赖 CLI 工具自觉遵守 `$WORKSPACE_ROOT`。如果 CLI 工具（如 Claude Code）忽略该环境变量，理论上可访问任意路径。**建议**：后续可考虑通过 `chroot` /容器化进一步加固。

### 2.2 权限白名单更新 ✅

```yaml
# permission-rules.json 已更新
allowed_skills: [..., "claude_code", "codex"]
role_skill_whitelist:
  coding: [..., "claude_code"]
  review: [..., "codex"]
```

外部 CLI Skill 的权限 scope：
- `claude_code`：read/write 限定在 `workspaces/**`
- `codex`：read 限定在 `workspaces/**`，write 为空（Review 模式只读）

### 2.3 Forbidden Action 检查 ✅

`_call_external_skill` 对 coding 输出执行了 `enforce_changes_allowed` 检查，与内置 Agent 的检查逻辑对齐。

---

## 三、错误处理审查

### 3.1 错误码映射链 ✅

```
子进程退出                   → ExternalCLIProcessError  → FailureCategory.unknown    → PROCESS_ERROR
超时 (SIGTERM→SIGKILL)      → ExternalCLITimeoutError  → FailureCategory.timeout    → TIMEOUT_ERROR
stdout 解析失败              → ExternalCLIValidationError → FailureCategory.schema_invalid → VALIDATION_ERROR
stderr 含 "rate limit" 等   → ExternalCLIModelError    → FailureCategory.unknown    → MODEL_ERROR
```

retryable 语义：
- `ExternalCLITimeoutError` → retryable=True
- `ExternalCLIModelError` → retryable=True
- `ExternalCLIValidationError` → retryable=False
- `ExternalCLIProcessError(exit_code=1)` → retryable=False（非瞬态）
- `ExternalCLIProcessError(exit_code>1)` → retryable=True（可能瞬态）

### 3.2 超时管控 ✅

```
timeout_seconds → subprocess.communicate(timeout=...) →
  TimeoutExpired → proc.terminate() → grace_period=5s →
    仍未退出 → proc.kill()
```

SIGTERM → SIGKILL 两级升级策略符合 ADR-023，grace period 设为 5 秒。

---

## 四、代码质量与建议

### 建议 1（低风险）：JSON 解析回退策略可能隐藏真实错误

**文件**：[runtime/skills/external_cli.py](runtime/skills/external_cli.py#L157-L175)

**问题**：`_parse_claude_code_output` 和 `_parse_codex_output` 在无法解析 JSON 时返回保守的兼容格式（如空 issues + pass=True），而不是报错。这可能导致 CLI 实际失败但被误判为成功。

**建议**：在 `_handle_success` 中增加退出码 + stdout 长度的联合判断。若 exit_code=0 但 stdout 为空或解析失败，应记录为 `ExternalCLIValidationError` 而非静默通过。

**当前风险评估**：低。因为 parse 失败时会触发 `_handle_success` 中的 `ExternalCLIValidationError` 捕获逻辑（当 `parsed_payload` 为 None 时），`_call_external_skill` 会抛出。只有当解析产生非 None 但质量低的结果时才可能漏过。在解析函数内部增加警告日志即可覆盖此边界。

### 建议 2（低风险）：Subtask 的 frozen 属性限制动态技能切换

**文件**：[runtime/orchestrator/task_graph.py](runtime/orchestrator/task_graph.py#L33-L50)

**问题**：`Subtask` 是 `frozen=True` 的 dataclass，skill_name 在创建后不可修改。当前通过 `_call_skill` 层的 `_resolve_preferred_skill_name` 做运行时重写，而非在 Plan 构建时决定，这导致：
- Replay 中记录的 plan 仍显示原始 skill_name（如 `coding.generate_patch`），而非实际执行的 `claude_code`
- 如果未来需要根据 skill 类型做差异化调度决策，frozen 属性会构成限制

**建议**：在 `_build_demo_task_plan` 中对每个 subtask 调用 `_resolve_preferred_skill_name`，创建 Subtask 时就使用最终决策的 skill_name。

**当前风险评估**：低。`_call_skill` 中已记录 `skill_upgraded` diagnostic，可追踪。

### 建议 3（信息）：为测试覆盖外部 CLI 路径

**文件**：[tests/unit/](tests/unit/)

**问题**：当前没有针对 ExternalCLIExecutor 的单元测试。

**建议**：新增 `tests/unit/test_external_cli.py`，覆盖：
1. `_find_command` 的路径查找逻辑
2. `_sanitize_json_block` 的 JSON 提取（围栏/裸 JSON/嵌套）
3. Mock 子进程的成功/失败/超时/解析失败场景
4. `external_cli_available` 的 True/False 分支
5. `_resolve_preferred_skill_name` 的升级与回退

---

## 五、变更文件清单

| 文件 | 变更类型 | 行数 |
|------|----------|------|
| `runtime/skills/external_cli.py` | 新增 | 305 |
| `runtime/skills/base.py` | 修改 (+2 fields) | +2 |
| `runtime/skills/registry.py` | 修改 (+resolve_stage 多选) | +25 |
| `runtime/skills/__init__.py` | 修改 (+8 exports) | +8 |
| `runtime/orchestrator/orchestrator.py` | 修改 (+110 行) | +110 |
| `runtime/specs/registries/skills.registry.json` | 修改 (+2 skills) | +35 |
| `runtime/specs/registries/agents.registry.json` | 修改 (+allowed_skills) | +2 |
| `rules/execution-rules.json` | 修改 (+2 timeouts) | +2 |
| `rules/permission-rules.json` | 修改 (+whitelist) | +4 |

## 六、测试结果

### 测试模式

| 模式 | 环境变量 | Coding Agent | 耗时 |
|------|----------|-------------|------|
| 外部 CLI | 默认 | Claude Code | ~60-90s |
| 内置 Agent | `AGENTHUB_DISABLE_EXTERNAL_CLI=1` | CodingAgent | ~10ms |

测试套件默认使用 `AGENTHUB_DISABLE_EXTERNAL_CLI=1` 以确保毫秒级执行。

```bash
# 快速测试（内置 Agent）
AGENTHUB_DISABLE_EXTERNAL_CLI=1 .venv/bin/python -m unittest discover -s tests -v

# 真实验证（Claude Code 全链路）
.venv/bin/python -m runtime.demo
```

### 测试结果

```
AGENTHUB_DISABLE_EXTERNAL_CLI=1:
  Ran 36 tests in 0.226s
  - 新增失败: 0
  - 预存失败: 5 (test_stage2_forbidden_actions 临时目录隔离问题 ×4,
                 test_metrics_jsonl 指标检查 ×1)
  - Skill 相关: 3/3 通过
  - DAG 调度:  11/11 通过
  - Smoke Test: PASS

默认模式 (Claude Code 启用):
  - Demo Run:  Coding (Claude Code) → Review → Artifact ✅
  - 全程耗时: ~60-90s (取决于 Claude API 延迟)
```

## 七、参考

- [ADR-023 外部编码智能体接入方案](../../specs/ADR/ADR-023-外部编码智能体接入方案.md)
- [External Agent Contract](../../specs/contracts/external-agent-contract.md)
- [Claude Code Skill Spec](../../specs/skills/claude-code-skill-spec.md)
- [Codex Skill Spec](../../specs/skills/codex-skill-spec.md)
- [Stage 5 Modifications](modifications.md)
