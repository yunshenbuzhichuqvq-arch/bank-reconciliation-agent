# ADR-24.3: CI stays deterministic; external diagnostics stay opt-in and report-only

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
