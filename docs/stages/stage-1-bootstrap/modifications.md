# 关键改动记录（比赛提交）

本页用于比赛提交：沉淀“根据规则落地运行时”的关键改动点，突出工程化可追踪。

## 1. Runtime 最小闭环落地

- Orchestrator 串行推进 workflow：coding -> review -> artifact
- 三个核心 Agent 输出结构化 payload（便于 Harness 校验与留痕）
- Artifact 归档：输出 `artifacts/<task_id>/metadata.json` 与 workspace snapshot

## 2. 冲突控制（不冲突）

- 引入同文件写锁/串行化：避免多方并行写入同一文件
- 引入 base_hash 版本基线检查：避免旧上下文覆盖新版本

## 3. 目录职责重构（对齐逻辑结构）

为对齐你定义的逻辑目录，将 runtime 按职责拆分：

- `runtime/config/`：rules/spec 加载
- `runtime/harness/`：权限、ownership、workspace、validator（并预留 retry/metrics/replay/cost）
- `runtime/orchestrator/`：调度与路由
- `runtime/agents/`：agent 实现
- `runtime/skills/`：skill 包预留

## 4. 入口收敛（删除旧文件）

为避免“同一能力多入口、多路径引用”导致比赛现场混乱：

- 删除旧 shim 模块（原先位于 runtime 根目录的转发文件）
- 统一从新目录 import，并保持 `python -m runtime.demo` / `python -m runtime.smoke_test` 可运行
- 将 rules 校验入口统一为：`python3 -m runtime.harness.validator.validate_rules`

