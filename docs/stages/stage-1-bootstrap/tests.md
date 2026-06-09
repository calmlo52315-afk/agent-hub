# 测试与验证（比赛提交）

本页用于比赛提交：列出可执行命令、验证目标与关键断言点，证明 runtime “能跑/不崩/不冲突/能产出 artifact”。

## 1. 规则加载校验

目标：证明运行时能加载你提供的四类 policy，并输出 policy_id 便于现场展示。

```bash
python3 -m runtime.harness.validator.validate_rules
```

预期输出示例：

```json
{
  "execution": "...",
  "permission": "...",
  "ownership": "...",
  "communication": "..."
}
```

## 2. Demo 闭环（E2E 最小链路）

目标：跑通一条 task 的最小 workflow，并生成 artifact。

```bash
python3 -m runtime.demo
```

验证点：

- 输出包含 `coding/review/artifact` 三段结构化结果
- artifact 段返回 `artifact_dir` 与 `created_files` 列表
- `artifacts/<task_id>/metadata.json` 存在
- `artifacts/<task_id>/workspace/<path>` 快照文件存在

## 3. Smoke Test（自动化成功标志）

目标：将比赛成功标志固化为可重复执行的自动化用例。

```bash
python3 -m runtime.smoke_test
```

断言点（见 `runtime/smoke_test.py`）：

- “能跑一个 task”：`Orchestrator.run_demo_task()` 返回 `task_id/trace_id/messages`
- “不冲突”：断言 coding 输入 target 的 `base_hash == 运行前文件 hash`
- “能输出 artifact”：断言 `metadata.json` 与 workspace snapshot 文件存在且内容包含关键字符串
- “不崩”：测试用例执行无未捕获异常（失败时应为可诊断错误返回/抛出）

