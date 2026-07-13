# Stage 30 Verification

- **Branch**: `stage-30-rag-query-optimization`
- **HEAD**: `6d2e718cc042a1a974a0e5438111e54e9889d4e2`
- **Date**: 2026-07-13T10:50:25Z
- **Environment**: Darwin 25.5.0 arm64 / Apple M5 / Python 3.11.15 / torch 2.12.1 / sentence_transformers 5.6.0
- **Final Stage State**: `experiment rejected`

## Task-Level Evidence Summary

| Task | Status | Key Evidence |
|------|--------|-------------|
| TASK-30.1 | done | `scripts/eval_rag.py` + tests: matrix artifact hashes, git_revision, query_enrichment metadata; comparison stage30 trust gate with hash/bucket fail-closed; MRR-only regression test; full non-target bucket reporting |
| TASK-30.2 | done | Baseline trusted: `reports/rag_quality_matrix_stage30_baseline.{json,md}`, bge_m3/dense, 120 cases, hash non-empty, jq gate passed |
| TASK-30.3 | done | `rules/rag_query_terms.yaml`, `src/.../query_enrichment.py`, `tests/test_rag_query_enrichment.py`; created, tested, and later deleted (rollback) |
| TASK-30.4 | done | Runtime + eval integration: `ReconciliationService._build_rag_query` and `scripts/eval_rag` using shared helper; created and later deleted (rollback) |
| TASK-30.5 | done | Experiment **rejected**: target bucket regressed (Recall@5 0.35→0.25, miss 8→9). Rollback executed—candidate integration, helper, and profile removed; TASK-30.1 evidence contract and after/comparison reports retained. Candidate revision `51b48ef`, profile SHA-256 `40dce1eb42546d416f3717f3c8027d761f62fa08671fd667dc86645e95ac6b7f`. |
| TASK-30.6 | done | This verification file |

## Full Gate Results

```bash
uv run pytest
```
- **Exit code**: 0
- **Result**: `1122 passed, 1 skipped, 6 warnings`

```bash
uv run ruff check .
```
- **Exit code**: 0
- **Result**: `All checks passed!`

```bash
uv run ruff format --check .
```
- **Exit code**: 1
- **Result**: `94 files would be reformatted, 110 files already formatted`
- **Status**: Inherited baseline failure — identical condition documented in Stage 29 `verification.md` ("repo-wide Ruff format baseline 需要独立治理"). Not caused by Stage 30 changes.

```bash
git diff --check main...HEAD
```
- **Exit code**: 2
- **Result**: `docs/stages/stage-30-rag-query-optimization/tasks.md: new blank line at EOF`
- **Note**: Trailing newline in planning file; not a code or security issue.

```bash
git diff --stat main...HEAD
```
- **Result**: 12 files, +3519/-126. Scope consistent with Stage 30 (ADRs, spec, tasks, reports, eval script, tests).

```bash
git status --short
```
- **Result**: Clean (no untracked or unexpected changes).

## Artifact and Metrics Summary

### Baseline (TASK-30.2, trusted)
- `reports/rag_quality_matrix_stage30_baseline.json`
- backend: `bge_m3`, mode: `dense`, top-k: 5, case_count: 120
- eval_set_sha256: `71fd0db2e02faeccca15bf177e1582b9db0518af9208dc5025ae6481699929c2`
- chunk_corpus_sha256: `b71d67f6a9954a7ee1a3ab0ad40f80ceaf7de0b14fa00dfd7978f14ed2f78018`
- git_revision: `b015add`
- Global: Hit@1 0.6333 / Recall@5 0.8250 / MRR 0.7353 / NDCG@5 0.7209
- Target (BANK_CLEARING/SINGLE_SIDE_MISSING): Recall@5 0.3500 / miss 8

### After (TASK-30.5, rejected)
- `reports/rag_quality_matrix_stage30_after.json`
- Same hash/backend/mode/top-k as baseline
- profile: `bank-clearing-single-side-missing`, enabled: true
- profile_sha256: `40dce1eb42546d416f3717f3c8027d761f62fa08671fd667dc86645e95ac6b7f`
- Global: Hit@1 0.6250 / Recall@5 0.8167 / MRR 0.7244 / NDCG@5 0.7110
- Target: Recall@5 **0.2500** / miss **9** (regressed)

### Comparison (TASK-30.5, rejected)
- `reports/rag_optimization_comparison.{json,md}`
- trust: `trusted=true`, success: `false`
- Target delta: Recall@5 -0.1000, miss_count +1, MRR -0.1300, NDCG@5 -0.1193
- Global: all regressions within 0.0200 limit
- Side effects: all 14 non-target buckets delta=0

### Verdict
- `experiment rejected` — target bucket regressed; candidate rollback performed; evidence retained

## Scope / Secret / Large-file Check

- `git diff --stat main...HEAD`: 12 files, all within Stage 30 scope (ADRs, spec, tasks, reports, eval script, tests)
- No `.env`, `.pkl`, `.bin`, `.pt`, `chroma/`, `__pycache__`, `*.log`, model files, or build artifacts in diff
- No secrets, credentials, or user data in any committed file

## Deviations From Spec

- `ruff format --check .` fails (94 files) — inherited baseline failure, documented in Stage 29 `verification.md`; not caused by Stage 30
- `git diff --check main...HEAD` returns exit 2 due to trailing newline in tasks.md (planning file); no code or security impact

## Risks / Follow-up

- Repo-wide `ruff format` baseline still needs separate governance
- Target bucket regression suggests that simple category-level term appending may dilute semantic matching for BANK_CLEARING / SINGLE_SIDE_MISSING queries; future enrichment attempts should consider different term selection or direction
