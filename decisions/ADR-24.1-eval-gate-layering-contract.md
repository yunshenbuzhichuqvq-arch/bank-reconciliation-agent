# ADR-24.1: Eval gate outcomes use an explicit layered gate contract

**Slug**: `eval-gate-layering-contract`
**Status**: accepted
**Date**: 2026-07-09

### Context

`docs/interview/eval-harness-next-steps.md` leaves one evaluation-harness gap after the
real DeepSeek safety re-eval, Agent Eval expansion, real embedding matrix, RAG before/after
reporting, and real provider performance/cost benchmark: the project still needs to explain
which checks are deterministic CI gates, which checks are opt-in real-environment diagnostics,
and which results are release blockers.

The current reports already contain most source facts:

- default fake/hash harness gates in `reports/eval_harness/comparison.json`;
- trusted DeepSeek Agent Eval metadata in `reports/agent_eval_deepseek_flash_metrics.json`;
- effective embedding backend and fallback state in `reports/rag_quality_matrix.json`;
- real provider latency/token/cost trust metadata in `reports/performance_cost_benchmark.json`;
- triage categories and resume-safe boundaries in `reports/real_quality_triage.json`.

However, the gate contract is currently implicit across reports and historical ADRs. Reviewers
must inspect multiple files to know whether a failing or missing real-provider run should block
local development, block release, or be recorded as an environment gap.

### Options Considered

- Option A: Make every evaluation with real providers and real embeddings part of the default
  required gate.
  Pros: Maximizes freshness of real-environment evidence.
  Cons: Violates ADR-RQT.3, ADR-21.1, and ADR-23.4; depends on API keys, network, local model
  cache, token spend, and provider behavior; makes normal local and CI feedback non-deterministic.
- Option B: Keep the separation in prose only and rely on `AGENTS.md` plus PR review discipline.
  Pros: No code or report changes.
  Cons: The release decision remains subjective; reports cannot be checked by a single script;
  future contributors can overclaim fake/hash or fallback evidence.
- Option C: Add an explicit layered gate contract that classifies each check as CI, manual
  diagnostic, or release gate, with machine-readable outcome and claim boundary.
  Pros: Preserves deterministic CI while making real evidence and release blockers auditable.
  Cons: Adds one more evaluation artifact and requires keeping gate definitions aligned with
  existing reports.

### Decision

Adopt Option C.

Stage 24 will define an explicit gate contract with three layers:

- CI layer: deterministic, low-cost checks that can run without credentials, network, or local
  embedding model cache.
- Manual diagnostic layer: opt-in checks that may require DeepSeek credentials, real embedding
  dependencies, local model cache, network, or token spend.
- Release layer: evidence and redline checks that decide whether a PR can honestly claim the
  evaluation harness is safe and properly bounded.

The contract must preserve historical ADR boundaries: real DeepSeek eval, real embedding matrix,
and real provider benchmark remain opt-in diagnostics; missing opt-in runs are not fake passes.
Release gate output may require these diagnostics to be visible as trusted, unavailable, or
environment-gap evidence, but must not force every local or CI run to execute them.

### Consequences

- Positive: Reviewers get one gate summary that explains what blocks CI, what blocks release,
  and what is only diagnostic evidence.
- Positive: Fake/hash baseline claims remain separated from real DeepSeek and real embedding
  claims.
- Positive: Environment gaps and fallback state become explicit instead of being inferred from
  scattered reports.
- Negative: Gate definitions become another contract to maintain when future eval reports change.
- Negative: A release gate may fail because trusted real-environment evidence is missing, even
  though deterministic local tests pass.
- Constraint: No release claim may describe fake-provider, hash, fallback, missing, or stale
  diagnostic evidence as trusted real-provider or real-embedding evidence.
