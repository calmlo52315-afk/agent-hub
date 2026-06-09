# Stage 5 Frontend Design

## 1. 文档目标

本文档用于指导 Stage 5 前端页面实现。

目标不是定义后端协议，而是把已经完成的 Gateway / Runtime 能力，整理成一份前端可直接落地的设计方案，供：

- Claude Code 生成前端代码
- 人工前端开发参考
- 比赛答辩时说明产品闭环设计

当前范围只覆盖：

- 会话列表
- IM 聊天区
- 多 Agent 协作消息流
- Artifact 展示
- Diff 展示
- Session / Task 状态联动

不包含：

- 登录注册正式页面
- 企业级权限系统
- 前端部署方案

## 2. 设计目标

### 2.1 产品感目标

前端整体视觉应偏：

- 字节系比赛风格
- 简洁、克制、现代
- 信息密度高，但层次清晰
- 看起来像一个真的 AI 协作开发工具，而不是普通聊天机器人页面

### 2.2 演示目标

页面必须能在 1 分钟内清楚展示：

- 用户输入需求
- Orchestrator / Agent 开始协作
- 消息流式更新
- 任务状态变化
- Review 结果返回
- Artifact / Diff 可视化展示

### 2.3 实现目标

前端必须优先保证：

- 能稳定消费 Gateway REST + WebSocket
- 状态模型简单清晰
- UI 不需要理解 Runtime 内部对象
- 后续可以扩展更多 Agent、Artifact、Task 状态

## 3. 整体风格

### 3.1 视觉关键词

- 深浅结合
- 卡片化
- 轻玻璃感
- 清晰分栏
- 状态颜色明确
- 偏企业级工作台，而不是娱乐型聊天 UI

### 3.2 建议基调

- 页面主背景：偏冷灰或浅雾蓝灰
- 主内容区域：白色或弱透明浅色卡片
- 强调色：蓝色系，少量紫蓝渐变
- 成功态：绿色
- 风险态：橙色
- 错误态：红色
- 辅助线与边框：尽量细、轻、克制

### 3.3 交互气质

- 默认安静，不要过多动效
- 实时消息出现时允许有轻微淡入
- Task 状态变化用轻量状态条或小标签表示
- Artifact 点击后在右侧区域切换，不建议使用全屏弹窗作为主交互

## 4. 页面信息架构

整体采用三栏结构。

### 4.1 左栏：Session Sidebar

职责：

- 展示最近会话
- 搜索会话
- 新建会话
- 切换会话

建议内容：

- 顶部品牌区：`AgentHub`
- 新建会话按钮
- 搜索框
- 会话列表
- 当前会话高亮

每个会话项建议展示：

- 标题
- 最近一条消息摘要
- 更新时间
- task 数量角标

### 4.2 中栏：Chat Workspace

职责：

- 承载主消息流
- 展示用户消息、Agent 消息、系统事件
- 展示任务状态变化
- 作为输入区上方的核心操作画布

建议分区：

- 顶部会话栏
- 中部消息流
- 底部输入区

顶部会话栏建议展示：

- 当前 Session 标题
- 模式标签：`Single Agent` / `Multi Agent`
- 连接状态：`Connected / Reconnecting`
- 可选任务总览按钮

### 4.3 右栏：Artifact Panel

职责：

- 展示 Preview / Diff / Review / File / Bundle
- 承载“这次 AI 协作产出了什么”

建议分区：

- 顶部标签页：`Artifacts` / `Diff` / `Review`
- 中部卡片列表或详情面板
- 空状态说明

右栏必须默认存在，不能把 Artifact 设计成隐藏很深的二级页面。

## 5. 核心页面组件

### 5.1 SessionList

能力：

- 渲染 session 列表
- 支持加载状态
- 支持空状态
- 支持点击切换当前 session

### 5.2 ChatMessageList

能力：

- 按 `seq` 排序渲染消息
- 支持流式追加
- 支持按 `task_id` 关联任务状态
- 支持 markdown、代码块、diff 片段、系统消息

### 5.3 MessageBubble

消息类型建议区分：

- `user`
- `agent`
- `system`
- `task-event`
- `review-event`

展示建议：

- 用户消息靠右或使用更明显的主色卡片
- Agent 消息靠左，附带 Agent 标签
- System / Task 事件使用更轻量的信息条样式

### 5.4 AgentTag

建议支持：

- `Orchestrator`
- `Coding Agent`
- `Review Agent`
- `Artifact Agent`

标签风格建议：

- 小尺寸圆角标签
- 不同 Agent 用不同浅色背景
- 不建议做过度花哨图标

### 5.5 TaskTimelineCard

职责：

- 展示任务当前状态
- 展示当前 agent
- 展示进度
- 展示 summary

适合在聊天流中以内联卡片形式出现。

### 5.6 ArtifactCardList

职责：

- 渲染所有 `artifact.created` 产生的 card
- 支持根据 `card_type` 切换不同 renderer

### 5.7 DiffViewerCard

职责：

- 显示文件变更数量
- 显示 `additions / deletions`
- 显示文件级 diff excerpt

### 5.8 ReviewCard

职责：

- 展示 `pass / fail`
- 展示 `score`
- 展示 issues 列表

### 5.9 InputComposer

职责：

- 输入消息
- 发送消息
- 展示发送中状态

MVP 阶段支持：

- 普通文本输入
- Enter 发送
- Shift + Enter 换行

## 6. 页面布局建议

推荐桌面端布局：

- 左栏：`280px`
- 中栏：自适应主区域
- 右栏：`360px - 420px`

推荐最大内容宽度：

- 中栏消息区域正文宽度不要过宽
- 单条消息推荐控制在 `720px - 820px`

推荐层级：

- App 背景
- 三栏主容器
- 卡片层
- 标签 / 状态 / 输入层

## 7. 关键视觉细节

### 7.1 比赛展示建议

为了更像“字节系产品答辩 Demo”，建议加入以下视觉点：

- 顶部轻量品牌标题与一句副标题
- 当前连接状态用小圆点和文案展示
- Multi Agent 相关状态用横向小标签显示
- Artifact 卡片边角更圆，阴影更轻
- 页面整体留白比传统管理后台略多

### 7.2 避免的问题

- 不要做成普通 ChatGPT 样式的一列聊天
- 不要过度霓虹或过度渐变
- 不要使用过深的纯黑背景
- 不要让右侧 Artifact 变成不重要的附属区

## 8. 前端数据模型

前端建议至少维护以下状态域。

### 8.1 Session State

```ts
type SessionSummary = {
  session_id: string
  title: string
  mode: "single_agent" | "multi_agent"
  updated_at: string
  last_event_seq: number
  last_message_preview?: string
  task_count?: number
}
```

### 8.2 Message State

```ts
type RealtimeMessage = {
  event_id: string
  session_id: string
  task_id?: string
  trace_id?: string
  type: string
  kind: string
  seq?: number
  timestamp: string
  status?: string
  payload: Record<string, unknown>
}
```

### 8.3 Task State

```ts
type TaskSummary = {
  task_id: string
  session_id: string
  title: string
  status: string
  summary?: string
  current_agent?: string
  retry_count?: number
  retry_limit?: number
  waiting_for_approval?: boolean
  updated_at: string
}
```

### 8.4 Artifact State

```ts
type ArtifactCard = {
  artifact_id: string
  task_id: string
  card_type: "preview" | "diff" | "file" | "review" | "bundle"
  title: string
  summary?: string
  status: "generating" | "ready" | "failed"
  updated_at: string
  content: Record<string, unknown>
}
```

## 9. 前端状态管理建议

推荐使用 `Zustand`。

建议拆分为：

- `sessionStore`
- `chatStore`
- `taskStore`
- `artifactStore`
- `connectionStore`

### 9.1 sessionStore

负责：

- session 列表
- 当前 session
- session detail

### 9.2 chatStore

负责：

- 消息列表
- `seq` 去重与排序
- 历史消息回补
- 流式消息拼接

### 9.3 taskStore

负责：

- task 列表
- 当前 task 状态
- task 状态更新映射

### 9.4 artifactStore

负责：

- artifact 列表
- 当前选中的 artifact
- 按 `card_type` 分组

### 9.5 connectionStore

负责：

- WebSocket 连接状态
- `ws_ticket`
- 重连状态
- `resume_from_seq`

## 10. 接入时序

前端初始化一个 session 的推荐流程如下：

1. 页面加载后先请求 session 列表
2. 默认打开最近一个 session，或创建新 session
3. 请求 session detail
4. 请求历史 messages
5. 请求 tasks
6. 请求 artifacts
7. 请求 `ws_ticket`
8. 建立 WebSocket 连接
9. 发送 `session.subscribe`
10. 开始接收实时消息

### 10.1 新建会话流程

1. 调用 `POST /api/v1/sessions`
2. 将 `initial_message` 作为第一条用户输入
3. 成功后写入左栏 session 列表
4. 获取 `ws_ticket`
5. 建立实时连接

### 10.2 重连流程

1. 记录当前最大 `seq`
2. 重连后重新申请 `ws_ticket`
3. 发送 `session.subscribe`
4. 携带 `resume_from_seq`
5. 处理 replay 或 `session.snapshot`

## 11. REST 接口使用建议

前端主要依赖：

- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/messages`
- `GET /api/v1/sessions/{session_id}/tasks`
- `GET /api/v1/sessions/{session_id}/artifacts`
- `POST /api/v1/ws-tickets`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/artifacts/{artifact_id}`

可暂时不优先实现：

- retry
- cancel
- approval
- conflict resolution

因为 Stage 5 当前更关注演示主链路。

## 12. WebSocket 事件消费规则

前端必须优先支持以下事件：

- `connection.ready`
- `session.snapshot`
- `ack`
- `chat.message`
- `task.created`
- `task.updated`
- `task.completed`
- `review.completed`
- `artifact.created`
- `system.error`
- `heartbeat`

### 12.1 渲染优先级

- `chat.message` 直接进入消息流
- `task.*` 更新 taskStore，并在消息流中插入轻量状态卡
- `review.completed` 生成 ReviewCard
- `artifact.created` 更新右栏 ArtifactPanel
- `system.error` 显示顶部提示或消息流错误条

### 12.2 排序规则

- 同一 session 内严格按 `seq` 排序
- UI 展示时允许按 `task_id` 聚合，但底层存储顺序仍以 `seq` 为准

## 13. Artifact 渲染策略

### 13.1 `diff`

渲染内容：

- 文件数
- 增删统计
- 文件级片段

交互建议：

- 默认展示摘要
- 点击后展开文件级 diff excerpt

### 13.2 `review`

渲染内容：

- 是否通过
- score
- issue 列表

交互建议：

- 失败时也必须展示
- 高风险 issue 用更明显颜色

### 13.3 `bundle`

渲染内容：

- bundle 内包含哪些产物
- 可下载链接

### 13.4 `preview`

当前后端真实 preview card 尚未完成。

前端设计上应预留：

- preview iframe 区域
- 打开新窗口按钮
- 加载中骨架态

## 14. Demo 版鉴权与环境变量

MVP 前端先按 Demo 模式处理。

建议：

- 前端通过环境变量注入 `access_token`
- 所有 REST 请求带 `Authorization: Bearer <token>`
- 获取 `ws_ticket` 后再建立 WebSocket

前端环境变量建议：

```bash
NEXT_PUBLIC_GATEWAY_BASE_URL=http://localhost:8080
NEXT_PUBLIC_DEMO_ACCESS_TOKEN=demo-access-token
```

## 15. 建议技术栈

建议与需求文档保持一致：

- Next.js
- TypeScript
- TailwindCSS
- shadcn/ui
- Zustand

建议补充：

- `react-markdown`
- `remark-gfm`
- `lucide-react`
- 轻量代码高亮组件

## 16. Claude Code 实现约束

给 Claude Code 的实现要求建议写死为：

- 只开发前端，不修改 Gateway / Runtime
- 优先消费现有 REST / WebSocket 契约
- UI 要偏企业级、简洁、现代
- 页面必须支持三栏布局
- 必须包含 Session Sidebar、Chat Workspace、Artifact Panel
- 必须支持消息流、任务状态、artifact card、review card、diff card
- 必须预留 WebSocket 重连与 replay 逻辑
- 对未知 artifact type 做兜底渲染
- 所有 mock 数据结构必须贴合现有 spec

## 17. Claude Code 输入文档

Claude Code 至少需要参考以下文档：

- `docs/specs/contracts/session-task-api-spec.md`
- `docs/specs/contracts/websocket-message-spec.md`
- `docs/specs/contracts/artifact-card-schema-spec.md`
- `docs/specs/rules/communication/communication.md`
- `docs/specs/rules/permission/permission.md`
- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-019-Session-Model.md`
- `docs/specs/需求文档.md`
- 本文档

## 18. MVP 实现优先级

建议 Claude Code 按以下顺序实现：

1. 三栏页面框架
2. Session Sidebar
3. Chat Message Flow
4. Input Composer
5. Artifact Panel
6. Diff / Review Card Renderer
7. REST 数据接入
8. WebSocket 实时接入
9. 重连与 replay
10. 视觉细节优化

## 19. 结论

Stage 5 前端不是普通聊天页，而是一个：

- 以 IM 为外壳
- 以多 Agent 协作为核心
- 以 Artifact / Diff 展示为亮点
- 以工程化感和演示完整度为目标

的 AI Coding 工作台。

实现时必须优先保证：

- 产品观感成立
- 主链路稳定
- 状态流清晰
- 协议消费准确
