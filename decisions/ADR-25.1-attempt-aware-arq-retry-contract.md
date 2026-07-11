# ADR-25.1: ARQ 基础设施错误采用 attempt-aware 显式重试契约

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
