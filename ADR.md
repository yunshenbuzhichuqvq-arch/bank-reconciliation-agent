# Stage 24 — Architectural Decisions

## ADR-24.1: Eval gate outcomes use an explicit layered gate contract

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

## ADR-24.2: Release gates fail closed on safety redlines and missing trust metadata

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

## ADR-24.3: CI stays deterministic; external diagnostics stay opt-in and report-only

**Slug**: `deterministic-ci-opt-in-diagnostics`
**Status**: accepted
**Date**: 2026-07-09

### Context

The repository currently has deterministic pytest coverage around report contracts and provider
fallback behavior, plus opt-in markers for live services and real embedding models. The project
uses `uv run pytest` and `uv run ruff check .` as the default DoD. Real DeepSeek runs and real
embedding matrix runs depend on credentials, network, token spend, optional dependencies, and
local model cache. Stage 24 should not make default development slower or less reliable while
adding gate clarity.

### Options Considered

- Option A: Add GitHub Actions or CI-secret wiring in this stage.
  Pros: Turns the layer model into actual remote automation.
  Cons: The repo has no existing CI workflow contract to extend; secret wiring and remote runner
  behavior would expand scope beyond evaluation semantics.
- Option B: Add a local gate summary/report that can be run deterministically against existing
  JSON reports and tested without network access.
  Pros: Keeps scope small; reuses current report files; gives opencode and reviewers a concrete
  artifact before any GitHub CI automation exists.
  Cons: It is still a local/manual command until a future stage adds remote workflow integration.
- Option C: Only update interview notes and PR text guidance.
  Pros: Fastest documentation-only path.
  Cons: No machine-readable gate result; future PRs can drift from the intended contract.

### Decision

Adopt Option B.

Stage 24 will keep CI expectations deterministic and local:

- no new external service dependency;
- no mandatory live DeepSeek call;
- no mandatory real embedding model load;
- no GitHub Actions or CI secret wiring in this stage;
- deterministic tests validate the gate contract using stubbed or fixture report data.

Manual diagnostics remain report-only inputs. They can improve release confidence when trusted,
but their absence must be represented as an explicit diagnostic/environment-gap outcome instead
of causing default CI to call external systems.

### Consequences

- Positive: Local development and future CI can rely on stable, low-cost checks.
- Positive: Real-provider and real-embedding evidence remains available for release review when
  the environment supports it.
- Positive: The stage can be completed without changing runtime reconciliation behavior.
- Negative: Remote CI automation remains future work; this stage defines the contract rather than
  wiring a hosted pipeline.
- Negative: Manual diagnostic evidence can become stale and must be refreshed deliberately when a
  release claim depends on it.
- Constraint: No implementation task in this stage may add a mandatory network call, model
  download, or credential requirement to the default DoD.
