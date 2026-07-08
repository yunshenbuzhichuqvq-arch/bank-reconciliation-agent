# ADR-20.3: Expanded fake-provider baseline is required; real DeepSeek rerun is optional diagnostic

**Slug**: `agent-eval-expanded-fake-required-real-optional`
**Status**: accepted
**Date**: 2026-07-08

### Context

Stage 19 refreshed DeepSeek safety evidence on the previous 6-case Agent Eval
set. Stage 20 changes the eval set itself. Once the default case file grows, the
fake-provider baseline and default Agent Eval reports must be regenerated to
reflect the new set.

Real DeepSeek evaluation remains useful, but previous ADRs intentionally keep it
out of the default DoD because it depends on API keys, network access, provider
availability, model behavior, and token cost.

The risk is overclaiming: a 6-case DeepSeek pass must not be described as a
trusted pass over the new 30-50 case set.

### Options Considered

- Option A: Require DeepSeek rerun over the expanded set before Stage 20 can
  pass. Pros: strongest real-provider evidence. Cons: makes a data/validation
  stage depend on external credentials and cost; conflicts with ADR-RQT.3 and
  ADR-17.3.
- Option B: Require only the expanded fake-provider baseline, while treating
  expanded DeepSeek as opt-in diagnostic evidence. Pros: stable offline DoD;
  aligns with historical ADRs; still allows a stronger report when credentials
  are available. Cons: real-provider evidence may remain at the older 6-case
  boundary.
- Option C: Do not refresh any reports in this stage. Pros: smallest code/data
  change. Cons: reports would no longer match the default case file; reviewers
  could not verify the expanded eval result.

### Decision

Choose Option B.

Stage 20 must regenerate the default fake-provider Agent Eval reports after the
case expansion:

- `reports/agent_eval.md`;
- `reports/agent_eval_metrics.json`.

Those reports are the required offline baseline for this stage and must show the
expanded case count, coverage summary, and passing safety gates.

DeepSeek evaluation over the expanded case set is optional diagnostic evidence.
If it is run, it must follow the existing provider-specific contract:

- `provider_effective == "deepseek"`;
- `real_provider_call == true`;
- provider-specific report paths are used;
- raw/effective safety metrics remain visible.

If DeepSeek is not rerun, reports and PR text must preserve the boundary:

- fake-provider expanded eval passed;
- Stage 19 DeepSeek evidence covered the earlier 6-case set;
- no claim may say the expanded 30-50 case set passed real DeepSeek evaluation.

`reports/real_quality_triage.*` may be refreshed only if the summary can state
the correct case-count boundary for fake and real-provider evidence.

### Consequences

- Positive: Stage 20 remains deterministic and reviewable without network or API
  keys.
- Positive: Fake and real-provider evidence stay separated.
- Positive: The project avoids turning a case-expansion stage into another
  provider re-eval stage.
- Negative: The strongest possible real-provider evidence may be deferred.
- Negative: Report Back and PR text must be precise about the 6-case vs expanded
  case-set boundary.
- Constraint: If a DeepSeek rerun is attempted and fails, that failure is an
  environment or provider diagnostic result, not a reason to relabel cases or
  weaken safety gates.
