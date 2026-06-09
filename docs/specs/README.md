# docs/specs

本目录用于沉淀全局通用规范（所有阶段共用，长期维护且相对稳定），面向人类阅读与评审。

需要特别区分两个概念：

- 过程 Spec（阶段文档）：描述阶段目标、场景、变更、任务拆解、验收与测试等，存放在 `docs/stages/`。
- 运行时 Spec（Schema/Contract）：面向运行时校验与执行的结构化契约，代码侧应放在 `runtime/specs/`（本目录仅保留可读说明）。

## 目录结构（固定）

- `contracts/`：核心契约定义（agent/message/context）
- `rules/`：全局通用规则文档（给人读，用于讲解与评审）

