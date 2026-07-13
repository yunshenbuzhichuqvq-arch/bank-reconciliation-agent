# Stage 30 Tasks: RAG 弱桶单变量 query enrichment

- **Stage**: `stage-30-rag-query-optimization`
- **Branch**: `stage-30-rag-query-optimization`
- **Spec**: `docs/stages/stage-30-rag-query-optimization/spec.md`
- **ADR**: `decisions/ADR-30.1-metric-gated-branch-aware-query-enrichment.md`
- **Status**: planned
- **Date**: 2026-07-13

## Execution Rules

- opencode 每次只执行一个 task；开始前阅读 `AGENTS.md`、accepted spec、accepted ADR 和当前 task。
- 规划文件必须由用户先单独提交。opencode 不修改或混入提交：本文件、spec、ADR、其他规划文档。
- 每个实现 task 先增加能证明当前缺口的失败测试，再做最小实现并运行指定门禁。
- `Files to Modify` 是当前 task 的完整允许边界；需要扩大时停止并报告，由 Codex 修订 task。
- 不修改 eval set、labels、raw knowledge、chunk、embedding、mode、top-k、threshold、fusion 或 reranker。
- 不扩展 `RagSearchRequest`、HTTP API、Tool Executor、retriever、数据库、权限或 Trace contract。
- 不新增依赖，不建立 feature-flag framework、通用 query DSL 或第三轮调参流程。
- Task 完成后检查 `git diff`，创建只引用当前 task 的 Conventional Commit；不得 push 或 merge。
- opencode 不自行修改 task 状态。Codex review 通过后再由 Codex 更新本文件。
- 任何测试、baseline 或 after 命令未运行或失败，必须按真实状态 Report Back，不得标记完成。

## Dependency Order

```text
TASK-30.1 Evidence/trust contract
  → TASK-30.2 Freeze bge_m3/dense baseline
      ├─ baseline trusted
      │   → TASK-30.3 Query enrichment helper/profile
      │     → TASK-30.4 Runtime/eval integration
      │       → TASK-30.5 After evaluation and verdict enforcement
      │         → TASK-30.6 Stage verification
      └─ environment gap
          → skip TASK-30.3–30.5
          → TASK-30.6 Stage verification
```

TASK-30.2 是硬入口门禁。只有其 baseline 为可信 `bge_m3/dense`，TASK-30.3 才能开始。
如果 TASK-30.2 得到 environment gap，停止 candidate 工作，由 Codex 将 TASK-30.3–30.5 标记为
`out-of-scope`，然后只执行 TASK-30.6。

---

## TASK-30.1 — 加固 matrix 与 comparison 的可信证据 contract

**Status**: ready
**Spec Ref**: `Matrix Artifact`、`Comparison Artifact`、`Trust and Reporting`
**ADR Ref**: `ADR-30.1` Decision 7–10

### Goal

在不改变任何检索结果的前提下，为 Stage 30 matrix 增加可复现 metadata，并让 comparison 对新格式
artifact 的 hash/backend/mode/完整 bucket 数据 fail closed；本 task 不生成真实 baseline，不实现 query
enrichment。

### Files to Modify

- Modify: `scripts/eval_rag.py`
- Modify: `tests/test_mvp2b3_eval_rag.py`
- Modify: `tests/test_v1_1_eval_rag_report.py`

### Do Not Touch

- `src/bank_reconciliation_agent/`
- `rules/`
- `data/`
- `reports/`
- `docs/stages/stage-30-rag-query-optimization/`
- 其他 tests、scripts 或项目文档

### Out of Scope

- 加载 query profile、改变 eval query、运行真实 `bge_m3`。
- runtime/eval enrichment、latency 计时或 candidate CLI。
- 删除 Stage 22 的 guarded legacy reader；旧 artifact 仍须按原 metadata gate 兼容。
- 修改成功阈值以外的 RAG 评分公式。

### Acceptance Criteria

- 新 matrix artifact 至少包含稳定 `eval_set_sha256`、`chunk_corpus_sha256`、`git_revision` 和
  `query_enrichment` metadata；默认状态明确为 disabled、profile 为 null/等价空值。
- eval set hash 基于实际读取的 eval set bytes；chunk corpus hash 覆盖实际参与 BANK_ENTERPRISE 与
  BANK_CLEARING 检索的 tracked chunk bytes，并使用稳定文件顺序。
- measured mode 继续输出 mode-specific `bucket_metrics`，原有指标计算不变。
- Stage 30 新格式 comparison 对 case count、top-k、两个 hash、requested/effective backend、status、
  requested mode 和 target bucket 逐项校验；缺失或不一致时 `trust.trusted=false`、`success=false`。
- comparison success 继续要求 target Recall@5 严格上升、miss count 下降、全局 MRR 与 NDCG@5
  各自回退不超过 `0.0200`；新增单独覆盖 MRR 回退的测试。
- comparison JSON 新增全部非目标 bucket 的 before/after/delta；现有 top-3 regression/improvement
  摘要可以保留，但不得作为完整副作用数据的替代。
- Markdown 能直接审查完整副作用数据，或明确链接同次生成 JSON 中的完整字段。
- Stage 22 legacy baseline 的精确 mode compatibility 测试继续通过，不允许无条件 legacy fallback。
- 没有任何检索 query、结果排序或 runtime 行为变化。

### Verification Commands

```bash
uv run pytest tests/test_mvp2b3_eval_rag.py tests/test_v1_1_eval_rag_report.py -q
uv run ruff check scripts/eval_rag.py tests/test_mvp2b3_eval_rag.py tests/test_v1_1_eval_rag_report.py
uv run ruff format --check scripts/eval_rag.py tests/test_mvp2b3_eval_rag.py tests/test_v1_1_eval_rag_report.py
```

### Report Back Requirements

- Changed Files
- Artifact Contract Summary：字段、hash 输入、schema/legacy 区分
- Trust Gate Summary：所有 fail-closed 条件和 success 条件
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.1`

---

## TASK-30.2 — 冻结可信 `bge_m3/dense` Stage 30 baseline

**Status**: pending
**Spec Ref**: `Baseline Entry Gate`、`Determinism and Reproducibility`
**ADR Ref**: `ADR-30.1` Decision 7、10

### Goal

使用 TASK-30.1 的新 evidence contract 对当前代码、固定 eval set 和固定 chunk corpus 生成一次
`bge_m3/dense` baseline，并给出唯一入口结论：`baseline trusted` 或 `environment gap`。本 task 不修改
Python 代码，不实现 candidate。

### Files to Modify

- Create: `reports/rag_quality_matrix_stage30_baseline.md`
- Create: `reports/rag_quality_matrix_stage30_baseline.json`
- Create only on environment gap: `docs/stages/stage-30-rag-query-optimization/verification.md`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`rules/`、`data/`
- `reports/rag_quality_matrix.md`
- `reports/rag_quality_matrix.json`
- `reports/rag_optimization_comparison.md`
- `reports/rag_optimization_comparison.json`
- spec、tasks、ADR 和项目级文档

### Out of Scope

- hash fallback、其他 embedding backend、hybrid/reranker 对比。
- query enrichment、运行时改动或关键词选择。
- 为使 gate 通过而下载之外修改代码、数据、标签或报告。
- 将 environment gap 解释为可信实验失败。

### Acceptance Criteria

- 完整运行 spec 固定的 baseline 命令；不得复用旧报告或手工复制指标。
- 输出记录 requested/effective backend、status、mode、top-k、case count、两个 hash、Git revision 和
  query enrichment disabled 状态。
- `BANK_CLEARING / SINGLE_SIDE_MISSING` 存在一条 case_count=10 的 `dense.bucket_metrics`。
- **Trusted path**：requested/effective backend 均为 `bge_m3`、status=`measured`、mode=`dense`、
  top-k=5、case_count=120、hash 非空；Report Back 明确允许 TASK-30.3 开始。
- **Environment-gap path**：任一入口条件不满足时，保留真实命令输出和可生成的 unavailable report，
  在 `verification.md` 记录 gap；Report Back 明确禁止 TASK-30.3–30.5 开始。
- 不修改任何检索、数据或评测代码。

### Verification Commands

```bash
uv run python -m scripts.eval_rag \
  --matrix-backends bge_m3 \
  --matrix-modes dense \
  --real-backend-policy auto \
  --matrix-report reports/rag_quality_matrix_stage30_baseline.md \
  --matrix-json reports/rag_quality_matrix_stage30_baseline.json

jq -e '
  .case_count == 120 and
  .top_k == 5 and
  (.eval_set_sha256 | type == "string" and length > 0) and
  (.chunk_corpus_sha256 | type == "string" and length > 0) and
  .query_enrichment.enabled == false and
  .rows.bge_m3.requested_backend == "bge_m3" and
  .rows.bge_m3.effective_backend == "bge_m3" and
  .rows.bge_m3.status == "measured" and
  ([.rows.bge_m3.modes.dense.bucket_metrics[] |
    select(.scenario_type == "BANK_CLEARING" and
           .error_type == "SINGLE_SIDE_MISSING" and
           .case_count == 10)] | length == 1)
' reports/rag_quality_matrix_stage30_baseline.json
```

如果第一条命令完成但 `jq` gate 失败，按 environment gap 处理，不得修改 JSON 使其通过。

### Report Back Requirements

- Changed Files
- Exact Commands and Exit Codes
- Environment：OS/CPU、Python、依赖可用性、requested/effective backend；不得记录凭据
- Baseline Gate：逐项值与 `baseline trusted | environment gap`
- Target Baseline Metrics：case count、miss、Hit@1、Recall@5、MRR、NDCG@5
- Deviations From Spec
- Risks/Follow-up
- Commit：只有产生可审查 baseline/gap artifact 时创建，body 包含 `Refs: TASK-30.2`

---

## TASK-30.3 — 实现单一 target query enrichment helper 与 profile

**Status**: pending
**Spec Ref**: `Query Enrichment`、`Query Behavior`
**ADR Ref**: `ADR-30.1` Decision 1–6

### Goal

实现一个无 I/O 副作用的共享确定性 helper 和唯一 target YAML profile，证明 eval taxonomy 与 runtime
taxonomy/branch 能命中同一 enrichment，其他输入严格 identity；本 task 不接入 runtime 或 eval。

### Files to Modify

- Create: `rules/rag_query_terms.yaml`
- Create: `src/bank_reconciliation_agent/rag/query_enrichment.py`
- Create: `tests/test_rag_query_enrichment.py`

### Do Not Touch

- `src/bank_reconciliation_agent/services/`
- `src/bank_reconciliation_agent/schemas/`
- `src/bank_reconciliation_agent/rag/retriever.py`
- `src/bank_reconciliation_agent/rag/query_rewrite.py`
- `scripts/`、`reports/`、`data/`
- 其他 tests、spec、tasks、ADR 和项目级文档

### Out of Scope

- runtime/eval integration、CLI、latency 与真实评测。
- 多 profile、通用 DSL、动态配置、远程配置或 feature flag。
- LLM rewrite、prompt、chunk、embedding、threshold、reranker。

### Acceptance Criteria

- YAML 只有一个稳定 profile identity：`bank-clearing-single-side-missing` 或等价 spec 明确名称。
- profile 只覆盖 `scenario_type=BANK_CLEARING`，并受控识别：
  `SINGLE_SIDE_MISSING`、`CLEARING_SINGLE_SIDE`、`BC-R001`。
- 匹配规则为 scenario 必须匹配，且 error type 或 exception branch 至少一个匹配。
- 命中后只在原 query 后追加规范化、类别级业务词项；不删除、不重写原 query。
- 非目标 scenario、非目标 error/branch、空 alias 全部字节级返回原 query。
- YAML 经过明确 schema validation；重复 profile、空 terms、非法类型等配置错误 fail closed。
- helper 不调用 LLM、网络、数据库、embedding 或 retriever，不引入新依赖。
- profile 不包含 eval case id、expected chunk id、eval query 原句或单 case 答案式硬编码。
- 测试覆盖两个 taxonomy alias、branch-only 命中、scenario gate、identity paths、确定性和非法配置。

### Verification Commands

```bash
uv run pytest tests/test_rag_query_enrichment.py -q
uv run ruff check src/bank_reconciliation_agent/rag/query_enrichment.py tests/test_rag_query_enrichment.py
uv run ruff format --check src/bank_reconciliation_agent/rag/query_enrichment.py tests/test_rag_query_enrichment.py
```

### Report Back Requirements

- Changed Files
- Profile Summary：identity、aliases、terms 来源；不得粘贴 eval case 文本
- Helper Contract Summary：match、identity、validation
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.3`

---

## TASK-30.4 — 将同一 helper 接入 runtime 与 eval candidate 路径

**Status**: pending
**Spec Ref**: `Main Flow` 4–6、`Query Enrichment`、`Matrix Artifact`
**ADR Ref**: `ADR-30.1` Decision 2–7

### Goal

在不改变公共 request/retriever/Tool contract 的前提下，把 TASK-30.3 的同一 helper 显式接入
`ReconciliationService` query construction 和 `scripts.eval_rag` candidate 路径，并为 after artifact
记录 profile identity/hash 与 enrichment latency；本 task 不运行真实 after evaluation。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/services/reconciliation.py`
- Modify: `scripts/eval_rag.py`
- Modify: `tests/test_mvp2b3_eval_rag.py`
- Modify: `tests/test_mvp2a3_clearing_rag.py`
- Modify only if an existing non-target assertion requires it:
  `tests/test_mvp2a2_workflow_integration.py`

### Do Not Touch

- `src/bank_reconciliation_agent/schemas/rag.py`
- `src/bank_reconciliation_agent/rag/retriever.py`
- `src/bank_reconciliation_agent/rag/query_rewrite.py`
- `src/bank_reconciliation_agent/services/workflow.py`
- `src/bank_reconciliation_agent/services/tool_executor.py`
- `src/bank_reconciliation_agent/services/rule_engine.py`
- `rules/rag_query_terms.yaml`
- `data/`、`reports/`、frontend、数据库 schema
- spec、tasks、ADR 和项目级文档

### Out of Scope

- 修改 helper/profile 以追逐指标。
- 运行真实 `bge_m3` after 或决定 candidate 成败。
- 修改现有 query prefix、金额字段、route result、Audit/Fallback/Trace 行为。
- 默认 CI 中启用真实 embedding。

### Acceptance Criteria

- eval CLI 提供单一显式 opt-in：
  `--query-enrichment-profile bank-clearing-single-side-missing`；不传时保持 baseline disabled 行为。
- eval candidate 在构造 `RagSearchRequest` 前调用 shared helper，并使用 `EvalCase.scenario_type/error_type`。
- runtime 在 `ReconciliationService._build_rag_query()` 的现有 base query 构造完成后调用同一 helper，
  使用 result `error_type/exception_branch` 与当前 `scenario_type`；不得复制 profile terms。
- runtime `CLEARING_SINGLE_SIDE/BC-R001` 和 eval `SINGLE_SIDE_MISSING` 产生同一追加词项。
- BANK_ENTERPRISE、BC-R003、非目标 error/branch 的现有 query 完全不变。
- candidate matrix metadata 为 enabled，并包含稳定 profile identity、非空 profile SHA-256 与实际
  `git_revision`；baseline default 仍为 disabled。
- candidate matrix 包含 enrichment latency count、P50、P95、max；只测 helper，不把 embedding latency
  混入该字段。
- `RagSearchRequest`、HTTP API、retriever、Tool、response、RAG log 和 Trace contract 无变化。
- 测试证明 runtime/eval 两个入口都调用 shared helper，并覆盖 default disabled 与非目标零回归。

### Verification Commands

```bash
uv run pytest tests/test_rag_query_enrichment.py tests/test_mvp2b3_eval_rag.py tests/test_mvp2a3_clearing_rag.py tests/test_mvp2a2_workflow_integration.py -q
uv run ruff check src/bank_reconciliation_agent/services/reconciliation.py scripts/eval_rag.py tests/test_mvp2b3_eval_rag.py tests/test_mvp2a3_clearing_rag.py tests/test_mvp2a2_workflow_integration.py
uv run ruff format --check src/bank_reconciliation_agent/services/reconciliation.py scripts/eval_rag.py tests/test_mvp2b3_eval_rag.py tests/test_mvp2a3_clearing_rag.py tests/test_mvp2a2_workflow_integration.py
```

### Report Back Requirements

- Changed Files
- Integration Summary：runtime/eval call sites 与无 contract 变化证明
- Candidate Metadata Summary：profile/hash/revision/latency 口径
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.4`

---

## TASK-30.5 — 生成 after/comparison 并强制执行 accept/reject verdict

**Status**: pending
**Spec Ref**: `Main Flow` 6–9、`Comparison Artifact`、`Verdict`
**ADR Ref**: `ADR-30.1` Decision 7–10

### Goal

在 TASK-30.4 candidate commit 上生成可信 `bge_m3/dense` after 和 before/after comparison，根据报告
唯一 verdict 保留或回滚 candidate。报告命令成功不等于优化成功；不得在本 task 调整 profile 或进行
第二次 candidate 尝试。

### Files to Modify

- Create: `reports/rag_quality_matrix_stage30_after.md`
- Create: `reports/rag_quality_matrix_stage30_after.json`
- Modify: `reports/rag_optimization_comparison.md`
- Modify: `reports/rag_optimization_comparison.json`
- Conditional rollback only when trust/success gate fails:
  - Modify: `src/bank_reconciliation_agent/services/reconciliation.py`
  - Modify: `scripts/eval_rag.py`
  - Delete: `rules/rag_query_terms.yaml`
  - Delete: `src/bank_reconciliation_agent/rag/query_enrichment.py`
  - Delete: `tests/test_rag_query_enrichment.py`
  - Modify: `tests/test_mvp2b3_eval_rag.py`
  - Modify: `tests/test_mvp2a3_clearing_rag.py`
  - Modify only if changed in TASK-30.4: `tests/test_mvp2a2_workflow_integration.py`

### Do Not Touch

- `data/`、raw knowledge、chunks、embedding config、RAG scoring/config
- `src/bank_reconciliation_agent/schemas/`
- retriever、LLM rewrite、workflow、Tool、Trace、数据库和 frontend
- TASK-30.1 的 evidence/hash/legacy compatibility 逻辑，即使 candidate 被回滚也必须保留
- baseline reports
- spec、tasks、ADR 和项目级文档

### Out of Scope

- 修改 target terms、增加 profile、改变 query、标签、mode、top-k 或 success threshold。
- 因 `success=false` 再跑一个新 candidate。
- 用 hash fallback、旧报告或手工 JSON 替代真实 after。
- 将 environment gap 包装为可信 experiment rejected。

### Acceptance Criteria

- 在 TASK-30.4 candidate commit 上完整运行 after 命令；after 明确记录 candidate Git revision。
- after requested/effective backend 均为 `bge_m3`、status=`measured`、mode=`dense`、top-k=5、
  case_count=120、profile enabled/hash 非空，才可进入可信 comparison。
- baseline/after 的 eval set hash、chunk corpus hash、case count、top-k、backend 和 mode 完全一致。
- comparison `trust.trusted=true` 才能给出可信 optimization verdict。
- comparison 输出 target/global/全部非目标 bucket delta、latency、failure reasons 与唯一 `success`。
- **Optimization accepted**：仅当 `success=true`；保留 candidate，不做额外调参。
- **Experiment rejected**：`trust.trusted=true` 且 `success=false`；回滚所有 candidate runtime/eval
  integration、helper 和 target profile，保留 TASK-30.1 evidence contract、after/comparison 和 Git 历史。
- **Environment gap**：after trust 不成立；回滚 candidate，保留真实 unavailable evidence，明确不能评价
  优化成功或失败。
- rollback 后公共行为恢复到 baseline，candidate revision/profile hash 仍可从报告定位。
- comparison 命令退出 0 但 JSON `success=false` 时必须走 reject rollback，不能仅凭退出码保留代码。

### Verification Commands

```bash
uv run python -m scripts.eval_rag \
  --matrix-backends bge_m3 \
  --matrix-modes dense \
  --real-backend-policy auto \
  --query-enrichment-profile bank-clearing-single-side-missing \
  --matrix-report reports/rag_quality_matrix_stage30_after.md \
  --matrix-json reports/rag_quality_matrix_stage30_after.json

uv run python -m scripts.eval_rag \
  --optimization-baseline-json reports/rag_quality_matrix_stage30_baseline.json \
  --optimization-after-json reports/rag_quality_matrix_stage30_after.json \
  --optimization-backend bge_m3 \
  --optimization-mode dense \
  --optimization-target-scenario BANK_CLEARING \
  --optimization-target-error-type SINGLE_SIDE_MISSING \
  --optimization-report reports/rag_optimization_comparison.md \
  --optimization-json reports/rag_optimization_comparison.json

jq '{trust, success, failure_reasons, target_bucket, global, side_effect_buckets}' \
  reports/rag_optimization_comparison.json
```

无论 verdict 为何，完成保留/回滚后运行：

```bash
uv run pytest tests/test_mvp2b3_eval_rag.py tests/test_v1_1_eval_rag_report.py tests/test_mvp2a3_clearing_rag.py tests/test_mvp2a2_workflow_integration.py -q
uv run ruff check scripts/eval_rag.py src/bank_reconciliation_agent/services/reconciliation.py tests/test_mvp2b3_eval_rag.py tests/test_v1_1_eval_rag_report.py tests/test_mvp2a3_clearing_rag.py tests/test_mvp2a2_workflow_integration.py
uv run ruff format --check scripts/eval_rag.py src/bank_reconciliation_agent/services/reconciliation.py tests/test_mvp2b3_eval_rag.py tests/test_v1_1_eval_rag_report.py tests/test_mvp2a3_clearing_rag.py tests/test_mvp2a2_workflow_integration.py
```

若 candidate accepted，以上 Ruff 命令还必须加入
`src/bank_reconciliation_agent/rag/query_enrichment.py tests/test_rag_query_enrichment.py`。

### Report Back Requirements

- Changed Files
- Candidate Revision and Profile Hash
- Exact Evaluation Commands and Exit Codes
- Trust Gate：逐项 metadata/hash 值
- Target/Global/Side-effect Metrics：before、after、delta
- Verdict：`optimization accepted | experiment rejected | environment gap`
- Rollback Summary：如适用，列出所有移除/恢复文件并证明 baseline behavior
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.5`

---

## TASK-30.6 — 运行 Stage/PR 全量门禁并记录 verification

**Status**: pending
**Spec Ref**: `Regression`、`Observability and Honesty`、全部 Acceptance Criteria
**ADR Ref**: `ADR-30.1`

### Goal

对最终代码树运行 Stage/PR 全量验证，并将真实结果、最终实验状态和 artifact 摘要写入正式
`verification.md`。本 task 不修复实现问题；任何失败必须报告并交回 Codex review。

### Files to Modify

- Create or Modify: `docs/stages/stage-30-rag-query-optimization/verification.md`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`rules/`、`data/`、`reports/`
- spec、tasks、ADR、README、架构/PRD 和 frontend

### Out of Scope

- 修复测试、调整 candidate、重跑新实验或改变 verdict。
- 修改 task 状态或把未运行命令标为 passed。
- push、PR、merge 或 stage closeout。

### Acceptance Criteria

- `verification.md` 记录 branch、HEAD、日期、环境和最终状态：
  `optimization accepted | experiment rejected | environment gap`。
- 逐条记录 task-level evidence、baseline/after/comparison artifact 路径和关键 trust metadata。
- optimization accepted/rejected 时记录 target/global/side-effect verdict；environment gap 时记录具体缺口，
  不填写虚构 after delta。
- 完整运行并记录 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`。
- 检查 `git diff --stat main...HEAD` 与 Stage 30 范围一致，`git status --short` 无意外文件。
- 检查没有密钥、`.env`、缓存、模型文件、Chroma 本地数据、构建产物或大文件进入提交。
- 任一全量 gate 失败时 verification 明确失败，Stage 不得标记完成。
- 不修改实现、报告、accepted spec/ADR 或 tasks 状态。

### Verification Commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

### Report Back Requirements

- Changed Files
- Final Stage State
- Full Gate Results：逐条命令、退出码、passed/failed
- Artifact and Metrics Summary
- Scope/Secret/Large-file Check
- Deviations From Spec
- Risks/Follow-up
- Commit：`docs: record stage 30 verification`，body 包含 `Refs: TASK-30.6`

