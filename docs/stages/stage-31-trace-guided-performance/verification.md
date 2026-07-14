# Stage 31 Verification — Clean-revision baseline rerun

- **Stage**: `stage-31-trace-guided-performance`
- **Branch**: `stage-31-trace-guided-performance`
- **Verified Code Revision**: `6b75d1c89072318cf4cfea4465689eb7fad1ae22`
- **Date**: 2026-07-14
- **Final Outcome**: not accepted — measured direction is `no_go`, artifact contract remains review-blocked
- **Review Status**: **`review-blocked`**
- **Runtime Candidate**: not implemented; workflow remains serial

## Executive result

The post-review correction was committed and the working tree was clean at revision `6b75d1c` before
the real benchmark started. The fixed command completed with real DeepSeek and real bge_m3, producing
1 cold, 1 warm-up and 20/20 complete measured flows. The measured theoretical warm P95 improvement was
`0.47%`, below the `20.0%` entry threshold, and the unimplemented concurrency safety findings remained
fail-closed. The measured direction is therefore `no_go`; TASK-31.3 and TASK-31.4 are not authorized.

The generated artifact cannot yet be accepted as final Stage evidence. The accepted spec requires the
Environment section to contain OS, architecture, Python, CPU and boundary. The generated JSON omits
`environment.cpu`, while its trust section still says `trusted=true`. The Stage 31 schema validator and
comparison contract also validate/compare OS, architecture, Python and boundary without requiring CPU.
This is a report-contract failure, not an environment outage, and must not be repaired by editing JSON
by hand. TASK-31.11 records the bounded implementation repair; TASK-31.9 and TASK-31.10 must then be
rerun from the new clean revision.

The earlier `0.353%` artifact remains superseded. The current `0.47%` run is real and informative, but
it is review-blocked and cannot close Stage 31 or authorize a candidate.

## Clean revision proof

Before the benchmark:

```bash
git branch --show-current
git status --short
git rev-parse HEAD
```

- Branch: `stage-31-trace-guided-performance`
- Working tree: clean
- HEAD: `6b75d1c89072318cf4cfea4465689eb7fad1ae22`

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
- Runtime window: 2026-07-14 10:44–10:48 Asia/Shanghai
- Artifact evaluation time: `2026-07-14T02:48:21.573143Z`
- Boundary: offline benchmark; not production SLA

## Generated artifact identity and measurements

- JSON: `reports/performance_cost_benchmark_stage31_baseline.json`
  - SHA-256: `9a0b89a89a5ae2b06dc7fbd8470e1e57d885a8717c7f58eff156e3d09b4767e1`
- Markdown: `reports/performance_cost_benchmark_stage31_baseline.md`
  - SHA-256: `bb9140dd0c9c5fb9c365fa6e158a9e0359becda336e8254125978f59476548b9`
- Artifact role: `baseline`
- Git revision: `6b75d1c89072318cf4cfea4465689eb7fad1ae22`
- Input SHA-256: `252b547ba756af6d71fea1f8ce7ee7d448c6bf67172c4bbeb136116d937cbdca`
- Provider/model: requested/effective `deepseek` / `deepseek-v4-flash`
- Embedding/retrieval: requested/effective `bge_m3`; mode `dense`
- Environment present in JSON: Darwin, arm64, Python 3.11.15, offline benchmark boundary
- Environment contract omission: required `cpu` field is absent
- Run plan: 1 cold, 1 warm-up, 20 measured, 20 complete
- Trace completeness: 20/20 (`1.0`)
- Reliability: 20 successful, 0 failed, error rate `0.0`
- Warm E2E P50/P95: `9462.284 ms` / `13621.027 ms`
- Predicted parallel warm P95: `13557.027 ms`
- Theoretical warm P95 improvement: `0.47%`
- Logical calls: 40 Agent, 27 Tool; 40 provider transport attempts
- Usage: 58,960 input, 14,550 output, 73,510 total tokens; 3,675 per successful run
- Estimated cost: `$0.0383061` total; `$0.001915305` per successful run, using the artifact's stated assumptions
- Generated decision: `no_go`
- Closed reasons: `independence_gate_failed`, `theory_pct_0.47_lt_20.0`

The independence findings were honestly closed: data dependency `safe`, shared state `unknown`, failure
order `unsafe`, cancellation `unbounded`, and resource reclamation `unknown`. No runtime candidate exists
that could upgrade those findings.

## Artifact-contract blocker

The spec's `Baseline JSON Contract` requires a CPU field in the Environment section. Current evidence:

- the generated JSON has only `os`, `architecture`, `python` and `boundary`;
- Stage 31 schema validation requires the same four fields and does not require CPU;
- comparison checks OS, architecture and Python but not CPU;
- the report nevertheless emits `trust.trusted=true`.

This violates the higher-priority accepted spec. Because artifacts must be generated from the runner and
Markdown must consume the same validated JSON, manually adding CPU to the current files is prohibited.

## Task status after rerun

- TASK-31.1–31.2: remain review-blocked until the required environment contract is satisfied.
- TASK-31.3–31.4: conditional pending and not authorized; current measured direction is `no_go`.
- TASK-31.5: previous verification remains superseded by the repair path.
- TASK-31.6–31.7: reviewed repair contract and focused tests passed.
- TASK-31.8: review-blocked only on CPU comparison coverage.
- TASK-31.9: real rerun completed, but its artifact is review-blocked by missing CPU identity.
- TASK-31.10: gates rerun and recorded here, but final acceptance waits for TASK-31.11 and a clean rerun.
- TASK-31.11: pending bounded CPU identity/schema/comparison repair.

## Verification results

### Contract and Trace focused suite

```bash
uv run pytest tests/test_bench_agent_latency.py tests/test_trace_recorder.py \
  tests/test_trace_schema.py -q
```

- Exit code: 0
- Result: 164 passed in 47.33s

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
- Result: 211 passed in 48.59s

### Full pytest

```bash
uv run pytest
```

- Exit code: 0
- Result: 1204 passed, 1 skipped, 6 warnings in 205.38s

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
- Interpretation: not an all-gates-passed result. The two changed Stage 31 Python files add no format
  regression, but repo-wide inherited drift remains outside Stage 31 scope.

### Diff checks

```bash
git diff --check main...HEAD
git diff --check
```

- Exit code: 0 for both commands
- Result: no whitespace errors in the committed Stage slice or generated local artifacts

## Scope and hygiene

- `git diff --stat main...HEAD`: 8 files changed, 5,657 insertions, 330 deletions at committed HEAD
  `6b75d1c`.
- `git diff --stat main`: final local tree is 8 files changed, 7,028 insertions, 330 deletions.
- `git status --short`: only the expected Stage 31 `tasks.md`, `verification.md`, baseline JSON and
  baseline Markdown are modified after the rerun/review; no unrelated working-tree path is present.
- Changed paths remain limited to the accepted ADR/spec/tasks/verification, Stage 31 reports, benchmark
  runner and its tests.
- All formal Stage files and reports are tracked.
- Secret-pattern scan over the Stage 31 changed paths found no key, credential, DSN or private-key match.
- No tracked file exceeds 10 MiB; no `.env`, cache, model weight, Chroma data or build artifact is in the
  Stage 31 change set.

## Verdict

```text
Blocking
- Required Environment.cpu is absent from the Stage 31 artifact, schema validator and comparison
  identity gate, while the report still claims trust=true. Implement TASK-31.11, commit it, then rerun
  TASK-31.9 and TASK-31.10 from that clean revision.

Non-blocking
- Repo-wide Ruff format remains an inherited 92-file failure; Stage 31 changed Python files pass.

Verdict: Request Changes
```
