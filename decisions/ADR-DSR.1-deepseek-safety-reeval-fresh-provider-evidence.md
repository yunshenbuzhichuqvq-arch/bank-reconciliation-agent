# ADR-DSR.1: DeepSeek re-eval evidence must be freshly regenerated

**Slug**: `deepseek-safety-reeval-fresh-provider-evidence`
**Status**: accepted
**Date**: 2026-07-08

## Context

The previous Stage 18 closed the known `BE-R008 / DUPLICATE_BOOKING` unsafe
auto-fix at the effective system boundary by adding:

- deterministic AuditAgent safety policy gating;
- Audit Prompt v3 with a narrow duplicate-booking safety contract;
- Agent Eval reporting that separates raw provider output from effective
  policy-gated output.

The repository still contains an older `reports/agent_eval_deepseek_flash.*`
run from 2026-07-07. That report shows the original DeepSeek unsafe auto-fix
failure and does not contain the Stage 18 raw/effective/policy metrics. Current
`reports/real_quality_triage.*` correctly records DeepSeek Agent Eval as not
present for the post-hardening evidence summary.

This stage must not reuse stale DeepSeek evidence to claim that the safety fix
has been revalidated.

## Options Considered

- Option A: Reuse the existing `reports/agent_eval_deepseek_flash.*` files.
  Pros: no network, no token cost, no new work. Cons: stale pre-hardening
  evidence; lacks raw/effective/policy fields; still shows the old unsafe
  failure; cannot validate this stage.
- Option B: Re-run `scripts.eval_agent` with `--provider deepseek` and update the
  canonical provider-specific reports `reports/agent_eval_deepseek_flash.md` and
  `reports/agent_eval_deepseek_flash_metrics.json`. Pros: matches existing tool
  defaults; keeps fake baseline reports separate; report metadata can prove
  `provider_effective=deepseek` and `real_provider_call=true`. Cons: overwrites
  the old provider-specific report in the working tree; requires credentials,
  network, and token cost.
- Option C: Write timestamped or stage-specific DeepSeek after reports. Pros:
  before/after artifacts are visible side by side. Cons: adds report sprawl;
  existing triage defaults and reviewer expectations already point to the
  canonical provider-specific path; git history already preserves the old report.

## Decision

Choose Option B.

This stage accepts DeepSeek safety evidence only if the report is freshly
generated from the current code and contains all of the following:

- `provider_requested == "deepseek"`;
- `provider_effective == "deepseek"`;
- `model_requested` and `model_effective` for `deepseek-v4-flash` unless the
  later spec explicitly chooses another DeepSeek model;
- `real_provider_call == true`;
- current `evaluated_at` metadata from this stage run;
- effective safety metrics:
  - `agent_unsafe_auto_fix_rate`;
  - `agent_hard_constraint_violation_rate`;
- raw/policy metrics:
  - `agent_raw_unsafe_auto_fix_rate`;
  - `agent_safety_policy_intervention_count`;
  - `agent_safety_policy_intervention_rate`.

If DeepSeek credentials, network, or provider behavior prevent a trusted run,
the result must be recorded as an environment gap. The stage must not claim
DeepSeek safety closure from the stale 2026-07-07 report.

## Consequences

- Positive: The stage result can be traced to a real post-hardening provider
  call instead of old evidence.
- Positive: Fake-provider baseline reports remain isolated and deterministic.
- Positive: Reviewers can inspect the canonical DeepSeek report without hunting
  for ad hoc filenames.
- Negative: The report refresh depends on an external provider and may fail for
  reasons unrelated to code correctness.
- Negative: The current tree loses the old failing DeepSeek report as a visible
  file after regeneration; historical evidence remains in git history and Stage
  18 ADRs/reports.
- Constraint: A failed or unavailable DeepSeek run is not a pass and must not be
  converted into resume-safe evidence.
