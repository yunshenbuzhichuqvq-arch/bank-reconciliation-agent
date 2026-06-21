# ADR-072: 限流 vs 熔断的边界 —— 为何 LLM 出站只限流不熔断

- Status: Accepted (2026-06-21)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: decisions/ADR-029(熔断 RAG-only), decisions/ADR-007(三级 Fallback), decisions/ADR-060(LLM 重试边界), decisions/ADR-071(超限协调)

## Context

ADR-029 给 RAG(ChromaDB)实装了熔断、LLM 链上无熔断。新增 LLM 限流后会自然引出对称质疑:"RAG 有熔断,LLM 为何只限流不熔断?连续 429/失败要不要 OPEN?"需在 ADR 给出可解释边界。

## Options Considered

- **A. LLM 出站只限流、不加熔断**
  - Pros:限流=主动节流防超配额(已知配额、主动控速),熔断=被动 fail-fast 防雪崩(依赖不可用时停打),语义不同;DeepSeek 是付费核心依赖,整条对账靠它,熔断 OPEN = 对账整体停摆,不像 RAG OPEN 可空检索转人工降级(ADR-029);LLM 失败已有有界重试 + 三级 Fallback + 翻 `FAILED` 三层兜底,无需熔断再叠一层。
  - Cons:DeepSeek 长时间故障时无 fast-fail,每个任务都要走完重试+Fallback 才 `FAILED`,较慢。
- **B. LLM 也上熔断(连续 429/失败 N 次 OPEN)**
  - Pros:故障时快速失败、省无谓调用。
  - Cons:LLM 是不可降级核心,OPEN 期所有对账直接失败、无 RAG 那样的降级路径,收益 ≤ 现有 `FAILED` 兜底,纯增状态机复杂度与测试面。
- **C. 限流器内置自适应降速(429 反馈调低速率)**
  - Pros:贴合上游真实余量。
  - Cons:实现复杂(反馈环、抖动),本 stage 范围外。

## Decision

选 **A**:LLM 出站只限流不熔断;429/失败沿用有界重试 + 三级 Fallback + `FAILED`;自适应降速 defer。

## Consequences

- 正面:不为不可降级的核心依赖背熔断复杂度;限流 / 熔断职责边界清晰、可向 review 与面试解释。
- 负面:DeepSeek 长故障时无熔断 fast-fail,失败任务较慢才翻 `FAILED`(异步队列下时延非关键路径,可接受;登记)。
