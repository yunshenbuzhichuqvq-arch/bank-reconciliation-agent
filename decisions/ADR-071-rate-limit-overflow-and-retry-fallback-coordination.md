# ADR-071: 超限行为及与有界重试 / 三级 Fallback / ARQ job 重试的协调

- Status: Accepted (2026-06-21)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/rate_limit.py(complete 协调 + _sleep_or_reject), decisions/ADR-060(job vs LLM 重试边界), decisions/ADR-007(三级 Fallback), decisions/ADR-029(熔断对照), decisions/ADR-059(点名"重新协调")

## Context

一次对账在 LLM 链上可能多次打 DeepSeek:AuditAgent Schema 校验失败的有界重试(ADR-060),三级 Fallback L1→L2→L3 每级各一次(ADR-007)。新增限流后必须定:超 RPM/并发时等待还是拒绝?重试/各 Fallback 级是否豁免限流?等待超时算哪类错误(与 ADR-060 "job 重试只兜底基础设施瞬时错误、业务失败翻 FAILED" 边界协调)?DeepSeek 自身返回 429 怎么处理?这是 ADR-059 点名要"重新协调"的核心。

## Options Considered

- **超限行为**:(a) 有界等待(协程挂起,配 max_wait 超时)vs (b) 立即拒绝。
  - 选 **(a)**:限流目的是平滑节流而非拒绝服务,等待让请求最终通过;配 `rate_limit_max_wait_seconds` 上限防无限等。(b) 会把可稍后成功的请求直接打成失败。
- **重试 / Fallback 是否各自过闸**:(a) 每次真实出网调用(有界重试的每次、L1/L2/L3 每级)各自独立过闸 vs (b) 一次对账只过一次。
  - 选 **(a)**:它们都是真实出网请求,豁免就破坏节流、配额仍会被打爆。
- **等待超时归类**:(a) 抛 `LLMUnavailable` 交现有有界重试 + 三级 Fallback,最终翻 `FAILED`,不交 ARQ job 重试 vs (b) 当瞬时基础设施错误交 ARQ `max_tries` 重试。
  - 选 **(a)**:限流等待超时不是"Redis/DB 瞬时基础设施故障",归 ARQ 重试会重放整条对账、与 ADR-060 决策 A 冲突、重复烧 token。
- **DeepSeek 返回 429**:走现有失败路径(归 `LLMUnavailable` → 重试/Fallback),不引入熔断(见 ADR-072);429→自适应降速 defer。

## Decision

超限 → **有界等待**(`max_wait` 可配,web 路径取值需短以防 HTTP 超时);**每次真实出网调用各自过闸**(重试、L1–L3 不豁免);**等待超时抛 `LLMUnavailable`**,交现有有界重试 + 三级 Fallback,最终 `FAILED`,不交 ARQ job 重试(对齐 ADR-060);**429 走 Fallback 不熔断**,自适应降速 defer。

## Consequences

- 正面:节流不拒服务;失败处理职责不与 ADR-060/007 叠加放大、token 不被重复消耗;边界可解释。
- 负面:有界等待会增加任务时延——worker 协程挂起占用 worker 池、web 协程挂起占用 HTTP 请求,故并发上限需与 worker/连接池规模协调,避免池耗尽(登记);`max_wait` 超时→`FAILED` 可能把"再等等本可成功"的任务误判失败,属 margin 调参(登记)。

## 实现注记 (2026-06-21 收尾 review)

- acquire 顺序 = **先并发后 RPM**,故 RPM 等待期间并发名额被持有(合理背压,但 RPM 拥塞会传导致并发槽占满)。并发槽在成功 `finally` / `LLMUnavailable` / `RedisError` 三条路径均归还;并发超限会先 `DECR` 回退本次多增计数再进入等待,避免自占名额死锁。
- 等待超时统一抛 `LLMUnavailable("rate limit wait timeout")`,**未改动既有重试 / Fallback / job 代码**,它们自动接管。
- **设计-实现张力(登记 follow-up)**:默认 `max_wait`(10s) < `window_seconds`(60s),固定窗口下 RPM 一旦打满,被拒请求需等到下一窗口(最多 60s)才放行,但 10s 即等待超时 → 实际表现接近"快速失败→FAILED"而非排队放行。上线按 DeepSeek 实际配额校准(调大 `max_wait` 趋近 `window`,或后续换滑动窗口/令牌桶平滑)。
