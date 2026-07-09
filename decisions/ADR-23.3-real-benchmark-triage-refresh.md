# ADR-23.3: Triage summary must promote real benchmark evidence or preserve the gap

**Slug**: `real-benchmark-triage-refresh`
**Status**: accepted
**Date**: 2026-07-09

### Context

`reports/real_quality_triage.*` is the repository-level summary that separates
measured passes, measured gaps, environment gaps, deferred online metrics, and
out-of-scope items. Current triage marks real performance/cost as deferred
because the benchmark report is fake-provider evidence.

Refreshing only the benchmark report would leave the summary and resume-safe
facts stale.

### Options Considered

- Option A: Update only `reports/performance_cost_benchmark.*`. Pros: smallest
  artifact change. Cons: triage would still say real performance/cost is
  deferred or would omit the new cost fact.
- Option B: Refresh `reports/real_quality_triage.*` after the benchmark, using
  the performance/cost JSON as an input. Pros: keeps the source report and the
  evidence summary consistent. Cons: touches an additional report surface and
  may expose unrelated existing findings that are not Stage 23 work.
- Option C: Replace triage with a stage-specific summary document. Pros: avoids
  changing an existing report. Cons: creates report sprawl and weakens the
  repository's single evidence summary.

### Decision

Choose Option B.

Stage 23 must refresh:

- `reports/real_quality_triage.json`
- `reports/real_quality_triage.md`

The triage refresh must classify real-provider benchmark evidence as:

- `measured_pass` when `provider_effective=deepseek` and token/cost metadata are
  available under the Stage 23 benchmark contract;
- `environment_gap` when the real provider benchmark cannot run because of
  credentials, network, provider availability, or missing required metadata;
- not a production latency or production cost measurement.

The resume-safe facts and bullet draft may include real benchmark cost only when
the report is trusted. They must continue to state that the measurement is an
offline benchmark, not production SLA, online traffic cost, or human-review
adoption evidence.

### Consequences

- Positive: The top-level evidence summary will match the refreshed benchmark
  artifacts.
- Positive: Interview and resume statements can be traced to both the raw report
  and the triage summary.
- Negative: Triage output can change for adjacent findings because it is a
  generated summary over multiple reports.
- Negative: If the real provider benchmark is unavailable, Stage 23 still needs
  to update or document the preserved gap rather than producing a success story.
