# Stage 30 Verification

- **Branch**: `stage-30-rag-query-optimization`
- **HEAD**: `db12c718aa08ac92d4b650954629508c23f7b39c` (code/artifact state under verification; this verification commit becomes the new HEAD)
- **Date**: 2026-07-13T11:28:36Z
- **Environment**: Darwin 25.5.0 arm64 / Apple M5 / Python 3.11.15 / torch 2.12.1 / sentence_transformers 5.6.0
- **Final Experiment State**: `experiment rejected`
- **Stage/PR Gate State**: **NOT passing** — `git diff --check main...HEAD` fails on the committed planning file `tasks.md` (trailing blank line at EOF); `ruff format --check .` remains an inherited repo-wide baseline failure. The experiment conclusion (`experiment rejected`) is independent of and does not override these gate failures.

## Task-Level Evidence Summary

| Task | Status | Key Evidence |
|------|--------|-------------|
| TASK-30.1 | done | `scripts/eval_rag.py` + tests: matrix artifact hashes, git_revision, query_enrichment metadata; comparison stage30 trust gate with hash/bucket fail-closed; MRR-only regression test; full non-target bucket reporting |
| TASK-30.2 | done | Baseline trusted: `reports/rag_quality_matrix_stage30_baseline.{json,md}`, bge_m3/dense, 120 cases, hash non-empty, jq gate passed |
| TASK-30.3 | done | `rules/rag_query_terms.yaml`, `src/.../query_enrichment.py`, `tests/test_rag_query_enrichment.py`; created, tested, and later deleted (rollback) |
| TASK-30.4 | done | Runtime + eval integration: `ReconciliationService._build_rag_query` and `scripts/eval_rag` using shared helper; created and later deleted (rollback) |
| TASK-30.5 | done | Experiment **rejected**: target bucket regressed (Recall@5 0.35→0.25, miss 8→9). Rollback executed—candidate integration, helper, and profile removed; TASK-30.1 evidence contract and after/comparison reports retained. Candidate revision `51b48ef`, profile SHA-256 `40dce1eb42546d416f3717f3c8027d761f62fa08671fd667dc86645e95ac6b7f`. |
| TASK-30.6 | done | Initial verification record (superseded by this file / TASK-30.10) |
| TASK-30.7 | done | `scripts/eval_rag.py` + `tests/test_v1_1_eval_rag_report.py`: OR-based Stage 30 detection; artifact role gate (baseline disabled, after enabled+profile+profile_sha256+latency); git_revision required both sides; after latency count/order validation; source/trust evidence surfaced in JSON+Markdown; 11 role/negative tests |
| TASK-30.8 | done | `scripts/eval_rag.py` + `tests/test_v1_1_eval_rag_report.py`: bucket set equality, key uniqueness, per-bucket case_count equality, case_count sum == matrix case_count, required-field/type checks, `_bucket_deltas` hardened; 7 bucket-integrity tests |
| TASK-30.9 | done | Regenerated `reports/rag_optimization_comparison.{json,md}` from committed baseline/after JSON with hardened contract; `trust.trusted=true`, `success=false`, exactly 10 non-target buckets all delta=0; byte-reproducible |
| TASK-30.10 | done | This verification record |

## Full Gate Results

```bash
uv run pytest
```
- **Exit code**: 0
- **Result**: `1139 passed, 1 skipped, 6 warnings`

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
- **Status**: **Inherited baseline failure** — repo-wide condition documented in Stage 29 `verification.md`. Targeted evidence for the Stage 30 changed Python files (`scripts/eval_rag.py`, `tests/test_mvp2b3_eval_rag.py`, `tests/test_v1_1_eval_rag_report.py`):
  - On `stage-30-rag-query-optimization`: `3 files would be reformatted`
  - On `main` (same three files): `3 files would be reformatted`
  - Conclusion: the format non-compliance for these files exists identically on `main`; Stage 30 did not introduce new format violations. Newly authored Stage 30 code regions were kept format-clean (pre-existing lines were not reformatted, per surgical-change policy).

```bash
git diff --check main...HEAD
```
- **Exit code**: 2
- **Result**: `docs/stages/stage-30-rag-query-optimization/tasks.md:515: new blank line at EOF`
- **Status**: **FAILED**. The offending line is a trailing blank line at EOF in the committed planning file `tasks.md` (from commit `47eaa10`, authored during planning). `tasks.md` is a planning file and is Do Not Touch for implementation tasks, so it was not modified here. Per TASK-30.10 acceptance, this gate must pass; because it does not, this verification is marked FAILED and the Stage must not be closed until the planning file's trailing blank line is fixed (owner: planning/user commit of the plan update).

```bash
git diff --stat main...HEAD
```
- **Result** (as measured before this verification commit): `13 files changed, 4227 insertions(+), 138 deletions(-)`
- Files: ADR-30.1, spec.md, tasks.md, verification.md, `reports/rag_optimization_comparison.{json,md}`, `reports/rag_quality_matrix_stage30_after.{json,md}`, `reports/rag_quality_matrix_stage30_baseline.{json,md}`, `scripts/eval_rag.py`, `tests/test_mvp2b3_eval_rag.py`, `tests/test_v1_1_eval_rag_report.py`
- Note: this commit updates `verification.md`, so its line count in the final diff will increase relative to the snapshot above.

```bash
git status --short
```
- **Result**: ` M docs/stages/stage-30-rag-query-optimization/tasks.md` — the working tree holds the user's uncommitted plan update (TASK-30.7–30.10 additions). No unexpected code, data, cache, or build artifacts.

## Artifact and Metrics Summary

### Baseline (TASK-30.2, trusted)
- `reports/rag_quality_matrix_stage30_baseline.json`
- backend `bge_m3`, mode `dense`, top-k 5, case_count 120
- eval_set_sha256 `71fd0db2…9929c2`, chunk_corpus_sha256 `b71d67f6…f78018`, git_revision `b015add`
- query_enrichment disabled
- Global: Hit@1 0.6333 / Recall@5 0.8250 / MRR 0.7353 / NDCG@5 0.7209
- Target (BANK_CLEARING/SINGLE_SIDE_MISSING): Recall@5 0.3500 / miss 8

### After (TASK-30.5, rejected candidate)
- `reports/rag_quality_matrix_stage30_after.json`
- Same eval_set/chunk_corpus hash, backend, mode, top-k, case_count as baseline
- query_enrichment enabled, profile `bank-clearing-single-side-missing`, profile_sha256 `40dce1eb…c6b7f`, git_revision `51b48ef`, latency count 120
- Global: Hit@1 0.6250 / Recall@5 0.8167 / MRR 0.7244 / NDCG@5 0.7110
- Target: Recall@5 **0.2500** / miss **9** (regressed)

### Comparison (TASK-30.9, hardened contract)
- `reports/rag_optimization_comparison.{json,md}`
- trust `trusted=true`, `success=false`
- Target delta: Recall@5 -0.1000, miss_count +1, MRR -0.1300, NDCG@5 -0.1193
- Global delta: all within 0.0200 limit (Hit@1 -0.0083, Recall@5 -0.0083, MRR -0.0108, NDCG@5 -0.0099)
- **Bucket totals: 11 total buckets, 10 non-target buckets** (corrects the earlier "14 non-target buckets" error); all 10 non-target deltas = 0
- Verdict: `experiment rejected`

## Scope / Secret / Large-file Check

- `git diff --stat main...HEAD`: 13 files, all within Stage 30 scope (ADR, spec, tasks, verification, reports, eval script, tests)
- No `.env`, `.pkl`, `.bin`, `.pt`, model files, `chroma/`, `__pycache__`, `*.log`, archives, or `node_modules` in the diff
- Largest added files are JSON/MD reports and test files (≤ 757 lines each); no large binaries
- No secrets, credentials, or user data in any committed file

## Deviations From Spec / Open Gate Failures

1. `git diff --check main...HEAD` — **FAILED** at `tasks.md:515` (planning file trailing blank line). Not fixable within implementation scope (Do Not Touch); requires the plan owner to remove the trailing blank line when committing the plan update. Stage is not complete until resolved.
2. `ruff format --check .` — inherited repo-wide baseline failure (94 files), identical on `main` for the Stage 30 changed files; not introduced by Stage 30.

## Risks / Follow-up

- Repo-wide `ruff format` baseline still needs separate governance.
- The working-tree `tasks.md` plan update (TASK-30.7–30.10) is uncommitted; the plan owner must commit it (and fix the EOF blank line) so `git diff --check` passes.
- Experiment learning: appending category-level terms for BANK_CLEARING / SINGLE_SIDE_MISSING reduced target Recall@5 (0.35→0.25); a future attempt would need a different enrichment direction.
