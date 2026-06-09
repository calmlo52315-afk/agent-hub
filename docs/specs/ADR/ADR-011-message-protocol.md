ADR-011 Agent 通信协议（核心）
决策
全链路统一使用 结构化 JSON 消息协议，废弃纯字符串传递，保证跨角色、跨架构兼容。

背景与选择原因
纯字符串通信无字段、无状态、无法自动化解析；结构化协议是多 Agent 协作、后续架构升级的基础。

标准消息体（全局唯一协议）
{
  "task_id": "string",       // 全局唯一任务ID
  "sender": "string",        // 发送方Agent标识
  "receiver": "string",      // 接收方Agent标识
  "status": "string",        // 状态：pending/running/success/failed
  "payload": {}              // 业务载荷（对应各Agent出入参）
}

字段说明
- task_id：全链路透传，用于追踪、回放、统计；
- status：统一状态枚举，控制流程流转；
- payload：承载实际业务数据，按 ADR-006 出入参规范填充。
边界约束
1. 所有 Agent 间交互必须使用该协议封装；
2. 禁止直接裸传业务数据。
演进路径
架构升级为 Worker Pool 后，协议完全复用，仅增加消息队列转发层。