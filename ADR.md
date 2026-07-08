# Stage DSR - DeepSeek Safety Re-eval Architectural Decisions

## Working Assumptions

- Current branch: `stage-DeepSeek-safety-re-eval`.
- This stage maps to `docs/interview/eval-harness-next-steps.md` section
  "Stage A: DeepSeek safety re-eval".
- Stage identifier uses `DSR` because the branch does not carry a numeric stage
  id. If the user wants a numeric id later, rename `ADR-DSR.*` before accepting
  and committing this file.
- Existing `spec.md`, `tasks.md`, and `PR.md` are gitignored scratch files from
  the previous Stage 18 safety-hardening work. They are historical context only;
  new `spec.md` and `tasks.md` must be regenerated after these ADRs are reviewed.
- A real DeepSeek re-eval requires `DEEPSEEK_API_KEY` and network access. Missing
  credentials or provider failure is an environment gap, not a pass.

## ADR-DSR.1: DeepSeek re-eval evidence must be freshly regenerated

**Slug**: `deepseek-safety-reeval-fresh-provider-evidence`
**Status**: proposed
**Date**: 2026-07-08

### Context

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

### Options Considered

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

### Decision

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

### Consequences

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

## ADR-DSR.2: Effective safety gates are the release gate; raw provider output is a diagnostic caveat

**Slug**: `effective-safety-gate-raw-provider-caveat`
**Status**: proposed
**Date**: 2026-07-08

### Context

Stage 18 intentionally separated raw LLM output from effective system decisions.
For high-risk duplicate booking, the system may be safe because the deterministic
safety policy intervenes even if raw DeepSeek still emits unsafe output.

The re-eval must answer two different questions without mixing them:

- Is the effective application boundary safe for this eval set?
- Did raw DeepSeek behavior itself improve, or did safety policy gating block
  unsafe output?

### Options Considered

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

### Decision

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

### Consequences

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

## ADR-DSR.3: Refresh triage summary only; do not expand eval scope in this stage

**Slug**: `deepseek-reeval-triage-refresh-only`
**Status**: proposed
**Date**: 2026-07-08

### Context

`docs/interview/eval-harness-next-steps.md` lists multiple follow-up stages:

- Stage A: DeepSeek safety re-eval;
- Stage B: Agent Eval case expansion;
- Stage C: real embedding RAG matrix;
- Stage D: RAG before/after optimization;
- Stage E: real provider latency/token/cost benchmark.

The current branch name targets Stage A. Mixing case expansion, RAG work, and
cost benchmarking into the same stage would blur the acceptance criteria and
make failures harder to attribute.

At the same time, a standalone DeepSeek report is not enough. The repository
also needs `reports/real_quality_triage.*` to summarize which claims are now
measured, which are still environment gaps, and which remain out of scope.

### Options Considered

- Option A: Only regenerate the DeepSeek Agent Eval report. Pros: smallest
  change. Cons: `real_quality_triage` would still say DeepSeek is not measured,
  so the repository-level evidence summary would be stale.
- Option B: Regenerate DeepSeek Agent Eval, then regenerate
  `reports/real_quality_triage.md` and `reports/real_quality_triage.json` with
  `--agent-real-json reports/agent_eval_deepseek_flash_metrics.json`. Pros:
  updates the summary layer while preserving scope. Cons: triage will still show
  unrelated RAG/performance gaps, which must be understood as out of this stage.
- Option C: Complete all follow-up items from the next-steps document in one
  stage. Pros: more comprehensive final report. Cons: large scope expansion;
  mixes safety re-eval with dataset expansion, embedding setup, RAG tuning, and
  cost benchmarking.

### Decision

Choose Option B.

This stage may update:

- `reports/agent_eval_deepseek_flash.md`;
- `reports/agent_eval_deepseek_flash_metrics.json`;
- `reports/real_quality_triage.md`;
- `reports/real_quality_triage.json`;
- tests or scripts only if implementation discovers that the current report
  contract cannot represent ADR-DSR.1 and ADR-DSR.2 faithfully.

This stage must not update by default:

- `data/agent_eval_cases.json` for 30-50 case expansion;
- RAG eval sets, RAG matrix reports, RAG thresholds, chunking, query rewrite, or
  production retrieval defaults;
- performance/cost benchmark reports;
- production runtime defaults;
- prompt or safety-policy behavior unless effective safety gates fail and the
  user accepts a revised ADR/spec.

If DeepSeek cannot be run, triage may be regenerated without trusted
`agent-real-json` evidence, but Report Back must state that Stage A did not
produce measured DeepSeek safety closure.

### Consequences

- Positive: Stage A has a clear, reviewable deliverable: post-hardening DeepSeek
  safety evidence plus refreshed triage summary.
- Positive: Later stages can still use the next-steps document as their backlog
  without inheriting accidental changes from this branch.
- Positive: Report consumers get a current summary instead of manually merging
  DeepSeek and triage reports.
- Negative: The final triage summary will still mention RAG real-embedding,
  RAG-quality, real-cost, and online-metric gaps because they are genuinely not
  solved here.
- Negative: If DeepSeek is unavailable, this stage may end with an environment
  gap rather than the intended measured-pass evidence.
- Constraint: No resume or interview statement may claim Stage B-E outcomes from
  this Stage A branch.
