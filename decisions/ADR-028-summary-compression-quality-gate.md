# ADR-028: 摘要压缩触发 + 质量验证门禁 + 失败降级不压缩

- Status: Accepted (2026-06-10)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/memory/manager.py(_try_compact_summary/_summary_passes_validation), services/memory/summary.py, core/llm/provider.py

## Context

PRD §7.4:摘要记忆满 20 笔触发 LLM 压缩(DeepSeek)成 ~300 token,有关键信息丢失风险(漏某笔 HIGH 风险或 PENDING_HUMAN 的处理结果)。压缩质量需可验证。

## Options

- **A. 快照 + 回检 + 失败降级(采纳)** — 触发时先把 20 条原始记录写临时快照(JSON);LLM 压缩后回检:所有 `risk_level=HIGH` 被提及、所有 `decision=PENDING_HUMAN` 保留、摘要含 `flow_id` 数 ≥ 原始 80%;任一不过 → 丢弃压缩结果、保留全量记录、记 WARNING。压缩 LLM 走现有 `LLMProvider`(fake 默认 / deepseek)。
  - Pros: 与 PRD §7.4 一致;信息丢失可拦截;降级安全(宁可不压缩不可丢关键)。
  - Cons: 回检是启发式(字符串/flow_id 命中),非语义等价(语义相似度评分留 V1)。
- **B. 压缩不验证** — Cons: 关键信息静默丢失,违金融可追溯红线。
- **C. 压缩推迟 V1** — Cons: PRD 要 2b 实现;长 thread 的 context 会膨胀。

## Decision

采用 **A**。压缩为副作用(满 20 笔触发,非阻塞主决策);回检阈值(HIGH 全提及 / PENDING_HUMAN 全保留 / flow_id ≥80%)可配置。

## Consequences

- 正面:压缩质量有门禁、失败安全降级;复用 LLMProvider 不引依赖。
- 负面:回检是启发式,过严→常降级不压缩(context 不收敛)、过松→漏检丢失,阈值需可调;摘要触发是副作用,绝不阻塞主决策路径。「满 20」口径按未过期短期行计数(TASK-2b2.11 统一 count 与取数口径)。
