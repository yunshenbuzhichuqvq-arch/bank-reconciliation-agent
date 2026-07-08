# ADR-DSR.3: Refresh triage summary only; do not expand eval scope in this stage

**Slug**: `deepseek-reeval-triage-refresh-only`
**Status**: accepted
**Date**: 2026-07-08

## Context

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

## Options Considered

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

## Decision

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

## Consequences

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
