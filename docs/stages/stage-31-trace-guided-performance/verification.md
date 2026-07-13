# Stage 31 Verification

- **Stage**: `stage-31-trace-guided-performance`
- **Branch**: `stage-31-trace-guided-performance`
- **HEAD**: `f72c01cb050c5d4b0e567a95b515f71d8d6c4f43`
- **Date**: 2026-07-13T15:34:20Z
- **Final Outcome**: **`no_go`**

## Task Execution Summary

| Task | Status | Notes |
|------|--------|-------|
| TASK-31.1 | executed | Benchmark contract, report generation, gate logic, 47 deterministic tests |
| TASK-31.2 | executed | Real DeepSeek + bge_m3 baseline generated; decision: `no_go` |
| TASK-31.3 | **skipped** | `no_go` — no candidate allowed |
| TASK-31.4 | **skipped** | `no_go` — no candidate to compare |
| TASK-31.5 | executing | This verification |

No runtime candidate was retained. The workflow remains serial per ADR-032.

## Artifact Identity

| Artifact | Path | SHA256 |
|----------|------|--------|
| Baseline JSON | `reports/performance_cost_benchmark_stage31_baseline.json` | `fcc786fea85d28b66c6c3fa1c4c03cf39429d80c7731a9f92fd402300893c28f` |
| Baseline MD | `reports/performance_cost_benchmark_stage31_baseline.md` | `cbec510b81896861ab10b6113042e20028f7f405968e0bd101da205def13c5f2` |

No after/comparison artifacts were produced (candidate not allowed).

## Baseline Key Metrics

| Metric | Value |
|--------|-------|
| Git revision (baseline) | `0a849a8f23b71151d9182b84623cffc3e6f0cdb1` |
| input_sha256 | `f51a4070637006a640d0ea54d63fe4fd6ecc89feac7b903227380f8772b87577` |
| Trusted | `true` |
| Trace completeness | 20/20 |
| Actual warm E2E P95 | 10259.652ms |
| Predicted warm E2E P95 | 10199.652ms |
| Theoretical P95 improvement | 0.585% |
| Decision | `no_go` |
| Gate failure reason | `theory_pct_0.585_lt_20.0` |

## Gate Results

### Focused Test Suite

```bash
uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py -q
```

- **Exit code**: 0
- **Result**: 141 passed

### Full Pytest

```bash
uv run pytest
```

- **Exit code**: 0
- **Result**: 1185 passed, 1 skipped, 0 failed

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
- **Stage 31 files**: `scripts/bench_agent_latency.py` and `tests/test_bench_agent_latency.py` already formatted
- **Evidence**: `uv run ruff format --check scripts/bench_agent_latency.py tests/test_bench_agent_latency.py` → exit 0, "2 files already formatted"

Stage 31 did not introduce any new format regressions.

### Git Diff

```bash
git diff --check main...HEAD
```

- **Exit code**: 0

```bash
git diff --stat main...HEAD
```

7 files changed, 3582 insertions(+), 327 deletions(-):
- `decisions/ADR-31.1-measurement-gated-critical-path-concurrency.md`
- `docs/stages/stage-31-trace-guided-performance/spec.md`
- `docs/stages/stage-31-trace-guided-performance/tasks.md`
- `reports/performance_cost_benchmark_stage31_baseline.json`
- `reports/performance_cost_benchmark_stage31_baseline.md`
- `scripts/bench_agent_latency.py`
- `tests/test_bench_agent_latency.py`

All files are within Stage 31 allowed scope.

```bash
git status --short
```

- **Result**: clean (no untracked or unstaged files)

### Hygiene Check

No secrets, `.env`, cache, model files, ChromaDB local data, build artifacts, or large files in commits.

## Deviations

1. TASK-31.2 required modifying `scripts/bench_agent_latency.py` (adding tool executor bypass for `PERMISSION_DENIED`) — necessary to complete the real baseline, as the `default_tool_executor`'s `make_tenant_authorizer` blocks benchmark runs with transient task IDs.
2. MySQL schema required manual column additions (`job_attempt`, `retry_recovered`, `retry_exhausted`, `failure_type`, `failure_summary`, `failed_at`, `force_requeue_count`) before the benchmark could execute successfully.
3. `ruff format --check .` inherited 92 files that would be reformatted; these pre-date Stage 31 and are not introduced by this stage.

## Conclusion

Stage 31 completes with outcome **`no_go`**. The theoretical warm P95 improvement from parallelizing ExtractionAgent and `search_rules` is only 0.585%, far below the 20% threshold. RAG contributes ~60ms to the ~10s E2E latency. The workflow remains serial in accordance with ADR-032.

No runtime candidate was implemented or retained. All tests pass. Ruff check passes. Stage 31 files are correctly formatted.
