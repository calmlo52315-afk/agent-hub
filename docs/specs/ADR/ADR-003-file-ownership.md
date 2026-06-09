ADR-003 文件所有权 & 冲突策略
决策
全局采用 one_file_one_owner 单文件单归属原则，结合目录级所有权绑定 + 文件锁机制，从源头杜绝跨主体篡改。

背景与选择原因
1. 代码冲突核心根源为多主体同时修改同一文件；目录+文件绑定可从分配阶段拦截风险；
2. 明确只读/读写权限，统一规则，AI/开发不会出现越权修改。
方案详情（目录所有权配置）
# 文件所有权配置
ownership_rules:
  coding_frontend:
    write:
      - frontend/**
    read: all
  coding_backend:
    write:
      - gateway/**
      - runtime/**
    read: all
  coding_db:
    write:
      - db/**
      - sql/**
    read: all
  review_agent:
    write: []       # 只读权限
    read: all
  artifact_agent:
    write:
      - workspace/**/artifacts/
      - workspace/**/preview/
    read: all

冲突处理策略
1. 事前规避：Orchestrator 分配任务前校验所有权，非归属 Agent 直接拒绝分配；
2. 运行防护：搭配全局文件锁，已占用文件禁止二次写入；
3. 事后处置：出现非归属修改 → 判定为违规操作，自动回滚并记录告警。
边界约束
1. 一个文件/目录仅绑定一个可写主体；
2. Review、Artifact 类角色默认全局只读，仅允许操作产物目录；
3. 禁止手动修改所有权配置，变更需统一走配置文件更新。
演进路径
复杂项目可补充代码块级行号锁，支持单文件内多区域并行编辑。