# ADR-054: 单任务指标聚合归属 —— 扩展 metrics.py 而非新服务

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/metrics.py, decisions/ADR-047(指标数据源分层:线上 SQL 聚合 + 离线快照), decisions/ADR-014(task-ai-stats replace 语义)

## Context

报告数字需 per-task 聚合(总笔数/金额、自动平账率、异常分布、Agent 决策分布、Fallback 分布、复核数、Token/成本),但 `metrics.py` 现仅有全局 `get_dashboard(user_id)`,无单任务聚合。聚合逻辑放哪。

## Options

**A. 扩展 metrics.py 加 `get_task_report_metrics(*, user_id, task_id)`(选定)** —— 聚合集中在 metrics 一处,全局与单任务同源同口径。
- Pros: 聚合口径单一可信源,避免两处 SQL 漂移;复用 ADR-047 分层与现有表;report_service 只编排不算数。
- Cons: metrics.py 体量增长(需留意是否过大,过大则拆模块)。

**B. 新建 report 专属聚合服务** —— Cons: 同样的 SQL 聚合散到两个服务,口径易漂(项目已有 schema/口径漂移的教训)。

**C. 在 report_service 里直接写 SQL** —— Cons: 业务编排层混入聚合 SQL,违背现有分层。

## Decision

选 A。新增 `get_task_report_metrics(user_id, task_id)` 到 metrics.py,与 dashboard 共用聚合口径与 `user_id` 过滤;report_service 仅消费,不自行算数。

## Consequences

正向:
- 全局/单任务聚合单一可信源,口径不漂;复用既有表与 replace 语义。

负向 / 成本:
- metrics.py 增长 —— 若超出单文件合理体量,后续按 dashboard / report 聚合拆分。
- 共享聚合代码须保证 `user_id` 过滤在两条路径上都生效(租户隔离红线;本 stage 已在 task/ledger/review/rag 四组查询全部 `where(user_id==, task_id==)`)。
