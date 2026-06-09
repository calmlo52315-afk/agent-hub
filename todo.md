# AgentHub Todo

## 当前结论

- `Stage 3` 主体验收通过，当前成果已经足够支撑阶段结项、代码 review 和比赛提交。
- 剩余事项统一归档到本清单，作为后续小迭代或后续阶段开发内容。
- 当前应停止无限制补全，避免继续消耗时间在非阻塞项上。

## Stage 3 收尾 Todo

- [ ] 补强 Skill 粒度 Replay
  - 当前 Replay 已具备任务 / Agent 视角的 MVP 留痕，但 Skill 粒度还不完整
  - 目标是把 Replay 从“能记录任务怎么跑”升级到“能记录每次 Skill 怎么被调、怎么结束、为什么失败”
  - 最小规划：
    - 增加 `skill.dispatch`
    - 增加 `skill.start`
    - 增加 `skill.success`
    - 增加 `skill.failed`
    - 为每次 Skill 调用补 `invocation_id`
    - 记录 `skill_name / version / workflow_stage / agent_binding`
    - 记录 `duration_ms / retry_count / error_category / error_code`
    - 先存输入输出摘要，不做全量 payload 快照
  - 价值：
    - 直接支撑 Skill Runtime 的可观测性
    - 为 Skill 幂等、重放排查、预算分析打基础
    - 面试和答辩时能更自然地讲清 Skill 不是概念抽象，而是运行时真正可观察对象
  - 优先级：
    - 当前最高优先级
    - 高于 Skill 幂等，因为 Replay 事件补齐后，幂等的执行记录与去重判断更容易落地
  - 最合适的启动时机：
    - 比赛提交流程和核心 review 完成后，作为 `Stage 3` 收尾小迭代立即开始
    - 不建议拖到非常后面，因为后续补幂等、统一错误码、预算拦截都会依赖更细粒度的 Replay

- [ ] 落地 Skill 幂等
  - 为每次 Skill 调用引入 `invocation_id` 或 `idempotency_key`
  - 持久化 Skill 执行记录，支持重复调用识别与结果复用
  - 区分读类 Skill 与写类 Skill，对有副作用的调用建立更严格的幂等边界
  - 对文件写入、产物归档、后续外部工具调用统一补幂等策略
  - 这项优先级高于一般优化项，建议早于多模型接入推进

- [ ] 落地 Prompt 物理目录
  - 在仓库中创建 `docs/prompts/` 实际目录结构
  - 按 `coding / review / artifact` 维度落 Prompt 文件
  - 增加 `active.json` 或等价配置作为启用版本入口

- [ ] 将 `prompt_ref` 真实挂载到 Skill
  - 在 `runtime/specs/registries/skills.registry.json` 中补充 `prompt_ref`
  - 让 Skill Registry / Skill Runtime 能解析当前启用 Prompt
  - 让 Skill 与 Prompt 形成“Contract 版本独立、Prompt 可切换”的真实关系

- [ ] 接入多模型底层 LLM 工厂
  - 抽象统一 LLM Factory / Provider Adapter
  - 接入 `ClaudeCode`、`Codex` 等底层能力
  - 保证上层 Orchestrator / Skill Runtime 不直接依赖具体模型 SDK

- [ ] 按 Skill 路由模型
  - 建立 `Skill -> Model Provider` 的路由映射
  - 支持不同 Skill 使用不同模型能力
  - 为后续模型降级、fallback 和成本优化预留入口

- [ ] 完整落地统一错误码
  - 把 `error-code-spec.md` 中的错误码真正写入运行时失败对象
  - 统一 `category / error_code / retryable / stage` 输出
  - 对齐 Replay、Metrics、日志和结果返回结构

- [ ] 完整落地全链路 cost 预算拦截
  - 让 `execution-rules` 中的 budget 不只是配置，还能在运行时生效
  - 对单次 Skill 调用、单任务、单链路做 token / cost 预算检查
  - 超预算时执行明确的阻断或降级策略

## 之前遗留改造事项

- [ ] `RuntimeValidator` 混合 `Pydantic + JSON Schema` 改造
  - 当前不做
  - 统一挪到 `Stage 3` 收尾小迭代或 `Stage 7` 可观测阶段

- [ ] `error-code` 全量落地改造
  - 当前不做
  - 统一挪到后续阶段，避免继续打断主线开发

- [ ] 全规则消费改造
  - 当前 rules 已完成关键消费，但尚未做到“所有规则段都被运行时完整执行”
  - 当前不继续扩写，统一延后整理

## Stage 4 低优先级增强项

- [ ] 多层 DAG / 返工回路
  - 当前 `Stage 4` 已支持 Task Split、DAG、依赖调度、等待队列与基础防饥饿
  - 但 `Review` 与 `Artifact` 仍以单 fan-in 节点为主，尚未扩展为更复杂的多层依赖图
  - 后续可补 `review -> coding rework -> review -> artifact` 这类正式返工回路
  - 优先级：
    - 低
    - 不阻塞当前阶段结项、review 和比赛提交

- [ ] 更精细的 token budget 估算
  - 当前 context budget 采用序列化字节大小做轻量裁剪，已经能用于演示和主链路保护
  - 后续可接入更接近模型调用成本的 token 估算器与硬拦截策略
  - 优先级：
    - 低
    - 放在多层 DAG 之后更合适

- [ ] 等待队列持久化与恢复
  - 当前锁调度已支持 `lease_seconds`、过期清理、基础等待队列和 age-based 防饥饿
  - 但等待队列仍是内存态，尚未支持持久化恢复、更丰富的公平策略和更细粒度冲突事件
  - 优先级：
    - 低
    - 适合放到后续平台化或可观测增强阶段

- [ ] TaskPlanner 语义理解增强
  - 当前通用 `TaskPlanner` 已支持 `@agent`、文件路径、优先级和自动补齐 review/artifact
  - 但仍属于启发式拆分，后续可继续提升复杂任务语义理解、拆分质量和依赖推断能力
  - 优先级：
    - 低
    - 不影响当前 Stage 4 主链路可运行状态

## 延后原则

- 不再把以上事项插入当前 Stage 3 主开发流程
- 仅在以下时机处理：
  - `Stage 3` 收尾小迭代
  - `Stage 7` 可观测 / 平台化阶段
  - 比赛提交前，如确有展示价值且实现成本可控

## 执行建议

- 现在优先进入 review、讲解材料整理和比赛提交流程
- 若还有可用时间，优先级建议如下：
  1. Skill 粒度 Replay
  2. Skill 幂等
  3. `prompt_ref` + `docs/prompts/` 物理目录落地
  4. 统一错误码落地
  5. 多模型工厂与按 Skill 路由
  6. 全链路 cost 预算拦截
