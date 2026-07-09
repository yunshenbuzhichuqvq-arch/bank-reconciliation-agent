# Evaluation Gate Summary

| Key | Value |
|---|---|
| Evaluated At | 2026-07-09T12:24:16.934053Z |
| Stage | stage-24-eval-gate-layering |
| Overall Status | pass |

## Source Reports

| Report | Path |
|---|---|
| harness_comparison | `/Users/hunengtao/Projects/AI_agent/bank-reconciliation-agent/reports/eval_harness/comparison.json` |
| schema_conformance | `/Users/hunengtao/Projects/AI_agent/bank-reconciliation-agent/reports/agent_schema_conformance.json` |
| agent_real_json | `/Users/hunengtao/Projects/AI_agent/bank-reconciliation-agent/reports/agent_eval_deepseek_flash_metrics.json` |
| rag_matrix | `/Users/hunengtao/Projects/AI_agent/bank-reconciliation-agent/reports/rag_quality_matrix.json` |
| performance_cost_json | `/Users/hunengtao/Projects/AI_agent/bank-reconciliation-agent/reports/performance_cost_benchmark.json` |
| triage_json | `/Users/hunengtao/Projects/AI_agent/bank-reconciliation-agent/reports/real_quality_triage.json` |

## CI Layer

- Status: `pass`
- Blocks CI: False
- Blocks Release: False
- Required For Default CI: True

| Check | Status | Blocks CI | Blocks Release | Summary |
|---|---|---|---|---|
| ci_default_fake_hash_harness_gates | pass | False | False | Deterministic fake/hash harness after-gates all pass. |
| ci_agent_schema_conformance | pass | False | False | Agent schema conformance rate is 1.0. |

## Manual Diagnostic Layer

- Status: `pass`
- Blocks CI: False
- Blocks Release: False
- Required For Default CI: False

| Check | Status | Blocks CI | Blocks Release | Summary |
|---|---|---|---|---|
| manual_deepseek_agent_eval | pass | False | False | DeepSeek Agent Eval evidence is trusted (real provider call). |
| manual_real_embedding_rag_matrix | pass | False | False | Real embedding RAG matrix has a trusted measured non-hash backend. |
| manual_real_provider_performance_cost | pass | False | False | Real provider performance/cost evidence is trusted. |

## Release Layer

- Status: `pass`
- Blocks CI: False
- Blocks Release: False
- Required For Default CI: False

| Check | Status | Blocks CI | Blocks Release | Summary |
|---|---|---|---|---|
| release_effective_unsafe_auto_fix_zero | pass | False | False | Trusted DeepSeek effective unsafe auto-fix rate is 0. |
| release_effective_hard_constraint_violation_zero | pass | False | False | Trusted DeepSeek effective hard constraint violation rate is 0. |
| release_real_provider_trust_visible | pass | False | False | Real provider trust metadata is trusted DeepSeek evidence. |
| release_real_embedding_trust_visible | pass | False | False | Real embedding trust metadata satisfies the manual real embedding rule. |
| release_performance_cost_trust_visible | pass | False | False | Performance/cost trust metadata is trusted real-provider evidence. |

## Claim Boundary

- CI layer is deterministic: fake-provider harness gates and agent schema conformance run without credentials, network, token spend, or model loads.
- Manual diagnostic layer is opt-in: real DeepSeek Agent Eval, real embedding RAG matrix, and real provider performance/cost require external resources and never block default CI.
- Release layer fails closed: missing or untrusted safety/trust metadata is reported as an environment gap that blocks release, not as a pass.
- Fake-provider, hash-embedding, fallback, missing, or stale evidence must not be presented as trusted real-provider or real-embedding evidence.
- Release safety is based on effective policy-gated system output; raw provider safety metrics are diagnostic caveats only.

## Exit Semantics

- Return `0` when the CI layer passes, even if manual diagnostics or release gates show environment gaps.
- Return `1` when the CI layer fails.
- With `--fail-on-release-block`, return `2` when CI passes but the release layer is blocked.
