# Diff Spec

## 1. 目标

定义 Coding Agent 输出的统一变更结构，避免不同模型或不同 Agent 返回不一致格式。

## 2. 最小 Schema

```yaml
- path: string
  action: create | update | delete
  summary: string
  content: string | null
```

## 3. 规则

- `path` MUST 为仓库内可定位路径
- `action` 仅允许 `create|update|delete`
- `summary` MUST 用于前端 Diff 卡片展示
- `content` 在 `delete` 场景 MAY 为空

## 4. 非目标

- Stage 6 不强制统一完整 unified diff 文本格式
- Stage 6 先保证文件级结构化变更稳定
