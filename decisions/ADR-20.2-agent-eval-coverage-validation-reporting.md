# ADR-20.2: Coverage validation and reporting become part of Agent Eval

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
