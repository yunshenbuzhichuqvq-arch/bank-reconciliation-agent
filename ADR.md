# Stage 25 — Architectural Decisions

## ADR-25.1: ARQ 基础设施错误采用 attempt-aware 显式重试契约

**Slug**: `attempt-aware-arq-retry-contract`  
**Status**: accepted  
**Date**: 2026-07-11

### Context

历史 `decisions/ADR-060-job-retry-vs-llm-retry-boundary.md` 已决定：ARQ job 级重试只覆盖 Redis / DB 瞬时基础设施错误，业务错误和 LLM 失败继续由既有确定性失败、有限重试与 Fallback 语义处理，避免整条任务重复消费 token 或重复落库。

当前实现把 `RedisConnectionError` / `OperationalError` 原样抛给 ARQ，并仅通过 `WorkerSettings.max_tries = 3` 表达重试上限。但仓库锁定的 ARQ 0.28 只会把 `arq.Retry`、内部 `RetryJob` 或特定取消路径重新排队；普通异常会直接记录为失败，不会因为 `max_tries` 自动执行三次。因此，现有代码和测试只证明异常被重新抛出，没有证明真实 ARQ worker 会完成“前两次重试、第三次耗尽”的契约。

Stage 25 必须先修正这一事实偏差，才能可靠处理 retry exhaustion。该修正细化 ADR-060 的实现机制，不改变 ADR-060 对 job retry 与 LLM / 业务失败的职责边界。

### Options Considered

- **Option A：worker 边界读取 ARQ `job_try`，显式抛出 `arq.Retry`（采纳）**
  - Pros：使用 ARQ 0.28 的公开重试语义；三次总 attempt 可被真实 worker 测试；基础设施错误分类仍由现有服务边界提供；最终失败可在最后一次 attempt 内确定性收口。
  - Cons：worker 需要感知 `ctx["job_try"]` 和统一的最大 attempt 配置；比单纯重新抛出异常多一层协调逻辑；ARQ 升级时需要回归验证上下文字段和 `Retry` 语义。
- **Option B：继续抛出普通异常并依赖 `max_tries`**
  - Pros：代码最少；保持当前表面结构。
  - Cons：与 ARQ 0.28 实际行为不符；普通异常第一次即结束，无法满足 Stage 25 的故障注入与重试恢复验收。
- **Option C：使用通用 lifecycle hook、DLQ 或外部 recovery daemon 统一处理失败**
  - Pros：可以演进为更通用的异步任务恢复平台；可承载跨任务失败事件历史。
  - Cons：ARQ 0.28 没有携带完整失败结果的通用 `on_job_failure` hook，部分 max-tries 分支也不会进入普通 job hook；引入 DLQ / daemon 明显超出本 Stage，违背最小切片原则。

### Decision

采用 **Option A**。

- ARQ attempt 使用 `ctx["job_try"]` 的 1-based 语义，最大总 attempt 固定为 3；重试判断与 `WorkerSettings` 必须引用同一策略来源，禁止出现两个可漂移的数字。
- 每次 attempt 开始时记录当前 attempt。服务层仍只把 `RedisConnectionError` / `OperationalError` 归为 job-retryable 基础设施错误。
- 当基础设施错误发生且当前 attempt 小于 3 时，worker 将其转换为 `arq.Retry`，由 ARQ 重新排队；不得把业务错误、LLM 失败、输入校验失败或 hard constraint violation 转成 job retry。
- 当第 3 次基础设施错误发生时，不再抛 `arq.Retry`。worker 先执行 ADR-25.2 定义的幂等失败终结，再重新抛出原异常，使 ARQ job 本身仍被记录为失败，而不是伪装成成功返回。
- 成功返回时持久化最终 attempt 和 retry-recovered 事实；后续任务状态从 `UPLOADED` 进入 `AI_RUNNING / COMPLETED` 时，该恢复事实不得丢失。
- 不把本决策描述为“接入通用 ARQ failure hook”；Stage 25 使用的是 attempt-aware worker boundary，因为这是当前依赖版本可验证的真实契约。

### Consequences

- 正面：第 1、2 次瞬时错误可以真实恢复，第 3 次耗尽具有确定路径；实现与锁定依赖行为一致；继续保护 ADR-060 的 token、幂等和 Fallback 边界。
- 正面：测试可以运行真实 ARQ worker，而不是只断言服务函数重新抛出异常。
- 负面：worker 与 ARQ 0.28 的 `job_try` / `Retry` API 形成显式耦合；依赖升级时必须重新验证重试次数、hook 顺序和最终结果记录。
- 负面：本决策只覆盖已声明的 Redis / DB 瞬时错误；错误分类遗漏仍可能导致本应重试的异常直接失败，或把不可重试错误错误放大为整任务重放。

## ADR-25.2: 任务失败终态使用 user-scoped 条件更新并保留可恢复事实

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

## ADR-25.3: 恢复指标采用 DB-backed 当前事实与真实 worker 故障注入

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
