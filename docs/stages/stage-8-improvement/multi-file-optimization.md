# Stage 8 — 多文件读写优化：快照 + Delta + 并发安全

## 问题背景

AgentHub 的编码管线有两类执行路径：

| 路径 | 文件写入方式 | 并发安全 |
|---|---|---|
| **内置 Agent** (CodingAgent) | 通过 `Workspace.apply_change()` → 有锁、有版本校验 | ✅ |
| **外部 CLI** (Claude Code / Codex) | `subprocess` 拉起 `claude -p` → **直接写磁盘** | ❌ |

外部 CLI 的执行模型是黑盒的——我们不知道它读了哪些文件、写了哪些文件、改了什么内容。当前的应对方式是在 CLI 执行后用 `_scan_workspace_for_files()` 做**全目录扫描**，有四个致命缺陷：

1. **不知道真正改了什么** — 扫描把已有文件和新建文件混在一起，丢失 diff 信息
2. **无并发保护** — 两个 Claude Code 同时跑会互相踩文件
3. **无回滚能力** — 外部 CLI 写了不该写的文件，无法撤销
4. **O(n) 性能** — 每次都遍历整个工作区

## 解决方案：快照 + Delta 机制

### 核心思路

```
Before CLI:  [拍摄快照] → 记录 scope 内所有文件的 path→hash+size
     │
     ▼
  [执行外部 CLI]  (claude -p "...")
     │
     ▼
After CLI:   [计算 Delta] → 对比快照 vs 当前磁盘
     │
     ├─ created:   快照中没有，磁盘中新增
     ├─ modified:  哈希变化
     ├─ deleted:   快照中有，磁盘中删除
     └─ unchanged: 哈希一致
     │
     ▼
  [安全检查] → forbidden? → rollback / 拒绝
  [替换 changes] → 精确的变更列表替代全量扫描
```

### 实现模块

新增 `runtime/harness/snapshot.py`（~170 行），核心数据结构：

```
WorkspaceSnapshot.capture(repo_root, scope)
    │
    ├─ .compute_delta() → WorkspaceDelta
    │   ├─ .changes         (created + modified + deleted)
    │   ├─ .has_forbidden_changes(write_paths, deny_paths) → bool
    │   ├─ .summary()       → {total, created, modified, deleted, unchanged}
    │   └─ .to_changes_payload() → AgentHub Coding Agent 兼容格式
    │
    └─ .rollback(delta)  — 恢复文件到快照状态
```

### 集成点

在 `ExternalCLIExecutor.execute()` 中（[external_cli.py](runtime/skills/external_cli.py)）：

1. **执行前**：`WorkspaceSnapshot.capture(repo_root, scope=permission_scope 中的读写路径)`
2. **执行后**：`snapshot.compute_delta()` 获取精确变更
3. **安全检查**：`delta.has_forbidden_changes()` → 若违反 → `snapshot.rollback()` + 抛异常
4. **输出增强**：用 `_enrich_parsed_with_delta()` 将 delta 合并到解析结果中，替换旧的 changes 列表

### 解决的并发问题

| 场景 | 之前 | 之后 |
|---|---|---|
| 两个 coding 任务并发 | 可能互相覆盖文件（无保护） | 快照捕获文件状态，delta 检测冲突 |
| 外部 CLI 写入超出权限范围的文件 | 发现不了，静默通过 | `has_forbidden_changes` 检测 + rollback |
| CLI 执行后想知道改了什么 | 全量扫描（O(n)，丢失 diff） | Delta 精确报告 created/modified/deleted |
| CLI 崩溃后文件状态被破坏 | 无法恢复 | 快照支持 rollback |

## 使用示例

```python
from runtime.harness.snapshot import WorkspaceSnapshot

# 拍摄快照
snap = WorkspaceSnapshot.capture(repo_root, scope=["demo_workspace/**"])

# ... 执行外部 CLI ...

# 获取变更
delta = snap.compute_delta()
print(delta.summary())
# => {"total": 3, "created": 1, "modified": 2, "deleted": 0, "unchanged": 5}

# 安全检查
if delta.has_forbidden_changes(
    write_paths=["demo_workspace/**"],
    deny_paths=["**/secret/**"],
):
    snap.rollback(delta)
    raise ForbiddenError(...)
```

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `runtime/harness/snapshot.py` | **新增** | 快照 + Delta 核心模块 |
| `runtime/skills/external_cli.py` | **修改** | 集成 snapshot/delta 到 execute() |
| `runtime/specs/registries/skills.registry.json` | 已有 | permission_scope 的 read_paths/write_paths 被 snapshot 读取 |
| `docs/stages/stage-8-improvement/multi-file-optimization.md` | **新增** | 本文档 |

## 与已有并发原语的关系

| 已有机制 | 继续使用 | 说明 |
|---|---|---|
| `OwnershipManager.acquire_write_lock` | ✅ | 内置 Agent 仍走锁机制 |
| `LockReservation` (调度器租约) | ✅ | DAG 调度器的跨任务协调 |
| `Workspace.apply_change` (版本校验) | ✅ | 内置 Agent 的写入入口 |
| **Snapshot + Delta** | **新增** | 外部 CLI 的专属保护层 |

四层并发保护互补，互不替代：
- **Snapshot** = 外部 CLI 的事前/事后保护
- **Write Lock** = 内置 Agent 的写入保护
- **LockReservation** = 调度器级别的时间窗口保护
- **Version Check** = 乐观锁，检测中途被改

## 性能收益

| 指标 | 旧方案 (`_scan_workspace_for_files`) | 新方案 (Snapshot + Delta) |
|---|---|---|
| 时间复杂度 | O(n) 全目录遍历 | O(n) 快照拍摄 + O(m) delta 对比 (m=变化文件数) |
| 变更精度 | 无 diff 信息 | created/modified/deleted 精确分类 |
| 安全检查 | 无 | `has_forbidden_changes` |
| 回滚能力 | 无 | `rollback()` |

## 后续扩展方向

- [ ] **内容级快照**（当前只拍哈希）— 支持完整文件内容回滚
- [ ] **增量快照** — 对大型项目只快照 git-diff 范围的文件
- [ ] **并发写冲突自动解决** — 当两个任务修改同一文件时尝试 merge
- [ ] **快照缓存** — 复用同一 workspace 的 base snapshot，只重拍变更部分
