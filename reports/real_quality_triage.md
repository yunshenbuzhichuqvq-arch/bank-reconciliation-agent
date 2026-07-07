# Real Quality Triage Summary

## Metadata

| Key | Value |
|---|---|
| Evaluated At | 2026-07-07T16:20:22.710585Z |
| Harness Comparison | `reports/eval_harness/comparison.json` |
| RAG Matrix | `reports/rag_quality_matrix.json` |
| Agent Real JSON | `(not present)` |
| Performance/Cost JSON | `reports/performance_cost_benchmark.json` |

## Findings

### Measured Pass (2)

- **default_fake_hash_gates**: Default offline safety gates (system + agent) remain passing.
  - Evidence: {"gates": {"system_unsafe_auto_fix_pass": true, "system_hard_constraint_violation_pass": true, "agent_unsafe_auto_fix_pass": true, "agent_hard_constraint_violation_pass": true}, "boundary": "offline, fake-provider, hash embedding"}
- **performance_latency_fake**: Offline latency benchmark measured (fake provider); not representative of real LLM latency.
  - Evidence: {"latency": {"extraction_agent": {"avg_latency_ms": 0.062, "p95_latency_ms": 0.108, "min_latency_ms": 0.04, "max_latency_ms": 0.108, "samples_ms": [0.066, 0.108, 0.057, 0.04, 0.04]}, "rag_search": {"avg_latency_ms": 49.342, "p95_latency_ms": 243.564, "min_latency_ms": 0.707, "max_latency_ms": 243.564, "samples_ms": [243.564, 0.88, 0.782, 0.779, 0.707]}}, "boundary": "fake provider; offline benchmark"}

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

### Deferred Online Metric (4)

- **performance_cost_real**: Real LLM token usage, latency and cost are deferred (fake provider used).
- **online_adoption**: Online human adoption / override rate is not measured in offline eval.
- **production_latency**: Production end-to-end latency and per-agent call latency are not measured.
- **production_cost**: Production LLM token usage, embedding compute cost, and infrastructure cost are not measured.

### Out of Scope (2)

- **llm_as_judge**: LLM-as-Judge evaluation of explanation completeness, reasoning quality, or natural-language audit judgment is not included.
- **immediate_remediation**: Automatic remediation of observed misses is out of scope in this triage stage.

## Resume-Safe Facts

1. **rag**: RAG hash baseline (hybrid_rerank) measured Hit@1=0.433, Recall@5=0.658, MRR=0.568, NDCG@5=0.553
   - Source: `reports/rag_quality_matrix.json`
   - Boundary: offline eval set; hash embedding
2. **latency**: Offline latency benchmark: ExtractionAgent avg=0ms, P95=0ms; RAG avg=49ms, P95=244ms
   - Source: `reports/performance_cost_benchmark.json`
   - Boundary: offline benchmark; fake provider

## Resume Bullet Draft

- RAG quality measured on 120-case offline eval set with hash baseline.

## Claim Boundary

- offline benchmark only; not production SLA
- no online adoption rate measured
- no production traffic or real user data
- DeepSeek Agent Eval not run; real LLM safety not verified
- performance/cost benchmark uses fake provider; not real LLM latency/cost

## Next Stage Recommendations

1. **rag**: RAG hash baseline is below PRD targets. Consider tuning chunk structure or retrieval parameters.
   - Scope: Pick one measured miss bucket; do not relabel eval data to fit output.
2. **rag**: Real embedding backends are not measured. Set up sentence-transformers and rerun with --real-backend-policy auto.
   - Scope: Install sentence-transformers, then compare real embedding quality before changing production defaults.
3. **agent**: Real LLM (DeepSeek) agent quality is not measured. Run the DeepSeek eval command when credentials are available.
   - Scope: Do not tune prompts before measuring real DeepSeek behavior on the existing eval set.
