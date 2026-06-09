# 第六阶段任务清单

## 阶段任务描述

本阶段目标是把 AgentHub 当前“可跑通的 Demo Runtime”升级为“真实可演示的 Agent Runtime 主链路”，并明确 MVP 的执行模型、规划策略、事件模型与产物版本语义。

本阶段重点围绕以下能力展开：

- Agent Execution Model 定型
- Planner Strategy 定型
- 真实任务规划
- 真实代码生成
- 真实代码评审
- 实时阶段事件
- 真实 diff / artifact 展示
- Artifact 版本化
- Human Approval 门控
- 最小模型接入边界
- 比赛演示样例固化

## 任务拆解

- [ ] 任务 1：补齐 Stage 6 文档留痕
  - [ ] 更新 `spec.md`
  - [ ] 更新 `tasks.md`
  - [ ] 更新 `checklist.md`
  - [ ] 创建 `README.md`
  - [ ] 创建 `tests.md`
  - [ ] 创建 `modifications.md`

- [ ] 任务 2：补齐关键 ADR
  - [ ] 创建 `ADR-024 Agent Execution Model`
  - [ ] 创建 `ADR-025 Planner Strategy`
  - [ ] 创建 `ADR-026 Agent Event Model`
  - [ ] 创建 `ADR-027 Artifact Versioning`
  - [ ] 创建 `ADR-028 Human Approval`

- [ ] 任务 3：补齐 Runtime 关键协议文档
  - [ ] 创建 `task-plan-spec.md`
  - [ ] 创建 `agent-execution-spec.md`
  - [ ] 创建 `event-spec.md`
  - [ ] 创建 `diff-spec.md`
  - [ ] 创建 `artifact-card-v2-spec.md`

- [ ] 任务 4：补齐 Runtime 关键规则文档
  - [ ] 创建 `runtime/agent-execution-rules.md`
  - [ ] 创建 `runtime/event-rules.md`
  - [ ] 创建 `runtime/llm-output-rules.md`

- [ ] 任务 5：替换 Demo Task Plan
  - [ ] 将固定 `demo_workspace/hello.txt` 目标改为真实规划结果
  - [ ] 支持按 instruction 推断语言与目标文件
  - [ ] 为 `Go Gin API`、`React Todo 页面`、`修改已有代码新增接口` 建立稳定规划模板
  - [ ] 建立 `llm_planner -> rule_planner` fallback 机制

- [ ] 任务 6：升级 Coding Agent
  - [ ] 接入最小模型调用边界
  - [ ] 让 Coding Agent 输出真实 `changes`
  - [ ] 支持真实文件创建与更新
  - [ ] 输出遵守统一 `diff` 与 `agent execution` 协议

- [ ] 任务 7：升级 Review Agent
  - [ ] 对真实代码内容做评审
  - [ ] 产出结构化 `issues`
  - [ ] 评审结果与具体文件绑定
  - [ ] 高风险问题可进入人工审批

- [ ] 任务 8：补齐执行过程可视化
  - [ ] Gateway 增加标准阶段事件
  - [ ] 前端任务时间线展示 `planning/coding/review/artifact`
  - [ ] 在消息区展示阶段摘要
  - [ ] 事件可被 WS / Replay / Metrics 复用

- [ ] 任务 9：修正 Artifact / Diff 真值化
  - [ ] Diff 卡片展示真实改动文件
  - [ ] Bundle / Artifact Card 字段与前端对齐
  - [ ] Artifact 指向真实产物目录
  - [ ] Artifact 具备版本号与版本留痕

- [ ] 任务 10：固化比赛演示样例
  - [ ] 创建 `docs/demo-cases/stage-6/README.md`
  - [ ] 产出 `Go Gin API` 演示案例
  - [ ] 产出 `React Todo 页面` 演示案例
  - [ ] 产出 `修改已有代码新增接口` 演示案例

- [ ] 任务 11：补充验证
  - [ ] 为规划链路补测试
  - [ ] 为生成链路补测试
  - [ ] 为事件链路补测试
  - [ ] 为 artifact/diff 展示契约补测试
