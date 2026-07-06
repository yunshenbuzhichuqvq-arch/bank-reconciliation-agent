# ADR-EH.4: Agent 评测优先规则判定，不先引入 LLM-as-Judge

**Slug**: `agent-eval-rule-based-before-llm-judge`
**Status**: accepted
**Date**: 2026-07-06

### Context

现有 Agent 相关测试主要覆盖 schema conformance、固定 fake provider 决策分布和部分 workflow 行为。它能证明“输出结构合法”，但还不足以证明“决策质量可评估”。Agent 评测需要针对 AuditAgent 的金融安全边界：无证据不能自动判定，非人工决策必须有 evidence，危险自动平账必须为 0。

当前阶段的目标是快速形成可复现、可讲清的评测证据，而不是建立复杂的主观评分体系。

### Options Considered

- **Option A: 只保留 schema conformance**
  - Pros: 已有基础，成本低。
  - Cons: 只能证明 JSON 合法，不能证明决策是否对。
- **Option B: 规则判定 Agent Eval（采纳）**
  - Pros: 确定性强、便于 pytest、能直接覆盖安全红线；适合当前求职冲刺。
  - Cons: 对“解释文字质量”的评价有限。
- **Option C: LLM-as-Judge 多维评分**
  - Pros: 可以评价理由完整性、表达质量和复杂 case。
  - Cons: 非确定性、成本高、需要 judge prompt 和复核机制；本 stage 先不做。

### Decision

采用 **Option B**。Agent Eval case 使用结构化输入和规则化期望，不先引入 LLM-as-Judge。每个 case 至少包含：

- `case_id`
- `error_type`
- `exception_branch`
- `bank_amount`
- `clear_amount`
- `amount_diff`
- `rag_evidence`
- `tool_result` 或 `trace_context`
- `expected_decision`
- `expected_risk_level`
- `must_include_evidence`
- `must_not_auto_fix`

Agent Eval 指标至少包括：

- `schema_pass_rate`
- `decision_accuracy`
- `evidence_citation_rate`
- `no_evidence_to_human_rate`
- `hard_constraint_violation_rate`，门禁目标为 0
- `unsafe_auto_fix_rate`，门禁目标为 0
- `decision_consistency_rate`

真实 provider 下允许统计分布而非断言具体自然语言；fake provider 下作为确定性 baseline。

### Consequences

- 正向：Agent 评测可以直接覆盖面试最容易被追问的安全问题：为什么不会乱自动平账。
- 负向：暂时不能量化“解释是否足够像资深审计员”；这类主观质量留给后续 LLM-as-Judge 或人工 review。
- 约束：任何 `unsafe_auto_fix_rate > 0` 或 `hard_constraint_violation_rate > 0` 都视为 blocking，不允许作为优化成功结果。
