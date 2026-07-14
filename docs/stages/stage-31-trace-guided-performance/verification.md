# Stage 31 Verification — Final no-go

- **Stage**: `stage-31-trace-guided-performance`
- **Branch**: `stage-31-trace-guided-performance`
- **Verified Revision**: `b7468fd8ad8eb849a7811a3f8e0964da2912b631`
- **Date**: 2026-07-14
- **Final Outcome**: `no_go`
- **Review Status**: `local-closeout-ready`
- **Runtime Candidate**: not implemented; workflow remains serial

## Final decision

TASK-31.11 closed the final CPU environment identity, schema and comparison contract gaps. From the
clean revision `b7468fd`, the fixed Stage 31 command completed with real DeepSeek, real bge_m3 and a
runtime-derived CPU identity. All 20 measured flows were complete and the artifact was trusted.

The theoretical warm P95 improvement was `0.633%`, below the `20.0%` entry threshold. The independence
gate also remained fail-closed because no concurrency candidate exists to prove shared-state, failure
ordering, cancellation and resource-reclamation safety. The accepted Stage outcome is therefore
`no_go`. TASK-31.3 and TASK-31.4 are `out-of-scope`; no runtime candidate, after artifact or comparison
artifact was created or retained.

## Clean revision proof

Immediately before the real benchmark:

```bash
git branch --show-current
git status --short
git rev-parse HEAD
```

- Branch: `stage-31-trace-guided-performance`
- Working tree: clean
- HEAD: `b7468fd8ad8eb849a7811a3f8e0964da2912b631`

## Real baseline command

```bash
uv run python -m scripts.bench_agent_latency \
  --scenario stage31-critical-path \
  --provider deepseek \
  --embedding-backend bge_m3 \
  --cold-runs 1 \
  --warmup-runs 1 \
  --runs 20 \
  --report reports/performance_cost_benchmark_stage31_baseline.md \
  --json-report reports/performance_cost_benchmark_stage31_baseline.json
```

- Exit code: 0
- Runtime window: 2026-07-14 11:32–11:36 Asia/Shanghai
- Artifact evaluation time: `2026-07-14T03:36:13.019280Z`
- Boundary: offline benchmark; not production SLA

## Accepted artifact identity and measurements

- JSON: `reports/performance_cost_benchmark_stage31_baseline.json`
  - SHA-256: `f2618627054299bb520aab3251d8770071c6dc5550a749d22e6ae6a0cdebc690`
- Markdown: `reports/performance_cost_benchmark_stage31_baseline.md`
  - SHA-256: `bdfeb085dd536efbfca0303bc56d24588e8adc7f900fb3c46328263dc9bc2b21`
- Artifact role: `baseline`
- Git revision: `b7468fd8ad8eb849a7811a3f8e0964da2912b631`
- Input SHA-256: `252b547ba756af6d71fea1f8ce7ee7d448c6bf67172c4bbeb136116d937cbdca`
- Environment: Darwin, arm64, CPU `arm`, Python 3.11.15
- Provider/model: requested/effective `deepseek` / `deepseek-v4-flash`
- Embedding/retrieval: requested/effective `bge_m3`; mode `dense`
- Trust: `true`; no trust reasons; no environment gap
- Run plan: 1 cold, 1 warm-up, 20 measured, 20 complete
- Trace completeness: 20/20 (`1.0`)
- Reliability: 20 successful, 0 failed, error rate `0.0`
- Warm E2E P50/P95: `8668.141 ms` / `10583.555 ms`
- Predicted parallel warm P95: `10516.555 ms`
- Theoretical warm P95 improvement: `0.633%`
- Logical calls: 40 Agent, 23 Tool; 40 provider transport attempts
- Usage: 58,960 input, 14,101 output, 73,061 total tokens; 3,653 per successful run
- Estimated cost: `$0.03791547` total; `$0.0018957735` per successful run, using the artifact's stated assumptions
- Decision: `no_go`
- Closed reasons: `independence_gate_failed`, `theory_pct_0.633_lt_20.0`

Independence findings: data dependency `safe`; shared state `unknown`; failure order `unsafe`;
cancellation `unbounded`; resource reclamation `unknown`. These tokens correctly prevent candidate work.

## Task disposition

- TASK-31.1: done — benchmark/report/gate contract.
- TASK-31.2: done — final accepted baseline supplied by TASK-31.9.
- TASK-31.3: out-of-scope — baseline outcome is `no_go`.
- TASK-31.4: out-of-scope — no candidate exists.
- TASK-31.5: out-of-scope — superseded by TASK-31.10.
- TASK-31.6–31.8: done — post-review contract repairs.
- TASK-31.9: done — clean-revision real baseline, outcome `no_go`.
- TASK-31.10: done — final Stage/PR verification recorded here.
- TASK-31.11: done — CPU identity, validator and comparison fail-closed contract.

## Verification results

### TASK-31.11 benchmark contract suite

```bash
uv run pytest tests/test_bench_agent_latency.py -q
```

- Exit code: 0
- Result: 77 passed in 48.05s

The previous missing-CPU baseline now returns `baseline_runtime_identity_invalid` from
`_stage31_artifact_validation_reasons()`.

### Final Stage 31 focused suite

```bash
uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py \
  tests/test_trace_schema.py -q
```

- Exit code: 0
- Result: 222 passed in 50.69s

### Full pytest

```bash
uv run pytest
```

- Exit code: 0
- Result: 1215 passed, 1 skipped, 6 warnings in 213.89s

### Ruff check

```bash
uv run ruff check .
```

- Exit code: 0
- Result: All checks passed

### Stage 31 changed-path format

```bash
uv run ruff format --check scripts/bench_agent_latency.py tests/test_bench_agent_latency.py
```

- Exit code: 0
- Result: 2 files already formatted

### Repo-wide Ruff format

```bash
uv run ruff format --check .
```

- Exit code: 1
- Result: 92 inherited files would be reformatted; 112 files already formatted
- Interpretation: this is not recorded as a passed command. The two changed Stage 31 Python files pass,
  so Stage 31 adds no format regression; repo-wide inherited drift remains out of scope.

### Diff checks

```bash
git diff --check main...HEAD
git diff --check
```

- Exit code: 0 for both commands
- Result: no whitespace errors in the committed Stage slice or final local artifacts/docs

## Scope and hygiene

- `git diff --stat main...HEAD`: 8 files changed, 7,380 insertions, 330 deletions at verified revision
  `b7468fd`.
- `git diff --stat origin/main`: final local tree is 8 files changed, 7,355 insertions, 330 deletions.
- `git status --short`: only the expected removal of the stale, non-formal Stage `pr.md` plus Stage 31
  `tasks.md`, `verification.md` and baseline JSON/Markdown updates remain before user-owned commits.
- Changed paths remain limited to the accepted ADR/spec/tasks/verification, Stage 31 reports, benchmark
  runner and its tests.
- All formal Stage files and reports are tracked.
- Secret-pattern scan found no key, credential, DSN or private-key match in Stage 31 changed paths.
- No tracked file exceeds 10 MiB; no `.env`, cache, model weight, Chroma data or build artifact is in the
  Stage 31 change set.

## Verdict

```text
Blocking
- None.

Non-blocking
- Repo-wide Ruff format retains an inherited 92-file failure; Stage 31 changed Python files pass.

Verdict: Approve
```
