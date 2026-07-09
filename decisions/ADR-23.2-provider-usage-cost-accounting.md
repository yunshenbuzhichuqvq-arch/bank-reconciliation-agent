# ADR-23.2: Token and cost claims use provider usage metadata with explicit assumptions

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
