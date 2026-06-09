ADR-004 产物存储规范
决策
采用 按 Session（对话）隔离的分层目录结构 存储所有产物，统一目录范式，避免文件混乱。

Stage 8 更新：Workspace 已从 Task 级改造为 Session 级。一个对话（Session）对应一个 Workspace，
Session 内的所有 Task 共享 source/ 目录，各自在 tasks/{task_id}/ 下有独立归档子目录。

背景与选择原因
1. 多轮任务、多版本文件混杂会导致溯源、回放、产物整理困难；
2. 分层目录区分源码、编译产物、预览资源，结构标准化，便于 Artifact Agent 解析；
3. Session 级隔离使得同一对话中的多个 Task 可以共享和迭代同一组源文件。
目录规范（强制标准）
workspace/
  ├─ {session_id}/              # Session 级工作区（一个对话一个）
  │  ├─ source/                 # 共享源文件（所有 Task 共享读写）
  │  ├─ tasks/                  # 按 Task 组织的产物归档
  │  │  ├─ {task_id_1}/
  │  │  │  ├─ artifacts/        # 编译产物、测试结果
  │  │  │  ├─ diffs/            # 变更 Diff
  │  │  │  └─ metadata.json     # Task 元数据
  │  │  └─ {task_id_2}/
  │  │     └─ ...
  │  ├─ snapshots/              # 版本快照（用于回滚）
  │  ├─ bundles/                # Session 级打包产物
  │  ├─ preview/                # 预览资源
  │  └─ workspace_meta.json     # Workspace 元数据
  └─ ...

边界约束
1. 所有 Session 的工作文件必须归入 `workspace/{session_id}/` 目录；
2. 所有 Task 产物必须归入对应的 `workspace/{session_id}/tasks/{task_id}/` 子目录；
3. 不同类型文件严格归入对应子目录，不得跨目录存放；
4. source/ 目录为 Session 内所有 Task 共享，文件锁机制保证并发安全。
演进路径
后期增加定时清理策略、冷热数据分离、远程对象存储对接。