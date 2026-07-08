# Stage 20 — Architectural Decisions

## ADR-20.1: Agent Eval case set uses curated stratified fixtures

**Slug**: `agent-eval-curated-stratified-fixtures`
**Status**: accepted
**Date**: 2026-07-08

### Context

`docs/interview/eval-harness-next-steps.md` lists Stage B as Agent Eval case
expansion. Current Agent Eval has 6 cases, enough for smoke and safety
regression, but not enough to support the claim that the eval set is designed
by exception type, risk level, evidence state, and safety redline.

Historical decisions already define the boundary:

- ADR-EH.1: Agent Eval is one layer of the offline eval harness.
- ADR-EH.4: Agent Eval is rule-based first, not LLM-as-Judge.
- ADR-18.1: high-risk duplicate booking must be blocked by deterministic safety
  policy at the effective decision boundary.
- ADR-RQT.3 / ADR-17.3: real DeepSeek Agent Eval is opt-in diagnostic evidence,
  not the default gate.

This stage should deepen the Agent Eval set without changing production
AuditAgent behavior or turning the work into RAG optimization, real embedding
setup, or real cost benchmarking.

### Options Considered

- Option A: Keep the 6-case eval set and rely on existing safety reports.
  Pros: no implementation risk; reports already pass. Cons: still a smoke set;
  misses important branches and negative cases; weak interview evidence.
- Option B: Expand to 30-50 manually curated, stratified JSON fixtures.
  Pros: deterministic, reviewable, aligned with ADR-EH.4; labels can explain the
  business reason for each expected decision; failures are attributable. Cons:
  higher maintenance cost; labels require careful review.
- Option C: Generate cases from templates or an LLM.
  Pros: fast scale-up and broad surface area. Cons: label quality is harder to
  trust; generated fixtures may encode invalid banking assumptions; review
  becomes about generator behavior instead of eval coverage.

### Decision

Choose Option B.

Stage 20 will expand `data/agent_eval_cases.json` from 6 cases to 30-50 curated
cases. The expanded set must cover at least these buckets:

- amount mismatch;
- bank-side unarrived / enterprise already recorded;
- enterprise-side unrecorded / bank already arrived;
- cross-period or T+1 trace context;
- duplicate booking;
- narrative or counterparty-name mismatch;
- RAG no-evidence path;
- conflicting or insufficient evidence;
- high-risk case with equal amount;
- low-risk candidate confirmation;
- schema-valid but business-unsafe model output scenario.

Each case remains a deterministic, rule-scored fixture. It must include the
existing Agent Eval contract fields and add a human-readable label reason or
coverage annotation that explains why the expected decision and risk level are
correct.

The stage must not:

- introduce LLM-as-Judge;
- change production AuditAgent prompt, safety policy, or runtime decision
  behavior just to fit labels;
- use generated labels without human-readable rationale;
- claim real DeepSeek coverage for the expanded case set unless a trusted
  provider-specific run is actually executed.

### Consequences

- Positive: Agent Eval becomes a coverage-designed eval set instead of a smoke
  sample.
- Positive: Failures can be traced to a business bucket and label rationale.
- Positive: Resume and interview claims can cite a concrete case count and
  coverage boundary.
- Negative: Case fixtures become a maintained artifact; future business-rule
  changes may require relabeling.
- Negative: Manually curated data is slower to produce than generated samples.
- Constraint: Labels must not be changed merely to make fake or real provider
  metrics look better.

## ADR-20.2: Coverage validation and reporting become part of Agent Eval

**Slug**: `agent-eval-coverage-validation-reporting`
**Status**: accepted
**Date**: 2026-07-08

### Context

The current loader validates basic fields and decision enum values. After the
case set grows to 30-50 items, basic validation is not enough. A large eval set
can still be misleading if it is unbalanced, duplicates case IDs, omits safety
redlines, or lacks a reason for expected labels.

Stage B needs a verifiable definition of "expanded eval set", not just a larger
JSON file.

### Options Considered

- Option A: Rely on manual review of `data/agent_eval_cases.json`.
  Pros: no script changes. Cons: easy to miss duplicate IDs, unbalanced buckets,
  or missing label rationale; weak DoD.
- Option B: Add validation and coverage summary to the existing Agent Eval
  script and tests. Pros: keeps one eval entry point; no new dependency; makes
  coverage failures reproducible in pytest and reports. Cons: adds some logic to
  `scripts/eval_agent.py`.
- Option C: Build a separate schema/manifest validator for Agent Eval cases.
  Pros: clean separation. Cons: extra tool surface for a single JSON artifact;
  more task and documentation overhead than this stage needs.

### Decision

Choose Option B.

The existing Agent Eval entry point should validate the expanded data set and
report coverage. Validation must check at least:

- `case_id` uniqueness;
- allowed values for `expected_decision` and `expected_risk_level`;
- required branch and business-label metadata for every curated case;
- case count between 30 and 50;
- at least one case in every required coverage bucket from ADR-20.1;
- presence of no-evidence and unsafe-auto-fix redline cases.

The Agent Eval report should include coverage information in both Markdown and
JSON outputs, in addition to existing metrics:

- total case count;
- count by error type / exception branch;
- count by risk level;
- count by evidence state;
- count by coverage bucket or tag;
- explicit safety gates for `unsafe_auto_fix_rate == 0` and
  `hard_constraint_violation_rate == 0`.

Coverage validation is an eval harness contract. It must not become production
runtime validation and must not introduce new dependencies.

### Consequences

- Positive: "30-50 cases" becomes mechanically checkable.
- Positive: Reports explain what the eval set covers, not only whether it
  passed.
- Positive: Reviewers can detect case-count inflation that does not improve
  coverage.
- Negative: Updating the eval set now requires updating coverage metadata
  correctly.
- Negative: Some validation choices are conservative and may need revision if
  future stages add new branches or risk labels.
- Constraint: A coverage validation failure is blocking for this stage even if
  metric rates are otherwise green.

## ADR-20.3: Expanded fake-provider baseline is required; real DeepSeek rerun is optional diagnostic

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
