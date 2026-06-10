# ADR-024: DecisionHook 终态路由 vs 2a 三级 Fallback 的职责边界

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: services/workflow.py(_apply_post_hooks / run_item), services/hooks.py(decision_hook / constraint_hook), decisions/ADR-007

## Context

PRD §8.2 把 DecisionHook 描述为「按 confidence 和 RAG 命中路由到不同 Fallback 级别或转人工」。但 2a 已有 ADR-007 三级 Fallback 状态机(L1 标准 → L2 Few-shot → L3 TraceAgent → HUMAN,在 run_item 内由 confidence 驱动升级)。两者都谈「按 confidence 路由」,职责会重叠;若 DecisionHook 也做升级=双重路由 + 搬迁 2a 核心状态机=高回归风险。

## Options

- **A. 切分职责(采纳)** — L1→L2→L3 升级仍由 run_item 状态机负责(ADR-007 不动);DecisionHook 只做终态映射:拿最终 (decision, confidence, fallback_level, rag best_score, constraint) 映射到落库动作(AUTO_FIXED 落库 / PENDING_HUMAN 转人工 / UNRESOLVED 挂账),不触发新 LLM 升级。Pros: 2a 零回归、纯函数易测、职责单一。Cons: 与 PRD 字面略偏,需登记。
- **B. DecisionHook 接管全部 confidence 路由** — Pros: 与 PRD 字面更近、路由集中。Cons: 重写 2a 核心状态机=高回归,违背「2b-1 是加固非重构」定位。

## Decision

采用 A。DecisionHook 定位终态映射;fallback 升级权威留 ADR-007。约束违规时 _apply_post_hooks 同步改 decision=PENDING_HUMAN(保 decision 与 next_action 一致,避免 ledger handle_status 与 next_action 矛盾)。与 PRD 字面偏离在此登记(PRD 属 main 自有文档,留 main 同步)。

## Consequences

- 正面:2a 主链路零回归;DecisionHook/Fallback 边界清晰,避免双重路由。
- 负向:DecisionHook 能力比 PRD 描述窄(不做 LLM 升级);未来若要路由集中化,需重评并可能 supersede 本条。
