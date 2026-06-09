ADR-009 指标监控（Metrics）定义
决策
统一监控指标项，用于质量统计、性能分析、效果评估。

监控指标清单（强制采集）
metrics:
  - task_success_rate    # 任务成功率
  - retry_count          # 全局重试次数
  - review_pass_rate     # 代码评审通过率
  - token_usage          # Token 消耗量
  - avg_response_time    # 平均响应耗时

边界约束
所有指标按任务 ID、Agent 维度做维度拆分统计。

演进路径
后续增加告警阈值、可视化大盘、异常指标告警。