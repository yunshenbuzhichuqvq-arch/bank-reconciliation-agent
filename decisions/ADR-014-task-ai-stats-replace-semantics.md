# ADR-014: 任务级 ai_stats 采用幂等覆盖(replace)语义

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(review 提为独立决策)
- Related: services/reconciliation.py, services/task.py, t_reconciliation_task, decisions/ADR-013

## Context

`ReconciliationService` AI 收尾阶段对同一 `task_id` 的 ledger / rag_log / agent_log 行统一用 `replace_task_rows` 幂等覆盖。任务级统计列(`ai_processed_rows` / `fallback_l2_rows` / `fallback_l3_rows` / `total_llm_tokens` / `total_llm_cost`)语义是「该次任务处理完成后的汇总快照」,而非可无限叠加的事件流。原实现 `increment_ai_stats` 对这些列做 `col = col + delta` 累加,与同段 replace 语义不一致:同一 `task_id` 重跑收尾会重复累加、统计漂移。该改动最初由 TASK-2a2.9(scope 写明「don't touch 业务逻辑」)夹带实现,经 review 提为独立决策显式化。

## Options

- **A. increment 累加(原实现)** — Pros: 适合「事件流持续累计」模型。Cons: 与 `replace_task_rows` 不一致;同任务重跑收尾重复累加,汇总列漂移;与「汇总快照」语义冲突。
- **B. replace 覆盖(采纳)** — Pros: 与 ledger/rag_log/agent_log 幂等覆盖一致,重跑以本次计算结果为准,主链路收尾全程同一语义。Cons: 不保留跨次累计(但这些列语义本就是单次汇总,非真实损失)。

## Decision

采用 **B**。`task.py` 移除 `increment_ai_stats` 生产接口,收尾统一走 `replace_ai_stats`。跨次累计需求若未来出现,另立事件/审计表承载,不复用 task 汇总列。

## Consequences

- `reconciliation` 收尾写库与 ledger/rag_log/agent_log 的 replace 模式保持一致;同任务重跑不再导致 `ai_stats` 漂移。
- 移除 `increment_ai_stats` 公有接口(测试加 `hasattr` 守卫防回归);依赖该方法的旧测试改用 replace 覆盖语义断言。
