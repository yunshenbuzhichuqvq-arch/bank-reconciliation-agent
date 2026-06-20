# ADR-064: 缓存接入方式、开关与 Redis 不可用降级

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/provider.py(get_llm_provider 接入 + 构造期 ping 降级), src/bank_reconciliation_agent/core/llm/cache.py(_log_degraded 运行期降级), src/bank_reconciliation_agent/core/config.py(enable_llm_cache), decisions/ADR-029(circuit breaker 降级哲学对照)

## Context
项目既有开关惯例:`enable_rag_rewrite/hybrid/reranker`、`async_queue_enabled` 默认关、主链路零回归。Redis 可能不可用(本地未起 Redis)。本项目有两次**静默降级**踩坑史(V1-1 SSE 真实时→回放、stage-fix emitter 观测被丢),降级必须可观测。

## Options Considered
- **接入点**:
  - 在 `get_llm_provider()` 内按 `settings.enable_llm_cache` 决定是否包 `CachingLLMProvider`。Pros:单点、与现有 provider 工厂一致;Cons:工厂多一分支。
  - 每个 agent 各自注入缓存。Pros:可按 agent 控;Cons:六处重复,违背 ADR-062 的复用初衷。
- **Redis 运行期不可用时**:
  - 静默 pass-through。Pros:简单;Cons:**重蹈静默降级覆辙**,出问题排查无依据。
  - 记日志 + 计数后 pass-through。Pros:可观测、主链路不挂;Cons:多一条健康检查/异常路径。
  - 直接抛错中断主链路。Pros:问题立刻暴露;Cons:Redis 抖动即拖垮对账,违背缓存"锦上添花"定位。

## Decision
- 在 `get_llm_provider()` 内:`enable_llm_cache` 为真**且** Redis 可连 → 返回 `CachingLLMProvider(inner)`;否则返回裸 provider。
- Redis 运行期读写异常 → **降级为 pass-through,但必须 `log.warning("llm_cache_degraded", ...)` + 计数**,绝不静默(显式对标 V1-1 / stage-fix 教训)。
- 默认 `enable_llm_cache=False`,与既有开关默认关一致,主链路零回归。

## Consequences
- 正面:无 Redis 环境零回归;降级有日志有计数,可排查;缓存定位为"可选加速",不影响正确性。
- 负面:多一个开关 + 一条连接健康检查/降级路径需测试覆盖(命中 / 未命中 / Redis 不可用三态)。
