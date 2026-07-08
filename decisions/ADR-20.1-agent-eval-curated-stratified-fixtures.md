# ADR-20.1: Agent Eval case set uses curated stratified fixtures

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
