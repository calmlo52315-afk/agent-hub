# Purpose

定义 Stage 6 中 LLM 输出进入 Runtime 前的校验与回退规则。

# Scope

适用于 Planner、Coding 及其他直接消费模型结构化输出的运行时模块。

# Rules

1. LLM 输出 MUST 通过 schema 校验后才能进入后续执行。
2. 校验失败时，Runtime MUST 触发 retry 或 fallback。
3. Runtime MUST NOT 直接消费裸文本作为结构化执行结果。
4. LLM 输出 SHOULD 为可解析 JSON 或等价结构化对象。
5. 输出中的必填字段缺失时，系统 MUST 视为校验失败。
6. 校验失败原因 SHOULD 作为结构化错误或事件记录。

# Forbidden Actions

- 直接把自由文本当作 `Task Plan`。
- 直接把未校验的模型输出当作 `changes` 或 `issues`。
