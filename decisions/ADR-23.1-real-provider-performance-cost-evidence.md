# ADR-23.1: Real provider benchmark refreshes canonical performance/cost evidence

**Slug**: `real-provider-performance-cost-evidence`
**Status**: accepted
**Date**: 2026-07-09

### Context

`docs/interview/eval-harness-next-steps.md` lists Stage E as the remaining
evaluation-harness gap: real provider latency / token / cost benchmark.

Stage 17 already established an offline performance/cost benchmark contract in
`decisions/ADR-17.4-performance-cost-offline-benchmark-evidence.md`, but the
current canonical benchmark report still records `provider_effective=fake`.
`reports/real_quality_triage.md` therefore correctly treats real LLM latency,
token usage, and cost as deferred. Stage 23 needs to turn that deferred item
into measured evidence when DeepSeek credentials and network are available,
without claiming production SLA or online cost.

### Options Considered

- Option A: Keep the fake provider benchmark as the only benchmark evidence.
  Pros: deterministic, free, and CI-friendly. Cons: cannot answer the Stage E
  requirement and cannot support real LLM latency or cost claims.
- Option B: Refresh the canonical performance/cost reports with a real DeepSeek
  benchmark and make trust/fallback state explicit. Pros: reuses the existing
  report surface, gives reviewers one source of truth, and directly closes the
  Stage E gap. Cons: requires API credentials, network access, token spend, and
  may fail for reasons unrelated to code.
- Option C: Add production telemetry for online latency and cost before doing
  the offline benchmark. Pros: closest to production operations. Cons: much
  larger scope, requires runtime instrumentation and traffic semantics that are
  explicitly outside the current evaluation-harness backlog.

### Decision

Choose Option B.

Stage 23 will refresh the canonical performance/cost benchmark artifacts only
when a trusted real provider run is available:

- `reports/performance_cost_benchmark.json`
- `reports/performance_cost_benchmark.md`

The refreshed benchmark is trusted only if the report records:

- `provider_requested == "deepseek"`
- `provider_effective == "deepseek"`
- `model_requested` and `model_effective`
- current stage `evaluated_at`
- non-empty latency samples for the measured components
- token and cost metadata, or an explicit token/cost unavailable state

If DeepSeek credentials, network, provider errors, or token metadata prevent a
trusted run, Stage 23 must record an environment gap instead of preserving or
relabeling fake-provider evidence as real-provider evidence.

### Consequences

- Positive: Stage 23 can close the next-steps Stage E gap with report files that
  are already part of the repository evidence model.
- Positive: Reviewers can distinguish real provider evidence from deterministic
  fake-provider baseline evidence.
- Negative: The stage depends on external provider availability and may produce
  an environment-gap result even if local code is correct.
- Negative: Canonical report files will be overwritten, so the old fake-provider
  benchmark remains available through git history rather than side-by-side files.
