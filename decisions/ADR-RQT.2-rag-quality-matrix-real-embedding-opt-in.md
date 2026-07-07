# ADR-RQT.2: RAG quality matrix separates CI hash baseline from opt-in real embeddings

**Slug**: `rag-quality-matrix-real-embedding-opt-in`
**Status**: accepted
**Date**: 2026-07-07

## Context

Historical ADRs already define the embedding boundary:

- ADR-083 accepts local real embeddings over hash for semantic quality.
- ADR-088 keeps CI/default tests on hash and makes real embeddings opt-in.
- ADR-089 requires effective backend metadata after fallback.
- ADR-EO.2 keeps mode comparison evidence-driven and forbids hash-specific overfitting.

Current reports cover two partial views:

- `reports/rag_eval_real_vs_hash.md` compares hash, `bge_m3`, and `bge_small` on dense retrieval.
- `reports/rag_eval_mode_comparison.md` compares `dense`, `hybrid`, and `hybrid_rerank` on hash.

The missing view is a backend-by-mode matrix: whether real embeddings plus hybrid/rerank behave better, worse, or differently than hash plus hybrid/rerank.

## Options Considered

- Option A: Switch the combined harness and production default to real embeddings now.
  - Pros: Aligns with semantic retrieval goals.
  - Cons: Violates ADR-088's CI boundary and risks hidden model download/cache dependency in default workflows.
- Option B: Keep only the hash mode comparison from the previous stage.
  - Pros: Simple and deterministic.
  - Cons: Leaves real embedding quality as an old standalone report, not comparable to the selected retrieval mode.
- Option C: Add an opt-in RAG quality matrix across available backends and retrieval modes.
  - Pros: Preserves default hash CI while generating real-embedding evidence when the environment supports it; allows case-level miss analysis before changing defaults.
  - Cons: Matrix generation can be slow and may produce skipped/unavailable rows when models are not cached.

## Decision

Choose Option C.

The RAG triage contract should produce Markdown and JSON reports that include:

- Backend rows for `hash`, `bge_small`, and `bge_m3`.
- Mode columns for `dense`, `hybrid`, and `hybrid_rerank`.
- Effective backend metadata for each run, so fallback to hash is visible.
- Metrics: `hit_at_1`, `recall_at_5`, `mrr`, and `ndcg_at_5`.
- Case-level miss buckets by scenario and error type for the best available real backend/mode.
- Explicit `not_run` / `unavailable` status when dependencies or local model cache are missing.

This report is diagnostic only. It must not silently change production RAG defaults or the default combined harness.

## Consequences

- Positive: The project can compare hash-mode gains against real semantic retrieval instead of treating them as interchangeable.
- Positive: Miss buckets can drive the next optimization stage without relabeling or query tuning during this stage.
- Negative: Running the full matrix may be expensive on CPU, especially for `bge_m3`.
- Negative: If real embeddings are unavailable locally, the stage may only prove that the environment gap still exists.
- Constraint: Eval scripts must keep `min_score=0.0` for ranking-quality measurement, consistent with ADR-086's clarification.
