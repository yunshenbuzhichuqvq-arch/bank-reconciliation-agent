# ADR-28.3: Tool 使用有界超时与局部重试并保留 ARQ 和 RAG breaker 边界

**Slug**: `bounded-tool-timeout-retry-and-breaker`
**Status**: accepted
**Date**: 2026-07-12

### Context

三个底层能力当前都是同步调用。仅在函数返回后统计耗时不能形成可验证的 timeout contract；只依赖
各依赖自行抛出超时，又无法为 SQL、Chroma 和本地适配器提供统一故障注入语义。

Stage 25 与 `decisions/ADR-25.1-attempt-aware-arq-retry-contract.md` 已冻结 job retry 边界：
`RedisConnectionError` 和 SQLAlchemy `OperationalError` 必须到达 worker，由 ARQ 执行最多三个 job
attempts。Stage 28 不得把这些错误吞成普通 Tool failure。

同时，`decisions/ADR-029-circuit-breaker-rag-only.md` 已决定 breaker 只保护 RAG，但其 OPEN 时返回空
检索的旧表达会把依赖故障与 ADR-28.2 的 `EMPTY` 混为一谈。

### Options Considered

- **Option A：有界共享线程池 + Tool 内一次重试 + 保留 ARQ/RAG 专属边界（采纳）**
  - Pros：不引入新依赖即可为同步 Tool 提供统一且可测试的 timeout；只读调用允许安全的有限重试；保留既有 job recovery 和 RAG breaker 能力。
  - Cons：Python 线程无法被安全强杀，timeout 后底层调用可能短暂继续占用线程；Tool 与 ARQ 形成两层 attempt 计数，需要清晰观测。
- **Option B：只依赖底层依赖的原生 timeout**
  - Pros：不增加线程池；依赖最了解自己的取消语义。
  - Cons：三个 Tool 无法形成统一 contract；部分本地同步调用没有可注入 timeout，测试只能模拟异常而不能验证执行边界。
- **Option C：迁移为异步调用、独立进程或外部任务系统**
  - Pros：可以获得更强的取消和资源隔离能力。
  - Cons：需要改造同步工作流、依赖和部署拓扑，明显超出 Stage 28；为三个只读 Tool 引入过度复杂度。

### Decision

采用 **Option A**。

- Tool 底层调用在共享、固定容量的线程池中执行；registry 为每个 Tool 声明固定 timeout，调用方不得自行扩大预算。
- 达到 timeout 后执行 best-effort `cancel()` 并记录 `TIMEOUT`。因为运行中的 Python 线程不能被强制终止，所有 Stage 28 Tool 必须保持只读，晚完成不得产生业务写副作用。
- `TIMEOUT` 和明确声明的 `TRANSIENT_READ_ERROR` 最多原地重试一次，因此单个逻辑 Tool call 最多两个 1-based physical attempts。
- `UNKNOWN_TOOL`、`VALIDATION_ERROR`、`PERMISSION_DENIED`、`INTERNAL_ERROR` 和 `CIRCUIT_OPEN` 不重试；`EMPTY` 不是错误，也不重试。
- Tool timeout、线程池容量、退避与重试上限引用单一策略来源，禁止在 adapter 和 executor 中维护可漂移的重复数值。
- `RedisConnectionError` 和 SQLAlchemy `OperationalError` 在 Tool 层最终仍原样上抛，不转换为终态 `ToolCallResult`，由 ADR-25.1 的 worker 边界决定 ARQ job retry 或 exhaustion。Tool attempt 与 ARQ job attempt 分别记录，不合并成一个计数。
- RAG circuit breaker 继续只保护 `search_rules`，不扩展到另两个 Tool。其状态协调下沉到 `search_rules` Tool 边界，每个物理检索失败按现有状态机计入 breaker。
- breaker OPEN 时返回 `FAILED/CIRCUIT_OPEN` 且不可重试，工作流仍转人工。本条只修订 ADR-029 中“OPEN 表达为空检索”的结果语义，不改变 RAG-only breaker 的选择、阈值或状态机。

### Consequences

- 正面：三个同步 Tool 获得一致、可故障注入的 timeout/retry contract；瞬时只读故障可以在不重放整个 job 的情况下恢复。
- 正面：Redis/DB job recovery 与 RAG breaker 的既有职责继续保留，依赖不可用和正常无命中可以被准确区分。
- 负面：timeout 无法终止已经运行的 Python 线程；连续慢调用可能暂时耗尽有界线程池，必须通过容量限制、测试和观测承认该风险。
- 负面：同一异步任务可能经历最多两个 Tool attempts 和最多三个 ARQ job attempts；排查时必须同时展示两层计数，不能将其宣传为单一重试机制。
- 约束：本决策不引入新的 timeout 库、异步框架迁移、子进程执行器、Celery 或通用 resilience 平台。
