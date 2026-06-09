ADR-006 Agent 思维链 & 输入输出规范
决策
各 Agent 使用领域定制化线性思维链；统一标准化输入/输出结构，形成可复用 agent-spec。
顶层 Orchestrator 采用 Plan-and-Execute 范式，内外范式分层解耦。

背景与选择原因
1. 业务专属步骤链更贴合编码评审场景，稳定性、演示效果优于通用 ReAct；
2. 标准化出入参，上下游解析零歧义，适配自动化流转。
一、各 Agent 思维链路（最终版）
Coding Agent
1. 需求理解 & 上下文加载
2. 任务规划
3. 代码生成
4. 自我审查 & 缺陷自检
5. 单元测试生成
6. 变更 Diff 生成
7. 结果上报
Review Agent
1. 产物加载 & 冲突合并检测
2. 全维度代码审查
3. 问题识别 & 归类
4. 风险评级（高/中/低）
5. 分级处置 + 修复建议
6. 评审报告输出
Artifact Agent
1. 产物收集 & 完整性校验
2. 文件快照 & 版本归档
3. 元数据生成
4. 预览卡片生成
5. 最终工程打包输出
二、标准化输入输出（YAML 规范）
Coding Agent
input:
  - 任务基础信息 task
  - 全局上下文 context
output:
  - 业务代码 code
  - 变更差异 diff
  - 单元测试 unit_test

Review Agent
input:
  - 原始代码 code
  - 变更记录 diff
output:
  - 质量评分 score
  - 问题列表 issues
  - 修复建议 suggestions

Artifact Agent
input:
  - 评审后全量产物
output:
  - 归档文件包
  - 元数据 metadata
  - 预览卡片 preview_card

边界约束
1. 思维链禁止跳步、逆序执行；
2. 输出严格按照约定字段返回，自由文本仅作为补充描述。
演进路径
单步骤可嵌套小型 ReAct 循环做精细化推理；整体主链路保持线性不变。


---