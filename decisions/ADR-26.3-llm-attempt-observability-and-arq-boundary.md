# ADR-26.3: LLM attempt 使用结构化摘要观测且不得触发 ARQ job 重放

**Slug**: `llm-attempt-observability-and-arq-boundary`
**Status**: accepted
**Date**: 2026-07-11

## Context

Stage 26 需要证明 attempt count、retry recovery、structured repair、fallback by error type、额外 token
和 breaker open 等结果。当前 `LLMResult` 与 Agent 的 `last_llm_result` 主要表达最后一次成功返回，无法完整
表达“首次结构无效后 correction 成功”等路径的实际 token/cost；进程内 breaker 或计数器也不能替代
可审查的调用记录。

另一方面，Stage 25 与历史 ADR-060 已冻结 ARQ job retry 边界：Redis/DB 瞬时基础设施错误可以重放
job，LLM 或业务失败必须在当前 job 内完成 fallback。Stage 26 若把 LLM timeout/429/5xx 重新抛给 ARQ，
会重放整条对账、重复消费 token，并可能重复执行业务写入。

Stage 29 已规划统一 TraceSpan 与任务回放。Stage 26 不应提前建立完整 attempt 事件表或分布式追踪系统。

## Options Considered

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

## Decision

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

## Consequences

- 正向：Stage 26 可以用确定性故障注入证明 retry、repair、breaker、fallback 与成本边界，而无需真实
  DeepSeek 或外部监控系统。
- 正向：LLM 失败与 ARQ 基础设施重试保持严格隔离，避免整任务重复烧 token 或重复业务副作用。
- 负向：在 Stage 29 前，结构化日志与 Agent 摘要不能提供完整、持久的 attempt 级时间线；多 worker
  聚合只表达可用证据，不宣称为统一 trace。
- 负向：为准确累计无效首次响应和 correction 的 token/cost，Agent 结果汇总契约需要扩展，不能再只
  依赖最后一次 `LLMResult`。
- 约束：本决策不新增数据库表、前端页面、真实 provider CI、分布式追踪依赖或告警基础设施。
