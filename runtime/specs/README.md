# runtime/specs

本目录用于存放运行时可加载的“Schema/Contract”（机器可用），供 Harness/Validator 在执行期进行结构化校验与约束执行。

注意：这与 `docs/specs/` 下的“过程 Spec（文档）”不是一个概念。

当前目录结构建议如下：

- `index.json`：总索引，声明 schema 与 registry 的入口
- `schemas/`：JSON Schema 文件
- `registries/`：最小注册表设计，例如 agent/skill registry

建议内容形态：

- JSON Schema（推荐）
- 或 Pydantic Model（若 runtime 统一采用 Python）

当前已覆盖的机器可读对象：

- Message Envelope
- Task State Machine
- Skill Invocation / Result
- Error Payload
- Agent Registry
- Skill Registry
