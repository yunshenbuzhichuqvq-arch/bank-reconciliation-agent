# ADR-26.1: 真实 LLM 调用采用分层错误治理与 Provider 包装链

**Slug**: `layered-llm-failure-governance`
**Status**: accepted
**Date**: 2026-07-11

## Context

现有 `LLMProvider` 已统一承载 Audit、Extraction、Trace 等调用点，并通过
`CachingLLMProvider` 与 `RateLimitedLLMProvider` 形成
`Caching(RateLimited(provider))` 包装顺序。`DeepSeekProvider` 当前把所有 SDK 异常统一转换为
`LLMUnavailable`，调用方无法区分超时、上游限流、服务端错误和认证/配置错误，也无法据此执行稳定的
retry、breaker 与 fallback 策略。

历史 ADR-005 已确定 Fake provider 是默认离线测试路径，真实 DeepSeek 是 opt-in 外部依赖；
ADR-068 已确定缓存命中不得占用上游限流配额；ADR-071 已确定每次真实出网调用都必须独立经过限流，
且 LLM 失败不得升级为 ARQ job 级重试。Stage 26 需要细化这些边界，同时避免把重复治理逻辑散落到
各 Agent 或 Workflow。

## Options Considered

- **Option A：在 Provider 边界增加错误分类、有限重试与真实 provider breaker 包装器（采纳）**
  - Pros：所有调用点共享同一策略；每次物理重试都经过限流；Cache hit 可在治理链之前短路；
    transport 治理与 Agent 业务 fallback 保持隔离；能够用注入式 client 独立测试。
  - Cons：Provider 包装栈继续加深；包装顺序成为正式契约；工厂组合和故障矩阵测试数量增加。
- **Option B：把错误分类、重试和 breaker 全部写入 `DeepSeekProvider`**
  - Pros：修改文件较少；单个 provider 的调用路径直观。
  - Cons：SDK 适配器同时承担策略、计时、退避和状态机，职责膨胀；不利于独立测试和未来 provider
    扩展；限流与重试的先后关系容易隐含在实现内部。
- **Option C：由各 Agent 或 Workflow 分别处理 transport 失败**
  - Pros：调用方掌握完整业务上下文，可以定制每条 fallback。
  - Cons：Audit、Extraction、Trace 等调用点会复制错误矩阵；非 Workflow 调用容易漏治理；重试次数、
    breaker 计数和日志语义会漂移。

## Decision

采用 **Option A**。

- 机器可读错误分类固定为：`timeout`、`rate_limited`、`provider_5xx`、`auth_config`、
  `invalid_json`、`schema_invalid`。其中 `auth_config` 对应路线图中的 auth/config 类别。
- 保留 `LLMUnavailable` 作为兼容基类，并为可分类失败提供稳定的错误类型、retryable 标记和脱敏原因；
  SDK 的具体异常类不得泄漏到 Agent contract。
- 真实 provider 的包装顺序固定为
  `Caching(Retrying(RateLimited(CircuitBreaking(DeepSeek))))`：Cache hit 不进入治理链；每次 retry
  都重新经过限流；限流等待超时不会推动真实 provider breaker；breaker 只包围真实 DeepSeek 调用。
- `timeout`、`rate_limited`、`provider_5xx` 可执行有限重试；`auth_config` 不重试。最大总 attempt 为
  3，即首次调用加最多 2 次重试。
- 退避采用有上限的指数退避。请求 timeout、最大总 attempt、退避基数/上限、breaker 失败阈值和
  open 时长进入配置契约；精确字段名和默认值由 `spec.md` 冻结。不得引入新的重试依赖。
- breaker 只把 `timeout` 和 `provider_5xx` 计为上游可用性失败；`rate_limited`、`auth_config`、
  输出校验失败和 hard constraint violation 均不推动 breaker。
- breaker open 是控制结果而不是第七种 provider 错误。观测记录 `breaker_state=OPEN`，最终降级记录
  `fallback_reason=breaker_open`。
- Fake provider 不进入 retry 或 breaker 运行时包装链，继续作为零密钥、确定性的默认 CI 路径；
  故障注入测试可使用 fake client 驱动真实 provider 包装链。

## Consequences

- 正向：transport 失败在一个边界内获得稳定分类、有限尝试和一致 breaker 语义，所有真实调用点自动
  复用，且延续既有缓存与限流决策。
- 正向：429/本地限流与真实上游故障不会混入同一 breaker 计数，避免配额拥塞误触发服务熔断。
- 负向：Provider 工厂需要覆盖 Fake/DeepSeek、Cache、RateLimit、Retry、Breaker 的组合与嵌套顺序；
  排查调用链比当前多两层。
- 负向：最多 3 次物理调用会增加单次逻辑生成的尾延迟和 token 成本；配置过宽可能放大上游故障期间
  的请求量，因此退避和 breaker 参数必须有有限默认值。
- 约束：本决策不引入多模型路由、通用模型网关、分布式 breaker 或无限重试。
