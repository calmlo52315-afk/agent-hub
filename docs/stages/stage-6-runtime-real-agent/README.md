# Stage 6: Runtime Real-Agent

## 阶段目标

把 AgentHub 从“能跑的 Demo Runtime”推进为“执行模型明确、协议清晰、流程可展示、案例可复现”的比赛主链路版本。

## 阶段交付物

1. 阶段主规范：`spec.md`
2. 任务拆解：`tasks.md`
3. 验收清单：`checklist.md`
4. 测试与验证：`tests.md`
5. 关键改动记录：`modifications.md`
6. 比赛案例：`docs/demo-cases/stage-6/`

## 当前状态

文档骨架已建立，开发已启动。

## 当前现实约束

- 代码主链路仍是 `Stage 4 DAG + demo agents`
- `Stage 6` 的 `linear_pipeline / llm_planner / artifact version / approval` 目前主要完成了文档定型
- 当前可以优先跑通的是“任务闭环流程验证”，还不是“真实语义代码生成”

## 本阶段开发策略

优先顺序如下：

1. 先把执行模型、Planner 策略、事件协议、Artifact 版本协议定型
2. 再把 `Stage 6` 比赛案例固化为可重复执行的输入集
3. 先验证“流程跑通”，再推进“真实能力替换”
4. 最后逐步把 demo runtime 升级为真实 `Planner -> Coding -> Review -> Artifact`
