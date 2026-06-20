# Stage llm-cache — Architectural Decisions

> 续全局连续编号(decisions/ 现到 ADR-061),本 stage 从 ADR-062 起。
> 范围 = ADR-059 显式 defer 的「LLM 结果缓存」+ ADR-059 收尾 follow-up「`job:{task_id}` 无 TTL 堆积」收口。
> ADR-059 另一 defer 项「API 限流」仍留 backlog,不在本 stage。
> 状态:用户 2026-06-20 review 后全部拍板 accepted。

---

## ADR-062: LLM 缓存的边界位置 —— Provider 层 memoization vs Agent 层语义缓存
**Slug**: `llm-cache-provider-layer-memoization`
**Status**: accepted
**Date**: 2026-06-20

### Context
ADR-059 把「LLM 结果缓存」措辞为 key = `prompt_version + 异常指纹`,defer 到后续 stage,现在落地。代码里有两个可放缓存的层:
- **Provider 层**:`core/llm/provider.py` 的 `LLMProvider.complete(messages, *, temperature, response_format) -> LLMResult`,是 audit / extraction / query_rewrite / trace / report / memory_summary 六个调用点的唯一收口;返回**未经下游校验的原始 `text`**。
- **Agent 层**:`agents/audit_agent.py` 的 `decide_with_llm`,在 `provider.complete()` 之后才做 `LLMAuditDecision.model_validate(...)`、C2 等校验,产出最终 `AuditDecision`。

「缓存什么内容、缓存放哪层」会牵出"为什么不是另一种"的连锁问题,必须先定。

### Options Considered
- **A. Provider 层 memoization**:包一个实现 `LLMProvider` 协议的 `CachingLLMProvider(inner)`,key = `sha256(model | temperature | response_format | messages_json)`,value = `LLMResult.text`(+ token 元数据)。
  - Pros:一处接入复用全部六个调用点;`prompt_version` 隐式入键(system prompt 文本变即 key 变);「异常指纹」隐式入键(`user_payload` 已在 messages 里,且 `decide_with_llm` 用 `sort_keys=True` 确定性序列化);Schema 校验 / C1–C6 / Fallback 全在缓存**外**,命中仍走校验(边界干净,关联 ADR-022/023/024);`memory_summary` 等有状态调用因内容寻址天然安全(memory 变 → messages 变 → 不会脏命中)。
  - Cons:key 不可读(无法从 key 反推"哪个异常",靠日志补,见 ADR-065);缓存的是过校验前原文,可能缓存到下游会校验失败的坏输出;跨 agent 差异化策略需额外开关。
- **B. Agent 层语义缓存**:在 `decide_with_llm` 内构造 key = `prompt_version + 归一化字段指纹`,value = 过校验后的 `AuditDecision`。
  - Pros:key 可读、可审计;只缓存合法决策;字面贴合 ADR-059 措辞。
  - Cons:每个 agent 各写一遍,无法复用;**漏字段风险高**——指纹一旦漏掉 `memory_context` / `few_shot_cases` / `trace_context`,两个不同上下文会撞同一 key 返回错误缓存决策(典型 design-vs-impl gap);命中跳过校验管线,校验若非纯函数会引入不一致。

### Decision
选 **A,Provider 层 memoization**。理由:① ADR-059 的"prompt_version + 异常指纹"被 full-message 哈希**严格覆盖**(任何相关输入变化都改 key),省掉手维护语义指纹的漏字段风险;② 一处接入复用六个调用点;③ 校验 / Fallback 留在缓存外,命中仍校验,边界最干净。per-call 差异化交给开关(ADR-064)。
**缓存什么(what-to-cache 边界,随 A 直接确定)**:只缓存 `provider.complete()` **成功返回的 text**(含下游会校验失败的——provider 看不到下游校验,不引回写信号以保持纯 memoization);**`LLMUnavailable` 异常绝不缓存**。命中坏输出会重走 Fallback(L1),可接受:省掉重复 token,且 `temperature=0` 下重算大概率仍坏。

### Consequences
- 正面:六个调用点零散改动即获缓存;命中仍过校验,决策正确性不依赖缓存;有状态调用内容寻址安全。
- 负面:key 不可读 → 依赖 ADR-065 的命中日志补可观测;坏输出会被缓存,同输入持续 Fallback 直到 TTL 过期或 prompt 升版(登记 follow-up:坏输出率高时可在 agent 层加"校验失败不缓存"旁路,本 stage defer);`LLMResult` 需带 hit 信号以正确记成本(ADR-065)。

---

## ADR-063: 缓存键构成、命名空间与失效策略
**Slug**: `llm-cache-key-namespace-ttl`
**Status**: accepted
**Date**: 2026-06-20

### Context
承 ADR-062 选 provider 层 memoization。key 要稳定可复现、随 prompt 版本自动失效、且不能让 Redis 无界堆积(呼应 ADR-050 emitter 泄漏教训)。

### Options Considered
- **key 是否显式拼 `prompt_version`**:
  - 仅靠 system prompt 文本隐式带入(prompt 升版即换文本即换哈希)。Pros:无冗余、单一真相源;Cons:key 不含可读版本号。
  - 额外把 `prompt_version` 拼进 key。Pros:可读;Cons:与 messages 里的 prompt 文本重复,两处不一致时反而有歧义。
- **失效策略**:
  - 仅靠 prompt 文本变更自然失效(无 TTL)。Pros:命中率最高;Cons:键无界堆积,重蹈 ADR-059 follow-up 覆辙。
  - 加 TTL。Pros:防堆积;Cons:TTL 内 prompt 文件回滚到旧版会命中旧缓存(内容一致即应一致,可接受)。

### Decision
- key = `llmcache:v1:{sha256(model | temperature | response_format | messages_json)}`;**不单独拼 `prompt_version`**(system prompt 文本已在 messages 内,升版天然 miss)。
- key 前缀带 schema 版本 `v1`,将来键格式演进可整体失效不撞旧键。
- **加 TTL**:`settings.llm_cache_ttl_seconds`,默认 7 天(`604800`),防无界增长。

### Consequences
- 正面:prompt 升版自动 miss、无需手动清缓存;`v1` 前缀给键格式留演进余地;TTL 兜住堆积。
- 负面:TTL 内 prompt 回滚会命中旧版缓存(语义上内容一致即应一致,接受);7 天为拍脑袋初值,需在 spec 标注可按实际命中/容量调。

---

## ADR-064: 缓存接入方式、开关与 Redis 不可用降级
**Slug**: `llm-cache-toggle-and-observable-degrade`
**Status**: accepted
**Date**: 2026-06-20

### Context
项目既有开关惯例:`enable_rag_rewrite/hybrid/reranker`、`async_queue_enabled` 默认关、主链路零回归。Redis 可能不可用(本地未起 Redis)。本项目有两次**静默降级**踩坑史(V1-1 SSE 真实时→回放、stage-fix emitter 观测被丢),降级必须可观测。

### Options Considered
- **接入点**:
  - 在 `get_llm_provider()` 内按 `settings.enable_llm_cache` 决定是否包 `CachingLLMProvider`。Pros:单点、与现有 provider 工厂一致;Cons:工厂多一分支。
  - 每个 agent 各自注入缓存。Pros:可按 agent 控;Cons:六处重复,违背 ADR-062 的复用初衷。
- **Redis 运行期不可用时**:
  - 静默 pass-through。Pros:简单;Cons:**重蹈静默降级覆辙**,出问题排查无依据。
  - 记日志 + 计数后 pass-through。Pros:可观测、主链路不挂;Cons:多一条健康检查/异常路径。
  - 直接抛错中断主链路。Pros:问题立刻暴露;Cons:Redis 抖动即拖垮对账,违背缓存"锦上添花"定位。

### Decision
- 在 `get_llm_provider()` 内:`enable_llm_cache` 为真**且** Redis 可连 → 返回 `CachingLLMProvider(inner)`;否则返回裸 provider。
- Redis 运行期读写异常 → **降级为 pass-through,但必须 `log.warning("llm_cache_degraded", ...)` + 计数**,绝不静默(显式对标 V1-1 / stage-fix 教训)。
- 默认 `enable_llm_cache=False`,与既有开关默认关一致,主链路零回归。

### Consequences
- 正面:无 Redis 环境零回归;降级有日志有计数,可排查;缓存定位为"可选加速",不影响正确性。
- 负面:多一个开关 + 一条连接健康检查/降级路径需测试覆盖(命中 / 未命中 / Redis 不可用三态)。

---

## ADR-065: 命中可观测与成本记账
**Slug**: `llm-cache-hit-observability-and-cost`
**Status**: accepted
**Date**: 2026-06-20

### Context
`core/llm/cost.py` 的 `compute_cost(prompt_tokens, completion_tokens)` 按 token 计费;缓存命中**没有新 token 消耗**。指标盘(ADR-047 数据源分层 / ADR-054 per-task 聚合)要能体现缓存省了多少。但现有 `LLMResult` 无 hit/miss 信号,直接复用缓存里的 token 数会把已省的成本**重复计入**。

### Options Considered
- **hit 信号怎么带**:
  - `LLMResult` 增 `cached: bool = False` 字段。Pros:显式、调用点可分辨;Cons:schema 变更,触及所有读 token 的调用点。
  - 命中时把 token 清零。Pros:成本天然算 0;Cons:丢失"原本要花多少"的省本信号,且掩盖真实 prompt 规模。
  - provider 外挂旁路信号(如返回值外的线程局部)。Pros:不动 schema;Cons:隐式、易漏、并发不安全。
- **成本口径**:命中计 0 新成本(真实)vs 命中仍按原 token 计(会与"省本"重复)。

### Decision
- `LLMResult` 增 `cached: bool = False`;命中返回**缓存里的原始 token 数**但置 `cached=True`。
- **成本记账**:`cached=True` 时本次**计 0 新成本**;省下的成本 = 用缓存原始 token 反算,作为**单独**的 saved-cost 指标,不混入实付成本。
- structlog 增 `llm_cache_hit` 事件(字段含 `agent_name`、`prompt_version`、`cache_key`(前缀+短哈希));命中率 / 省本接入指标盘(扩展 ADR-047,聚合方式对齐 ADR-054)。

### Consequences
- 正面:实付成本不被缓存污染;省本可量化、命中可追踪,正好作为作品化的量化指标卖点。
- 负面:`LLMResult` schema 变更需同步所有读 token 的调用点(audit / extraction / report 及 metrics 聚合识别 `cached`),改动面比纯加缓存大,须在 tasks 显式列出受影响调用点。

---

## ADR-066: Redis 客户端边界与测试策略
**Slug**: `llm-cache-sync-redis-client-and-fakeredis`
**Status**: accepted
**Date**: 2026-06-20

### Context
`provider.complete()` 是**同步**调用(对账核心 `run_reconciliation_job` / `_execute_reconciliation` 均同步;live 路径用 `asyncio.to_thread` 把同步核心丢线程)。而 ADR-056 引入的 arq `ArqRedis` 池是**异步**、只服务入队幂等(`queue_client.py`)。LLM 缓存落在同步路径上。ADR-061 定了测试用 fakeredis、不连真 Redis。

### Options Considered
- **缓存用哪个 Redis 客户端**:
  - 复用 arq 异步池。Pros:单一连接来源;Cons:要把缓存做成 async,侵入同步 `provider.complete` 及其所有同步调用栈,改动面巨大。
  - 为缓存单开同步 `redis.Redis.from_url(settings.redis_dsn)`。Pros:贴合同步 provider,零侵入;Cons:进程内多一个 Redis 连接来源,需文档说明两套客户端用途。
- **测试**:连真 Redis(违背 ADR-061)vs `fakeredis.FakeStrictRedis`(同步变体,延续 ADR-061)。

### Decision
- LLM 缓存用**独立同步 `redis.Redis.from_url(settings.redis_dsn)`**,与 arq 异步池**物理分离**(同一 Redis 实例、不同客户端、不同用途)。
- 测试用 `fakeredis.FakeStrictRedis`(同步),延续 ADR-061 不连真 Redis 策略。
- 本 ADR 是 ADR-059「Redis 用途边界」的扩展:Redis 用途现 = 入队幂等(异步池)+ LLM 结果缓存(同步客户端)。

### Consequences
- 正面:不污染同步 provider 路径,零侵入;测试无需真 Redis;Redis 用途边界清晰留痕。
- 负面:同步 / 异步两套 Redis 客户端并存,需在 spec / 注释说明各自职责,避免后人误用;`fakeredis` 需确认已在测试依赖内(ADR-061 已引则复用)。

---

## ADR-067: `job:{task_id}` 幂等键 TTL 收口(ADR-059 follow-up)
**Slug**: `job-idempotency-key-ttl`
**Status**: accepted
**Date**: 2026-06-20

### Context
ADR-059 收尾 follow-up 明确记账:`queue_client.enqueue_reconciliation` 用 `set(job_key, "1", nx=True)` 做入队幂等,**无 TTL**,键会随任务累积、永久滞留(同 ADR-050 emitter 泄漏教训)。本 stage 顺带收口。

### Options Considered
- **TTL 怎么加**:
  - 入队时 `set(job_key, "1", nx=True, ex=TTL)`。Pros:一行收口、与 SETNX 原子;Cons:TTL 选值需覆盖最长任务执行。
  - 任务终态时显式 `delete(job_key)`。Pros:语义精确(完成即释放);Cons:任务崩溃 / 终态漏走则键又滞留,需兜底。
  - 两者结合。Pros:最稳;Cons:本 stage 体量不值,过度工程。
- **TTL 取值**:覆盖单任务执行 + 余量(如 1 小时)vs 与"防重复上传"语义窗口对齐(更长)。

### Decision
- 入队幂等键加 TTL:`set(job_key, "1", nx=True, ex=settings.job_idempotency_ttl_seconds)`,默认 **1 小时**(`3600`,足够覆盖单任务执行,远短于内容寻址语义窗口)。
- **不**动现有 `force` 删除键逻辑(ADR-059 终态可 force 重算的语义保持)。
- 不引入终态 delete(避免崩溃漏走的兜底复杂度,TTL 已足够)。

### Consequences
- 正面:防 Redis 键无界堆积,闭合 ADR-059 follow-up。
- 负面:**幂等窗口从"永久"变"TTL 内"**——TTL 过后同 `task_id`(= 文件 sha256)再次上传会再入队、重算一次。可接受:此时 ADR-062 的 LLM 缓存大概率命中,重算开销小。这是与 ADR-057 异步状态机 / ADR-059 幂等语义的边界协调点,须在 spec 写明。
