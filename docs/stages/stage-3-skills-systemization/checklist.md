# 第三阶段验收清单

- [x] `runtime/specs/` 已提供 Skill Registry 与相关 schema，可被运行时加载
- [x] `rules/execution-rules.json` 已定义 Skill 默认超时、按 Skill 超时映射与成本预算
- [x] `rules/permission-rules.json` 已定义 Skill 白名单与按角色白名单
- [x] `runtime/skills/` 已存在最小 Skill 协议、注册表与运行时计划生成能力
- [x] Orchestrator 主流程已通过 Skill 名称驱动，而不是直接写死 Agent ID
- [x] 每次 Skill 调度都能产生诊断事件，并可写入 replay 事件流
- [x] 现有 Agent 仍可作为底层执行体复用，未破坏 MVP 闭环
- [x] `prompt-management-spec.md` 已补齐，可作为 Stage 3 Prompt 治理依据
- [x] 已新增 Stage 3 单元测试，验证 Skill Runtime 与主流程接线生效
