# 第四阶段任务清单

## 阶段任务描述

本阶段目标是把 AgentHub 运行时从“单任务串行链路”推进到“可拆解子任务、可表达依赖、可并行/串行调度”的协作系统，同时保持三核心 Agent 边界不变。

本阶段重点围绕以下能力展开：

- Task Split：把主任务拆成细粒度子任务
- DAG：用结构化依赖关系表达先后顺序与并发机会
- Dispatch：基于 `@agent`、优先级、依赖满足情况做路由与调度
- Ownership / Lock：处理跨任务文件冲突
- Context：在多任务执行下做可控上下文拼装与裁剪
- Review / Replay：为比赛提交、review 和答辩保留可追踪留痕

## 任务拆解

- [x] 任务 1：补齐 Stage 4 输入规范与规则文档
  - [x] 补充 `task-schema-spec.md`
  - [x] 补充 `dag-execution-spec.md`
  - [x] 补充 `dispatch/dispatch.md`
  - [x] 补充 `context/context.md`
  - [x] 补充 `ownership/ownership.md` 与 `ownership/lock.md`
  - [x] 补充 `global/state-machine.md`

- [x] 任务 2：补充核心编排代码说明，降低 Stage 4 改造理解成本
  - [x] 为 `Orchestrator` 类补充职责说明
  - [x] 为 Agent、消息协议、状态机补充类说明
  - [x] 为关键函数补充输入输出与职责说明

- [x] 任务 3：实现 Task Schema 与 DAG 运行时对象
  - [x] 定义主任务 / 子任务运行时模型
  - [x] 定义 DAG 节点、边、就绪判定与调度事件
  - [x] 增加 DAG 非法环路与非法依赖校验

- [x] 任务 4：升级 Orchestrator 调度链路
  - [x] 从单任务串行执行升级为 Task Split + DAG 调度
  - [x] 支持 `@agent` 显式路由与默认角色回退
  - [x] 支持依赖满足判定、并发度控制与异步队列执行

- [x] 任务 5：升级 Ownership / Lock / Context 的运行时消费
  - [x] 在子任务运行前申请文件锁
  - [x] 在子任务完成、失败、超时时释放锁
  - [x] 基于 token budget 与摘要规则拼装子任务上下文

- [x] 任务 6：补充测试与验证
  - [x] 增加 Task Split / DAG 正向测试
  - [x] 增加依赖未满足、文件锁冲突、非法并发的负向测试
  - [x] 增加多子任务 replay / metrics / diagnostics 验证
