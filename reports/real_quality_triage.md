# Real Quality Triage Summary

## Metadata

| Key | Value |
|---|---|
| Evaluated At | 2026-07-09T07:46:19.562574Z |
| Harness Comparison | `reports/eval_harness/comparison.json` |
| RAG Matrix | `reports/rag_quality_matrix.json` |
| Agent Real JSON | `reports/agent_eval_deepseek_flash_metrics.json` |
| Performance/Cost JSON | `reports/performance_cost_benchmark.json` |

## Findings

### Measured Pass (3)

- **default_fake_hash_gates**: Default offline safety gates (system + agent) remain passing.
  - Evidence: {"gates": {"system_unsafe_auto_fix_pass": true, "system_hard_constraint_violation_pass": true, "agent_unsafe_auto_fix_pass": true, "agent_hard_constraint_violation_pass": true}, "boundary": "offline, fake-provider, hash embedding"}
- **real_llm_agent_eval**: DeepSeek Agent Eval safety gates pass with trusted real provider.
  - Evidence: {"provider_effective": "deepseek", "real_provider_call": true, "unsafe_auto_fix_rate": 0.0, "hard_constraint_violation_rate": 0.0, "gates": {"unsafe_auto_fix_pass": true, "hard_constraint_violation_pass": true}, "trusted": true}
- **performance_cost_real**: Real DeepSeek benchmark measured with trusted token/cost evidence. Estimated cost: 0.001446375 USD (0.000289275 per case).
  - Evidence: {"provider_effective": "deepseek", "model_effective": "deepseek-v4-flash", "latency": {"extraction_agent": {"avg_latency_ms": 3312.742, "p95_latency_ms": 4661.419, "min_latency_ms": 1493.089, "max_latency_ms": 4661.419, "samples_ms": [3240.832, 4495.113, 2673.257, 4661.419, 1493.089]}, "rag_search": {"avg_latency_ms": 1308.533, "p95_latency_ms": 6278.735, "min_latency_ms": 59.224, "max_latency_ms": 6278.735, "samples_ms": [6278.735, 59.224, 68.768, 67.165, 68.774]}}, "tokens": {"token_usage_available": true, "input_tokens": 1115, "output_tokens": 1105, "total_tokens": 2220, "unavailable_reason": null}, "cost": {"cost_available": true, "estimated_cost_usd": "0.001446375", "per_case_estimated_cost_usd": "0.000289275", "assumptions": "DeepSeek v4 Pro pricing: input $0.435/1M, output $0.87/1M", "unavailable_reason": null}, "trust": {"trusted": true, "real_provider_evidence": true, "cost_evidence_available": true, "reasons": []}}

### Measured Gap (3)

- **rag_hash**: RAG hash baseline (hybrid_rerank) below PRD targets: Recall@5=0.700, MRR=0.644, NDCG@5=0.617
  - Evidence: {"backend": "hash", "selected_mode": "hybrid_rerank", "metrics": {"hit_at_1": 0.5333333333333333, "recall_at_5": 0.7, "mrr": 0.6443055555555556, "ndcg_at_5": 0.6168479692395881}}
- **rag_bge_small_dense**: RAG backend bge_small (dense) measured but below PRD targets: Recall@5=0.787, MRR=0.713, NDCG@5=0.695
  - Evidence: {"backend": "bge_small", "effective_backend": "bge_small", "selected_mode": "dense", "metrics": {"hit_at_1": 0.5916666666666667, "recall_at_5": 0.7875, "mrr": 0.712638888888889, "ndcg_at_5": 0.6947968918851234}}
- **rag_bge_m3_dense**: RAG backend bge_m3 (dense) measured but below PRD targets: Recall@5=0.825, MRR=0.735, NDCG@5=0.721
  - Evidence: {"backend": "bge_m3", "effective_backend": "bge_m3", "selected_mode": "dense", "metrics": {"hit_at_1": 0.6333333333333333, "recall_at_5": 0.825, "mrr": 0.7352777777777778, "ndcg_at_5": 0.7209402917441399}}

### Deferred Online Metric (3)

- **online_adoption**: Online human adoption / override rate is not measured in offline eval.
- **production_latency**: Production end-to-end latency and per-agent call latency are not measured.
- **production_cost**: Production LLM token usage, embedding compute cost, and infrastructure cost are not measured.

### Out of Scope (2)

- **llm_as_judge**: LLM-as-Judge evaluation of explanation completeness, reasoning quality, or natural-language audit judgment is not included.
- **immediate_remediation**: Automatic remediation of observed misses is out of scope in this triage stage.

## Resume-Safe Facts

1. **rag**: RAG hash baseline (hybrid_rerank) measured Hit@1=0.533, Recall@5=0.700, MRR=0.644, NDCG@5=0.617
   - Source: `reports/rag_quality_matrix.json`
   - Boundary: offline eval set; hash embedding
2. **rag**: RAG bge_small baseline (dense) measured Hit@1=0.592, Recall@5=0.787, MRR=0.713, NDCG@5=0.695
   - Source: `reports/rag_quality_matrix.json`
   - Boundary: offline eval set; bge_small embedding
3. **rag**: RAG bge_m3 baseline (dense) measured Hit@1=0.633, Recall@5=0.825, MRR=0.735, NDCG@5=0.721
   - Source: `reports/rag_quality_matrix.json`
   - Boundary: offline eval set; bge_m3 embedding
4. **agent**: DeepSeek Agent Eval: decision_accuracy=1.000, risk_accuracy=1.000, unsafe_auto_fix_rate=0.000, hard_constraint_violation_rate=0.000
   - Source: `reports/agent_eval_deepseek_flash_metrics.json`
   - Boundary: offline eval set; real DeepSeek provider
5. **cost**: Estimated cost 0.001446375 USD (0.000289275 per case, 5 runs)
   - Source: `reports/performance_cost_benchmark.json`
   - Boundary: offline benchmark; estimated from token counts
6. **latency**: Offline latency benchmark: ExtractionAgent avg=3313ms, P95=4661ms; RAG avg=1309ms, P95=6279ms
   - Source: `reports/performance_cost_benchmark.json`
   - Boundary: offline benchmark; real provider

## Resume Bullet Draft

- RAG quality measured on 120-case offline eval set with hash baseline.
- Agent safety evaluation: DeepSeek Agent Eval: decision_accuracy=1.000, risk_accuracy=1.000, unsafe_auto_fix_rate=0.000, hard_constraint_violation_rate=0.000
- Performance/cost benchmark: Estimated cost 0.001446375 USD (0.000289275 per case, 5 runs)

## Claim Boundary

- offline benchmark only; not production SLA
- no online adoption rate measured
- no production traffic or real user data
- DeepSeek Agent Eval safety gates pass with no policy intervention.
- performance/cost benchmark uses real provider

## Next Stage Recommendations

1. **rag**: RAG hash baseline is below PRD targets. Consider tuning chunk structure or retrieval parameters.
   - Scope: Pick one measured miss bucket; do not relabel eval data to fit output.
