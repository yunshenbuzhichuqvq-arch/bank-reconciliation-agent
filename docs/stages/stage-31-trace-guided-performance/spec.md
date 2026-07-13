# Stage 31 Spec: Trace 驱动的测量门禁与条件式关键路径优化

**Stage**: `stage-31-trace-guided-performance`
**Branch**: `stage-31-trace-guided-performance`
**Status**: accepted
**Date**: 2026-07-13

## Stage Goal

以真实 DeepSeek、真实 bge_m3、同一次 `BE-R004` flow 的 canonical Trace 建立 cold/warm 关键路径
baseline，并用可复现、fail-closed 的门禁决定是否值得并行 `ExtractionAgent` 与 `search_rules`。

本 Stage 的首要交付是可信决策，不是并行代码：

- 若理论 warm 端到端 P95 收益不足 20%、Trace 不完整或独立性/副作用证明失败，输出 `no_go` 并保持
  运行时串行。
- 若真实环境不可用，输出 `environment_gap`，不得进入候选实现。
- 只有 baseline 输出 `candidate_allowed` 时，才实现一个只覆盖目标路径的最小并行候选。
- 候选只有在实测 warm P95 改善达到 20%，且安全、质量、成本和错误率门禁无回归时才保留；否则
  回滚候选并输出 `optimization_rejected`。

## Builds On

- `decisions/ADR-032-agent-parallel-defer-serial-by-latency.md`：当前保持串行的权威决策。
- `decisions/ADR-17.4-performance-cost-offline-benchmark-evidence.md`：offline benchmark 与非生产 SLA
  边界。
- `decisions/ADR-23.1-real-provider-performance-cost-evidence.md`：真实 DeepSeek evidence trust contract。
- `decisions/ADR-23.2-provider-usage-cost-accounting.md`：provider token 与估算成本口径。
- Stage 29：canonical `TraceSpan`、flow-scoped recorder、Tool/Agent 安全投影和 Trace 结构不变量。
- Stage 30：指标门禁、before/after/comparison、失败回滚和诚实失败报告模式。

## Architecture Impact

**Architecture Impact**: Yes
**ADR Required**: Yes
**ADR**: `decisions/ADR-31.1-measurement-gated-critical-path-concurrency.md` (`accepted`)

该 ADR 冻结：

- 用户覆盖原“分支创建前门禁”，但不预先批准 runtime 并行。
- baseline gate、理论收益公式、独立性证明和三类 baseline 结果。
- 达标后候选的边界、失败语义与保留/回滚门禁。

在 ADR 被用户接受前不得拆分实现 tasks；若 ADR 决策变化，必须先同步本 spec。

## Outcome State Machine

以下 token 仅用于 Stage 31 报告，不是业务 API 或数据库状态：

```text
BASELINE_PENDING
  ├─ environment unavailable ─────────────→ ENVIRONMENT_GAP
  ├─ trust/independence/20% gate failed ──→ NO_GO
  └─ all baseline gates passed ───────────→ CANDIDATE_ALLOWED
                                               ├─ retention gates passed
                                               │    → OPTIMIZATION_ACCEPTED
                                               └─ any retention gate failed
                                                    → OPTIMIZATION_REJECTED
```

`NO_GO`、`ENVIRONMENT_GAP` 和 `OPTIMIZATION_REJECTED` 都禁止保留未经门禁接受的 runtime 并行。

## In Scope

### Phase A — Baseline contract and decision gate

1. 扩展 `scripts/bench_agent_latency.py`，增加 Stage 31 端到端 Trace benchmark mode；保留现有 Stage 23
   CLI 和报告兼容行为。
2. 固定一个真实进入 `ExtractionAgent` 与 `search_rules` 的 `BANK_ENTERPRISE / BE-R004` 冲正输入。
3. 使用真实 `run_item()`、canonical `TraceRecorder`、真实 DeepSeek 和 bge_m3 运行 cold/warm 测量。
4. 报告同一 Trace 的端到端、Extraction 和 RAG duration，以及理论并行端到端值。
5. 显式审查数据依赖、共享写、副作用、失败顺序、取消/超时和资源回收可行性。
6. 生成 baseline JSON + Markdown，并输出唯一 gate decision：
   `candidate_allowed | no_go | environment_gap`。

### Phase B — Conditional candidate

只有 Phase A 为 `candidate_allowed` 时才进入：

1. 只并行 `BE-R004` 冲正类路径中的 Extraction 与 `search_rules`。
2. 使用标准库有界线程适配同步 provider/retriever，不引入新依赖或 LangGraph 主图迁移。
3. 父执行流保持状态合并、Agent/Tool 日志、Trace、SSE 和最终业务决定的唯一所有权。
4. 覆盖双方成功、Extraction 失败、RAG EMPTY/FAILED、超时、取消请求和资源回收。
5. 用相同环境和输入生成 after 与 comparison。
6. 根据 retention gate 保留候选，或撤销 runtime 变化并保留失败证据。

### Phase C — Stage verification

1. 记录最终 outcome、实际命令、环境、artifact hash 和 gate 明细。
2. 运行 focused tests、全量 pytest、Ruff check 和 Ruff format check。
3. 将结果写入 `docs/stages/stage-31-trace-guided-performance/verification.md`。

## Out of Scope

- 并行其他 exception branch、AuditAgent、TraceAgent、Fallback L2/L3 或多笔 flow。
- LangGraph 主图迁移、`Send`、分布式 worker、任务级 fan-out 或批量并行。
- 新增线程池服务、进程池、队列、Redis channel、GPU 服务或并发依赖。
- 改变 HTTP API、Tool schema、Agent schema、RAG request/response、SSE 公共 schema或数据库表。
- 修改金额计算、异常分类、Audit hard constraints、RAG threshold、prompt、模型参数或 eval labels。
- 优化或隐藏首次模型下载/加载；cold 数据只观察，不进入 warm 收益门禁。
- 生产压测、生产 SLA、容量、并发用户数或线上成本声明。
- 因 Stage 30 实验失败而继续修改 query、chunk、embedding、reranker 或 RAG 质量逻辑。
- repo-wide Ruff format 治理和无关重构。

## Inputs and Outputs

### Fixed benchmark input

Stage 31 使用单一、版本化的固定输入，至少满足：

- `scenario_type=BANK_ENTERPRISE`
- `exception_branch=BE-R004`
- `error_type=NARRATIVE_NAME_MISMATCH`
- 摘要或备注包含现有 `REVERSAL_HINTS` 中的词，使 `ExtractionAgent` 确实执行。
- 固定 Decimal-compatible 金额字符串；金额只作为现有 RAG query 输入，不参与 benchmark 计算。
- 输入序列化后生成非空 `input_sha256`；baseline 与 after 必须一致。

不得使用 eval case ID、预期 chunk ID 或针对单条规则答案的硬编码 query。

### Required artifacts

- `reports/performance_cost_benchmark_stage31_baseline.json`
- `reports/performance_cost_benchmark_stage31_baseline.md`
- 仅当进入候选时：
  - `reports/performance_cost_benchmark_stage31_after.json`
  - `reports/performance_cost_benchmark_stage31_after.md`
  - `reports/performance_cost_benchmark_stage31_comparison.json`
  - `reports/performance_cost_benchmark_stage31_comparison.md`
- `docs/stages/stage-31-trace-guided-performance/verification.md`

JSON 是机器事实源；Markdown 必须从同次 JSON 数据生成，不得手工重算或修改指标。

## Benchmark CLI Contract

保留现有 Stage 23 CLI。新增 Stage 31 mode 的目标调用形式：

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

`--runs` 在 Stage 31 mode 中只表示计入统计的 warm measured runs，不包含 cold 或 warm-up。

若进入候选，after 使用相同参数，仅替换输出路径。comparison 继续由同一脚本读取 baseline/after
JSON 生成，不新建第二套指标实现；具体参数名由 tasks 冻结。

### CLI failure behavior

- 缺少 DeepSeek key、provider/network/model/backend 不可用：写出 `environment_gap` artifact，命令返回
  非零；不得沿用旧 baseline。
- requested/effective provider 或 embedding 不一致：`environment_gap`，禁止 candidate。
- JSON/Markdown 写入失败、输入非法或 report schema validation 失败：命令返回非零，不得输出
  `candidate_allowed`。
- `no_go` 是成功完成测量后的业务 gate 结果；命令可返回 0，但 artifact 必须明确
  `gate_decision=no_go`。

## Baseline JSON Contract

Baseline 至少包含以下稳定字段：

| Section | Required fields |
| --- | --- |
| Identity | `schema_version`, `stage`, `artifact_role=baseline`, `evaluated_at`, `git_revision`, `input_sha256` |
| Environment | OS、architecture、Python、CPU、boundary=`offline benchmark; not production SLA` |
| Provider | requested/effective provider、requested/effective model |
| RAG | requested/effective embedding backend、retrieval mode |
| Run plan | cold/warmup/measured counts、complete measured count |
| Trust | `trusted`, closed `reasons`, `environment_gap` |
| Trace | completeness numerator/denominator/rate、每个 run 的 `trace_id` 与 required span counts |
| Latency | cold observations；warm end-to-end/Extraction/RAG 的 samples、P50、P95、min、max |
| Theory | per-run predicted parallel E2E、predicted P95、`theoretical_p95_improvement_pct` |
| Independence | data dependency、shared state/write、failure-order、cancellation/timeout/resource findings |
| Usage | provider call count、input/output/total tokens、per-successful-run tokens |
| Cost | assumptions、total/per-successful-run estimated USD 或明确 unavailable reason |
| Reliability | success/failure counts、error rate、stable error distribution |
| Decision | `candidate_allowed | no_go | environment_gap` 与 closed reason list |

自由异常文本、prompt、模型输出、RAG query、金额、规则正文、Tool args/result、traceback、key 和连接信息
不得进入报告。

## Measurement and Gate Semantics

### Cold/warm separation

- cold probe 单独报告，至少包含端到端和 RAG 首次调用耗时。
- warm-up 不进入任何 percentile 或 gate。
- warm gate 至少使用 20 个完整 measured runs。
- percentile 算法固定并由单元测试覆盖；baseline 与 after 必须使用同一算法。

### Trace sample eligibility

一个 warm sample 只有同时满足以下条件才是 complete：

- 恰好一个完整 `WORKFLOW` root 和一个 canonical terminal span。
- 恰好一个 `AGENT(name=ExtractionAgent)`。
- 恰好一个 `TOOL(name=search_rules)`。
- required spans 的时间、status、parent、sequence 和 duration 满足 Stage 29 schema/invariants。
- provider/tool 最终成功，且没有使用 fallback backend。

baseline decision 要求 `complete_count == measured_run_count >= 20`。不得静默丢弃慢样本、失败样本或
outlier 后继续计算 gate。

### Theoretical gate

每个 complete warm run 使用 ADR-31.1 的公式计算 predicted parallel E2E；再从两组同 run samples
计算 P95 和理论收益。只有 `theoretical_p95_improvement_pct >= 20.0` 才满足性能入口。

### Independence gate

报告必须分别给出并验证：

1. RAG query 不读取 `extraction_result`，Audit 只在两侧完成后运行。
2. worker 是否会修改共享 state、Trace、SSE、数据库、breaker、attempt log 或 Agent usage state。
3. Extraction 失败时 speculative RAG 与当前串行“RAG 不执行”的差异能否安全收口。
4. 同步 provider/retriever 的超时、取消和线程退出是否有界、可测试且不会留下后台副作用。

任何一项为 unknown、unsafe 或 unbounded，decision 必须为 `no_go`。

## Conditional Runtime Contract

本节只有 baseline 为 `candidate_allowed` 时生效。

- 公共 `run_item()` 签名和 `ReconciliationState` schema 不变。
- 只改变符合固定 predicate 的 `BE-R004` 冲正路径；其他路径调用次数和顺序不变。
- 两个 worker 只返回分支结果；父执行流负责 Pydantic validation、state merge、Agent/Tool log、Trace、
  SSE 和 Audit 调用。
- AuditAgent 必须在 Extraction 和 RAG 均成功并完成 canonical projection 后运行。
- RAG EMPTY/FAILED、Extraction failed、timeout/cancellation 任一情况都不得产生自动判断；按现有 contract
  转 `PENDING_HUMAN` 或传播现有受控异常。
- 不改变 Tool timeout/retry/breaker、LLM retry/repair/cache、RAG no-evidence 和 hard constraint 语义。
- Trace 仍满足单 root、单 terminal、连续 sequence、合法 parent 和完整 batch；并行 duration 可以重叠，
  但不得伪造 start/end 或把等待时间重复计入两个 spans。
- SSE 和 Agent/Tool 日志不得从 worker 并发写入；父执行流按稳定 canonical 顺序投影。
- 所有线程在 `run_item()` 返回或抛出前完成或被证明安全终止，不得跨 flow 泄露 context。

## Comparison and Retention Gate

comparison 必须先验证：

- baseline/after 均 trusted，且 artifact role 正确。
- input hash、provider/model、embedding backend/mode、run plan、环境关键字段一致。
- 两侧 complete warm count 均不少于 20，且无静默删样本。
- before/after Git revision 非空且不同；candidate revision 可追溯。

只有以下全部成立，输出 `optimization_accepted`：

1. `actual_warm_p95_improvement_pct >= 20.0`。
2. focused success/failure/concurrency tests 通过。
3. 全量 pytest 与 Ruff gate 按本 Stage verification 如实记录，无 Stage 31 新增回归。
4. 业务决定、evidence IDs、RAG response、Fallback、安全 hard constraints 和 Trace invariants 无回归。
5. successful path 的逻辑 Agent/Tool 调用数量不增加。
6. per-successful-run token 与 estimated cost 不超过 baseline 的 105%。
7. after error rate 不超过 baseline 5 个百分点，且 error distribution 无新增未知 token。

任一项失败时输出 `optimization_rejected`，撤销 `workflow.py`、`trace.py` 等 runtime candidate；保留
benchmark/report/test contract 和全部 evidence。comparison 必须 `success=false` 并列出失败原因。

## Data Model and Public Contract Impact

- 数据库 schema：None。
- HTTP API：None。
- Pydantic public response：None。
- Tool name/args/result：None。
- Agent prompt/output schema：None。
- SSE schema/version：None。
- 新依赖：None。

若实现发现必须改变任一项，停止并回到 ADR/spec 修订，不得在 task 内自行扩大范围。

## Cross-cutting Requirements

### Business safety

- 金额继续使用 `Decimal` 和确定性代码；benchmark 不把金额交给 LLM 计算。
- RAG 无命中不得产生 evidence 或自动判断。
- candidate 不扩大 Agent 工具权限、自动平账范围或异常分支范围。

### Tenant and context isolation

- 固定 benchmark 使用明确测试 `user_id/task_id/flow_id`，不得读取其他用户业务数据。
- 并发 worker 不得依赖 contextvars 隐式传播 tenant/Trace；必要上下文必须显式、只读传入。
- 任一 context 丢失或错配必须 fail closed，且测试覆盖跨 flow/context 泄露。

### Observability truth

- Trace duration 使用 monotonic clock；wall clock 只用于 UTC timestamp。
- 理论收益、实测收益、cold、warm 和环境缺口必须分开。
- Fake provider/hash 只用于确定性 contract tests，不能通过真实性能 gate。

## Acceptance Criteria

### Planning gate

- [x] ADR-31.1 被用户接受，且本 spec 的 outcome、范围、错误语义和阈值被确认。
- [x] 之后才创建 `tasks.md`，每个 task 保持单一目标和独立 gate。

### Baseline path

- [ ] Stage 23 legacy CLI 行为保持兼容并有回归测试。
- [ ] Stage 31 JSON/Markdown schema、validation、cold/warm 分离和 percentile 算法有确定性测试。
- [ ] 真实命令从固定 `BE-R004` flow 生成新 baseline，不复用旧 Stage 23 报告。
- [ ] baseline 记录不少于 20 个完整 warm runs、同 Trace required spans 和全部 trust metadata。
- [ ] independence gate 覆盖数据依赖、共享副作用、失败顺序、取消/超时和资源回收。
- [ ] gate decision 严格为 `candidate_allowed | no_go | environment_gap` 之一。

### Valid no-candidate completion

- [ ] `no_go` 或 `environment_gap` 时没有任何 runtime workflow/trace candidate 被保留。
- [ ] `verification.md` 明确区分 measured no-go 与 environment gap，不宣称性能成功。
- [ ] baseline artifact、测试和规划文件保留，可由后续审查复算同一结论。

### Conditional candidate path

- [ ] 只有 `candidate_allowed` 才修改 runtime critical path。
- [ ] 只覆盖目标 `BE-R004` predicate；其他路径顺序和行为保持不变。
- [ ] 双成功、单侧失败、RAG EMPTY/FAILED、timeout、cancellation 和资源回收测试通过。
- [ ] state、日志、Trace 和 SSE 只由父执行流合并/投影，无跨 flow context 泄露。
- [ ] after/comparison 与 baseline 使用相同输入、环境和 run plan。
- [ ] comparison 自动计算 actual warm P95、token/cost、error 和全部 retention gates。
- [ ] 未通过任一 retention gate 时 runtime candidate 已回滚，报告保留 `success=false`。

### Stage/PR gate

- [ ] `uv run pytest` 真实运行并通过，或任何失败被如实记录且 Stage 不标记通过。
- [ ] `uv run ruff check .` 真实运行并通过。
- [ ] `uv run ruff format --check .` 真实运行；若存在 inherited baseline，必须证明 Stage 31 未新增
  format regression，不得隐藏退出码。
- [ ] `git diff --check` 通过，diff 只包含 Stage 31 允许文件。
- [ ] 无密钥、prompt/model output、业务数据、cache、模型文件或构建产物进入提交。

## Verification Strategy

任务级命令在用户确认本 spec 后由 `tasks.md` 按实际文件范围细化。Stage gate 至少包含：

```bash
uv run pytest tests/test_bench_agent_latency.py \
  tests/test_workflow.py \
  tests/test_workflow_fallback.py \
  tests/test_trace_workflow.py \
  tests/test_trace_recorder.py -q

uv run pytest
uv run ruff check .
uv run ruff format --check .
git diff --check
```

真实 DeepSeek/bge_m3 benchmark 是 manual diagnostic gate，不进入默认 CI。CI 使用 Fake/hash 验证 CLI、
schema、公式、decision、comparison 和 failure handling，但不能把 Fake/hash 结果标为
`candidate_allowed`。

## Risks and Open Questions

### Risks

- 真实 provider/network 波动可能导致 `environment_gap` 或让 20 个本地样本仍有较大噪声。
- 首次 bge_m3 初始化可能显著抬高 cold 数据；它必须被隔离，不能成为并行收益。
- Extraction 失败时 speculative RAG 会偏离当前串行调用语义；若无法无副作用收口，independence gate
  应直接 no-go。
- Python 线程不能强制终止已进入的同步网络/检索调用；若现有 timeout contract 不足以有界回收，
  candidate 不得实现。
- Stage 29 recorder 当前按单线程顺序设计；不得为了候选把共享 recorder 直接暴露给 worker。

### Open Questions

None for planning。用户已决定覆盖原 pre-branch gate，并已确认 ADR/spec 后进入 task 执行阶段。
