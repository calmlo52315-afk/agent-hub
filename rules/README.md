# /rules

本目录存放“可执行规则配置”（Rules），用于驱动运行时行为与安全边界。Rules 必须是结构化配置，`/runtime` 可直接加载。

## 入口文件

- [index.json](./index.json)：规则集索引（运行时从此处定位各规则文件）
- [execution-rules.json](./execution-rules.json)
- [permission-rules.json](./permission-rules.json)
- [ownership-rules.json](./ownership-rules.json)
- [communication-rules.json](./communication-rules.json)

## 规则文件通用结构

每个规则文件均采用：

```json
{
  "schema_version": "1.0",
  "kind": "execution|permission|ownership|communication",
  "policy_id": "string",
  "description": "string",
  "rules": {}
}
```

## 如何验证

```bash
python3 -m runtime.validate_rules
```
