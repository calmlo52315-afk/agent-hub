ADR-005 上下文（Context）管理策略
决策
定义上下文优先级 + 裁剪规则，明确 Token 不足时的淘汰顺序，保障核心信息不丢失。

背景与选择原因
长流程下上下文溢出、信息丢失是高频问题；必须提前约定优先级与裁剪逻辑，Prompt 与代码才有统一依据。

基础配置
context_config:
  recent_messages: 10
  pinned_messages: all
  artifact_summary: 3

上下文优先级（从高到低，高优先级最后裁剪）
priority:
  1: pinned_messages    # 固定规则、全局约束、原始需求（永久保留）
  2: active_task        # 当前执行任务、文件信息、锁状态（核心运行数据）
  3: artifact_summary   # 产物摘要、评审结论（业务结果）
  4: recent_messages    # 历史交互、过往日志（最先裁剪）

裁剪规则
1. Token 达到阈值时，从最低优先级开始逐步裁剪；
2. pinned_messages 全局固定，永不裁剪；
3. 单轮上下文保留当前任务完整链路，不截断活跃任务信息。
边界约束
禁止打乱优先级顺序做随机裁剪。

演进路径
后期接入独立向量记忆、阶段摘要、RAG 按需检索，彻底弱化上下文窗口限制。