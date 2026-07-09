# Stage 23 — Architectural Decisions

## ADR-23.1: Real provider benchmark refreshes canonical performance/cost evidence

**Slug**: `real-provider-performance-cost-evidence`
**Status**: accepted
**Date**: 2026-07-09

### Context

`docs/interview/eval-harness-next-steps.md` lists Stage E as the remaining
evaluation-harness gap: real provider latency / token / cost benchmark.

Stage 17 already established an offline performance/cost benchmark contract in
`decisions/ADR-17.4-performance-cost-offline-benchmark-evidence.md`, but the
current canonical benchmark report still records `provider_effective=fake`.
`reports/real_quality_triage.md` therefore correctly treats real LLM latency,
token usage, and cost as deferred. Stage 23 needs to turn that deferred item
into measured evidence when DeepSeek credentials and network are available,
without claiming production SLA or online cost.

### Options Considered

- Option A: Keep the fake provider benchmark as the only benchmark evidence.
  Pros: deterministic, free, and CI-friendly. Cons: cannot answer the Stage E
  requirement and cannot support real LLM latency or cost claims.
- Option B: Refresh the canonical performance/cost reports with a real DeepSeek
  benchmark and make trust/fallback state explicit. Pros: reuses the existing
  report surface, gives reviewers one source of truth, and directly closes the
  Stage E gap. Cons: requires API credentials, network access, token spend, and
  may fail for reasons unrelated to code.
- Option C: Add production telemetry for online latency and cost before doing
  the offline benchmark. Pros: closest to production operations. Cons: much
  larger scope, requires runtime instrumentation and traffic semantics that are
  explicitly outside the current evaluation-harness backlog.

### Decision

Choose Option B.

Stage 23 will refresh the canonical performance/cost benchmark artifacts only
when a trusted real provider run is available:

- `reports/performance_cost_benchmark.json`
- `reports/performance_cost_benchmark.md`

The refreshed benchmark is trusted only if the report records:

- `provider_requested == "deepseek"`
- `provider_effective == "deepseek"`
- `model_requested` and `model_effective`
- current stage `evaluated_at`
- non-empty latency samples for the measured components
- token and cost metadata, or an explicit token/cost unavailable state

If DeepSeek credentials, network, provider errors, or token metadata prevent a
trusted run, Stage 23 must record an environment gap instead of preserving or
relabeling fake-provider evidence as real-provider evidence.

### Consequences

- Positive: Stage 23 can close the next-steps Stage E gap with report files that
  are already part of the repository evidence model.
- Positive: Reviewers can distinguish real provider evidence from deterministic
  fake-provider baseline evidence.
- Negative: The stage depends on external provider availability and may produce
  an environment-gap result even if local code is correct.
- Negative: Canonical report files will be overwritten, so the old fake-provider
  benchmark remains available through git history rather than side-by-side files.

## ADR-23.2: Token and cost claims use provider usage metadata with explicit assumptions

**Slug**: `provider-usage-cost-accounting`
**Status**: accepted
**Date**: 2026-07-09

### Context

Stage E requires `input tokens`, `output tokens`, `total tokens`,
`estimated cost`, and per-case cost. The current DeepSeek provider returns token
counts when the provider response includes usage metadata, while the existing
cost helper uses repository-defined DeepSeek pricing constants.

Cost numbers are sensitive because model pricing, cache behavior, and provider
usage fields can change. The project must avoid presenting a calculated cost as
an invoice or production cost.

### Options Considered

- Option A: Estimate tokens locally from prompt length and report cost from that
  estimate. Pros: works even if the provider does not return usage. Cons:
  introduces tokenizer drift, hides provider metadata gaps, and can overstate
  precision.
- Option B: Use provider-returned prompt/completion token counts for benchmark
  cost estimates, with repository-defined pricing assumptions shown in the
  report. Pros: traceable to the actual API response and consistent with
  ADR-17.4. Cons: cost is unavailable if the provider omits usage metadata, and
  pricing constants can become stale.
- Option C: Use billing-dashboard exports as the only accepted source of cost.
  Pros: closest to actual billing. Cons: not currently automated, harder to
  reproduce in review, and outside the narrow benchmark script contract.

### Decision

Choose Option B.

Stage 23 cost accounting will use provider-returned token counts as the trusted
usage source. The report must include:

- `input_tokens`
- `output_tokens`
- `total_tokens`
- total `estimated_cost_usd`
- per-case estimated cost derived from total estimated cost divided by
  `run_count`
- pricing assumptions used for the estimate

If token usage is absent, the report must set token/cost availability to false
and state that cost cannot be estimated from provider usage. The implementation
must not backfill real-provider cost from fake-provider constants, local prompt
length, or assumed average token counts.

### Consequences

- Positive: Cost claims stay tied to real provider response metadata.
- Positive: Resume-safe facts can quote estimated benchmark cost while preserving
  an honest offline boundary.
- Negative: A successful real DeepSeek call may still fail the cost-evidence
  requirement if token usage metadata is missing.
- Negative: Repository-defined pricing assumptions require future maintenance
  when provider pricing changes.

## ADR-23.3: Triage summary must promote real benchmark evidence or preserve the gap

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

## ADR-23.4: Real provider benchmark remains an opt-in diagnostic, not a CI gate

**Slug**: `real-provider-benchmark-manual-gate`
**Status**: accepted
**Date**: 2026-07-09

### Context

The next-steps document distinguishes stable CI gates from manual or nightly
diagnostics. Real DeepSeek benchmark runs require credentials, network access,
and token spend. They are useful evidence for engineering tradeoff discussion,
but they are not deterministic enough to block every local or CI run.

### Options Considered

- Option A: Add the real DeepSeek benchmark to required CI. Pros: ensures fresh
  evidence on every change. Cons: requires secrets and network in CI, increases
  cost, and can fail because of provider availability rather than regression.
- Option B: Keep the real DeepSeek benchmark as an opt-in/manual diagnostic with
  deterministic fake-provider tests covering report contracts. Pros: preserves
  reliable CI while allowing trusted real evidence when credentials are
  available. Cons: real benchmark evidence can become stale between manual runs.
- Option C: Remove fake-provider benchmark tests and rely only on manual real
  provider runs. Pros: avoids maintaining fake-path assertions. Cons: weakens
  regression protection and makes local validation expensive.

### Decision

Choose Option B.

Stage 23 will keep deterministic test coverage around benchmark report schema,
trust classification, token/cost availability, and triage rendering. The actual
DeepSeek benchmark run remains a manual or opt-in diagnostic command.

The stage is out of scope for:

- CI secret wiring;
- production latency instrumentation;
- online traffic cost accounting;
- human adoption or override metrics;
- prompt tuning, safety-policy changes, or RAG optimization.

### Consequences

- Positive: Local and CI validation remains deterministic and low cost.
- Positive: The project can still produce real provider evidence when the
  environment supports it.
- Negative: Reviewers must inspect report metadata to know whether the latest
  branch contains fresh real-provider benchmark evidence.
- Negative: Manual evidence can drift as provider performance, pricing, and
  network conditions change.
