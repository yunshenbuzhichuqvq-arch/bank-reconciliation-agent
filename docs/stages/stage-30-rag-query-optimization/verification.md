# Stage 30 Verification

- **Branch**: `stage-30-rag-query-optimization`
- **HEAD**: `b963496ce0b2efa6200f0689db963a3240a2d789` (code/artifact state under verification; this verification commit becomes the new HEAD)
- **Date**: 2026-07-13T12:16:28Z
- **Environment**: Darwin 25.5.0 arm64 / Apple M5 / Python 3.11.15 / torch 2.12.1 / sentence_transformers 5.6.0
- **Final Experiment State**: `experiment rejected`
- **Stage/PR Gate State**: `pytest`, `ruff check .`, and `git diff --check main...HEAD` pass. `ruff format --check .` remains an inherited repo-wide baseline failure (identical on `main` for the Stage 30 changed files). The experiment conclusion (`experiment rejected`) is a separate axis from gate status and does not override it.

## Task-Level Evidence Summary

| Task | Status | Key Evidence |
|------|--------|-------------|
| TASK-30.1 | done | `scripts/eval_rag.py` + tests: matrix artifact hashes, git_revision, query_enrichment metadata; comparison stage30 trust gate with hash/bucket fail-closed; MRR-only regression test; full non-target bucket reporting |
| TASK-30.2 | done | Baseline trusted: `reports/rag_quality_matrix_stage30_baseline.{json,md}`, bge_m3/dense, 120 cases, hash non-empty, jq gate passed |
| TASK-30.3 | done | `rules/rag_query_terms.yaml`, `src/.../query_enrichment.py`, `tests/test_rag_query_enrichment.py`; created, tested, and later deleted (rollback) |
| TASK-30.4 | done | Runtime + eval integration: `ReconciliationService._build_rag_query` and `scripts/eval_rag` using shared helper; created and later deleted (rollback) |
| TASK-30.5 | done | Experiment **rejected**: target bucket regressed (Recall@5 0.35→0.25, miss 8→9). Rollback executed—candidate integration, helper, and profile removed; TASK-30.1 evidence contract and after/comparison reports retained. Candidate revision `51b48ef`, profile SHA-256 `40dce1eb42546d416f3717f3c8027d761f62fa08671fd667dc86645e95ac6b7f`. |
| TASK-30.6 | done | Initial verification record (superseded by TASK-30.10 / TASK-30.13) |
| TASK-30.7 | done | Artifact role + enrichment metadata fail-closed: baseline disabled / after enabled+profile+profile_sha256+latency, git_revision required both sides, latency count/order validation; source/trust evidence surfaced in JSON+Markdown |
| TASK-30.8 | done | Bucket set equality, key uniqueness, per-bucket case_count equality, case_count sum == matrix case_count, required-field checks, `_bucket_deltas` hardened |
| TASK-30.9 | done | Regenerated `reports/rag_optimization_comparison.{json,md}` with hardened contract; `trusted=true`, `success=false`, exactly 10 non-target buckets all delta=0; byte-reproducible |
| TASK-30.10 | done | First corrected verification record (bucket totals fixed to 11 total / 10 non-target) |
| TASK-30.11 | done | `scripts/eval_rag.py` + `tests/test_v1_1_eval_rag_report.py`: Stage 30 intent detected by ANY of `query_enrichment/eval_set_sha256/chunk_corpus_sha256/git_revision` (both-sides-drop-query_enrichment no longer falls back to legacy); top-level `requested_backends`/`modes` must be consistent across sides and contain the selected backend/mode; legacy artifacts without any intent key still use the guarded legacy reader; 5 new tests |
| TASK-30.12 | done | `scripts/eval_rag.py` + `tests/test_v1_1_eval_rag_report.py`: exception-free bucket schema validation (non-empty string identity; non-bool non-negative int counts with `miss<=case`; finite metric values; guarded sum), illegal artifacts return structured `trusted=false/success=false` without raising; Stage 30 target locked to exactly 10 cases both sides (`STAGE30_TARGET_CASE_COUNT`); 6 new tests |
| TASK-30.13 | done | This final verification record |

## Comparison Reproducibility

- Rebuilt comparison from committed baseline/after JSON to `/tmp/stage30-comparison-review.{json,md}`
- `cmp -s reports/rag_optimization_comparison.json /tmp/stage30-comparison-review.json` → byte-identical
- `cmp -s reports/rag_optimization_comparison.md /tmp/stage30-comparison-review.md` → byte-identical
- Rebuilt report: `trust.trusted=true`, `success=false`, target bucket case_count 10 (baseline and after), 10 non-target buckets all delta=0

## Full Gate Results

```bash
uv run pytest
```
- **Exit code**: 0 — `1150 passed, 1 skipped, 6 warnings`

```bash
uv run ruff check .
```
- **Exit code**: 0 — `All checks passed!`

```bash
uv run ruff format --check .
```
- **Exit code**: 1 — `94 files would be reformatted, 110 files already formatted`
- **Status**: **Inherited baseline failure** (documented since Stage 29). Targeted evidence for the Stage 30 changed Python files (`scripts/eval_rag.py`, `tests/test_mvp2b3_eval_rag.py`, `tests/test_v1_1_eval_rag_report.py`):
  - On `stage-30-rag-query-optimization`: `3 files would be reformatted`
  - On `main` (same three files): `3 files would be reformatted`
  - Conclusion: identical on `main`; Stage 30 introduced no new format violations. Newly authored Stage 30 code regions were kept format-clean without reformatting pre-existing lines.

```bash
git diff --check main...HEAD
```
- **Exit code**: 0 — **PASS** (the earlier `tasks.md` trailing-blank-line issue was resolved when the plan owner committed the plan update `d3d79e2`)

```bash
git diff --stat main...HEAD
```
- **Result**: `13 files changed, 5022 insertions(+), 142 deletions(-)`
- Files: ADR-30.1, spec.md, tasks.md, verification.md, `reports/rag_optimization_comparison.{json,md}`, `reports/rag_quality_matrix_stage30_after.{json,md}`, `reports/rag_quality_matrix_stage30_baseline.{json,md}`, `scripts/eval_rag.py`, `tests/test_mvp2b3_eval_rag.py`, `tests/test_v1_1_eval_rag_report.py`
- Note: this commit updates `verification.md`, so its line count in the final diff will increase relative to the snapshot above.

```bash
git status --short
```
- **Result**: clean (no uncommitted `tasks.md`, no unexpected code/data/cache/build artifacts)

## Artifact and Metrics Summary

### Baseline (TASK-30.2, trusted)
- `reports/rag_quality_matrix_stage30_baseline.json`
- backend `bge_m3`, mode `dense`, top-k 5, case_count 120
- eval_set_sha256 `71fd0db2…9929c2`, chunk_corpus_sha256 `b71d67f6…f78018`, git_revision `b015add`
- query_enrichment disabled
- Global: Hit@1 0.6333 / Recall@5 0.8250 / MRR 0.7353 / NDCG@5 0.7209
- Target (BANK_CLEARING/SINGLE_SIDE_MISSING): 10 cases, Recall@5 0.3500 / miss 8

### After (TASK-30.5, rejected candidate)
- `reports/rag_quality_matrix_stage30_after.json`
- Same eval_set/chunk_corpus hash, backend, mode, top-k, case_count as baseline
- query_enrichment enabled, profile `bank-clearing-single-side-missing`, profile_sha256 `40dce1eb…c6b7f`, git_revision `51b48ef`, latency count 120
- Global: Hit@1 0.6250 / Recall@5 0.8167 / MRR 0.7244 / NDCG@5 0.7110
- Target: 10 cases, Recall@5 **0.2500** / miss **9** (regressed)

### Comparison (regenerated TASK-30.9, hardened by TASK-30.7/30.8/30.11/30.12)
- `reports/rag_optimization_comparison.{json,md}`
- trust `trusted=true`, `success=false`
- Target delta: Recall@5 -0.1000, miss_count +1, MRR -0.1300, NDCG@5 -0.1193
- Global delta: all within 0.0200 limit (Hit@1 -0.0083, Recall@5 -0.0083, MRR -0.0108, NDCG@5 -0.0099)
- **11 total buckets, 10 non-target buckets**; all 10 non-target deltas = 0
- Verdict: `experiment rejected`

## Scope / Secret / Large-file Check

- `git diff --stat main...HEAD`: 13 files, all within Stage 30 scope (ADR, spec, tasks, verification, reports, eval script, tests)
- No `.env`, `.pkl`, `.bin`, `.pt`, model files, `chroma/`, `__pycache__`, `*.log`, archives, or `node_modules` in the diff
- Largest added files are JSON/MD reports and test files; no large binaries
- No secrets, credentials, or user data in any committed file

## Deviations From Spec / Open Gate Items

1. `ruff format --check .` — inherited repo-wide baseline failure (94 files), identical on `main` for the Stage 30 changed files; not introduced by Stage 30. Requires separate repo-wide governance.
2. All other gates (`pytest`, `ruff check .`, `git diff --check main...HEAD`) pass.

## Risks / Follow-up

- Repo-wide `ruff format` baseline still needs separate governance before the whole repo can pass `ruff format --check .`.
- Experiment learning: appending category-level terms for BANK_CLEARING / SINGLE_SIDE_MISSING reduced target Recall@5 (0.35→0.25); a future attempt would need a different enrichment direction rather than plain category-term appending.
