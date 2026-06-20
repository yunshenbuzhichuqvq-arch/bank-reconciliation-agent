# ADR-062: LLM 缓存的边界位置 —— Provider 层 memoization vs Agent 层语义缓存

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/cache.py(CachingLLMProvider), src/bank_reconciliation_agent/core/llm/provider.py(LLMResult.cached / get_llm_provider 接入), decisions/ADR-059(Redis 用途边界,本 stage 扩展其 defer 项), decisions/ADR-022(硬约束 C1-C6)/ADR-023(副作用分离)/ADR-024(decisionhook-fallback 边界)

## Context
ADR-059 把「LLM 结果缓存」措辞为 key = `prompt_version + 异常指纹`,defer 到后续 stage,现在落地。代码里有两个可放缓存的层:
- **Provider 层**:`core/llm/provider.py` 的 `LLMProvider.complete(messages, *, temperature, response_format) -> LLMResult`,是 audit / extraction / query_rewrite / trace / report / memory_summary 六个调用点的唯一收口;返回**未经下游校验的原始 `text`**。
- **Agent 层**:`agents/audit_agent.py` 的 `decide_with_llm`,在 `provider.complete()` 之后才做 `LLMAuditDecision.model_validate(...)`、C2 等校验,产出最终 `AuditDecision`。

「缓存什么内容、缓存放哪层」会牵出"为什么不是另一种"的连锁问题,必须先定。

## Options Considered
- **A. Provider 层 memoization**:包一个实现 `LLMProvider` 协议的 `CachingLLMProvider(inner)`,key = `sha256(model | temperature | response_format | messages_json)`,value = `LLMResult.text`(+ token 元数据)。
  - Pros:一处接入复用全部六个调用点;`prompt_version` 隐式入键(system prompt 文本变即 key 变);「异常指纹」隐式入键(`user_payload` 已在 messages 里,且 `decide_with_llm` 用 `sort_keys=True` 确定性序列化);Schema 校验 / C1–C6 / Fallback 全在缓存**外**,命中仍走校验(边界干净,关联 ADR-022/023/024);`memory_summary` 等有状态调用因内容寻址天然安全(memory 变 → messages 变 → 不会脏命中)。
  - Cons:key 不可读(无法从 key 反推"哪个异常",靠日志补,见 ADR-065);缓存的是过校验前原文,可能缓存到下游会校验失败的坏输出;跨 agent 差异化策略需额外开关。
- **B. Agent 层语义缓存**:在 `decide_with_llm` 内构造 key = `prompt_version + 归一化字段指纹`,value = 过校验后的 `AuditDecision`。
  - Pros:key 可读、可审计;只缓存合法决策;字面贴合 ADR-059 措辞。
  - Cons:每个 agent 各写一遍,无法复用;**漏字段风险高**——指纹一旦漏掉 `memory_context` / `few_shot_cases` / `trace_context`,两个不同上下文会撞同一 key 返回错误缓存决策(典型 design-vs-impl gap);命中跳过校验管线,校验若非纯函数会引入不一致。

## Decision
选 **A,Provider 层 memoization**。理由:① ADR-059 的"prompt_version + 异常指纹"被 full-message 哈希**严格覆盖**(任何相关输入变化都改 key),省掉手维护语义指纹的漏字段风险;② 一处接入复用六个调用点;③ 校验 / Fallback 留在缓存外,命中仍校验,边界最干净。per-call 差异化交给开关(ADR-064)。

**缓存什么(what-to-cache 边界,随 A 直接确定)**:只缓存 `provider.complete()` **成功返回的 text**(含下游会校验失败的——provider 看不到下游校验,不引回写信号以保持纯 memoization);**`LLMUnavailable` 异常绝不缓存**。命中坏输出会重走 Fallback(L1),可接受:省掉重复 token,且 `temperature=0` 下重算大概率仍坏。

## Consequences
- 正面:六个调用点零散改动即获缓存;命中仍过校验,决策正确性不依赖缓存;有状态调用内容寻址安全。
- 负面:key 不可读 → 依赖 ADR-065 的命中日志补可观测;坏输出会被缓存,同输入持续 Fallback 直到 TTL 过期或 prompt 升版(登记 follow-up:坏输出率高时可在 agent 层加"校验失败不缓存"旁路,本 stage defer);`LLMResult` 需带 hit 信号以正确记成本(ADR-065)。
