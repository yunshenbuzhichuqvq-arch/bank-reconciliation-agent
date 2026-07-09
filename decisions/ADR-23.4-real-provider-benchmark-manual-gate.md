# ADR-23.4: Real provider benchmark remains an opt-in diagnostic, not a CI gate

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
