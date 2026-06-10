# ADR-022: 硬约束 C1–C6 分层落地与失败策略

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: agents/audit_agent.py(AuditDecision Literal + C2 model_validator + decide_with_llm), services/hooks.py(schema_hook / constraint_hook), services/workflow.py(_audit_with_schema_retry / _apply_post_hooks), decisions/ADR-007

## Context

audit_agent.AuditDecision 原仅 confidence 有 Field 约束;decision/risk_level 为自由 str,PRD §8.3 的 C1–C6 几乎全未强制。PRD §8.2 规定两类失败语义不同:SchemaHook 失败→重试≤3→转人工;ConstraintHook 失败→直接转人工不重试(业务规则不应被绕过)。

## Options

- **A. 按「结构 vs 业务」分层(采纳)** — SchemaHook 用 Pydantic 承载 C1(decision 收 Literal)、C2(evidence 非空 validator);ConstraintHook 用自定义 ConstraintValidator 承载 C3–C6(跨字段 / 依赖 RAG best_score)。SchemaHook 失败重试≤3→人工;ConstraintHook 失败直接人工。Pros: 失败语义清晰、与 PRD 一致、可单测、C6 依赖的 model 外信息放 ConstraintHook 自然。Cons: decision 收 Literal 是破坏性变更,所有构造点须对齐。
- **B. 全塞 Pydantic validator(含 C3–C6)** — Pros: 单一校验入口。Cons: 跨字段业务规则难表达「重试 vs 转人工」差异化失败策略;C6 依赖 model 外 best_score 别扭。

## Decision

采用 A。C1/C2 落 SchemaHook(Pydantic),C3–C6 落 ConstraintHook(自定义)。decision 收 Literal["AUTO_FIXED","PENDING_HUMAN","UNRESOLVED"]。C2 限定:**非 PENDING_HUMAN 时**才要求 evidence 非空——PRD 字面 blanket「evidence 非空」与「RAG 无据转人工不臆造 evidence」红线冲突(无命中时合法地 PENDING_HUMAN + 空 evidence),故收窄。

## Consequences

- 正面:硬门禁可单测、失败策略分明;Agent 输出从「软建议」变「硬约束后落库」。
- 负向:decision 枚举收紧需同步所有构造点与测试;C5/C6 与 run_item 既有 fallback 判断重叠(双保险),权威判定在 ConstraintHook。
- 落地补遗:decide_with_llm 把 LLM 自由 str decision 构造 AuditDecision,枚举外值(如 "APPROVED_MATCH")原会抛 ValidationError 掉外层粗兜底——TASK-2b1.7 修为捕获后走 agent _fallback_decision 优雅降级(保留 evidence / 可溯源 reason)。
