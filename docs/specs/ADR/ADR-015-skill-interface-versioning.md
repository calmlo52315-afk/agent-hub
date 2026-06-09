ADR-015 Skill 接口与版本管理

决策
AgentHub 从 Stage 3 开始将能力从 Agent Prompt 中解耦为可复用 Skill，并将版本号绑定在 Skill Contract 上，而不是绑定在 Agent 或 Prompt 上。

统一决策如下：
1. Skill 是运行时可编排的最小能力单元。
2. Skill 必须有稳定接口定义，包括元数据、输入 schema、输出 schema、错误语义与权限边界。
3. Skill 版本采用语义化版本，挂在 Contract 上。
4. Prompt 版本独立管理，不等同于 Skill Contract 版本。

背景与选择原因
1. 当前系统已经形成 `ADR + contracts + rules` 分层，如果继续把能力写死在单个 Agent Prompt 里，后续扩展多 Agent、多模型、多角色会迅速失控。
2. 面试与工程化视角下，“Skill 可复用、可治理、可灰度”比“Prompt 很长很聪明”更有平台价值。
3. 将版本放在 Contract 上，才能同时兼顾：
   - 运行时校验
   - 多版本兼容
   - Prompt 优化不触发 breaking change

Skill 定义
1. Skill 是单一职责能力单元，例如：
   - `coding.generate_patch`
   - `review.analyze_diff`
   - `artifact.package_result`
2. Skill 可由：
   - 外部模型驱动
   - 内部规则驱动
   - 工具执行驱动
   三种方式之一实现，但对上层暴露统一 Contract。

版本管理原则
1. `Major`
   - 不兼容变更，例如删除字段、修改字段语义、改变必填约束。
2. `Minor`
   - 向后兼容新增，例如新增可选字段、扩展枚举、增加元数据。
3. `Patch`
   - 不改变 Contract，只优化 Prompt、示例、阈值、描述、内部实现。

示例
```yaml
skill_name: coding.generate_patch
version: 1.0.0
```

Prompt 与 Contract 的关系
1. Prompt 是 Skill 的实现资源，不是 Skill 的身份标识。
2. Prompt 可以从 `v1` 调整到 `v2`，只要输入输出 Contract 不变，Skill 版本仍可保持 `1.0.x`。
3. 一旦 Prompt 优化引发输出结构变化，则必须提升 Skill Contract 版本，而不是只改 Prompt 文件名。

边界约束
1. 禁止只以 Prompt 文件名表达版本，而不维护 Skill Contract 版本。
2. 禁止 Agent 私有定义输入输出结构绕过 Skill Registry。
3. 同名 Skill 的不同版本必须可并存一段时间，以支持灰度切换与回滚。

影响
1. `docs/specs/contracts/` 需要新增 `skill-contract-spec.md`，作为人类可读规范。
2. 未来若需要运行时强校验，应在 `runtime/specs/` 生成机器可读 schema。
3. Orchestrator / Skill Registry 必须按 `skill_name + version` 做唯一寻址。

演进路径
1. 初期可先维护少量核心 Skill 的静态注册表。
2. 后续可增加：
   - `active version` 配置
   - 灰度发布
   - 按任务或模型路由到不同 Skill 版本

参考
- `docs/specs/contracts/agent-spec.md`
- `docs/specs/ADR/ADR-006-agent-spec.md`
