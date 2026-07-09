# ADR-24.2: Release gates fail closed on safety redlines and missing trust metadata

**Slug**: `release-gates-fail-closed-trust-metadata`
**Status**: accepted
**Date**: 2026-07-09

### Context

The next-steps document names three release gate requirements:

- effective `unsafe_auto_fix_rate` must be 0;
- effective `hard_constraint_violation_rate` must be 0;
- provider fallback and embedding fallback must be visible in reports.

Historical ADRs already enforce similar trust rules:

- ADR-RQT.3 requires real DeepSeek reports to record requested/effective provider and real call
  state.
- ADR-21.3 requires RAG matrix rows to expose requested backend, effective backend, status, and
  reason.
- ADR-23.4 keeps real provider performance/cost as manual evidence, with deterministic tests
  around trust classification.

Stage 24 needs to make the release decision deterministic: if the required evidence is missing,
partial, fallback, or unsafe, the release gate should not silently pass.

### Options Considered

- Option A: Treat missing diagnostic reports as warnings only.
  Pros: Fewer blocked releases when credentials or local model cache are unavailable.
  Cons: A PR could claim real provider or real embedding readiness without trusted evidence.
- Option B: Fail release gates only on explicit safety metric failures, but ignore missing trust
  metadata.
  Pros: Focuses on the two most important redlines.
  Cons: Fallback-to-fake or fallback-to-hash can still be misread as trusted evidence.
- Option C: Fail closed for safety redlines and for missing/untrusted trust metadata required by
  the layer being evaluated.
  Pros: Prevents overclaiming and makes release status auditable.
  Cons: Requires environment-gap outcomes to be explicit and may block release claims until
  manual diagnostics are rerun or deliberately scoped out.

### Decision

Adopt Option C.

Release gate classification must fail closed when:

- effective unsafe auto-fix rate is non-zero or absent from required safety reports;
- effective hard-constraint violation rate is non-zero or absent from required safety reports;
- a real-provider claim lacks trusted `provider_effective=deepseek` and `real_provider_call=true`;
- a real-embedding claim lacks a measured non-hash effective backend matching the requested
  backend;
- a fallback or environment gap is hidden instead of reported as fallback, unavailable, not-run,
  or environment-gap state.

The release layer may still distinguish "release blocked by unsafe result" from "release blocked
by missing trusted evidence" so Report Back and PR review can describe the real reason.

### Consequences

- Positive: Safety regressions and untrusted evidence cannot accidentally pass release review.
- Positive: The system can explain the difference between code failure and environment gap.
- Positive: This aligns release semantics with the project's existing effective-provider and
  effective-backend evidence model.
- Negative: Some stage branches may finish implementation but remain unable to claim release
  readiness until manual diagnostics are rerun.
- Negative: Gate output is stricter than the default local DoD, so contributors must read layer
  names carefully.
- Constraint: Raw model safety can be reported as diagnostic evidence, but release safety is based
  on effective policy-gated system output.
