# 测试与验证（Stage 6）

本页用于 Stage 6 开发期：把“文档目标”和“当前可运行链路”拆开验证，避免误把 demo runtime 当成真实 agent runtime。

## 1. 最小闭环回归

目标：证明当前 runtime 仍可执行一条最小任务链，并产出 artifact。

```bash
python3 -m runtime.smoke_test
```

验证点：

- `Orchestrator.run_demo_task()` 不崩溃
- 输出包含 `task_id`、`trace_id`
- artifact 目录存在
- `metadata.json` 与 workspace snapshot 存在

## 2. Stage 6 比赛案例回归

目标：用 3 个比赛案例 prompt 验证当前 runtime 至少能稳定跑通“提交任务 -> 编排 -> review -> artifact”流程。

```bash
AGENTHUB_DISABLE_EXTERNAL_CLI=1 python3 -m runtime.stage6_demo_cases
```

可选输出报告：

```bash
AGENTHUB_DISABLE_EXTERNAL_CLI=1 python3 -m runtime.stage6_demo_cases --output artifacts/stage6-demo-cases/report.json
```

验证点：

- 每个案例都返回 `ok=true`
- 每个案例都返回 `artifact_dir`
- 每个案例都至少生成 `metadata.json`
- 运行报告中能看到 `task_id`、`trace_id`、诊断事件类型

## 3. Stage 6 自动化测试

目标：把比赛案例固化为自动化测试，避免开发过程中回归。

```bash
AGENTHUB_DISABLE_EXTERNAL_CLI=1 python3 -m unittest tests.unit.test_stage6_demo_cases
```

验证点：

- 三个案例均可运行
- 每个案例都生成 artifact
- artifact metadata 中的 `task_id` 与运行结果一致

## 4. 当前边界说明

本页验证的是“当前流程可跑通”，不是“当前已经具备真实语义生成能力”。

当前限制：

- prompt 会进入现有 demo runtime
- 文件产出仍偏向 demo 内容
- `Go Gin API / React Todo / 修改已有代码新增接口` 这三个案例，当前主要用于验证流程与后续替换真实 agent 的回归基线
