# ADR-25.3: 恢复指标采用 DB-backed 当前事实与真实 worker 故障注入

**Slug**: `db-backed-recovery-observability`
**Status**: accepted
**Date**: 2026-07-11

### Context

Stage 25 需要验证 retry count、retry recovery、exhausted、stuck `RUNNING` 和 force requeue 结果。当前 dashboard 的 `hung_count` 实际只统计 `AI_RUNNING`，不能被静默改名或复用为 ARQ stuck 指标；否则会改变既有前端含义。进程内计数也无法跨 worker 重启，并且无法按 `user_id` 隔离。

现有 `tests/test_worker_retry.py` 直接调用 service，只能证明基础设施异常被重新抛出，不能证明 ARQ 真的执行三次、`arq.Retry` 重新排队、最终 job 结果失败或重复终结安全。Stage 25 的证据必须覆盖真实 worker 调度语义，同时继续遵守 ADR-061：默认自动测试使用 fakeredis，不依赖外部 Redis 守护进程。

### Options Considered

- **Option A：从任务表恢复字段计算 user-scoped snapshot，并用真实 ARQ worker + fakeredis 做故障注入（采纳）**
  - Pros：重启后仍可查询；与终态事实同源；无需真实 Redis；能证明重试调度而非只证明异常传播；可保持既有 dashboard `hung_count` 语义不变。
  - Cons：主要表达当前任务事实而非每个 attempt 的时间序列；age-based stuck 判定依赖统一阈值；真实 worker 测试比直接函数测试更慢、更复杂。
- **Option B：使用 worker 进程内 counters**
  - Pros：写入成本低；实现快速。
  - Cons：worker 重启即丢失；多 worker 无法可靠聚合；难以按 `user_id` 隔离；不能作为任务恢复的持久证据。
- **Option C：本 Stage 引入独立指标事件表、Trace 平台或外部监控系统**
  - Pros：事件历史和时间序列最完整；便于长期分析。
  - Cons：与 Stage 29 Trace / Replay 范围重叠；需要额外 schema、写入可靠性和聚合设计；不符合 Stage 25 的窄修复目标。

### Decision

采用 **Option A**。

- 在后端 `MetricsService` 提供独立的 ARQ recovery snapshot，不改变既有 `hung_count` 的语义，也不要求 Stage 25 增加前端页面或外部监控依赖。
- snapshot 至少包含：retry count、retry recovered count / rate、retry exhausted count、age-based stuck `RUNNING` count 和 force requeue count；所有聚合显式按 `user_id` 过滤。
- 除累计 force requeue count 外，上述指标表达每个任务最新运行周期的当前事实，不宣称为跨运行周期的历史事件总量；完整 attempt 历史留待 Stage 29。
- retry count 从当前运行周期的 attempt 事实推导；retry recovered 只在 attempt 大于 1 且 worker 成功完成时成立；exhausted 只统计 ADR-25.2 成功写入的最终耗尽事实。
- stuck `RUNNING` 必须使用状态加年龄阈值判断，不能把所有正常执行中的 `RUNNING` 都算作 stuck。阈值与 worker job timeout 使用同一配置来源，且不得短于单次 job timeout；精确配置名和默认值在 `spec.md` 冻结。
- 每次 attempt、scheduled retry、recovered、exhausted、terminal no-op 和 force requeue 输出结构化日志，至少包含 `user_id`、`task_id`、当前 attempt、最大 attempt、稳定错误类型和 outcome；错误摘要遵循 ADR-25.2 的脱敏边界。
- 故障注入必须覆盖：第 1 次失败后第 2 次成功、第 1/2 次失败后第 3 次成功、第 3 次耗尽、终态操作重复执行、成功任务保护、`FAILED` force requeue 和跨用户隔离。
- 至少一组测试必须通过真实 ARQ `Worker` 与 fakeredis 推进队列和 retry，不得全部以直接调用 `run_reconciliation_job()` 替代。全量测试仍保持零外部 Redis、零模型密钥。
- 本 Stage 不建立完整 attempt 历史、分布式 Trace、告警系统或生产 SLA；这些属于 Stage 29 或后续部署工作。

### Consequences

- 正面：恢复指标来自持久化任务事实，worker 重启后仍可验证，并保持用户隔离；测试能够发现 ARQ 依赖升级或重试语义漂移。
- 正面：不破坏现有 dashboard `hung_count` 和前端展示，不提前引入 Stage 29 的 Trace 架构。
- 负面：snapshot 不是完整时间序列；force 开启新运行周期后，只保留明确声明的累计 force 事实和当前周期恢复状态。
- 负面：age-based stuck 是操作性判断，不等同于证明 worker 永久死亡；阈值过短会误报慢任务，过长会延迟暴露真实悬挂，需要通过故障注入校准。
- 负面：真实 ARQ worker 测试会增加测试复杂度和少量执行时间，但这是证明 Stage 25 契约所必需的成本。
