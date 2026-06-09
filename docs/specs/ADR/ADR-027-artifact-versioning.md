# ADR-027 Artifact Versioning

## 决策

Stage 6 的 Artifact 必须采用版本化模型。

最低字段：

```yaml
artifact:
  task_id:
  version:
  created_at:
```

---

## 背景

同一任务可能发生：

- 多次重试
- 人工审批后继续执行
- 多次生成产物
- 多次修订并重新归档

如果 Artifact 不具备版本号，就无法确定哪个版本用于展示、下载、回放或复盘。

---

## 规则

- 同一 `task_id` 下的 Artifact MUST 有递增或可排序的版本标识
- 新版本生成时 MUST NOT 无痕覆盖旧版本
- Gateway 与 Frontend 展示层 MUST 能区分当前版本与历史版本
- Artifact Card SHOULD 显示版本信息
