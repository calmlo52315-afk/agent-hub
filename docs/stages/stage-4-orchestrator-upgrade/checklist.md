# 第四阶段验收清单

- [x] 已补齐 Stage 4 所需规则文档：`dispatch`、`context`、`ownership`、`lock`、`state-machine`
- [x] 已补齐 Stage 4 所需 Spec：`task-schema-spec.md`、`dag-execution-spec.md`
- [x] 核心编排代码已补充类说明和关键函数说明，便于 review 与后续改造
- [x] Orchestrator 已支持主任务拆分为多个子任务，并生成结构化 Task Plan
- [x] 运行时已支持 DAG 节点依赖表示与无环校验
- [x] 调度器已支持依赖满足判定、优先级排序和并发度控制
- [x] 文件锁与所有权已在多任务场景下接入实际调度链路
- [x] 上下文拼装已支持 token budget、摘要规则和多任务隔离
- [x] 调度链路已明确采用 `asyncio + 内存任务队列`，且未引入第三方工作流框架
- [x] 已新增 Stage 4 单元测试 / smoke test，覆盖并发调度与冲突场景
