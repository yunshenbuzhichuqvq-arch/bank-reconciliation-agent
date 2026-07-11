# Stage 26 — Architectural Decisions

## ADR-26.1: 真实 LLM 调用采用分层错误治理与 Provider 包装链

**Slug**: `layered-llm-failure-governance`
**Status**: accepted
**Date**: 2026-07-11

### Context

现有 `LLMProvider` 已统一承载 Audit、Extraction、Trace 等调用点，并通过
`CachingLLMProvider` 与 `RateLimitedLLMProvider` 形成
`Caching(RateLimited(provider))` 包装顺序。`DeepSeekProvider` 当前把所有 SDK 异常统一转换为
`LLMUnavailable`，调用方无法区分超时、上游限流、服务端错误和认证/配置错误，也无法据此执行稳定的
retry、breaker 与 fallback 策略。

历史 ADR-005 已确定 Fake provider 是默认离线测试路径，真实 DeepSeek 是 opt-in 外部依赖；
ADR-068 已确定缓存命中不得占用上游限流配额；ADR-071 已确定每次真实出网调用都必须独立经过限流，
且 LLM 失败不得升级为 ARQ job 级重试。Stage 26 需要细化这些边界，同时避免把重复治理逻辑散落到
各 Agent 或 Workflow。

### Options Considered

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

### Decision

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

### Consequences

- 正向：transport 失败在一个边界内获得稳定分类、有限尝试和一致 breaker 语义，所有真实调用点自动
  复用，且延续既有缓存与限流决策。
- 正向：429/本地限流与真实上游故障不会混入同一 breaker 计数，避免配额拥塞误触发服务熔断。
- 负向：Provider 工厂需要覆盖 Fake/DeepSeek、Cache、RateLimit、Retry、Breaker 的组合与嵌套顺序；
  排查调用链比当前多两层。
- 负向：最多 3 次物理调用会增加单次逻辑生成的尾延迟和 token 成本；配置过宽可能放大上游故障期间
  的请求量，因此退避和 breaker 参数必须有有限默认值。
- 约束：本决策不引入多模型路由、通用模型网关、分布式 breaker 或无限重试。

## ADR-26.2: 结构化输出仅允许一次 Agent 级修复并延迟缓存验收

**Slug**: `single-structured-repair-and-cache-validation`
**Status**: accepted
**Date**: 2026-07-11

### Context

ExtractionAgent 与 TraceAgent 当前在 JSON/Pydantic 校验失败后重复相同请求；Audit 工作流还存在最多
3 次 SchemaHook 重试。这些路径没有向模型提供针对性的 correction 信息，也未统一区分
`invalid_json` 与 `schema_invalid`。同时，现有缓存包装器在 Agent 完成结构校验前保存 provider 原始结果，
导致结构无效输出可能被缓存并在后续调用中重复命中。

结构修复与业务安全判断属于不同问题：JSON/Pydantic 错误可以通过一次短 correction prompt 尝试修复；
金额、evidence、高风险重复记账等 hard constraint 必须由确定性 Safety Policy Gate 处理，不能要求模型
“自我修复”后绕过红线。

### Options Considered

- **Option A：Agent 持有 schema，一次定向 correction；Cache 通过通用 validator 延迟写入（采纳）**
  - Pros：schema 所有权留在 Agent；修复提示可以包含具体校验原因；无效输出不会污染缓存；Safety
    Policy 仍是独立、确定性的后置门禁。
  - Cons：`LLMProvider.complete()` 需要增加可选 validator contract，所有包装器必须透明透传；Agent
    调用契约和缓存测试均需同步调整。
- **Option B：把所有 Agent schema 移入 Provider/Cache 层校验**
  - Pros：缓存天然只接收有效输出；调用方代码较少。
  - Cons：基础设施层依赖 Audit/Extraction/Trace 业务模型，模块边界倒置；每增加 Agent 都要修改
    Provider；Safety Policy 与结构校验容易耦合。
- **Option C：保留重复原请求，修复时使用不同 cache key**
  - Pros：改动最小；无需扩展 Provider contract。
  - Cons：模型没有收到校验反馈；首次无效值仍留在缓存；无法满足“无效输出不得缓存”的验收要求。

### Decision

采用 **Option A**。

- Agent 对首次返回执行 JSON 解析和自身 Pydantic schema 校验，并稳定区分 `invalid_json` 与
  `schema_invalid`。
- 首次结构校验失败后只允许追加 1 次短 correction prompt。prompt 包含必要的脱敏校验原因和待修复
  输出，不扩展业务任务、不请求模型修改金额或绕过硬约束。
- correction 是第二个逻辑生成步骤，也适用 ADR-26.1 的 transport 策略。因此首次生成最多 3 次物理
  调用，correction 最多 3 次物理调用，单个 Agent 操作的理论上限为 6 次真实调用。
- correction 仍失败时必须稳定收口到调用方既有的安全 fallback；无法产生确定性安全结果时转为
  `PENDING_HUMAN`。不得继续第三次结构生成。
- 现有 Audit SchemaHook 的三次盲重试、Extraction/Trace 的原请求重复方式统一收敛为上述“一次定向
  correction”契约。
- Provider contract 增加可选、通用的 response validator。schema 仍由 Agent 定义；Cache wrapper
  在 validator 通过后才能写值，Cache hit 也必须重新校验，失败时删除旧值并按 miss 处理。未启用缓存
  时，Agent 仍在自身边界执行相同校验。
- validator 只覆盖 JSON 与 Pydantic schema，不执行 Safety Policy。结构有效但违反 hard constraint
  的输出可以作为原始模型输出缓存，但每次消费时都必须重新经过确定性 Safety Policy Gate。
- hard constraint violation 不触发 transport retry 或 correction；Safety Policy 直接覆盖危险决策并
  fail closed，保留 raw decision 与介入原因供审计。

### Consequences

- 正向：所有 Agent 的结构修复上限一致，模型获得一次有针对性的修复机会，同时避免盲目重复调用。
- 正向：无效 JSON/schema 不再形成持久坏缓存；schema 演进后，旧缓存值也可在读取时被淘汰。
- 负向：单个 Agent 操作在“首次生成和 correction 都经历 transport 重试”的极端情况下可达到 6 次
  真实调用，尾延迟和成本高于当前路径。
- 负向：Provider 协议增加 validator 参数后，Fake、DeepSeek、Cache、RateLimit、Retry、Breaker 等
  实现都必须保持签名与透传一致，增加 contract 回归面。
- 约束：本决策不允许 LLM 修复 hard constraint，不新增通用 schema registry，也不改变确定性金额、
  evidence 和人工复核红线。

## ADR-26.3: LLM attempt 使用结构化摘要观测且不得触发 ARQ job 重放

**Slug**: `llm-attempt-observability-and-arq-boundary`
**Status**: accepted
**Date**: 2026-07-11

### Context

Stage 26 需要证明 attempt count、retry recovery、structured repair、fallback by error type、额外 token
和 breaker open 等结果。当前 `LLMResult` 与 Agent 的 `last_llm_result` 主要表达最后一次成功返回，无法完整
表达“首次结构无效后 correction 成功”等路径的实际 token/cost；进程内 breaker 或计数器也不能替代
可审查的调用记录。

另一方面，Stage 25 与历史 ADR-060 已冻结 ARQ job retry 边界：Redis/DB 瞬时基础设施错误可以重放
job，LLM 或业务失败必须在当前 job 内完成 fallback。Stage 26 若把 LLM timeout/429/5xx 重新抛给 ARQ，
会重放整条对账、重复消费 token，并可能重复执行业务写入。

Stage 29 已规划统一 TraceSpan 与任务回放。Stage 26 不应提前建立完整 attempt 事件表或分布式追踪系统。

### Options Considered

- **Option A：每次物理调用输出结构化事件，并在现有 Agent execution payload 保存逻辑调用摘要（采纳）**
  - Pros：无需新增表即可证明 Stage 26 行为；能保留真实 token/cost 与最终 fallback 结果；与 Stage 29
    的未来 TraceSpan 边界清晰。
  - Cons：当前阶段只有结构化日志和任务/Agent 摘要，不能提供跨进程的完整 attempt 时间线回放；
    日志聚合能力取决于运行环境。
- **Option B：Stage 26 新增独立 LLM attempt 历史表**
  - Pros：每次调用可持久查询、聚合和回放；多进程证据完整。
  - Cons：新增 schema、写入生命周期和清理策略，明显扩大范围；与 Stage 29 Trace/Replay 重复设计。
- **Option C：只维护进程内 counters 和最后一次 `LLMResult`**
  - Pros：实现成本最低；无需持久化变化。
  - Cons：进程重启即丢失；无法解释 correction 和多次 retry 的累计成本；不能稳定关联最终 fallback。

### Decision

采用 **Option A**。

- 每次真实物理调用输出结构化事件，至少包含逻辑调用标识、1-based physical attempt、provider/model、
  稳定失败类型、retryable、耗时、退避时长、token（上游有 usage 时）、breaker 前后状态和 outcome。
- Agent 级摘要至少包含 transport attempt 总数、是否 retry recovered、是否执行 structured repair、repair
  是否成功、累计 token/cost、最终 error type 和 fallback reason；摘要复用现有 Agent execution payload
  与工作流持久化边界，不新增 Stage 26 专用表。
- 所有实际收到 provider 成功响应的调用都累计 token/cost，包括结构无效的首次输出与 correction。
  transport 失败且上游未返回 usage 时记 0，不估算 token；Cache hit 的本次新增 token/cost 为 0，同时
  可以继续记录 saved-token 指标。
- 日志和持久摘要只保存稳定分类与脱敏错误摘要，不保存 API key、认证头、连接串、完整异常对象、完整
  财务输入或不必要的完整 prompt。
- `timeout`、`rate_limited`、`provider_5xx`、`auth_config`、`invalid_json`、`schema_invalid` 和 hard
  constraint violation 都必须在当前 Agent/Workflow 内转换为安全 fallback 或 `PENDING_HUMAN`，不得转换为
  `arq.Retry`，不得重放整个 job。
- ARQ job retry 继续只覆盖 Stage 25/ADR-060 已定义的 Redis/DB 瞬时基础设施错误。LLM fallback 完成后，
  当前 job 按正常业务路径继续收口和落库。
- 故障注入必须使用 fake client 与可注入 clock/sleep，覆盖：三次 transport 上限、`auth_config` 单次
  失败、429 不推动 breaker、timeout/5xx 的 OPEN/HALF_OPEN/CLOSED、一次 correction、hard constraint
  零额外调用、无效缓存淘汰、累计 token/cost、Cache hit 零新增成本，以及 LLM 失败不触发 ARQ retry。
- 完整 attempt 历史、跨进程 TraceSpan、回放 API、告警系统和生产 SLA 留给 Stage 29 或部署阶段。

### Consequences

- 正向：Stage 26 可以用确定性故障注入证明 retry、repair、breaker、fallback 与成本边界，而无需真实
  DeepSeek 或外部监控系统。
- 正向：LLM 失败与 ARQ 基础设施重试保持严格隔离，避免整任务重复烧 token 或重复业务副作用。
- 负向：在 Stage 29 前，结构化日志与 Agent 摘要不能提供完整、持久的 attempt 级时间线；多 worker
  聚合只表达可用证据，不宣称为统一 trace。
- 负向：为准确累计无效首次响应和 correction 的 token/cost，Agent 结果汇总契约需要扩展，不能再只
  依赖最后一次 `LLMResult`。
- 约束：本决策不新增数据库表、前端页面、真实 provider CI、分布式追踪依赖或告警基础设施。
