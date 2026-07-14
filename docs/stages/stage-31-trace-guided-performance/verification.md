# Stage 31 Verification

- **Stage**: `stage-31-trace-guided-performance`
- **Branch**: `stage-31-trace-guided-performance`
- **Verified Revision**: `2cd4ff6081d0a1e2656752c0f17d8659dfdb701a`
- **Date**: 2026-07-14T01:40:17Z
- **Final Outcome**: **`no_go`**

## Task Execution Summary

| Task | Status | Notes |
|------|--------|-------|
| TASK-31.1 | executed | Benchmark contract, report generation, gate logic, 47 deterministic tests |
| TASK-31.2 | executed | Initial baseline generated; decision: `no_go` (review-blocked) |
| TASK-31.3 | **skipped** | `no_go` — no candidate allowed |
| TASK-31.4 | **skipped** | `no_go` — no candidate to compare |
| TASK-31.5 | executed | Initial verification (review-blocked) |
| TASK-31.6 | executed | Runtime identity, canonical input hash, environment gap, bench authorizer |
| TASK-31.7 | executed | Trace eligibility, full-flow accounting, independence truth |
| TASK-31.8 | executed | After artifact role, comparison retention contract |
| TASK-31.9 | executed | Regenerated real baseline with repaired contract |
| TASK-31.10 | executing | This final verification |

No runtime candidate was retained. The workflow remains serial per ADR-032.

## Artifact Identity

| Artifact | Path | SHA256 |
|----------|------|--------|
| Baseline JSON (final) | `reports/performance_cost_benchmark_stage31_baseline.json` | `2dc819f335b1ac933a1561d7d8371067bbe250c763a3819a795e67ba4792de07` |
| Baseline MD (final) | `reports/performance_cost_benchmark_stage31_baseline.md` | `7df7edb6067e6a0a6a1aca060ec2d0620e79073b4d223802a16d2bd47a6f8e75` |

No after/comparison artifacts were produced (no candidate to compare).

## Baseline Key Metrics (from JSON)

| Metric | Value |
|--------|-------|
| artifact_role | `baseline` |
| schema_version | `1.0` |
| Git revision | `7c4b0a7d13f6ab437cbbb0a20815980bbf944214` |
| input_sha256 | `1f4c2ccf28d6deccfe31caac3b01737aa842f351bc75fe847ff2a89c067233a3` |
| Provider | deepseek → deepseek |
| Model | deepseek-v4-flash → deepseek-v4-flash |
| Embedding | bge_m3 → bge_m3 |
| Retrieval mode | dense |
| Trusted | `true` |
| Cold runs | 1 |
| Warm-up runs | 1 |
| Measured runs | 20 |
| Complete runs | 20 (100%) |
| E2E P95 | 20400.707ms |
| Predicted P95 | 20328.707ms |
| Theoretical improvement | 0.353% |
| Agent calls | 40 |
| Tool calls | 24 |
| Transport attempts | 40 |
| Total tokens | 74,253 |
| Per-run tokens | 3,712 |
| Total cost | $0.039 |
| Per-run cost | $0.0019 |
| Success/failure | 20/0 |
| Decision | `no_go` |
| Gate failure reason | `theory_pct_0.353_lt_20.0` |

## Gate Results

### Focused Test Suite

```bash
uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py \
  tests/test_trace_schema.py -q
```

- **Exit code**: 0
- **Result**: 205 passed

### Full Pytest

```bash
uv run pytest
```

- **Exit code**: 0
- **Result**: 1198 passed, 1 skipped, 0 failed

### Ruff Check

```bash
uv run ruff check .
```

- **Exit code**: 0
- **Result**: All checks passed

### Ruff Format Check

```bash
uv run ruff format --check .
```

- **Exit code**: 1 (92 files would be reformatted — inherited baseline, not Stage 31)
- **Stage 31 changed-path proof**:
  ```bash
  uv run ruff format --check scripts/bench_agent_latency.py tests/test_bench_agent_latency.py
  ```
  - **Exit code**: 0 — "2 files already formatted"

Stage 31 did not introduce any new format regressions. 92 inherited files pre-date this stage.

### Git Diff

```bash
git diff --check main...HEAD
```

- **Exit code**: 0

```bash
git diff --stat main...HEAD
```

8 files changed, 4590 insertions(+), 331 deletions(-):
- `decisions/ADR-31.1-measurement-gated-critical-path-concurrency.md`
- `docs/stages/stage-31-trace-guided-performance/spec.md`
- `docs/stages/stage-31-trace-guided-performance/tasks.md`
- `docs/stages/stage-31-trace-guided-performance/verification.md`
- `reports/performance_cost_benchmark_stage31_baseline.json`
- `reports/performance_cost_benchmark_stage31_baseline.md`
- `scripts/bench_agent_latency.py`
- `tests/test_bench_agent_latency.py`

All files are within Stage 31 allowed scope.

### Hygiene Check

No secrets, `.env`, prompt/model output, business data, cache, model files, ChromaDB local data, build artifacts, or large files in commits.

## Deviations

1. `tasks.md` shows as locally modified (Codex review status updates: `planned` → `review-blocked`). Not included in this verification commit.
2. MySQL schema required manual column additions before TASK-31.2/TASK-31.9 could execute (`job_attempt`, `retry_recovered`, etc.).
3. `ruff format --check .` inherited 92 pre-existing files that would be reformatted; Stage 31 changed-path check confirms zero new regressions.

## Conclusion

Stage 31 completes with outcome **`no_go`**. The theoretical warm P95 improvement from parallelizing ExtractionAgent and `search_rules` is only 0.353%, far below the 20% threshold. RAG contributes ~70ms to the ~20s E2E latency dominated by LLM calls (ExtractionAgent + AuditAgent).

All gates pass: focused suite 205 tests, full pytest 1198 + 1 skipped, ruff check clean, no Stage 31 format regressions. No runtime candidate was implemented or retained. The workflow remains serial.
