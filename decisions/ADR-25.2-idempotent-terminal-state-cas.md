# ADR-25.2: 任务失败终态使用 user-scoped 条件更新并保留可恢复事实

**Slug**: `idempotent-terminal-state-cas`
**Status**: accepted
**Date**: 2026-07-11

### Context

异步任务当前使用 `QUEUED → RUNNING → UPLOADED` 状态链。基础设施错误发生时任务已被置为 `RUNNING`；历史 ADR-060 已登记：如果重试耗尽后只重新抛出异常，任务会永久停留在 `RUNNING`，而现有 `force=true` 又拒绝活动 `RUNNING`，用户没有恢复路径。

终态写入还必须处理并发与重复调用：同一最终失败动作可能被测试、worker 重入或未来恢复路径重复触发；与此同时，已经成功进入 `UPLOADED / COMPLETED` 的任务绝不能被迟到的失败动作覆盖。所有读写继续显式包含 `user_id`，不得只按内容寻址的 `task_id` 更新。

Stage 25 还需要保存当前运行周期的 attempt、结构化失败原因和最终失败时间，并保证 `FAILED` 的显式 force requeue 不产生重复业务记录。`db/schema.sql` 与 service `Table` 定义必须同步演进。

### Options Considered

- **Option A：在现有任务表上执行 user-scoped 状态 CAS，并保存当前运行周期恢复字段（采纳）**
  - Pros：改动集中；复用现有任务状态机和内容寻址幂等；单条条件更新天然支持重复执行 no-op；无需新增存储或事件消费链路。
  - Cons：任务行主要表达当前生命周期快照，不提供完整 attempt 事件历史；force requeue 时必须明确哪些字段重置、哪些累计事实保留；现有 replace 语义需要防止成功后丢失 attempt 信息。
- **Option B：无条件把任务更新为 `FAILED`**
  - Pros：实现最简单；无需设计状态前置条件。
  - Cons：迟到或重复的失败动作可能覆盖 `UPLOADED / COMPLETED`；无法区分首次终结与重复调用；存在跨状态竞态风险。
- **Option C：新增独立 job-run / attempt event 表**
  - Pros：可以保留每次 attempt、force 和失败的完整历史；长期指标表达最完整。
  - Cons：新增表、关联查询、生命周期与迁移范围显著扩大；Stage 29 已规划统一 Trace / Replay，本 Stage 提前建设事件系统会重复设计。

### Decision

采用 **Option A**。

- 提供幂等终态操作，更新条件必须同时包含 `user_id`、`task_id` 和当前状态属于 `{QUEUED, RUNNING}`；只有条件命中时才写入 `FAILED`。
- 终态操作保存：1-based job attempt count、稳定的失败类型、脱敏后的错误摘要、retry-exhausted 标记和最终失败时间。不得持久化原始财务文件内容、认证信息、连接串或完整异常对象。
- 同一终态操作重复执行时返回 no-op，不重复增加 exhausted 事实；如果任务已进入 `UPLOADED / AI_RUNNING / COMPLETED`，必须保持原状态和业务结果不变。
- 成功 recovery 必须在异步对账替换任务统计之后重新保存最终 attempt 和 retry-recovered 标记，避免现有 delete-and-insert 语义抹掉恢复证据。
- `FAILED` 继续属于可显式 force requeue 的终态。force requeue 创建同一 `task_id` 的新运行周期：清空当前周期的 attempt / failure / exhausted 字段，保留并增加累计 force requeue count；现有 `UPLOADED / COMPLETED` force 语义不变。
- 活动 `RUNNING` 继续拒绝 force，避免旧 worker 与新运行周期并发写同一 `task_id`。Stage 25 不引入 run generation、租约接管或强制取消正在执行的 worker。
- 继续复用既有 replace 覆盖与事务边界，不新增业务结果表，不改变同步 upload、start-live 或已完成任务的幂等语义。

### Consequences

- 正面：重复终结安全，迟到失败不能覆盖成功；`FAILED` 能通过既有显式 force 路径恢复；所有状态变化保持 tenant isolation。
- 正面：结构化字段可以同时支持任务查询、故障注入断言和 ADR-25.3 的指标聚合，无需新增 event store。
- 负面：现有任务表和 MySQL DDL 都需要增加恢复字段；成功路径必须在任务统计替换后恢复 attempt 元数据，增加一次受控状态写入。
- 负面：当前任务行不是完整审计历史；force requeue 会开始新周期，历史 attempt 明细留待 Stage 29 Trace / Replay，而非在本 Stage 建设。
- 负面：最终 CAS 本身仍依赖任务数据库可写。如果数据库在第 3 次业务操作失败后仍持续不可用，无法仅靠同一数据库绝对保证终态落盘；该情况必须通过 stuck 指标暴露，Stage 25 不把这一跨存储可用性限制包装成已解决。
