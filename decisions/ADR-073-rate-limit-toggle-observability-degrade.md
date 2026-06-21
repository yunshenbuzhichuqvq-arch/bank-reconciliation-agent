# ADR-073: 可观测、开关与 Redis 降级 —— 对齐缓存惯例、防静默降级

- Status: Accepted (2026-06-21)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/rate_limit.py(metrics_snapshot / _log_degraded / structlog 事件), src/bank_reconciliation_agent/core/llm/provider.py(连接降级), src/bank_reconciliation_agent/services/metrics.py(get_llm_rate_limit_metrics), src/bank_reconciliation_agent/core/config.py(enable_llm_rate_limit), decisions/ADR-064(缓存降级惯例), decisions/ADR-065(观测/成本口径), decisions/ADR-047(指标数据源分层), decisions/ADR-054(per-task 聚合)

## Context

项目有两次静默降级踩坑史(V1-1 SSE 真实时→回放、stage-fix emitter 观测被丢),ADR-064 已立"降级必可观测"规矩并落地缓存的开关 + Redis 降级 + `log.warning` + 计数;ADR-065 落地命中率/省本进程内计数器(`source=runtime_memory`,诚实口径)。限流的开关/降级/指标必须对齐同一惯例。

## Options Considered

- **开关**:`enable_llm_rate_limit` 默认 `False`(对齐 `enable_llm_cache` / `async_queue_enabled` 默认关、主链路零回归)vs 默认开。
  - 选默认 `False`:与既有开关惯例一致,无 Redis 环境零回归。
- **Redis 不可用时降级方向**:(a) fail-open(不限流但放行 + `log.warning("llm_rate_limit_degraded")` + 计数)vs (b) fail-closed(拒绝/阻断)vs (c) 静默 pass-through。
  - 选 **(a) fail-open + 显式日志/计数**:与 ADR-064 缓存"Redis 挂了 pass-through、不阻断主链路"哲学一致——限流是保护上游的"锦上添花",Redis 抖动不该把对账打死;绝不静默(对标 V1-1 / stage-fix)。(b) 会让 Redis 故障直接拖垮对账;(c) 重蹈静默降级覆辙。
- **指标**:限流器进程内计数器经 `metrics_snapshot` 暴露(等待次数 / 等待总时长 / 超时拒绝次数 / 当前并发),`source=runtime_memory`(对齐 ADR-065 诚实口径,不伪装持久化 SQL),structlog 事件 `llm_rate_limited` / `llm_rate_limit_degraded`,接入 `services/metrics.py`(对齐 ADR-047 数据源分层 / ADR-054 聚合)。

## Decision

`enable_llm_rate_limit` 默认 `False`;Redis 不可用 → fail-open + `log.warning` + 计数,绝不静默;限流指标走进程内计数器、`source=runtime_memory`、structlog 事件,接入 `metrics.py`。

## Consequences

- 正面:主链路零回归;降级可观测可排查;节流次数/等待时长/拒绝数可量化,作为作品化指标卖点。
- 负面:fail-open 意味 Redis 故障时限流静默失效(但有 `warning`+计数可发现,非静默);进程内计数器服务重启归零(对齐 ADR-065 已知口径);开关组合(cache × rate_limit)使可观测/降级测试态增多。

## 实现注记 (2026-06-21 收尾 review)

- `get_llm_rate_limit_metrics` 返回 `{source: "runtime_memory", waits, wait_seconds_total, rejections, degraded}`;structlog 事件 `llm_rate_limited`(带 `dimension`/`waited`)、`llm_rate_limit_degraded`(带 `op`/`reason`)。
- **设计-实现差异(登记 follow-up)**:Options 措辞含"当前并发"指标,但落地的 `metrics_snapshot` 只暴露累计 `waits/wait_seconds_total/rejections/degraded`,**未单列"当前并发"实时值**(需另读 Redis `llmratelimit:concurrency` 键)。不影响降级可观测性,作为后续指标增强 follow-up。
- 轮询间隔 `_poll_seconds = 0.1`(100ms)硬编码 ClassVar,符合 spec 建议、暂不外露为配置。
