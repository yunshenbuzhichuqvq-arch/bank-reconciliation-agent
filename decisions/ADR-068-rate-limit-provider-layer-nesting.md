# ADR-068: 限流闸位置与缓存包装器的嵌套顺序

- Status: Accepted (2026-06-21)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/provider.py(get_llm_provider 嵌套接入), src/bank_reconciliation_agent/core/llm/rate_limit.py(RateLimitedLLMProvider), src/bank_reconciliation_agent/core/llm/cache.py(CachingLLMProvider), decisions/ADR-062(provider 层 memoization), decisions/ADR-064(缓存开关/降级接入)

## Context

`core/llm/provider.py` 的 `LLMProvider.complete()` 是 audit/extraction/query_rewrite/trace/report/memory_summary 六个调用点的唯一收口(ADR-062)。缓存已用 `CachingLLMProvider(inner)` 包装在此、由 `get_llm_provider()` 接入(ADR-064)。限流要插哪一层、与缓存谁内谁外,会牵出"为什么不是另一种"的连锁问题,必须先定。

## Options Considered

- **A. provider 层包装器 `RateLimitedLLMProvider(inner)`,嵌套顺序 `Caching(RateLimited(real))`(缓存外、限流内)**
  - Pros:一处接入复用六个调用点(延续 ADR-062 复用初衷);缓存命中在限流之前短路返回,不占限流配额(命中本就不打网络,占配额是错的);限流只裹真正出网的裸 provider,语义干净。
  - Cons:`get_llm_provider()` 需处理 `enable_llm_cache` × `enable_llm_rate_limit` 四态组合,工厂多一层嵌套分支。
- **B. 限流外、缓存内 `RateLimited(Caching(real))`**
  - Pros:包装顺序书写直观。
  - Cons:缓存命中也要先过限流闸——命中明明不发起网络请求却被节流/排队,白占配额、徒增时延,与限流"保护上游"初衷矛盾。
- **C. 在 Agent 层(`decide_with_llm`)或 ARQ 入队处限流**
  - Pros:可按 agent 差异化;入队限流贴近任务粒度。
  - Cons:六处重复(违背 ADR-062);入队限流管不到"一次对账内的多次 LLM"(有界重试 + L1→L3 各一次),粒度错位,漏掉真正要节流的出网调用。

## Decision

选 **A**。新增 `RateLimitedLLMProvider(inner)`,嵌套为 `Caching(RateLimited(real_provider))`——限流只包真正出网的 provider,缓存命中短路在限流之前。`get_llm_provider()` 按两开关组合决定包装栈(裸 / 仅缓存 / 仅限流 / 缓存+限流)。

## Consequences

- 正面:复用六调用点;命中不占配额、不被节流;校验/Fallback/缓存全在限流外,边界与 ADR-062 一致。
- 负面:工厂出现 2×2 = 4 种包装组合,需测试矩阵覆盖(裸 / 仅缓存 / 仅限流 / 两者);包装栈加深一层,排查调用链时多一跳。

## 实现注记 (2026-06-21 收尾 review)

`get_llm_provider` 用两次独立 `redis.Redis.from_url` 连接(rate_limit_redis / cache_redis)各自 `ping` 降级,两条降级路径互不影响。`RateLimitedLLMProvider` 透传 `self.model = getattr(inner, "model", "")`,保证双开时 `CachingLLMProvider` 缓存键仍能拿到真实 model(否则键里 model 为空、脏命中)。四态组合 + `Caching(RateLimited(base))` 嵌套顺序由 `tests/test_llm_provider.py` 覆盖。
