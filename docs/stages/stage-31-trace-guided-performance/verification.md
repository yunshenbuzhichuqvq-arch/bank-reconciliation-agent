# Stage 31 Verification — Post-review correction

- **Stage**: `stage-31-trace-guided-performance`
- **Branch**: `stage-31-trace-guided-performance`
- **Reviewed HEAD**: `fbec6ff2e5b328426d4789e479ebdbb241cd4f85`
- **Verified Revision**: not assigned — review repairs are still uncommitted
- **Date**: 2026-07-14
- **Review Status**: **`review-blocked`**
- **Runtime Candidate**: not implemented; workflow remains serial

## Correction to the previous verification

The previous document marked all gates passed and treated the committed baseline as final. The
post-implementation review found that this was not supportable:

1. Unverified candidate properties were labelled `safe` or `bounded`, so the independence gate could
   pass without runtime proof.
2. Trace eligibility did not validate every span's tenant/task/flow identity and did not enforce the
   required parent, status, time and duration contract completely.
3. Missing Audit usage could still leave the artifact trusted because only Extraction usage was
   checked directly.
4. A broad `except Exception` converted unexpected `run_item()` programming errors into measured
   `no_go` results; its regression test asserted that incorrect behavior.
5. The canonical input hash omitted `source_b_item.remark` and was maintained separately from the
   actual state payload.
6. The benchmark authorizer did not bind the exact task and flow.
7. Comparison did not require per-run business decision, RAG evidence, Fallback, Trace and call-order
   equivalence; it also omitted effective-model comparison and accepted missing token/cost fields as
   zero.
8. The previous diff statistic (`4590 insertions`) did not match the committed tree (`4611
   insertions`). The repo-wide Ruff format gate also exited 1, so the conclusion must not say that all
   gates passed.

The committed baseline JSON/Markdown and their old hashes are therefore **superseded evidence**. They
must not be used to close Stage 31 or authorize a candidate.

## Direct repairs in the local working tree

- Runtime provider/model/backend/mode identity now comes from the objects and settings used by the
  benchmark; fake or stub providers cannot claim real DeepSeek identity.
- One canonical, versioned payload now drives both the state and `input_sha256`, including both
  source remarks and all amount strings.
- Tool authorization now requires the exact benchmark user, task, flow, scenario and branch.
- Unexpected `run_item()` errors propagate to a non-zero CLI result and do not produce a measured
  artifact.
- Trace completeness uses the canonical Trace validator plus required-span identity, parent, status,
  time and duration checks.
- Usage/cost includes all Agent spans, logical Agent/Tool counts and provider transport attempts;
  missing usage from any real Agent fails trust closed.
- Unimplemented candidate safety is reported honestly as `unknown`, `unsafe` or `unbounded`, forcing
  `independence_gate_failed`.
- Baseline/after artifacts now contain sanitized per-run contract observations. Comparison checks
  business decision, next action, RAG outcome/evidence, Fallback terminal, Trace validity and call
  sequence, in addition to runtime identity, latency, tokens, cost and reliability.
- Generated Stage 31 artifacts are schema-checked before Markdown or JSON is written.

## Local repair verification

### Focused Stage 31 suite

```bash
uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py \
  tests/test_trace_schema.py -q
```

- **Exit code**: 0
- **Result**: 211 passed

### Full pytest

```bash
uv run pytest
```

- **Exit code**: 0
- **Result**: 1204 passed, 1 skipped, 6 warnings

### Ruff check

```bash
uv run ruff check .
```

- **Exit code**: 0
- **Result**: All checks passed

### Ruff format

```bash
uv run ruff format --check scripts/bench_agent_latency.py tests/test_bench_agent_latency.py
```

- **Exit code**: 0
- **Result**: 2 files already formatted

```bash
uv run ruff format --check .
```

- **Exit code**: 1
- **Result**: 92 inherited files would be reformatted; the two Stage 31 changed Python files are clean

### Diff checks

```bash
git diff --check
git diff --check main...HEAD
```

- **Exit code**: 0 for both commands

## Evidence still required

The real DeepSeek + bge_m3 baseline was not rerun during this repair pass. Running it before the
repairs have a clean commit would incorrectly attribute new behavior to the old `HEAD`, violating the
artifact identity contract.

To clear `review-blocked`:

1. Commit the reviewed `scripts/bench_agent_latency.py` and
   `tests/test_bench_agent_latency.py` changes on the stage branch.
2. From that clean revision, rerun the fixed 1 cold + 1 warm-up + 20 measured DeepSeek/bge_m3 command.
3. Replace baseline JSON/Markdown only with those same-run generated artifacts.
4. Re-run the focused/full/Ruff/diff gates and update this file with the clean verified revision,
   artifact hashes, exact gate decision and current diff statistics.

Until those steps complete, the previous `0.353%` measurement may be informative but is not accepted
as the final repaired Stage 31 artifact. No runtime parallel candidate is authorized.
