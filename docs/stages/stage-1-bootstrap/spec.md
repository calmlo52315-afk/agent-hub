# AgentHub Runtime Bootstrap（基于规则生成运行时模块）

<br />

## 1. 背景与目标

比赛目标不是堆功能，而是证明 AI-Coding 的工程化闭环可控、可验证、可追踪：

- 能跑一个 task（单进程最小闭环）
- 不崩（失败可诊断）
- 不冲突（同文件串行 + 版本基线检查）
- 能输出 artifact（可归档与可回放）

## 2. 输入产物（由你提供）

本变更默认以下内容由你提供/预置，本文件不把它们当作“本次创建的成果”，而是作为运行时生成依据：

### 2.1 运行时 Rules（机器执行）

运行时加载的可执行策略（JSON/YAML），用于约束 workflow、权限、文件 ownership 与通信：

- `/rules/index.json`：规则索引
- `/rules/execution-rules.json`
- `/rules/permission-rules.json`
- `/rules/ownership-rules.json`
- `/rules/communication-rules.json`

### 2.2 规则文档（给人读/用于答辩讲解）

解释规则分类、边界、示例与约束（不要求运行时直接加载）：

- `docs/specs/rules/**`

### 2.3 规范文档（给人读/用于答辩讲解）

用于讲清“Agent / Message / Context”契约口径（比赛展示用）：

- `docs/specs/contracts/agent-spec.md`
- `docs/specs/contracts/message-spec.md`
- `docs/specs/contracts/context-spec.md`

### 2.4 Prompt（提示词）与模板

用于生成/维护 Rules 的提示词与模板（比赛可展示“规则生成方法论”）：

- `docs/contextPack/rule_generate.md`（Rule System Designer 提示词）
- `docs/contextPack/rule_template.md`（规则文档模板）

## 3. 输出产物（本次落地的运行时）

### 3.1 Runtime 逻辑目录（按职责划分）

Runtime 代码按你定义的职责结构归位（不再使用扁平脚本堆叠）：

```
runtime/
  agents/            # Agent 实现（Skill 组合容器）
  orchestrator/      # 任务调度器（唯一路由）
  harness/           # Harness 运行控制层（校验/权限/锁/工作区）
    validator/
    retry/
    metrics/
    replay/
    cost/
  config/            # Rules/Spec 加载
  skills/            # Skill 模块（预留）
  demo.py            # 最小 demo 入口
  smoke_test.py      # 最小回归
  messages.py        # 统一消息结构（envelope）
```

### 3.2 “根据 rules 文件生成 runtime 模块”的映射关系

运行时不是“写死逻辑”，而是把规则拆成可加载的数据，再由模块执行：

- Rules 加载
  - `runtime/config/rules_loader.py`：读取 `/rules/index.json` 并加载四类 policy
- execution-rules（workflow/重试/超时）
  - MVP 以 orchestrator 串行驱动最小状态机为主，校验入口独立成 `runtime/harness/validator/validate_rules.py`
- permission-rules（读写删边界、artifact 写入范围）
  - `runtime/harness/permissions.py`：路径与动作校验
- ownership-rules（owner 映射、同文件串行、版本策略）
  - `runtime/harness/ownership.py`：锁/串行化
  - `runtime/harness/workspace.py`：base\_hash 版本检查 + 应用变更
- communication-rules（必须经 orchestrator、消息约束）
  - `runtime/messages.py`：消息 envelope 校验
  - `runtime/orchestrator/orchestrator.py`：强制路由、payload 大小上限等

## 4. 最小闭环工作流（demo task）

Demo 用于比赛演示“可跑通且可追踪”的最小闭环：

1. Orchestrator 创建 task\_id/trace\_id
2. 调用 Coding Agent 生成结构化变更（含 base\_hash）
3. Workspace 按 ownership/permission 规则应用变更（串行 + 版本检查）
4. 调用 Review Agent 输出 pass/fail 与问题列表
5. 调用 Artifact Agent 写入 artifact（metadata + workspace snapshot）

运行入口：

```bash
python3 -m runtime.demo
```

## 5. 验证、错误处理与改动记录

- 测试与验证：见 [tests.md](./tests.md)
- 错误与失败路径：见 [errors.md](./errors.md)
- 关键改动（重构/迁移/入口收敛）：见 [modifications.md](./modifications.md)

