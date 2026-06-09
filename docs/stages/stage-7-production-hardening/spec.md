# 第七阶段 — 生产级加固与系统可靠性落地

## 阶段目标

将 AgentHub 从“真实可演示的 Agent Runtime 版本”继续升级为具备可靠性、可恢复、可观测能力的生产可用最小产品版本。

本阶段核心聚焦五大建设方向：

- 系统可靠性
- 故障容错能力
- 异常恢复能力
- 全链路可观测
- 任务执行一致性

本阶段的前提是：`Stage 6` 已经完成，系统已具备真实任务规划、真实代码生成、真实评审与真实产物展示能力。

**本阶段不新增全新业务能力，不继续补 Demo 缺失功能。**

---

## 验收达标标准

系统需全部满足以下能力：

- 可抵御模型瞬时突发故障
- 任务意外中断后支持断点恢复
- 杜绝重复执行问题
- 对外透出全链路运行指标
- 留存完整任务回放日志
- 支撑线上问题排查与故障复盘

---

## 工作项 1：完善全生命周期任务状态管理

### 目标

补全闭环的任务状态机管控逻辑。

### 落地要求

正常任务流转状态：

```text
已创建(CREATED)
    ↓
已完成规划(PLANNED)
    ↓
代码开发中(CODING)
    ↓
代码评审中(REVIEWING)
    ↓
产物打包中(PACKAGING)
    ↓
任务完成(COMPLETED)
```

任务失败分支：

```text
开发失败(CODING_FAILED)
评审失败(REVIEW_FAILED)
打包失败(PACKAGING_FAILED)
```

任务取消分支：

```text
已取消(CANCELLED)
```

任务超时分支：

```text
任务超时(TIMEOUT)
```

### 产出物

- `ADR-012` 任务状态机设计文档
- `state-machine-spec.md`
- `runtime/state_machine/` 目录实现

---

## 工作项 2：通用重试框架建设

### 目标

自动化处理各类瞬时异常故障。

### 覆盖异常类型

- 模型调用超时
- 第三方接口临时不可用
- 模型返回结构化数据校验失败
- 网络临时中断

### 重试配置规范

```yaml
retry:
  max_attempts: 3
  backoff: exponential
```

### 产出物

- `ADR-013` 重试策略设计文档
- `retry-spec.md`
- `runtime/retry/` 目录实现

---

## 工作项 3：幂等性能力建设

### 目标

彻底规避重复调用、重复执行问题。

### 落地规范

每一次能力（Skill）调用必须携带两个标识字段：

```yaml
invocation_id:
idempotency_key:
```

### 回放与重复执行规则

相同幂等键重复发起调用时，直接复用已有执行结果，不再重复执行逻辑。

### 产出物

- `idempotency-spec.md`
- `runtime/idempotency/` 目录实现

---

## 工作项 4：回放能力 V2 升级

### 目标

回放从任务级粒度细化至单个 Skill 调用粒度。

### 升级后需落地存储字段

```yaml
task_id:
skill_id:
invocation_id:
status:
duration:
input_summary:
output_summary:
error_type:
```

### 产出物

- `replay-v2-spec.md`
- `runtime/replay/` 目录升级

---

## 工作项 5：指标采集 V2 升级

### 目标

全链路量化指标落地，可衡量系统运行质量。

### 必备采集指标清单

```yaml
task_success_rate:
review_pass_rate:
retry_count:
token_usage:
avg_response_time:
skill_failure_rate:
agent_execution_time:
```

### 产出物

- `metrics-v2-spec.md`
- `runtime/metrics/` 目录升级

---

## 工作项 6：统一错误分类体系

### 目标

标准化全系统异常分类定义。

### 异常分类枚举

```yaml
SYSTEM_ERROR:
MODEL_ERROR:
VALIDATION_ERROR:
TIMEOUT_ERROR:
FILE_LOCK_ERROR:
PERMISSION_ERROR:
RETRY_EXHAUSTED:
```

### 产出物

- `ADR-014` 全局错误分类规范
- `error-spec.md`

---

## 工作项 7：全链路可观测建设

### 目标

全链路执行过程可视化，实现运行透明可查。

### 三类时序视图

1. 任务时序视图

```text
任务规划 → 代码开发 → 代码评审 → 产物生成
```

2. Agent 时序视图

```text
编码智能体 → 评审智能体 → 产物打包智能体
```

3. Skill 时序视图

```text
ClaudeCode能力 → Codex评审能力
```

### 产出物

- `ADR-015` 可观测性设计文档
- `observability-spec.md`

---

## 任务优先级划分

### P0（必做）

- 任务全状态机落地
- 通用重试框架
- 调用幂等机制

### P1（强烈建议）

- 新版回放 V2
- 统一错误分类体系

### P2（优化项）

- 指标体系 V2 落地
- 可视化观测面板

---

## 阶段结项验收标准

满足全部条件即宣告第七阶段完成：

1. 任务中断后可正常恢复执行
2. 从机制上杜绝重复执行
3. 回放数据可支撑线上问题调试定位
4. 全量指标可用于系统效果评估
5. 所有故障均可溯源定位根因
6. 全链路运行过程可观测

达成以上条件后，AgentHub 正式成为生产就绪 MVP 版本。
