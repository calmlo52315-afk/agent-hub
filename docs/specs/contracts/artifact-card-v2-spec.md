# Artifact Card V2 Spec

## 1. 目标

定义 Stage 6 真实 Artifact 卡片协议，解决前后端字段不一致与多版本信息缺失的问题。

## 2. 最小 Schema

```yaml
title: string
type: preview | diff | file | review | bundle
files:
  - path: string
    action: create | update | delete
summary: string
download_url: string | null
version: string
```

## 3. 规则

- 所有卡片 MUST 有 `title`
- `type` MUST 可枚举
- `files` SHOULD 用于前端列表展示
- `download_url` 对可下载卡片 MUST 存在
- `version` MUST 来自 Artifact 版本号

## 4. 兼容性

此文档作为 `artifact-card-schema-spec.md` 的 Stage 6 补充版本，用于真实产物场景。
