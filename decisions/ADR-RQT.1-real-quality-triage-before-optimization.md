# ADR-RQT.1: Real quality triage before optimization or runtime default changes

**Slug**: `real-quality-triage-before-optimization`
**Status**: accepted
**Date**: 2026-07-07

## Context

The previous stage produced a clean offline comparison:

- System Eval gates stayed passing.
- RAG improved under `embedding_backend=hash` when using `hybrid_rerank`.
- Agent Eval reached `risk_accuracy=1.0` under `FakeLLMProvider`.

However, the same reports explicitly keep several gaps honest: real DeepSeek quality is not measured, real embedding quality is not part of the combined harness, online human adoption is not measured, and production latency/cost are not measured. Moving directly from fake/hash improvements to production defaults would overstate what the system has proven.

This stage should therefore answer: "Which quality claims are supported by real evidence, which are still fake/hash-only, and what should be optimized next?"

## Options Considered

- Option A: Immediately optimize prompts, retrieval defaults, and production runtime behavior.
  - Pros: May improve visible metrics quickly.
  - Cons: Risks blind tuning without knowing whether the issue comes from real LLM behavior, embedding backend, retrieval mode, or evaluation coverage.
- Option B: Add online adoption, latency, and cost instrumentation first.
  - Pros: Addresses production-readiness gaps.
  - Cons: Requires runtime/schema/API work and still does not answer real model quality for current eval cases.
- Option C: Build a narrow real-quality triage stage before optimization.
  - Pros: Converts known honest gaps into explicit measured / not-run / not-measured findings; preserves the evaluation-driven workflow established by ADR-EH.5 and ADR-EO.1.
  - Cons: This stage may mostly produce reports and diagnosis rather than user-visible product behavior.

## Decision

Choose Option C.

This stage will focus on diagnostic evidence and scope control:

- Keep default CI and default DoD network-free.
- Keep production runtime defaults unchanged unless a later ADR explicitly changes them.
- Measure real RAG quality through opt-in real embedding paths where available.
- Measure real LLM Agent quality through opt-in DeepSeek paths where credentials are available.
- Produce a triage summary that separates measured evidence from environment gaps and deferred online metrics.

## Consequences

- Positive: The project can explain exactly which quality claims are fake/hash-only and which are real-provider or real-embedding backed.
- Positive: Later optimization tasks can be selected from observed misses instead of speculative tuning.
- Negative: The stage will not by itself solve online adoption, latency, or cost gaps.
- Negative: Real-provider and real-embedding evidence may be incomplete on machines without API keys or local model cache.
- Constraint: No report may claim real DeepSeek or real embedding quality unless the corresponding run produced `real_provider_call=true` or an effective non-hash embedding backend in metadata.
