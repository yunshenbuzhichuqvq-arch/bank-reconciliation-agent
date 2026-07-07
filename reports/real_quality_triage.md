# Real Quality Triage Summary

## Metadata

| Key | Value |
|---|---|
| Evaluated At | 2026-07-07T08:06:58.400813Z |
| Harness Comparison | `reports/eval_harness/comparison.json` |
| RAG Matrix | `reports/rag_quality_matrix.json` |
| Agent Real JSON | `reports/agent_eval_deepseek_flash_metrics.json` |

## Findings

### Measured Pass (1)

- **default_fake_hash_gates**: Default offline safety gates (system + agent) remain passing.
  - Evidence: {"gates": {"system_unsafe_auto_fix_pass": true, "system_hard_constraint_violation_pass": true, "agent_unsafe_auto_fix_pass": true, "agent_hard_constraint_violation_pass": true}, "boundary": "offline, fake-provider, hash embedding"}

### Measured Gap (1)

- **rag_hash**: RAG hash baseline (hybrid_rerank) below PRD targets: Recall@5=0.658, MRR=0.568, NDCG@5=0.553
  - Evidence: {"backend": "hash", "selected_mode": "hybrid_rerank", "metrics": {"hit_at_1": 0.43333333333333335, "recall_at_5": 0.6583333333333333, "mrr": 0.5681944444444444, "ndcg_at_5": 0.5528158133454631}}

### Environment Gap (3)

- **rag_bge_small**: RAG backend bge_small is not_run (real backend policy is skip).
  - Evidence: {"requested_backend": "bge_small", "effective_backend": null, "status": "not_run", "reason": "real backend policy is skip"}
- **rag_bge_m3**: RAG backend bge_m3 is not_run (real backend policy is skip).
  - Evidence: {"requested_backend": "bge_m3", "effective_backend": null, "status": "not_run", "reason": "real backend policy is skip"}
- **real_llm_agent_eval**: DeepSeek Agent Eval report is not present. Real LLM quality is not measured.
  - Evidence: {"report_present": false, "hint": "Run: uv run python -m scripts.eval_agent --cases data/agent_eval_cases.json --provider deepseek --model deepseek-v4-flash --report reports/agent_eval_deepseek_flash.md --json-report reports/agent_eval_deepseek_flash_metrics.json"}

### Deferred Online Metric (3)

- **online_adoption**: Online human adoption / override rate is not measured in offline eval.
- **production_latency**: Production end-to-end latency and per-agent call latency are not measured.
- **production_cost**: Production LLM token usage, embedding compute cost, and infrastructure cost are not measured.

### Out of Scope (2)

- **llm_as_judge**: LLM-as-Judge evaluation of explanation completeness, reasoning quality, or natural-language audit judgment is not included.
- **immediate_remediation**: Automatic remediation of observed misses is out of scope in this triage stage.

## Next Stage Recommendations

1. **rag**: RAG hash baseline is below PRD targets. Consider tuning chunk structure or retrieval parameters.
   - Scope: Pick one measured miss bucket; do not relabel eval data to fit output.
2. **rag**: Real embedding backends are not measured. Set up sentence-transformers and rerun with --real-backend-policy auto.
   - Scope: Install sentence-transformers, then compare real embedding quality before changing production defaults.
3. **agent**: Real LLM (DeepSeek) agent quality is not measured. Run the DeepSeek eval command when credentials are available.
   - Scope: Do not tune prompts before measuring real DeepSeek behavior on the existing eval set.
