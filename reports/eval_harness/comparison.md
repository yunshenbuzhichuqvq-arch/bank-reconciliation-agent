# Combined Harness Comparison Report

## Metadata Compatibility

| Key | Value |
|---|---|
| Seed Match | True |
| Normal Rows Match | True |
| Embedding Backend Match | True |
| Top K Match | True |
| Before RAG Mode | `dense` |
| After RAG Mode | `dense` |

## System Eval Deltas

| Metric | Δ Value |
|---|---|
| auto_fix_rate | 0.000000 |
| branch_accuracy | 0.000000 |
| case_count | 0.000000 |
| classification_accuracy | 0.000000 |
| fallback_trigger_rate | 0.000000 |
| hard_constraint_violation_rate | 0.000000 |
| pending_human_rate | 0.000000 |
| unsafe_auto_fix_rate | 0.000000 |

## RAG Eval Deltas

| Metric | Δ Value |
|---|---|
| hit_at_1 | 0.000000 |
| mrr | 0.000000 |
| ndcg_at_5 | 0.000000 |
| recall_at_5 | 0.000000 |

## Agent Eval Deltas

| Metric | Δ Value |
|---|---|
| case_count | 0.000000 |
| decision_accuracy | 0.000000 |
| decision_consistency_rate | 0.000000 |
| evidence_citation_rate | 0.000000 |
| hard_constraint_violation_rate | 0.000000 |
| no_evidence_to_human_rate | 0.000000 |
| risk_accuracy | +0.166667 |
| schema_pass_rate | 0.000000 |
| unsafe_auto_fix_rate | 0.000000 |

## Combined Gates

| Gate | Before | After |
|---|---|---|
| agent_hard_constraint_violation_pass | True | True |
| agent_unsafe_auto_fix_pass | True | True |
| system_hard_constraint_violation_pass | True | True |
| system_unsafe_auto_fix_pass | True | True |

All gates unchanged.

## Honest Gaps / Not Measured

- Real LLM provider quality: Agent Eval uses FakeLLMProvider; decision quality under a real LLM (e.g. DeepSeek) is not measured by this baseline.
- Real embedding quality: RAG Eval uses embedding_backend=hash; real embedding (e.g. bge-m3, bge-small) retrieval quality is not measured here.
- LLM-as-Judge: No LLM-based evaluation of explanation completeness, reasoning quality, or natural-language audit judgment is included.
- Online human adoption/override rate: This offline eval does not measure how often human reviewers accept, override, or escalate system decisions in production.
- Production latency: End-to-end system latency and per-agent call latency are not measured in this offline eval.
- Production cost: LLM token usage, embedding compute cost, and infrastructure cost are not measured in this offline eval.