# ADR-028 Human Approval

## 决策

Stage 6 将 Human Approval 作为执行链中的标准门控能力，而不是仅保留为概念能力。

触发条件示例：

- Review 发现高风险问题
- 变更范围超阈值
- 命中策略化敏感目录或接口

---

## 背景

仓库已有 `ADR-021 Human-in-the-Loop`，定义了 HITL 原则；但 Stage 6 需要更具体的“什么时候暂停、谁来审批、审批后如何恢复”的执行协议。

---

## 审批流

```text
Review 检测高风险
  ↓
approval.required
  ↓
Human Approve / Reject
  ↓
继续执行 / 终止任务
```

---

## 规则

- AI MUST NOT 自行批准高风险任务
- Approval 结果 MUST 进入事件流与回放存储
- 被拒绝后任务 MUST 进入终止或失败分支
- 被批准后系统 MAY 继续进入下一阶段
