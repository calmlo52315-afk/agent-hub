# Stage 5 低优先级待办

## 背景

以下内容都具备工程价值，但在当前 `Stage 5` 中不属于阻塞演示闭环的必需项。

当前口径是：

- 系统已经能跑
- Gateway + Runtime 主链路已经打通
- IM 实时流、任务流、artifact 流已经可演示

因此下面这些内容统一收敛为低优先级 TODO，用于下一阶段继续增强。

## TODO 列表

- [ ] `Task Cancel`
  - 原因：当前系统已经能跑。
  - 原因：严格的取消能力不是当前演示闭环必需项。
  - 口径：不影响演示，后续再做更完整的中断协商与状态收敛。

- [ ] `Task Timeout`
  - 原因：当前是单机 MVP。
  - 原因：不是生产环境，暂不追求完整超时治理。
  - 口径：后续再补更严格的执行超时、分阶段超时与告警策略。

- [ ] `Poll Timeout`
  - 原因：属于协议细节。
  - 口径：当前可先保持最小实现，后续再统一细化超时码、退避策略与客户端处理。

- [ ] `Retry 机制细化`
  - 原因：当前已有 `ADR-013` 作为规则依据。
  - 口径：MVP 阶段已有规范可讲，具体细化到后续阶段继续补。

- [ ] `Replay Skill 粒度`
  - 原因：当前 MVP 的 Replay 能力已经够讲。
  - 口径：面试或答辩可直接说明：
  - 口径：`MVP Replay 已完成，Skill 级 Replay 属于下一阶段增强。`

- [ ] `Metrics 细化`
  - 原因：当前已有：
  - 原因：`success_rate`
  - 原因：`retry_count`
  - 原因：`response_time`
  - 口径：这些指标已经足够支撑 MVP 讲解，细化指标后续再补。

- [ ] `Postgres`
  - 原因：当前 SQLite 已能支撑单机 MVP 演示。
  - 口径：Postgres 作为后续正式持久化后端增强项。

- [ ] `Worker Pool`
  - 原因：当前 FastAPI 异步任务模式已满足 Stage 5 闭环。
  - 口径：worker pool 进入下一阶段，用于提升调度能力与并发治理。

## 当前说明

- 当前 SQLite + FastAPI Async API 已满足 Stage 5 演示闭环。
- 上述事项不阻塞当前阶段提交。
- 后续如果进入更正式的工程化阶段，优先顺序建议是：
- 先补 `Postgres`
- 再补 `worker pool`
- 最后细化 `cancel / timeout / replay / metrics`
