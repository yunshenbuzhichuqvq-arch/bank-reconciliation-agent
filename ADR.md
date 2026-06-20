# Stage rate-limit — Architectural Decisions

> 范围:出站 DeepSeek 调用限流(RPM + 并发),保护上游配额、防重复烧 token。
> 本 stage 本地编号 ADR-RL.1~6,收尾归档时映射 `decisions/ADR-068~073`。
> 现状全部 `proposed`,待用户 review 拍板后改 `accepted`。
> 关联历史:ADR-059(Redis 用途边界,本 stage 兑现其 defer 的「API 限流」项)、ADR-062(provider 层 memoization)、ADR-064(缓存开关/降级惯例)、ADR-065(可观测/成本口径)、ADR-061(fakeredis 测试)、ADR-029(熔断 RAG-only)、ADR-060(job vs LLM 重试边界)、ADR-007(三级 Fallback)、ADR-056(ARQ/Redis)。

---

## ADR-RL.1: 限流闸位置与缓存包装器的嵌套顺序
**Slug**: `rate-limit-provider-layer-nesting`
**Status**: proposed
**Date**: 2026-06-21

### Context
`core/llm/provider.py` 的 `LLMProvider.complete()` 是 audit/extraction/query_rewrite/trace/report/memory_summary 六个调用点的唯一收口(ADR-062)。缓存已用 `CachingLLMProvider(inner)` 包装在此、由 `get_llm_provider()` 接入(ADR-064)。限流要插哪一层、与缓存谁内谁外,会牵出"为什么不是另一种"的连锁问题,必须先定。

### Options Considered
- **A. provider 层包装器 `RateLimitedLLMProvider(inner)`,嵌套顺序 `Caching(RateLimited(real))`(缓存外、限流内)**
  - Pros:一处接入复用六个调用点(延续 ADR-062 复用初衷);**缓存命中在限流之前短路返回,不占限流配额**(命中本就不打网络,占配额是错的);限流只裹真正出网的裸 provider,语义干净。
  - Cons:`get_llm_provider()` 需处理 `enable_llm_cache` × `enable_llm_rate_limit` 四态组合,工厂多一层嵌套分支。
- **B. 限流外、缓存内 `RateLimited(Caching(real))`**
  - Pros:包装顺序书写直观。
  - Cons:**缓存命中也要先过限流闸**——命中明明不发起网络请求却被节流/排队,白占配额、徒增时延,与限流"保护上游"初衷矛盾。
- **C. 在 Agent 层(`decide_with_llm`)或 ARQ 入队处限流**
  - Pros:可按 agent 差异化;入队限流贴近任务粒度。
  - Cons:六处重复(违背 ADR-062);入队限流管不到"一次对账内的多次 LLM"(有界重试 + L1→L3 各一次),粒度错位,漏掉真正要节流的出网调用。

### Decision
选 **A**。新增 `RateLimitedLLMProvider(inner)`,嵌套为 `Caching(RateLimited(real_provider))`——限流只包真正出网的 provider,缓存命中短路在限流之前。`get_llm_provider()` 按两开关组合决定包装栈(裸 / 仅缓存 / 仅限流 / 缓存+限流)。

### Consequences
- 正面:复用六调用点;命中不占配额、不被节流;校验/Fallback/缓存全在限流外,边界与 ADR-062 一致。
- 负面:工厂出现 2×2 = 4 种包装组合,需测试矩阵覆盖(裸 / 仅缓存 / 仅限流 / 两者);包装栈加深一层,排查调用链时多一跳。

---

## ADR-RL.2: 限流维度边界 —— RPM + 并发,TPM defer
**Slug**: `rate-limit-dimensions-rpm-concurrency`
**Status**: proposed
**Date**: 2026-06-21

### Context
DeepSeek 配额通常含三维:RPM(每分钟请求数)、并发数、TPM(每分钟 token 数)。维度越多越贴近上游真实约束,但 TPM 需在调用前预估本次 token,复杂度与收益需权衡。本 stage 限哪几维要先定边界。

### Options Considered
- **A. RPM + 并发上限,TPM defer**
  - Pros:RPM + 并发是最常见、最易触的两类上游约束;实现只需"窗口计数 + 并发计数",无需预估 token;契合 simplicity-first。
  - Cons:不控 TPM,超大 token 的突发请求仍可能触上游 429(由 ADR-RL.4 的重试/Fallback 兜底)。
- **B. 三维全做(含 TPM)**
  - Pros:最贴近上游配额。
  - Cons:TPM 需在 `complete()` 前估算 prompt token(messages 可估、completion 未知只能猜),估不准则限流要么过紧要么失效;复杂度高,与单 stage 2–4h/task 颗粒度冲突。
- **C. 仅并发上限**
  - Pros:实现最轻(一个并发计数)。
  - Cons:不控速率,短时高频小请求仍会超 RPM,达不到"防超配额"目标。

### Decision
选 **A**:本 stage 限 **RPM + 并发**;**TPM defer 到 backlog**(理由:预估不准 + 复杂度,收益边际)。

### Consequences
- 正面:覆盖主要配额约束,实现可控、可在单 stage 完成。
- 负面:TPM 不受控,超大请求仍可能上游 429(登记 follow-up,由 RL.4 退避/Fallback 兜底);若未来 DeepSeek 主要瓶颈转为 TPM,需另开 stage 补。

---

## ADR-RL.3: 作用域、算法与原子实现 —— Redis 分布式 + 原生命令,fakeredis 测试边界
**Slug**: `rate-limit-redis-scope-atomic-impl`
**Status**: proposed
**Date**: 2026-06-21

### Context
LLM 调用横跨 **FastAPI web 进程(同步 upload 路径,ADR-007 提到单次 audit 15~25s)+ ARQ worker 进程**(ADR-056),进程内 `asyncio.Semaphore` 只能限单进程、无法全局节流;ADR-059 已把限流登记为 Redis 用途。但分布式限流的原子"读-改-写"常用 Lua,而 ADR-061 指出 fakeredis 的 Lua / 过期精度与真 Redis 有差异,且 DoD 要求离线可复跑。算法与原子实现需一并定。

### Options Considered
- **A. Redis 分布式 + 原生原子命令(避自定义 Lua):RPM 用固定窗口 `INCR`+`EXPIRE`,并发用 `INCR`/`DECR` 计数键(带 TTL 兜底);fakeredis 作测试主体 + 真 Redis 手工 smoke**
  - Pros:跨 web/worker 全局节流;原生命令 fakeredis 支持好、DoD 离线可复跑;与 ADR-059/061 一致。
  - Cons:固定窗口有边界突刺(窗口切换瞬间最多 ~2 倍);并发计数依赖进程正常 `DECR`,进程崩溃会泄漏 → 需键 TTL 兜底,非强一致。
- **B. Redis + Lua 原子脚本(如 token bucket)**
  - Pros:原子性强、算法平滑突发。
  - Cons:fakeredis Lua 支持差 → 自动化测试盲区(放大 ADR-061 风险);实现与调试复杂度高。
- **C. 进程内 `asyncio.Semaphore`(不依赖 Redis)**
  - Pros:最简、零外部依赖。
  - Cons:web/worker 多进程各自为政,全局速率 = 单进程限 × 进程数,**失去全局节流意义**;与 ADR-059 背离。

### Decision
选 **A**:Redis 分布式 + 原生原子命令;RPM 固定窗口(`INCR`+`EXPIRE`)、并发计数键带 TTL 防崩溃泄漏;固定窗口突刺以"限到配额的留 margin 比例"缓解。fakeredis 作自动化测试主体,真 Redis 留可选手工 smoke 记入 PR.md(对齐 ADR-061),不进 DoD 必跑。

### Consequences
- 正面:跨进程全局节流;离线可测、DoD 不依赖真 Redis;实现简单可维护。
- 负面:固定窗口边界突刺(登记,靠 margin 容忍,DeepSeek 防配额场景可接受);并发计数靠 TTL 兜底而非强一致(极端崩溃下可能短暂少算);fakeredis 与真 Redis 残余语义差异靠手工 smoke 兜底(诚实登记,非已消除)。

---

## ADR-RL.4: 超限行为及与有界重试 / 三级 Fallback / ARQ job 重试的协调
**Slug**: `rate-limit-overflow-and-retry-fallback-coordination`
**Status**: proposed
**Date**: 2026-06-21

### Context
一次对账在 LLM 链上可能多次打 DeepSeek:AuditAgent Schema 校验失败的有界重试(ADR-060),三级 Fallback L1→L2→L3 每级各一次(ADR-007)。新增限流后必须定:超 RPM/并发时等待还是拒绝?重试/各 Fallback 级是否豁免限流?等待超时算哪类错误(与 ADR-060 "job 重试只兜底基础设施瞬时错误、业务失败翻 FAILED" 边界协调)?DeepSeek 自身返回 429 怎么处理?这是 ADR-059 点名要"重新协调"的核心。

### Options Considered
- **超限行为**:(a) 有界等待(协程挂起,配 `max_wait` 超时)vs (b) 立即拒绝。
  - 选 **(a)**:限流目的是平滑节流而非拒绝服务,等待让请求最终通过;配 `rate_limit_max_wait_seconds` 上限防无限等。(b) 会把可稍后成功的请求直接打成失败。
- **重试 / Fallback 是否各自过闸**:(a) 每次真实出网调用(有界重试的每次、L1/L2/L3 每级)各自独立过闸 vs (b) 一次对账只过一次。
  - 选 **(a)**:它们都是真实出网请求,豁免就破坏节流、配额仍会被打爆。
- **等待超时归类**:(a) 抛 `LLMUnavailable` 交现有有界重试 + 三级 Fallback,最终翻 `FAILED`,**不**交 ARQ job 重试 vs (b) 当瞬时基础设施错误交 ARQ `max_tries` 重试。
  - 选 **(a)**:限流等待超时不是"Redis/DB 瞬时基础设施故障",归 ARQ 重试会重放整条对账、与 ADR-060 决策 A 冲突、重复烧 token。
- **DeepSeek 返回 429**:走现有失败路径(归 `LLMUnavailable` → 重试/Fallback),**不引入熔断**(见 ADR-RL.5);429→自适应降速 defer。

### Decision
超限 → **有界等待**(`max_wait` 可配,web 路径取值需短以防 HTTP 超时);**每次真实出网调用各自过闸**(重试、L1–L3 不豁免);**等待超时抛 `LLMUnavailable`**,交现有有界重试 + 三级 Fallback,最终 `FAILED`,不交 ARQ job 重试(对齐 ADR-060);**429 走 Fallback 不熔断**,自适应降速 defer。

### Consequences
- 正面:节流不拒服务;失败处理职责不与 ADR-060/007 叠加放大、token 不被重复消耗;边界可解释。
- 负面:有界等待会增加任务时延——worker 协程挂起占用 worker 池、web 协程挂起占用 HTTP 请求,故并发上限需与 worker/连接池规模协调,避免池耗尽(登记);`max_wait` 超时→`FAILED` 可能把"再等等本可成功"的任务误判失败,属 margin 调参(登记)。

---

## ADR-RL.5: 限流 vs 熔断的边界 —— 为何 LLM 出站只限流不熔断
**Slug**: `rate-limit-vs-circuit-breaker-boundary`
**Status**: proposed
**Date**: 2026-06-21

### Context
ADR-029 给 RAG(ChromaDB)实装了熔断、LLM 链上无熔断。新增 LLM 限流后会自然引出对称质疑:"RAG 有熔断,LLM 为何只限流不熔断?连续 429/失败要不要 OPEN?"需在 ADR 给出可解释边界。

### Options Considered
- **A. LLM 出站只限流、不加熔断**
  - Pros:限流=主动节流防超配额(已知配额、主动控速),熔断=被动 fail-fast 防雪崩(依赖不可用时停打),语义不同;DeepSeek 是付费核心依赖,整条对账靠它,熔断 OPEN = 对账整体停摆,**不像 RAG OPEN 可空检索转人工降级**(ADR-029);LLM 失败已有有界重试 + 三级 Fallback + 翻 `FAILED` 三层兜底,无需熔断再叠一层。
  - Cons:DeepSeek 长时间故障时无 fast-fail,每个任务都要走完重试+Fallback 才 `FAILED`,较慢。
- **B. LLM 也上熔断(连续 429/失败 N 次 OPEN)**
  - Pros:故障时快速失败、省无谓调用。
  - Cons:LLM 是不可降级核心,OPEN 期所有对账直接失败、无 RAG 那样的降级路径,收益 ≤ 现有 `FAILED` 兜底,纯增状态机复杂度与测试面。
- **C. 限流器内置自适应降速(429 反馈调低速率)**
  - Pros:贴合上游真实余量。
  - Cons:实现复杂(反馈环、抖动),本 stage 范围外。

### Decision
选 **A**:LLM 出站只限流不熔断;429/失败沿用有界重试 + 三级 Fallback + `FAILED`;自适应降速 defer。

### Consequences
- 正面:不为不可降级的核心依赖背熔断复杂度;限流 / 熔断职责边界清晰、可向 review 与面试解释。
- 负面:DeepSeek 长故障时无熔断 fast-fail,失败任务较慢才翻 `FAILED`(异步队列下时延非关键路径,可接受;登记)。

---

## ADR-RL.6: 可观测、开关与 Redis 降级 —— 对齐缓存惯例、防静默降级
**Slug**: `rate-limit-toggle-observability-degrade`
**Status**: proposed
**Date**: 2026-06-21

### Context
项目有两次静默降级踩坑史(V1-1 SSE 真实时→回放、stage-fix emitter 观测被丢),ADR-064 已立"降级必可观测"规矩并落地缓存的开关 + Redis 降级 + `log.warning` + 计数;ADR-065 落地命中率/省本进程内计数器(`source=runtime_memory`,诚实口径)。限流的开关/降级/指标必须对齐同一惯例。

### Options Considered
- **开关**:`enable_llm_rate_limit` 默认 `False`(对齐 `enable_llm_cache` / `async_queue_enabled` 默认关、主链路零回归)vs 默认开。
  - 选默认 `False`:与既有开关惯例一致,无 Redis 环境零回归。
- **Redis 不可用时降级方向**:(a) fail-open(不限流但放行 + `log.warning("llm_rate_limit_degraded")` + 计数)vs (b) fail-closed(拒绝/阻断)vs (c) 静默 pass-through。
  - 选 **(a) fail-open + 显式日志/计数**:与 ADR-064 缓存"Redis 挂了 pass-through、不阻断主链路"哲学一致——限流是保护上游的"锦上添花",Redis 抖动不该把对账打死;**绝不静默**(对标 V1-1 / stage-fix)。(b) 会让 Redis 故障直接拖垮对账;(c) 重蹈静默降级覆辙。
- **指标**:限流器进程内计数器经 `metrics_snapshot` 暴露(等待次数 / 等待总时长 / 超时拒绝次数 / 当前并发),`source=runtime_memory`(对齐 ADR-065 诚实口径,不伪装持久化 SQL),structlog 事件 `llm_rate_limited` / `llm_rate_limit_degraded`,接入 `services/metrics.py`(对齐 ADR-047 数据源分层 / ADR-054 聚合)。

### Decision
`enable_llm_rate_limit` 默认 `False`;Redis 不可用 → **fail-open + `log.warning` + 计数,绝不静默**;限流指标走进程内计数器、`source=runtime_memory`、structlog 事件,接入 `metrics.py`。

### Consequences
- 正面:主链路零回归;降级可观测可排查;节流次数/等待时长/拒绝数可量化,作为作品化指标卖点。
- 负面:fail-open 意味 Redis 故障时限流静默失效(但有 `warning`+计数可发现,非静默);进程内计数器服务重启归零(对齐 ADR-065 已知口径);开关组合(cache × rate_limit)使可观测/降级测试态增多。
