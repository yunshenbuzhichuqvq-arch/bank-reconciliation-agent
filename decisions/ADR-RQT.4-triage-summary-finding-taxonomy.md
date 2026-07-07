# ADR-RQT.4: Triage summary uses finding taxonomy instead of immediate remediation tasks

**Slug**: `triage-summary-finding-taxonomy`
**Status**: accepted
**Date**: 2026-07-07

## Context

The project now has several evaluation reports, but they answer different questions and use different runtime assumptions. Without a stage-level triage summary, a reviewer can easily confuse:

- default fake/hash regression gates,
- opt-in real embedding reports,
- opt-in real LLM reports,
- online metrics that are not implemented yet.

The next stage should leave a clear artifact that says what is actually known, what was not runnable, what failed, and what should be optimized later.

## Options Considered

- Option A: Produce only raw RAG and Agent reports.
  - Pros: Less code and less documentation.
  - Cons: Reviewers still need to manually infer what matters and which gaps remain.
- Option B: Convert every observed miss into an immediate code fix in the same stage.
  - Pros: Potentially improves numbers quickly.
  - Cons: Mixes diagnosis and remediation; risks overfitting before the root cause is categorized.
- Option C: Produce a structured triage summary and defer remediation to a later stage.
  - Pros: Keeps this stage narrow; makes next-stage planning evidence-based.
  - Cons: Requires one extra artifact and may feel less satisfying because it intentionally defers fixes.

## Decision

Choose Option C.

The stage summary should classify findings into:

- `measured_pass`: measured and acceptable under the stated environment.
- `measured_gap`: measured and below expectation, with case IDs or metric deltas.
- `environment_gap`: not runnable because credentials, model cache, optional dependency, or local resource is missing.
- `deferred_online_metric`: requires online runtime instrumentation or human-review workflow data outside this stage.
- `out_of_scope`: known gap deliberately not handled in this stage.

The summary should point to source reports and recommend, but not implement, the next optimization targets.

## Consequences

- Positive: Review and interview narrative can distinguish "not measured" from "measured and failed."
- Positive: Next stage can choose tasks from concrete findings instead of speculative backlog.
- Negative: This adds reporting work that does not directly change runtime behavior.
- Negative: Some users may expect immediate fixes; the stage must explain why diagnosis comes first.
- Constraint: Any update to `docs/interview/` must be based on real observed findings and remain gitignored.
