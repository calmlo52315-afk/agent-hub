🔴 P0 — Review 闭环 ✅ DONE
    └─ claude_review skill 已注册，auto-upgrade 自动生效

🔴 P0 — User-Defined Agent ✅ DONE  
    ├─ Gateway: AgentDefinitionStore + SQLite 表 + CRUD API (6 routes)
    ├─ Python: PersonaLoader + AgentPromptBuilder + 5 内置 Agent
    ├─ Orchestrator 集成: persona 加载 → prompt 注入 → skill 白名单检查
    └─ 详见 docs/stages/stage-8-improvement/user-defined-agent.md

🟡 P1 — 存储统一（为后续所有功能打地基）
    ├─ 引入 PostgreSQL，Gateway Store + Replay Store 二合一
    ├─ 替代两个独立 SQLite
    └─ 不然后面做幂等、DAG、预算统计都要反复补存储层

🟡 P1 — Orchestrator 拆分（再不拆就改不动了）
    ├─ 2624 行太大了，_call_skill / _call_agent / _normalize_* 
    │   应该抽出独立模块
    └─ 最好跟 P0 一起做，因为加 review 会继续膨胀它

🟢 P2 — 多文件读写优化 ✅ DONE
    ├─ Delta 检测、冲突避免、批量回滚
    ├─ 新增 runtime/harness/snapshot.py：快照 + Delta 模块
    ├─ 集成到 external_cli.py：执行前快照、执行后 Delta、forbidden check + rollback
    └─ 详见 docs/stages/stage-8-improvement/multi-file-optimization.md

🟢 P2 — Skill 粒度 Replay
    └─ 按 todo.md 里写的做，先补事件再补幂等

🔵 P3 — 多层 DAG / 返工回路
    └─ Review fail → 自动触发 coding rework → 再次 review