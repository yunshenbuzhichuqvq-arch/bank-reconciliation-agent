# Combined After-Run Evaluation Report

## Metadata

| Key | Value |
|---|---|
| Seed | `20260706` |
| Scenario | `BANK_ENTERPRISE` |
| Normal Rows | 1000 |
| Embedding Backend | `hash` |
| Top K | 5 |
| RAG Mode | `hybrid_rerank` |
| Evaluated At | 2026-07-07T02:46:50.199728Z |

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
| hit_at_1 | 0.4333 |
| recall_at_5 | 0.6583 |
| mrr | 0.5682 |
| ndcg_at_5 | 0.5528 |

## Agent Eval

| Metric | Value |
|---|---|
| case_count | 6.0000 |
| schema_pass_rate | 1.0000 |
| decision_accuracy | 1.0000 |
| risk_accuracy | 1.0000 |
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

## Honest Gaps / Not Measured

- Real LLM provider quality: Agent Eval uses FakeLLMProvider; decision quality under a real LLM (e.g. DeepSeek) is not measured by this baseline.
- Real embedding quality: RAG Eval uses embedding_backend=hash; real embedding (e.g. bge-m3, bge-small) retrieval quality is not measured here.
- LLM-as-Judge: No LLM-based evaluation of explanation completeness, reasoning quality, or natural-language audit judgment is included.
- Online human adoption/override rate: This offline eval does not measure how often human reviewers accept, override, or escalate system decisions in production.
- Production latency: End-to-end system latency and per-agent call latency are not measured in this offline eval.
- Production cost: LLM token usage, embedding compute cost, and infrastructure cost are not measured in this offline eval.