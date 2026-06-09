# Worklog / Tasks（比赛提交版）

<br />

- [x] 1\. 接入规则输入
  - [x] 按 `/rules/index.json` 加载 execution/permission/ownership/communication 四类 policy
  - [x] 提供最小校验入口（validator）用于比赛演示“规则可加载、可校验”
- [x] 2\. 最小单进程闭环（Orchestrator + 3 Agents）
  - [x] Orchestrator：统一路由、workflow 串行推进、消息 envelope 校验
  - [x] Coding Agent：输出结构化变更（含 base\_hash）
  - [x] Review Agent：输出 pass/fail 与 issues
  - [x] Artifact Agent：归档 metadata + workspace snapshot
- [x] 3\. 冲突控制（满足比赛“不会冲突写入”）
  - [x] 同文件写锁/串行化（ownership）
  - [x] base\_hash 版本基线检查（workspace）
- [x] 4\. 运行时目录职责重构
  - [x] 将规则加载归位到 `runtime/config/`
  - [x] 将权限/ownership/workspace/validator 归位到 `runtime/harness/`
  - [x] 删除旧入口 shim，统一从新路径 import
- [x] 5\. 验证与回归
  - [x] `python3 -m runtime.demo`：跑通一条 task workflow
  - [x] `python3 -m runtime.smoke_test`：成功标志回归
  - [x] `python3 -m runtime.harness.validator.validate_rules`：规则加载校验

