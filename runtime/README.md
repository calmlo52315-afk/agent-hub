# /runtime

本目录用于存放可执行的最小运行时实现，按职责划分为 Agent、Orchestrator、Harness（运行控制层）、Config（规则/契约加载）、Skills 等模块。

## 入口文件

- `runtime/demo.py`：最小 demo（coding -> review -> artifact）
- `runtime/smoke_test.py`：最小回归（成功标志检查）
- `runtime/stage6_demo_cases.py`：Stage 6 比赛案例回归
- `runtime/server.py`：Runtime 内部 FastAPI 服务入口（供 Go Gateway 调用）

## 如何验证

在仓库根目录运行：

```bash
python3 -m runtime.harness.validator.validate_rules
```

运行 demo：

```bash
python3 -m runtime.demo
```

运行 smoke test：

```bash
python3 -m runtime.smoke_test
```

运行 Stage 6 比赛案例：

```bash
AGENTHUB_DISABLE_EXTERNAL_CLI=1 python3 -m runtime.stage6_demo_cases
```

启动 Runtime 内部服务：

```bash
python3 -m venv .venv
./.venv/bin/pip install -r runtime/requirements.txt
RUNTIME_INTERNAL_TOKEN=runtime-internal-token ./.venv/bin/python -m runtime.server
```

## Runtime Internal API

- `POST /internal/v1/tasks`：提交异步运行任务
- `GET /internal/v1/tasks/{task_id}`：查询异步任务状态与结果
- `DELETE /internal/v1/tasks/{task_id}`：发起 best-effort 取消
- `GET /healthz`：健康检查

Gateway 当前通过“提交任务 + 轮询状态”的方式对接 Runtime。
