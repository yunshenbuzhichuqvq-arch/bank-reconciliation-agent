# ADR-035: 记忆回滚——人工推翻清短期记忆

- Status: Accepted (2026-06-11)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/review.py(_is_override, _apply_review_side_effects), services/memory/short_term.py(delete_by_queue), decisions/ADR-023, decisions/ADR-027

## Context

PRD §16.3 行1797-1798:人工复核推翻 Agent 建议时(如 Agent 建议 `AUTO_FIXED` 但人工判 `FORCE_HOLD`),从短期记忆删除该条,避免错误上下文污染后续 Agent。2b-2 的 `approve` 只写长期(确认结果),未处理「推翻时清短期」。

## Options

- **A. `approve` 内按「实质冲突」判定 + 清短期(采纳)** — 判定「推翻」:人工 `action` 与 Agent `ai_suggestion`/`decision` 实质冲突(如 `APPROVED_MATCH/AUTO_FIXED` vs `FORCE_HOLD/HELD`);冲突时在 `review.approve` 记忆副作用内,按 `thread_id` + `queue_id`/`flow_id` 删该条短期记忆(`ShortTermMemoryService` 加 `delete`);非冲突沿用 2b-2。失败仅 WARNING(ADR-023)。
  - Pros: 兑现 §16.3、防错误上下文污染、复用副作用通道。
  - Cons: 「实质冲突」枚举映射需在 spec 定死。
- **B. 不删,只标记 `invalidated`** — Cons: 读取仍需过滤、半套方案;PRD 明确要求删除。

## Decision

采用 **A**。冲突判定的 action↔suggestion 映射在 spec 定死;删除按隔离键并防误删他条。

## Consequences

- 正面:记忆一致性(§16.3)、错误判断不留存污染后续召回。
- 负面:冲突判定依赖枚举映射(spec 维护);删除按隔离键须防误删;短期删除会改变摘要 `compressed_count` 锚点的计数口径(spec 须注明:删除发生在 approve 路径,与压缩触发的 count 口径协调)。
