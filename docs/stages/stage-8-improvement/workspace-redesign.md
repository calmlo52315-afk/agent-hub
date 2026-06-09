# Workspace 改造：从 Task 级到 Session 级

## 1. 问题分析

### 1.1 当前状态

目前系统中 "workspace" 概念在不同层面有不同含义，且核心模型存在不合理之处：

| 层面 | 当前 workspace 含义 | 问题 |
|------|-------------------|------|
| **ADR-004** 目录规范 | `workspace/task_001/source/` — 按任务隔离 | 任务间无共享文件状态 |
| **Runtime Workspace 类** | 以 `repo_root` 为根的文件 I/O 安全层 | 不区分 session/task，所有操作共享一个根 |
| **前端 ArtifactPanel** | 标为 "Workspace"，按 `task_id` 分组展示产物 | 语义混乱：叫 Workspace 但内容是 task 级 |
| **前端布局逻辑** | 根据最新 task 的属性决定是否显示 workspace 面板 | workspace 的显示与否不应由单个 task 决定 |

### 1.2 核心矛盾

**"一个任务 = 一个 workspace" 是不合理的。**

真实场景中：
- 一个对话（Session）中，用户和 Agent 会进行多轮交互
- 每轮交互可能产生多个 Task（Coding → Review → Artifact）
- 这些 Task 操作的是**同一组项目文件**（比如同一个 React 项目的不同组件）
- Task 之间需要共享文件状态——Task 2 需要看到 Task 1 的产出

当前模型把 Task 和 Workspace 绑定为 1:1，导致：
1. Task 间无法共享文件状态（除非手动跨 task 引用）
2. 前端 Workspace 面板展示混乱——需要跨 task 聚合产物
3. 无法表示"一个项目"的持续演进状态
4. Session 作为对话容器，缺少对应的持久化工作区

### 1.3 正确的关系应该是

```
Session (对话) 1 —— 1 Workspace (工作区)
Session (对话) 1 —— N Task (任务)
Task (任务)    N —— 1 Workspace (工作区)  ← 共享
```

## 2. 改造方案

### 2.1 核心变更

**一个对话（整个 Session）是一个 Workspace。**

- Workspace 与 Session 生命周期绑定：创建 Session 时创建 Workspace，删除 Session 时清理 Workspace
- 同一 Session 内的所有 Task 共享同一个 Workspace
- Task 在 Workspace 内仍有独立子目录用于产物归档和追溯

### 2.2 目录结构变更

**旧结构（Task 级）：**
```
workspace/
├── task_001/
│   ├── source/
│   ├── artifacts/
│   └── preview/
├── task_002/
│   ├── source/
│   ├── artifacts/
│   └── preview/
└── ...
```

**新结构（Session 级）：**
```
workspace/
├── {session_id}/                # Session 级工作区根目录
│   ├── source/                  # 共享源文件（所有 Task 共享）
│   │   ├── src/
│   │   │   ├── components/
│   │   │   └── ...
│   │   └── ...
│   ├── tasks/                   # 按 Task 组织的产物归档
│   │   ├── {task_id_1}/
│   │   │   ├── artifacts/       # 编译产物、测试结果
│   │   │   ├── diffs/           # 变更 Diff
│   │   │   └── metadata.json    # Task 元数据
│   │   └── {task_id_2}/
│   │       └── ...
│   ├── snapshots/               # 版本快照（用于回滚）
│   │   ├── snap_001.json
│   │   └── ...
│   ├── bundles/                 # Session 级打包产物
│   │   └── ...
│   ├── preview/                 # 预览资源
│   │   └── ...
│   └── workspace_meta.json      # Workspace 元数据
└── ...
```

### 2.3 数据模型变更

#### 2.3.1 Workspace 新增类型定义

```typescript
// fronted/types/index.ts 新增

export interface WorkspaceMeta {
  workspace_id: string;        // = session_id (1:1 映射)
  session_id: string;
  root_path: string;           // 工作区根目录路径
  source_files_count: number;  // 源文件数量
  total_tasks: number;         // 关联的 task 数量
  created_at: string;
  updated_at: string;
  status: "active" | "archived" | "cleaning";
}

export interface WorkspaceSnapshot {
  snapshot_id: string;
  workspace_id: string;
  task_id: string;            // 触发快照的 task
  file_states: FileState[];   // 快照时的文件状态列表
  created_at: string;
}

export interface FileState {
  path: string;
  hash: string;
  size_bytes: number;
  changed_by_task_id: string;
}
```

#### 2.3.2 TaskSummary 字段调整

```typescript
// 移除不再需要的字段
// workspace_required?: boolean;  // 移除 — workspace 现在是 session 级

// 新增/调整字段
export interface TaskSummary {
  // ... 保留现有字段
  workspace_id?: string;       // 新增：所属 workspace (即 session_id)
  // task_mode 仍然可用，但 workspace_required 语义迁移到 session
}
```

#### 2.3.3 SessionSummary 新增字段

```typescript
export interface SessionSummary {
  // ... 保留现有字段
  workspace_id?: string;       // 新增：关联的 workspace（通常等于 session_id）
  workspace_root?: string;     // 新增：工作区根路径
  source_files_count?: number; // 新增：工作区文件数
}
```

### 2.4 Runtime 层变更

#### 2.4.1 Workspace 类重构 (`runtime/harness/workspace.py`)

```python
@dataclass(frozen=True)
class Workspace:
    """Session-scoped workspace — one per conversation."""
    repo_root: Path              # 项目根（不变）
    session_id: str              # 新增：关联的 session
    session_root: Path           # 新增：workspace/{session_id}/
    source_root: Path            # 新增：workspace/{session_id}/source/
    permission: PermissionManager
    ownership: OwnershipManager
    ruleset_ownership: dict[str, Any]

    @classmethod
    def create(cls, *, repo_root: Path, session_id: str, ...) -> "Workspace":
        """为新 session 创建工作区目录结构"""
        session_root = repo_root / "workspace" / session_id
        (session_root / "source").mkdir(parents=True, exist_ok=True)
        (session_root / "tasks").mkdir(parents=True, exist_ok=True)
        (session_root / "snapshots").mkdir(parents=True, exist_ok=True)
        (session_root / "bundles").mkdir(parents=True, exist_ok=True)
        (session_root / "preview").mkdir(parents=True, exist_ok=True)
        # 写入 workspace_meta.json
        ...
        return cls(...)

    def task_dir(self, task_id: str) -> Path:
        """获取 task 在 workspace 内的子目录"""
        return self.session_root / "tasks" / task_id

    def abs_source_path(self, rel_path: str) -> Path:
        """将相对路径映射到 source/ 目录下"""
        return (self.source_root / rel_path).resolve()
```

#### 2.4.2 Orchestrator 变更

```python
# runtime/orchestrator/orchestrator.py

@dataclass
class Orchestrator:
    # ...
    workspace: Workspace  # 现在是 session 级的 workspace

    @classmethod
    def load(cls, repo_root: Path, session_id: str) -> "Orchestrator":
        """需要传入 session_id 来创建/加载 workspace"""
        workspace = Workspace.create(
            repo_root=root,
            session_id=session_id,
            permission=permission,
            ownership=ownership,
            ruleset_ownership=ruleset.ownership,
        )
        # ...

    def run_task(self, task_id: str, ...):
        """在 session workspace 中运行 task"""
        # task 的工作目录现在是 self.workspace.source_root
        # 产物写入 self.workspace.task_dir(task_id)
        ...
```

#### 2.4.3 Artifact Agent 变更

```python
# runtime/agents/artifact.py

class ArtifactAgent:
    def generate_artifact(self, task_id: str, workspace: Workspace, ...):
        # 产物路径: workspace.task_dir(task_id) / "artifacts" / ...
        task_artifact_dir = workspace.task_dir(task_id) / "artifacts"
        # 不再用 workspace/task_xxx/ 扁平结构
```

### 2.5 前端变更

#### 2.5.1 Workspace Panel 语义修正

[ArtifactPanel.tsx](fronted/components/layout/ArtifactPanel.tsx#L100-L161) — 当前称为 "Workspace" 的面板：

- 标题保持 "Workspace"，但内容逻辑改为以 Session 为维度组织
- 按 Task 分组展示仍然是合理的（便于追溯），但整体的 "Workspace" 属于 Session
- Empty state 文案：「No workspace content yet」→ 提示创建 session 后开始

#### 2.5.2 布局显示逻辑变更

[layout.tsx](fronted/app/(main)/layout.tsx#L155-L172) — `shouldShowWorkspacePanel`:

```typescript
// 旧逻辑：根据 latestTask 决定
const shouldShowWorkspacePanel = useMemo(() => {
  if (!latestTask) return hasArtifacts;
  if (latestTask.interaction_mode === "direct_agent" && hasArtifacts) return true;
  // ...
}, [latestTask, hasArtifacts]);

// 新逻辑：根据 session 决定
const shouldShowWorkspacePanel = useMemo(() => {
  // Session 有 workspace 且存在任何产物时就显示
  if (!currentSession) return false;
  if (hasArtifacts) return true;
  // 或者 session 明确声明需要 workspace
  if (currentSession.workspace_id) return true;
  return false;
}, [currentSession, hasArtifacts]);
```

#### 2.5.3 TaskSummary 清理

移除 `TaskSummary` 中与 workspace 直接相关的冗余字段：
- `workspace_required` — 移除（workspace 现在是 session 级的默认能力）
- `bundle_required` — 保留（bundle 仍然是 task 级别的可选需求）

### 2.6 API / Gateway 层变更

#### 2.6.1 Session 创建时自动创建 Workspace

```
POST /api/v1/sessions
→ 创建 Session 记录
→ 创建 Workspace (workspace/{session_id}/)
→ 返回 SessionDetail (含 workspace_id)
```

#### 2.6.2 新增 Workspace 查询端点

```
GET /api/v1/sessions/{sessionId}/workspace
→ 返回 WorkspaceMeta（文件数、磁盘占用、最后更新时间等）
```

#### 2.6.3 Session 删除时清理 Workspace

```
DELETE /api/v1/sessions/{sessionId}
→ 删除 Session 记录
→ 清理 Workspace 目录 (可配置为归档而非物理删除)
→ 返回操作结果
```

### 2.7 ADR-004 更新

[ADR-004 产物存储规范](docs/specs/ADR/ADR-004-artifact-storage.md) 需要更新目录规范部分：

```yaml
# 旧规范
workspace/
  ├─ task_001/
  │  ├─ source/
  │  ├─ artifacts/
  │  └─ preview/

# 新规范
workspace/
  ├─ {session_id}/
  │  ├─ source/          # 共享源文件
  │  ├─ tasks/           # 按任务归档
  │  │  └─ {task_id}/
  │  │     ├─ artifacts/
  │  │     └─ diffs/
  │  ├─ snapshots/       # 版本快照
  │  ├─ bundles/
  │  └─ preview/
```

## 3. 实施计划

### 3.1 分步实施

| 步骤 | 内容 | 影响范围 | 优先级 |
|------|------|---------|--------|
| **Step 1** | 更新类型定义 (`types/index.ts`) | 前端类型 | P0 |
| **Step 2** | 重构 `Workspace` 类，引入 `session_id` | Runtime Python | P0 |
| **Step 3** | 更新 `Orchestrator.load()` 接受 `session_id` | Runtime Python | P0 |
| **Step 4** | 调整 Artifact Agent 产物路径 | Runtime Python | P0 |
| **Step 5** | 更新前端 `shouldShowWorkspacePanel` 逻辑 | 前端布局 | P1 |
| **Step 6** | Session 创建 API 关联 Workspace 创建 | Gateway | P1 |
| **Step 7** | Session 删除 API 关联 Workspace 清理 | Gateway | P1 |
| **Step 8** | 新增 `/sessions/{id}/workspace` 端点 | Gateway | P1 |
| **Step 9** | 更新 ADR-004 文档 | 文档 | P1 |
| **Step 10** | 添加 Workspace Store (前端状态管理) | 前端 | P2 |
| **Step 11** | 迁移现有 artifacts 目录结构 | 数据迁移 | P2 |

### 3.2 兼容性策略

- **向下兼容**：Workspace 类增加 `session_id` 参数但保留默认值，旧调用路径不受影响
- **数据迁移**：现有 `workspace/task_xxx/` 目录在迁移前保持可读
- **渐进式**：先改 Runtime，再改 Gateway，最后改前端

## 4. 风险与注意事项

1. **并发 Task 操作同一文件**：所有 Task 共享 `source/` 目录后，文件锁机制（`ownership.acquire_write_lock`）变得更重要。现有的 ownership 机制已经支持这一点。

2. **Workspace 磁盘膨胀**：Session 级 workspace 可能积累大量文件。需要配合 Session 归档策略，定期清理过期 workspace。

3. **快照粒度**：从 task 级改为 session 级后，快照策略需要更新——每次 task 完成时对 source/ 做增量快照。

4. **回滚语义**：回滚到某个 task 之前的状态 = 恢复到该 task 执行前的快照。快照与 task 关联。

## 5. 与现有 Stage-8 改造的关联

本改造与 Stage-8 其他改进项的关系：

- **存储统一（P1）**：Workspace 元数据可存入 PostgreSQL 统一存储层
- **多文件读写优化** ✅：Workspace 的共享 source 目录天然支持多文件操作
- **Orchestrator 拆分（P1）**：拆出的模块需要感知 session 级的 workspace
- **User-Defined Agent** ✅：自定义 Agent 的 prompt 中可注入 workspace 上下文
