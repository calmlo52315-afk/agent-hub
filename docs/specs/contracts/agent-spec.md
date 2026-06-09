# Agent Spec

## 1. 目标

为 AgentHub MVP 的各类 Agent 定义统一、可复用、可机器解析的规范，包括：

- 角色与职责边界
- 输入/输出 schema（I/O Contract）
- 能力声明（Capability）
- 与权限（permission）与归属（ownership）的关联方式

## 2. 术语

- Agent：在 Orchestrator 管理下执行单一职责的执行体。
- Orchestrator：唯一的消息路由与工作流调度者。
- Contract：Agent 的输入/输出结构约束（JSON）。

## 3. 角色（Roles）

MVP 固定三类核心 Agent：

- Coding Agent：产出变更计划、diff、（可选）测试与自检结果
- Review Agent：对变更与约束进行审查，产出问题清单与结论
- Artifact Agent：将通过评审的产物归档并输出元数据

约束：

- Agent 间不得直连通信，必须经由 Orchestrator 路由（见 [communication-rules](../../../rules/communication-rules.json)）
- Agent 的文件操作必须符合权限规则（见 [permission-rules](../../../rules/permission-rules.json)）
- 变更文件的并发访问必须符合归属/锁规则（见 [ownership-rules](../../../rules/ownership-rules.json)）

## 4. 能力声明（Capability）

Agent 通过 capabilities 声明自身允许执行的动作集合，Orchestrator 在分发任务与校验输出时应对齐该声明。

能力最小集合（建议）：

- `plan`：生成执行计划
- `read_repo`：读取仓库文件
- `propose_patch`：提出变更（diff/patch）但不直接落盘
- `review_patch`：对 diff/patch 做审查
- `write_artifact`：写入 artifact/归档产物

## 5. I/O Contract（JSON Envelope 内的 payload）

消息 envelope 由 Message Spec 定义；本节仅定义 payload 结构。

### 5.1 Coding Agent

**Input: `CodingInput`**

```json
{
  "task": {
    "id": "string",
    "title": "string",
    "description": "string",
    "acceptance_criteria": ["string"]
  },
  "context": {
    "repo_root": "string",
    "pinned": ["string"],
    "recent_messages": ["string"],
    "artifacts": [
      {
        "id": "string",
        "type": "string",
        "summary": "string",
        "path": "string"
      }
    ]
  },
  "constraints": {
    "permission_policy_id": "string",
    "ownership_policy_id": "string"
  }
}
```

**Output: `CodingOutput`**

```json
{
  "plan": [
    {
      "step_id": "string",
      "title": "string",
      "files": ["string"],
      "actions": ["string"]
    }
  ],
  "changes": [
    {
      "path": "string",
      "action": "create|update|delete",
      "diff": "string"
    }
  ],
  "self_check": {
    "summary": "string",
    "risks": ["string"]
  }
}
```

### 5.2 Review Agent

**Input: `ReviewInput`**

```json
{
  "task": { "id": "string" },
  "changes": [
    { "path": "string", "action": "create|update|delete", "diff": "string" }
  ],
  "policies": {
    "execution": "object",
    "permission": "object",
    "ownership": "object",
    "communication": "object"
  }
}
```

**Output: `ReviewOutput`**

```json
{
  "decision": "pass|fail",
  "score": {
    "value": 0,
    "max": 100
  },
  "issues": [
    {
      "id": "string",
      "severity": "high|medium|low",
      "type": "policy|schema|logic|style|security|performance|other",
      "message": "string",
      "paths": ["string"]
    }
  ],
  "suggestions": ["string"]
}
```

### 5.3 Artifact Agent

**Input: `ArtifactInput`**

```json
{
  "task": { "id": "string" },
  "decision": "pass|fail",
  "changes": [
    { "path": "string", "action": "create|update|delete", "diff": "string" }
  ],
  "review": {
    "score": { "value": 0, "max": 100 },
    "issues": ["object"]
  }
}
```

**Output: `ArtifactOutput`**

```json
{
  "bundle": {
    "artifact_id": "string",
    "paths": ["string"]
  },
  "metadata": {
    "task_id": "string",
    "created_at": "string",
    "hashes": [
      { "path": "string", "sha256": "string" }
    ]
  }
}
```

## 6. 与 ownership/permission 的关联

- Orchestrator 在投递 `CodingInput.constraints` 时引用策略 ID，要求 Agent 产出的 `changes[].path` 必须满足：
  - permission：允许的读写/删除范围与操作类型
  - ownership：对变更文件的 owner/锁策略约束（串行化/最小合并）

## 7. 参考

- [ADR-006-agent-spec](../../ADR/ADR-006-agent-spec.md)
- [project rules](../rules/global/project.md)
