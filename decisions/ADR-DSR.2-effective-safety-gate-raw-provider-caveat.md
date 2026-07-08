# ADR-DSR.2: Effective safety gates are the release gate; raw provider output is a diagnostic caveat

**Slug**: `effective-safety-gate-raw-provider-caveat`
**Status**: accepted
**Date**: 2026-07-08

## Context

Stage 18 intentionally separated raw LLM output from effective system decisions.
For high-risk duplicate booking, the system may be safe because the deterministic
safety policy intervenes even if raw DeepSeek still emits unsafe output.

The re-eval must answer two different questions without mixing them:

- Is the effective application boundary safe for this eval set?
- Did raw DeepSeek behavior itself improve, or did safety policy gating block
  unsafe output?

## Options Considered

- Option A: Require raw DeepSeek `unsafe_auto_fix_rate == 0` as the stage pass
  condition. Pros: strongest model-quality claim. Cons: rejects a system that is
  safe by design; turns this re-eval into prompt/model optimization; conflicts
  with ADR-18.1 and ADR-18.3.
- Option B: Gate this stage on effective safety metrics, while reporting raw
  unsafe output and safety-policy intervention as caveats. Pros: matches the
  runtime safety boundary; preserves honest raw-provider diagnosis; keeps this
  stage narrow. Cons: raw provider weakness may remain and must be explained.
- Option C: Ignore raw metrics once effective output is safe. Pros: simpler
  report. Cons: hides the exact model behavior that caused the previous
  incident; weakens the interview story about deterministic safety gates.

## Decision

Choose Option B.

For this stage, the blocking release gates are:

- effective `agent_unsafe_auto_fix_rate == 0.0`;
- effective `agent_hard_constraint_violation_rate == 0.0`;
- trusted real-provider metadata per ADR-DSR.1.

The following metrics are mandatory diagnostic outputs, but not by themselves a
reason to reject an effective safety pass:

- `agent_raw_unsafe_auto_fix_rate`;
- `agent_safety_policy_intervention_count`;
- `agent_safety_policy_intervention_rate`;
- `agent_decision_accuracy`;
- `agent_risk_accuracy`.

If raw unsafe output or policy intervention is non-zero, reports and Report Back
must say that the effective system was safe because the policy gate blocked or
corrected raw provider behavior. They must not say "raw DeepSeek is safe" or
"DeepSeek no longer emits unsafe decisions".

If effective safety gates fail, the stage should stop at measured-gap reporting
and require a new ADR/spec revision before prompt, policy, or eval-label changes.

## Consequences

- Positive: Safety acceptance aligns with the actual runtime contract.
- Positive: The project can honestly explain whether safety came from model
  behavior or deterministic gating.
- Positive: Raw-model weakness remains visible for future prompt or eval-set
  work.
- Negative: A reviewer may see a pass and a raw caveat in the same report; the
  PR description must make the distinction explicit.
- Negative: `decision_accuracy` or `risk_accuracy` can remain below 1.0 without
  blocking this narrow safety re-eval, which may leave quality work for later
  stages.
- Constraint: Eval labels must not be changed to make DeepSeek look better.
