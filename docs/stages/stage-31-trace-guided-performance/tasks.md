# Stage 31 Tasks: Trace 驱动的测量门禁与条件式关键路径优化

- **Stage**: `stage-31-trace-guided-performance`
- **Branch**: `stage-31-trace-guided-performance`
- **Spec**: `docs/stages/stage-31-trace-guided-performance/spec.md`
- **ADR**: `decisions/ADR-31.1-measurement-gated-critical-path-concurrency.md`
- **Status**: planned
- **Date**: 2026-07-13

## Execution Rules

- opencode 每次只执行一个 task；开始前阅读 `AGENTS.md`、accepted spec、accepted ADR 和当前 task。
- 规划文件必须由用户先单独提交。opencode 不修改或混入提交：本文件、spec、ADR 和其他规划文档。
- 每个实现 task 先增加能证明 contract 缺口的失败测试，再做最小实现并运行指定门禁。
- `Files to Modify` 是当前 task 的完整允许边界；需要扩大时停止并报告，由 Codex 修订 task。
- Phase A 只建立可信 benchmark 与 baseline，不得提前修改 runtime critical path。
- 只有 TASK-31.2 的 artifact 明确输出 `candidate_allowed`，才能执行 TASK-31.3 和 TASK-31.4。
- `no_go` 是完整 Stage 结果；`environment_gap` 是环境缺口。两者都不得包装为性能优化成功。
- 不新增依赖，不改变 HTTP、数据库、Tool、Agent、RAG、SSE 或公开 schema contract。
- Task 完成后检查 `git diff`，创建只引用当前 task 的 Conventional Commit；不得 push 或 merge。
- opencode 不自行修改 task 状态。Codex review 通过后再由 Codex 更新本文件。
- 任何测试或真实 benchmark 未运行、失败或受环境阻塞，必须按真实状态 Report Back。

## Dependency Order

```text
TASK-31.1 Stage 31 benchmark and gate contract
  → TASK-31.2 Real baseline and entry decision
      ├─ candidate_allowed
      │   → TASK-31.3 Minimal runtime candidate
      │     → TASK-31.4 After/comparison and retain-or-rollback verdict
      │       → TASK-31.5 Stage verification
      ├─ no_go
      │   → skip TASK-31.3–31.4
      │   → TASK-31.5 Stage verification
      └─ environment_gap
          → skip TASK-31.3–31.4
          → TASK-31.5 Stage verification
```

TASK-31.2 是 runtime 变更的硬入口门禁。若结果为 `no_go` 或 `environment_gap`，由 Codex review 后将
TASK-31.3 和 TASK-31.4 标记为 `out-of-scope`；opencode 不得自行进入候选实现。

---

## TASK-31.1 — 建立 Stage 31 benchmark、报告与 fail-closed gate contract

**Status**: pending
**Spec Ref**: `Benchmark CLI Contract`、`Baseline JSON Contract`、`Measurement and Gate Semantics`、
`Comparison and Retention Gate`
**ADR Ref**: `ADR-31.1` Decision 2、3、5

### Goal

在保留 Stage 23 CLI 和报告兼容行为的前提下，为 `scripts/bench_agent_latency.py` 增加确定性的 Stage 31
端到端 Trace benchmark、baseline decision 和 before/after comparison contract。本 task 只实现和测试
测量工具，不运行真实 DeepSeek/bge_m3，也不修改 runtime。

### Files to Modify

- Modify: `scripts/bench_agent_latency.py`
- Modify: `tests/test_bench_agent_latency.py`

### Do Not Touch

- `src/bank_reconciliation_agent/`
- 其他 `scripts/` 和 tests
- `reports/`、`data/`、`rules/`、frontend、数据库 schema
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- 真实 provider/backend baseline 或 after 运行。
- 修改 `run_item()`、Trace recorder、Tool executor、provider、retriever 或任何业务行为。
- 实现并发、feature flag、线程池服务或第二套 benchmark 脚本。
- 修改阈值、固定输入、异常标签、prompt、RAG query 或知识库以追逐门禁。

### Acceptance Criteria

- 原 Stage 23 默认调用及 `--runs/--provider/--model/--report/--json-report` 行为保持兼容，现有测试通过。
- 新增 `--scenario stage31-critical-path`，并接受 spec 固定的 `--embedding-backend`、`--cold-runs`、
  `--warmup-runs` 和 `--runs`；`--runs` 只计 warm measured runs。
- Stage 31 使用版本化固定 `BANK_ENTERPRISE / BE-R004 / NARRATIVE_NAME_MISMATCH` 冲正输入，通过真实
  `run_item()` 边界获得同一 `trace_id` 的端到端、Extraction 和 `search_rules` 数据；输入产生稳定非空
  `input_sha256`，且不包含 eval case ID 或 expected chunk ID。
- JSON 覆盖 spec `Baseline JSON Contract` 的全部 section；Markdown 只从同次 JSON 生成，不重复计算。
- cold、warm-up 和 measured samples 严格分离；percentile 与逐 run predicted parallel 公式有边界测试，
  不允许独立 P95 相加或静默删除失败、慢样本和 outlier。
- complete sample 必须 fail closed 校验单个 WORKFLOW root/terminal、单个 Extraction span、单个
  `search_rules` span、parent/sequence/status/duration 和 provider/backend trust metadata。
- independence section 对数据依赖、共享写/副作用、失败顺序、取消/超时和资源回收输出 closed token；
  任一 `unknown | unsafe | unbounded` 都强制 `no_go`。
- baseline 只输出 `candidate_allowed | no_go | environment_gap`：Fake/hash/fallback、少于 20 个完整
  measured runs、trust 不完整或理论 P95 改善小于 20% 均不得得到 `candidate_allowed`。
- 缺 key、网络/provider/model/backend 不可用时生成全新 `environment_gap` JSON/Markdown 并返回非零；
  measured `no_go` 可返回 0。非法输入、schema 或写入失败返回非零且不得输出虚假允许结论。
- 新增 `--scenario stage31-comparison --baseline-json <path> --after-json <path>`；继续复用
  `--report/--json-report` 输出 comparison，并逐项 fail closed 校验 artifact role、input/environment、
  provider/model、backend/mode、run plan、Git revision、Trace completeness、调用次数、token/cost 和错误率。
- comparison 在缺少 focused/stage gate 证明时默认拒绝；CLI 只允许通过显式
  `--focused-gates-passed`、`--stage-gates-passed` 输入已真实运行的门禁结果，缺任一 flag 时不得输出
  `optimization_accepted`。
- comparison 唯一输出 `optimization_accepted | optimization_rejected`，并记录 closed reason list；任何
  trust 或 retention gate 失败时 `success=false`。
- 报告不写入 prompt、模型输出、RAG query、金额、规则正文、Tool args/result、traceback、凭据或连接信息。
- 确定性测试覆盖 trusted/no-go/environment-gap、20% 边界、Trace 缺失/重复、metadata mismatch、
  comparison accept/reject 和旧 CLI 回归；不通过真实网络或下载模型。

### Verification Commands

```bash
uv run pytest tests/test_bench_agent_latency.py -q
uv run ruff check scripts/bench_agent_latency.py tests/test_bench_agent_latency.py
uv run ruff format --check scripts/bench_agent_latency.py tests/test_bench_agent_latency.py
```

### Report Back Requirements

- Changed Files
- Legacy Compatibility Summary：旧 CLI/JSON/Markdown 行为及回归测试
- Stage 31 Contract Summary：固定输入、run 分类、Trace eligibility、schema 和公式
- Gate Summary：baseline/comparison 的全部 fail-closed 条件与 20% 边界
- Sensitive-data Exclusion Summary
- Tests Run：逐条命令、退出码和真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-31.1`

---

## TASK-31.2 — 生成真实 Stage 31 baseline 并冻结入口结论

**Status**: pending
**Spec Ref**: `Phase A — Baseline contract and decision gate`、`Fixed benchmark input`、
`Trace sample eligibility`、`Independence gate`
**ADR Ref**: `ADR-31.1` Decision 1–3

### Goal

使用 TASK-31.1 的 contract，在当前串行 runtime 上以真实 DeepSeek、真实 bge_m3 和固定 `BE-R004`
输入生成一次 cold/warm baseline，并给出唯一入口结论：`candidate_allowed | no_go | environment_gap`。
本 task 不修改 Python 代码，也不实现候选。

### Files to Modify

- Create: `reports/performance_cost_benchmark_stage31_baseline.json`
- Create: `reports/performance_cost_benchmark_stage31_baseline.md`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`rules/`、`data/`
- 既有 `reports/performance_cost_benchmark.json` 和 `reports/performance_cost_benchmark.md`
- Stage 31 after/comparison reports
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- Fake/hash/fallback 结果替代真实 baseline。
- 修改输入、run 数、20% 阈值、provider/model/backend/mode 或报告内容以使 gate 通过。
- 实现并发、修改 workflow/Trace/Tool/Agent，或先生成 after。
- 将 `environment_gap` 解释为 measured `no_go`，或把理论收益表述为实测收益。

### Acceptance Criteria

- 完整运行 spec 固定命令：1 个 cold、至少 1 个 warm-up、20 个 warm measured runs；不得复用旧 artifact。
- requested/effective provider 均为 `deepseek`，requested/effective embedding backend 均为 `bge_m3`，
  model、retrieval mode、环境、Git revision 和固定 `input_sha256` 均非空并进入 trust gate。
- 每个 measured run 都来自真实 `run_item()`，并在同一 Trace 内校验 required spans；任何失败/不完整
  样本保留在 artifact 并阻止 `candidate_allowed`，不得被过滤。
- 报告包含 cold 观察、warm samples/P50/P95/min/max、逐 run predicted parallel E2E、理论 P95 改善、
  usage/cost、error distribution、independence findings 和 closed reason list。
- **Candidate-allowed path**：全部 trust、Trace、independence/safety 条件成立，20 个 measured runs 完整且
  `theoretical_p95_improvement_pct >= 20.0`；Report Back 明确只允许 TASK-31.3 开始。
- **No-go path**：环境可测但任一 trust 以外的门禁失败；artifact 明确 `gate_decision=no_go`、具体原因和
  runtime 仍串行；Report Back 禁止 TASK-31.3–31.4。
- **Environment-gap path**：凭据、网络、provider/model/backend 等无法完成可信测量；写出全新 gap
  artifact，命令真实返回非零；Report Back 禁止 TASK-31.3–31.4，且不评价优化收益。
- JSON 为机器事实源，Markdown 与 JSON 同次生成且指标一致；两者均不包含 spec 禁止的敏感内容。
- 不修改任何代码、测试、输入、规划文件或既有报告。

### Verification Commands

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

jq '{stage, artifact_role, git_revision, input_sha256, provider, rag, run_plan, trust, trace, theory, independence, reliability, decision}' \
  reports/performance_cost_benchmark_stage31_baseline.json
```

若真实命令返回非零，仍检查新生成的 JSON/Markdown 并如实 Report Back；不得手工修改 artifact 或用旧
文件替代。

### Report Back Requirements

- Changed Files
- Exact Commands and Exit Codes
- Environment：OS/CPU/Python、provider/model/backend/mode；不得记录凭据
- Input/Artifact Identity：input hash、Git revision、artifact hash
- Run/Trace Completeness：cold/warmup/measured/complete 数量与失败分布
- Latency/Theory：actual/predicted warm P95 与理论改善百分比
- Usage/Cost/Reliability Summary
- Independence Gate：五类 closed findings
- Gate Decision：`candidate_allowed | no_go | environment_gap` 与全部原因
- Deviations From Spec
- Risks/Follow-up
- Commit：仅在产生可审查的新 baseline/gap artifact 时创建，body 包含 `Refs: TASK-31.2`

---

## TASK-31.3 — 条件式实现目标路径最小并发候选

**Status**: pending (conditional: TASK-31.2=`candidate_allowed` only)
**Spec Ref**: `Phase B — Conditional candidate`、`Conditional Runtime Contract`、
`Tenant and context isolation`
**ADR Ref**: `ADR-31.1` Decision 4

### Goal

仅在 TASK-31.2 的 accepted baseline artifact 明确为 `candidate_allowed` 时，使用 Python 标准库的有界
线程能力并行目标 `BE-R004` 冲正路径的 Extraction 与 `search_rules`。父执行流继续独占状态合并、日志、
Trace、SSE 和 Audit；本 task 不运行真实 after 或决定候选是否保留。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/services/workflow.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_workflow_fallback.py`
- Modify: `tests/test_trace_workflow.py`

### Do Not Touch

- `scripts/`、`reports/`、`data/`、`rules/`
- `src/bank_reconciliation_agent/services/trace.py`
- `src/bank_reconciliation_agent/services/tool_executor.py`
- `src/bank_reconciliation_agent/services/tool_adapters.py`
- provider、retriever、Agent 实现、schemas、API、数据库和 frontend
- 其他 tests、spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- TASK-31.2 不是 `candidate_allowed` 时的任何 runtime 变更。
- 并行其他 branch、TraceAgent、AuditAgent、Fallback、多笔 item 或整个 reconciliation job。
- 新依赖、全局线程池服务、进程池、队列、LangGraph 迁移或公共 feature flag。
- 改变 timeout/retry/breaker、LLM cache/repair、RAG no-evidence、hard constraints 或调用权限。

### Acceptance Criteria

- 开始前核验 baseline artifact identity、trust、complete count、理论收益和 decision；任一不满足立即停止。
- 并发只命中 `exception_branch=BE-R004` 且现有 reversal predicate 为 true 的路径；其他 branch、无冲正
  hint 路径及调用顺序保持原行为。
- 两个 worker 只接收显式只读输入并返回分支结果；不得直接修改 `ReconciliationState`、Trace recorder、
  emitter、数据库、Agent/Tool log 或共享 contextvars。
- 父执行流完成 Pydantic validation、稳定 state merge、Agent/Tool log、canonical Trace/SSE 投影和 Audit；
  Audit 只在两侧均成功且投影完成后执行。
- 双成功路径的业务 decision、RAG evidence/response、agent/tool usage 与逻辑调用数量和串行 baseline 等价；
  测试使用 barrier/event 等同步证据证明发生 overlap，不以脆弱 sleep 时序作为唯一断言。
- Extraction failed、RAG EMPTY/FAILED、timeout、cancellation 任一情况都 fail closed，不使用另一侧部分
  结果继续自动判断，也不产生 Audit 自动决定。
- worker 内同步调用有界；`run_item()` 返回或抛出前所有线程已完成或安全终止，不留下后台状态写入、
  跨 flow tenant/Trace context 泄露或未回收 executor。
- Trace 继续满足单 root/terminal、连续 sequence、合法 parent、完整 batch；并行 duration 可重叠但时间
  真实，日志和 SSE 由父线程按稳定顺序投影。
- 公共 `run_item()`、`ReconciliationState`、HTTP、Agent、Tool、RAG、SSE、数据库 contract 和依赖不变。
- 测试覆盖双成功、双侧主要失败、timeout/cancellation/resource cleanup、非目标零回归、Trace/SSE/log
  owner 和跨 flow/context isolation。

### Verification Commands

```bash
uv run pytest tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py -q

uv run ruff check src/bank_reconciliation_agent/services/workflow.py \
  tests/test_workflow.py tests/test_workflow_fallback.py tests/test_trace_workflow.py

uv run ruff format --check src/bank_reconciliation_agent/services/workflow.py \
  tests/test_workflow.py tests/test_workflow_fallback.py tests/test_trace_workflow.py
```

### Report Back Requirements

- Changed Files
- Baseline Gate Proof：artifact path/hash、decision 与进入本 task 的依据
- Target Predicate and Concurrency Boundary
- Parent-owned Merge/Projection Summary
- Failure/Timeout/Cancellation/Resource-cleanup Semantics
- Behavior/Trace/SSE/Usage Equivalence Evidence
- Tests Run：逐条命令、退出码和真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-31.3`

---

## TASK-31.4 — 条件式生成 after/comparison 并执行保留或回滚

**Status**: pending (conditional: TASK-31.2=`candidate_allowed` only)
**Spec Ref**: `Phase B — Conditional candidate`、`Comparison and Retention Gate`
**ADR Ref**: `ADR-31.1` Decision 5

### Goal

仅在 TASK-31.3 candidate commit 上，以和 baseline 完全相同的真实环境、输入和 run plan 生成 after，
运行 focused/Stage gates，再由 comparison 给出唯一 `optimization_accepted | optimization_rejected`。
任一 retention gate 失败时回滚 runtime candidate，只保留 benchmark/test contract 和诚实失败证据。

### Files to Modify

- Create: `reports/performance_cost_benchmark_stage31_after.json`
- Create: `reports/performance_cost_benchmark_stage31_after.md`
- Create: `reports/performance_cost_benchmark_stage31_comparison.json`
- Create: `reports/performance_cost_benchmark_stage31_comparison.md`
- Conditional rollback only when any retention gate fails:
  - Modify: `src/bank_reconciliation_agent/services/workflow.py`
  - Modify: `tests/test_workflow.py`
  - Modify: `tests/test_workflow_fallback.py`
  - Modify: `tests/test_trace_workflow.py`

### Do Not Touch

- `scripts/bench_agent_latency.py` 和 `tests/test_bench_agent_latency.py`
- baseline reports
- `src/bank_reconciliation_agent/services/trace.py`、Tool/Agent/provider/retriever、schemas、API 和数据库
- `data/`、`rules/`、frontend
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- TASK-31.2 不是 `candidate_allowed` 时生成 after 或修改 runtime。
- 修改输入、阈值、run 数、provider/model/backend/mode，或重跑一个新候选追逐指标。
- 用 Fake/hash/fallback、旧 after、手工 JSON 或理论收益替代真实 after。
- 在 comparison 之外手工改写 verdict，或因 reject 恢复/设计第二种并发方案。

### Acceptance Criteria

- after 在 TASK-31.3 candidate revision 上完整运行，且与 baseline 的 input hash、provider/model、backend/
  mode、环境关键字段、cold/warmup/measured 数量和 percentile 算法一致。
- before/after 均 trusted、artifact role 正确、Git revision 非空且不同、complete warm count 均不少于 20，
  无 fallback、静默删样本或敏感信息。
- 在生成最终 comparison 前真实运行 focused tests、全量 pytest、Ruff check 和 Ruff format check；只有
  相应命令满足 spec 才能传入 `--focused-gates-passed`、`--stage-gates-passed`。
- comparison 自动列出 actual warm P95、token/cost、error rate/distribution、逻辑 Agent/Tool 调用数量、
  业务/RAG/Trace 等价 gate 与 closed reason list。
- **Optimization accepted**：actual warm P95 改善 `>=20.0%`，focused/Stage gates 满足，业务与 Trace
  无回归，调用数不增加，per-success token/cost `<=105%` baseline，error rate 增幅 `<=5` 个百分点；
  保留 candidate。
- **Optimization rejected**：任一 gate 不成立；comparison `success=false` 并列原因，撤销 TASK-31.3 的
  runtime/test candidate 变化，保留 TASK-31.1 contract、after/comparison 和 Git 历史。
- trust 不成立或真实环境在 after 阶段失效时同样 fail closed 为 `optimization_rejected`，不得保留 candidate
  或宣称实测优化成功；environment failure 作为 reason 明确记录。
- 回滚后目标路径恢复串行，公共行为与 baseline 一致；candidate revision 仍可由 after/comparison 追溯。

### Verification Commands

```bash
uv run python -m scripts.bench_agent_latency \
  --scenario stage31-critical-path \
  --provider deepseek \
  --embedding-backend bge_m3 \
  --cold-runs 1 \
  --warmup-runs 1 \
  --runs 20 \
  --report reports/performance_cost_benchmark_stage31_after.md \
  --json-report reports/performance_cost_benchmark_stage31_after.json

uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py -q

uv run pytest
uv run ruff check .
uv run ruff format --check .

uv run python -m scripts.bench_agent_latency \
  --scenario stage31-comparison \
  --baseline-json reports/performance_cost_benchmark_stage31_baseline.json \
  --after-json reports/performance_cost_benchmark_stage31_after.json \
  --focused-gates-passed \
  --stage-gates-passed \
  --report reports/performance_cost_benchmark_stage31_comparison.md \
  --json-report reports/performance_cost_benchmark_stage31_comparison.json

jq '{trust, success, outcome, failure_reasons, latency, usage, cost, reliability, contract_gates}' \
  reports/performance_cost_benchmark_stage31_comparison.json
```

若任一 focused/Stage gate 未满足，不得传入对应 passed flag；comparison 必须输出 reject。完成 verdict 所需
的保留或回滚后，重新运行与最终代码树相关的 focused tests 和 Ruff changed-path gate。

### Report Back Requirements

- Changed Files
- Candidate Revision and Artifact Hashes
- Exact Benchmark/Test/Lint Commands and Exit Codes
- Baseline/After Trust and Comparability Gate
- Actual P95、Usage/Cost、Reliability、Call-count and Contract Deltas
- Verdict：`optimization_accepted | optimization_rejected`
- Rollback Summary：如适用，列出所有移除/恢复内容并证明串行 baseline behavior
- Tests Run After Final Retain/Rollback State
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-31.4`

---

## TASK-31.5 — 运行 Stage/PR 全量门禁并记录 verification

**Status**: pending
**Spec Ref**: `Phase C — Stage verification`、全部 `Acceptance Criteria`
**ADR Ref**: `ADR-31.1`

### Goal

对最终代码树运行 Stage/PR 全量验证，并把真实命令结果、最终 outcome、artifact identity 和 gate 明细
写入正式 `verification.md`。本 task 不修复实现或改变 benchmark verdict；失败必须交回 Codex review。

### Files to Modify

- Create: `docs/stages/stage-31-trace-guided-performance/verification.md`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`reports/`、`data/`、`rules/`、frontend
- spec、tasks、ADR、README、架构/PRD 和其他项目级文档

### Out of Scope

- 修复测试、修改测量、调整阈值、恢复 rejected candidate 或开始新实验。
- 修改 task 状态、把未运行/失败命令标为 passed，或补写不存在的真实数字。
- commit 以外的 push、PR、merge 或 Stage closeout。

### Acceptance Criteria

- `verification.md` 记录 branch、HEAD、日期、环境和唯一最终 outcome：`no_go | environment_gap |
  optimization_accepted | optimization_rejected`。
- 记录所有已执行 task、跳过的 conditional task 及原因；`no_go/environment_gap` 明确证明没有 runtime
  candidate 被保留。
- 记录 baseline 和可选 after/comparison 路径、artifact hash、Git revision、input hash、trust、run/Trace
  completeness 和关键 gate 值；不从 Markdown 手工重算指标。
- focused suite、全量 pytest、`ruff check`、`ruff format --check`、diff/scope/hygiene 命令均真实运行并记录
  完整命令、退出码和 passed/failed。
- inherited format baseline 若存在，记录 baseline 证据并证明 Stage 31 未新增 regression；不得隐藏真实
  `ruff format --check .` 退出码。
- `git diff --stat main...HEAD` 与 Stage 31 范围一致，`git status --short` 无意外文件；规划、实现、报告和
  verification 的 tracked 状态符合 AGENTS.md。
- 检查没有密钥、`.env`、prompt/model output、业务数据、cache、模型文件、Chroma 本地数据、构建产物
  或大文件进入提交。
- 任一 required gate 失败时 verification 明确失败，Stage 不得标记完成。
- 不修改实现、报告、accepted spec/ADR 或 tasks 状态。

### Verification Commands

```bash
uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py -q

uv run pytest
uv run ruff check .
uv run ruff format --check .
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

### Report Back Requirements

- Changed Files
- Final Stage Outcome
- Full Gate Results：逐条命令、退出码和 passed/failed
- Conditional Task Summary：executed/skipped 及原因
- Artifact Identity and Metrics Summary
- Scope/Secret/Large-file Check
- Deviations From Spec
- Risks/Follow-up
- Commit：`docs: record stage 31 verification`，body 包含 `Refs: TASK-31.5`
