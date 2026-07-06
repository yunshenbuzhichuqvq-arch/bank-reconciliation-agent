# Combined Baseline Evaluation Report

## Metadata

| Key | Value |
|---|---|
| Seed | `20260706` |
| Scenario | `BANK_ENTERPRISE` |
| Normal Rows | 1000 |
| Embedding Backend | `hash` |
| Top K | 5 |
| Evaluated At | 2026-07-06T10:21:52.514761Z |

## System Eval

| Metric | Value |
|---|---|
| case_count | 1007 |
| auto_fix_rate | 0.994042 |
| classification_accuracy | 1.0 |
| branch_accuracy | 1.0 |
| pending_human_rate | 0.005958 |
| fallback_trigger_rate | 0.0 |
| unsafe_auto_fix_rate | 0.0 |
| hard_constraint_violation_rate | 0.0 |

## RAG Eval

| Metric | Value |
|---|---|
| hit_at_1 | 0.1667 |
| recall_at_5 | 0.3875 |
| mrr | 0.2750 |
| ndcg_at_5 | 0.2824 |

## Agent Eval

| Metric | Value |
|---|---|
| case_count | 6.0000 |
| schema_pass_rate | 1.0000 |
| decision_accuracy | 1.0000 |
| evidence_citation_rate | 1.0000 |
| no_evidence_to_human_rate | 1.0000 |
| hard_constraint_violation_rate | 0.0000 |
| unsafe_auto_fix_rate | 0.0000 |
| decision_consistency_rate | 1.0000 |

## Combined Gates

| Gate | Result |
|---|---|
| system_unsafe_auto_fix_pass | PASS |
| system_hard_constraint_violation_pass | PASS |
| agent_unsafe_auto_fix_pass | PASS |
| agent_hard_constraint_violation_pass | PASS |

## Case Counts

- System Eval: 1007
- RAG Eval: 120
- Agent Eval: 6

## Baseline Review Gate

> This is the baseline report. opencode **must stop** after generating this report
> and wait for Codex to review the metrics and update `tasks.md` with at most 1-2
> optimization tasks per ADR-EH.5. No optimization may be implemented before this
> review gate is passed.
