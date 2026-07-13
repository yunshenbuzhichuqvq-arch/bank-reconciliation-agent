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

---

## Review Follow-up（2026-07-13）

首次 Codex review 复现出 Stage 30 comparison 的 fail-closed contract 仍有缺口：artifact 角色 metadata
缺失或失真时仍可能得到 `trust.trusted=true`，非目标 bucket 缺失时也会被静默跳过。以下任务只修复
可信度判定、重建派生 comparison，并更新最终验证；不得重跑真实 embedding 实验、改变指标或恢复
已拒绝的 candidate。

依赖顺序：

```text
TASK-30.7 Artifact role trust gate
  → TASK-30.8 Bucket completeness trust gate
    → TASK-30.9 Regenerate comparison artifacts
      → TASK-30.10 Re-run final verification
```

## TASK-30.7 — 对 Stage 30 artifact 角色与 enrichment metadata fail closed

**Status**: ready
**Spec Ref**: `Matrix Artifact`、`Comparison Artifact`、`Trust and Reporting`
**ADR Ref**: `ADR-30.1` Decision 7–10

### Goal

修复 Stage 30 comparison 对新格式 artifact 的识别和角色校验：只要任一输入体现 Stage 30 新格式，
另一输入缺失新格式字段就必须 fail closed；baseline 必须是 disabled，after 必须携带可复现的 candidate
profile、revision 和 latency metadata。本 task 不改变任何指标计算或 tracked report。

### Files to Modify

- Modify: `scripts/eval_rag.py`
- Modify: `tests/test_v1_1_eval_rag_report.py`

### Do Not Touch

- `src/`、`rules/`、`data/`、`reports/`
- `tests/test_mvp2b3_eval_rag.py` 和其他 tests
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- query enrichment helper/runtime/eval candidate 恢复。
- 真实 `bge_m3` baseline/after 重跑、指标调整或第三次 candidate。
- Stage 22 legacy artifact 的 guarded compatibility 删除。
- 公共 API、retriever、Tool、Trace 或数据库 contract 变化。

### Acceptance Criteria

- Stage 30 intent 不得依赖“两个输入都含 `query_enrichment`”才成立；任一输入带有 Stage 30 metadata
  而另一输入缺失时，comparison 返回 `trust.trusted=false`、`success=false` 和稳定原因。
- baseline 的 `query_enrichment` 必须为 disabled 且 profile 为空；after 必须为 enabled，并包含非空
  profile、`profile_sha256`、`git_revision` 和 latency summary。
- after latency summary 至少校验 `count/P50/P95/max`（允许现有小写 JSON key），count 必须等于 case count，
  数值必须非负且满足 `P50 <= P95 <= max`。
- baseline 也必须包含非空 `git_revision`；缺失 revision、profile hash 或 latency 任一项均 fail closed。
- requested backend、effective backend、status、mode、case count、top-k 与两个 corpus hash 的现有门禁继续
  生效；不得放宽 legacy compatibility gate。
- comparison JSON/Markdown 的 source/trust evidence 能直接审查 baseline/after revision、enrichment role、
  after profile/hash 和 latency，不再只能回查 matrix artifact。
- 新增负向测试至少覆盖：after 缺 `query_enrichment`、after disabled、profile/hash 缺失、revision 缺失、
  latency 缺失或 count/顺序非法；每例都断言 `trusted=false` 与 `success=false`。
- 当前真实 Stage 30 baseline/after artifacts 仍能通过新的 role metadata trust gate。

### Verification Commands

```bash
uv run pytest tests/test_v1_1_eval_rag_report.py -q
uv run ruff check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
uv run ruff format --check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
```

### Report Back Requirements

- Changed Files
- Reproduced Failures：逐项说明修复前为何错误得到 `trusted=true`
- Trust Contract Summary：Stage 30 intent、baseline/after 角色与 latency/revision 校验
- Legacy Compatibility：说明未放宽 Stage 22 guarded reader
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.7`

---

## TASK-30.8 — 对 bucket 集合、唯一性与 case count fail closed

**Status**: pending
**Spec Ref**: `Comparison Artifact`、`Trust and Reporting`
**ADR Ref**: `ADR-30.1` Decision 8–9

### Goal

阻止 comparison 在 baseline/after bucket 缺失、重复或 case count 不一致时静默生成不完整副作用表；
可信 Stage 30 comparison 必须证明目标和全部非目标 bucket 一一对应。本 task 不修改 tracked report。

### Files to Modify

- Modify: `scripts/eval_rag.py`
- Modify: `tests/test_v1_1_eval_rag_report.py`

### Do Not Touch

- `src/`、`rules/`、`data/`、`reports/`
- `tests/test_mvp2b3_eval_rag.py` 和其他 tests
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- 修改 metric 公式、success threshold、target bucket 或 legacy top-level fallback 规则。
- 重跑 baseline/after、恢复 candidate 或调整 enrichment terms。
- 将缺失 bucket 当作零值补齐或继续输出可信 verdict。

### Acceptance Criteria

- Stage 30 baseline/after 的 mode-specific bucket key 集合必须完全相同；任一侧缺失或新增 key 均
  `trust.trusted=false`、`success=false`，原因列出具体 key。
- 每侧 `(scenario_type, error_type)` 必须唯一；重复 key fail closed，不得由 dict 覆盖。
- 同一 bucket 的 `case_count` 必须在 before/after 相等；每侧 bucket case count 总和必须等于 matrix
  `case_count`；目标 bucket 必须保持 10 cases。
- bucket 的必需指标字段缺失或类型非法时 fail closed，不得在 Markdown 中用默认 0 掩盖。
- `_bucket_deltas` 或等价逻辑不得对 after 缺失项执行 `continue` 后仍生成可信结果。
- trust 通过时，`all_non_target` 数量必须等于完整 bucket 总数减 1；当前 Stage 30 artifact 应为
  `11 - 1 = 10`，且 10 个副作用 delta 均为 0。
- 新增负向测试至少覆盖：after 删除一个非目标 bucket、增加额外 bucket、重复 bucket、bucket case count
  不同、case count 总和不等；每例都断言 fail closed。
- 现有 target Recall/miss、global MRR/NDCG success gate 和 legacy compatibility tests 保持通过。

### Verification Commands

```bash
uv run pytest tests/test_v1_1_eval_rag_report.py -q
uv run ruff check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
uv run ruff format --check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
```

### Report Back Requirements

- Changed Files
- Bucket Integrity Contract：集合、唯一性、case count 与必需字段
- Reproduced Failures：至少列出删除非目标 bucket 的修复前/后 trust 差异
- Legacy Compatibility
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.8`

---

## TASK-30.9 — 用加固后的 contract 重建 comparison artifacts

**Status**: pending
**Spec Ref**: `Comparison Artifact`、`Verdict`
**ADR Ref**: `ADR-30.1` Decision 7–10

### Goal

只使用已提交的 Stage 30 baseline/after JSON，通过 TASK-30.7–30.8 的最终 comparison 代码重建
Markdown/JSON，证明真实 artifact 仍可信且实验结论仍为 `success=false`。本 task 不重跑 embedding。

### Files to Modify

- Modify: `reports/rag_optimization_comparison.md`
- Modify: `reports/rag_optimization_comparison.json`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`rules/`、`data/`
- `reports/rag_quality_matrix_stage30_baseline.*`
- `reports/rag_quality_matrix_stage30_after.*`
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- 真实 `bge_m3` baseline/after 重跑。
- 修改 matrix JSON、metric、profile hash、candidate revision 或 failure reasons 迁就 gate。
- 恢复 candidate、修改 query terms 或尝试第二个 enrichment 方案。

### Acceptance Criteria

- 使用 tasks 中既有 comparison 命令重建两个 tracked artifact，命令输入只读现有 baseline/after JSON。
- comparison 保持 `trust.trusted=true`、`success=false`，唯一实验结论仍为 `experiment rejected`。
- target/global before、after、delta 与现有 matrix artifacts 一致，不允许手工编辑数值。
- source/trust evidence 包含 baseline revision `b015add...`、candidate revision `51b48ef...`、profile
  `bank-clearing-single-side-missing`、非空 profile SHA-256 和 latency summary。
- 完整副作用表恰好包含 10 个非目标 bucket，全部 delta 为 0；不得再声称 14 个。
- JSON 与 Markdown 同口径，重复运行到 `/tmp` 后与 tracked artifact 字节一致。
- 不修改 baseline/after、代码、测试、数据或 rollback 后运行时行为。

### Verification Commands

```bash
uv run python -m scripts.eval_rag \
  --optimization-baseline-json reports/rag_quality_matrix_stage30_baseline.json \
  --optimization-after-json reports/rag_quality_matrix_stage30_after.json \
  --optimization-backend bge_m3 \
  --optimization-mode dense \
  --optimization-target-scenario BANK_CLEARING \
  --optimization-target-error-type SINGLE_SIDE_MISSING \
  --optimization-report reports/rag_optimization_comparison.md \
  --optimization-json reports/rag_optimization_comparison.json

jq -e '
  .trust.trusted == true and
  .success == false and
  (.side_effect_buckets.all_non_target | length == 10) and
  ([.side_effect_buckets.all_non_target[].delta |
    select(.miss_count != 0 or .hit_at_1 != 0 or .recall_at_5 != 0 or
           .mrr != 0 or .ndcg_at_5 != 0)] | length == 0)
' reports/rag_optimization_comparison.json
```

### Report Back Requirements

- Changed Files
- Exact Commands and Exit Codes
- Source Metadata：baseline/candidate revision、profile/hash、latency
- Target/Global/Side-effect Metrics
- Verdict：`experiment rejected`
- Reproducibility Check
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.9`

---

## TASK-30.10 — 复跑修复后的 Stage/PR 门禁并纠正 verification

**Status**: pending
**Spec Ref**: `Regression`、`Observability and Honesty`、全部 Acceptance Criteria
**ADR Ref**: `ADR-30.1`

### Goal

在 TASK-30.7–30.9 完成后复跑最终门禁，更新 `verification.md` 中的 HEAD、task evidence、diff 统计、
副作用数量和真实 gate 状态。本 task 只记录事实，不修复代码或改变实验 verdict。

### Files to Modify

- Modify: `docs/stages/stage-30-rag-query-optimization/verification.md`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`rules/`、`data/`、`reports/`
- spec、tasks、ADR、README、架构/PRD 和 frontend

### Out of Scope

- 修复实现、修改 comparison 数值、重跑真实 embedding 或恢复 candidate。
- 为使 repo-wide format gate 通过而格式化无关文件。
- 把失败/未运行的命令标为 passed，或自行批准 inherited gate exception。
- push、PR、merge 或 stage closeout。

### Acceptance Criteria

- `verification.md` 的 HEAD、日期、task-level evidence 与最终提交链一致，包含 TASK-30.7–30.9。
- artifact 摘要准确记录 11 个总 bucket、10 个非目标 bucket；删除原“14 个非目标 bucket”错误。
- `git diff --stat main...HEAD` 的文件数和增删行与命令输出一致，不沿用旧快照。
- `git diff --check main...HEAD` 必须通过；若仍失败，verification 明确 failed 且 Stage 不得完成。
- 完整运行并记录 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .` 的退出码。
- 若 repo-wide format 仍是 main 已存在的 baseline failure，必须同时记录：当前失败文件数、Stage 30
  改动 Python 文件的定向结果、main 对应文件的对照结果；不得把失败写成 passed，也不得擅自扩大格式化。
- 明确区分“实验结论 `experiment rejected`”与“Stage/PR gate 是否通过”；前者不能掩盖后者失败。
- scope/secret/large-file 检查使用最终 diff，且 `git status --short` 无意外文件。
- 本 task 不改代码、报告、accepted spec/ADR 或 tasks 状态。

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
- Final Experiment State
- Stage/PR Gate State
- Full Gate Results：逐条命令、退出码、passed/failed
- Artifact and Metrics Summary
- Scope/Secret/Large-file Check
- Deviations From Spec
- Risks/Follow-up
- Commit：`docs: correct stage 30 verification after review fixes`，body 包含 `Refs: TASK-30.10`

---

## Second Review Follow-up（2026-07-13）

第二次 Codex review 证明 TASK-30.7–30.8 已修复单侧 metadata 缺失和 bucket 集合缺失，但仍存在
三类 fail-closed 缺口：两侧同时删除 `query_enrichment` 会退回 legacy 路径；top-level requested mode
可与实际比较 mode 矛盾；非法 bucket 类型会在记录 trust reason 后继续参与算术并抛异常，且 target
case count 可从 10 被同步篡改为 9 后仍保持 trusted。以下任务不得改变真实 Stage 30 指标或恢复 candidate。

依赖顺序：

```text
TASK-30.11 Stage 30 intent and requested-mode trust
  → TASK-30.12 Total bucket-schema and target-count fail closed
    → TASK-30.13 Final evidence re-verification
```

执行 TASK-30.11 前，plan owner 必须先提交当前 `tasks.md` 规划更新；opencode 不得把规划文件混入
实现 commit。

## TASK-30.11 — 完整识别 Stage 30 intent 并校验 requested backend/mode

**Status**: ready
**Spec Ref**: `Matrix Artifact`、`Comparison Artifact`、`Trust and Reporting`
**ADR Ref**: `ADR-30.1` Decision 7–10

### Goal

防止 baseline/after 同时缺少 `query_enrichment` 时被误判为 legacy artifact，并让 comparison 校验
matrix top-level requested backend/mode 与实际选择的 backend/mode 一致。本 task 不修改 bucket 计算或报告。

### Files to Modify

- Modify: `scripts/eval_rag.py`
- Modify: `tests/test_v1_1_eval_rag_report.py`

### Do Not Touch

- `src/`、`rules/`、`data/`、`reports/`
- `tests/test_mvp2b3_eval_rag.py` 和其他 tests
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- 修改 Stage 22 legacy artifact 内容或删除 guarded legacy compatibility。
- bucket schema/count 修复；由 TASK-30.12 负责。
- 重跑真实 embedding、恢复 candidate、修改指标或 profile。
- 公共 API、retriever、Tool、Trace 或数据库 contract 变化。

### Acceptance Criteria

- Stage 30 intent 必须由任一 Stage 30-only metadata 明确识别，至少覆盖
  `query_enrichment/eval_set_sha256/chunk_corpus_sha256/git_revision`；不得只检查
  `query_enrichment` key。
- baseline/after 同时删除 `query_enrichment`、但仍含 Stage 30 hash/revision 时，comparison 返回
  `trust.trusted=false`、`success=false` 和明确缺失原因，不得退回 legacy 路径。
- 只要任一输入表达 Stage 30 intent，两个输入都必须通过完整 Stage 30 role/hash/bucket gate。
- baseline/after top-level `requested_backends` 必须彼此一致并包含 comparison 选择的 backend；top-level
  `modes` 必须彼此一致并包含 comparison 选择的 mode。缺失、类型非法或矛盾均 fail closed。
- row-level requested/effective backend、status 和 mode-specific metrics 的现有门禁继续生效。
- 旧 artifact 在完全不含 Stage 30-only metadata 时继续走现有 guarded legacy reader，不得扩大 fallback。
- 新增负向测试至少覆盖：两侧同时缺 `query_enrichment`、两侧 top-level mode 均与 requested mode 矛盾、
  baseline/after mode 列表不一致、requested backend 列表矛盾。
- 当前真实 Stage 30 baseline/after 仍为 `trust.trusted=true`、`success=false`，comparison 指标不变。

### Verification Commands

```bash
uv run pytest tests/test_v1_1_eval_rag_report.py -q
uv run ruff check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
uv run ruff format --check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
```

### Report Back Requirements

- Changed Files
- Reproduced Failures：两侧缺 metadata 与 mode contradiction 的修复前/后结果
- Stage 30 Intent Contract
- Requested Backend/Mode Contract
- Legacy Compatibility
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.11`

---

## TASK-30.12 — 使 bucket schema 校验全程无异常并锁定 target 10 cases

**Status**: pending
**Spec Ref**: `Comparison Artifact`、`Trust and Reporting`
**ADR Ref**: `ADR-30.1` Decision 8–9

### Goal

保证非法 bucket artifact 总是生成 `trusted=false/success=false` 的可审查报告，而不是在收集 trust reason
后继续执行不安全算术；同时显式锁定 Stage 30 target bucket 的 10-case contract。

### Files to Modify

- Modify: `scripts/eval_rag.py`
- Modify: `tests/test_v1_1_eval_rag_report.py`

### Do Not Touch

- `src/`、`rules/`、`data/`、`reports/`
- `tests/test_mvp2b3_eval_rag.py` 和其他 tests
- spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- 修改 metric 公式、success threshold、target identity 或 legacy fallback 规则。
- 重跑 baseline/after、恢复 candidate 或调整 query terms。
- 用默认零值修补非法 artifact 后继续给出可信 verdict。

### Acceptance Criteria

- bucket identity 的 `scenario_type/error_type` 必须为非空字符串；非法 identity fail closed。
- `case_count/miss_count` 必须为非 bool 的非负整数，且 `miss_count <= case_count`。
- `hit_at_1/recall_at_5/mrr/ndcg_at_5` 必须为有限数值；非法类型不得进入减法、排序或 Markdown
  格式化路径。
- 任一 schema/type 错误都必须返回结构化 comparison，包含稳定 trust/failure reason；不得抛
  `TypeError/KeyError/ValueError`。
- case count 求和只对通过类型校验的值执行；不得在记录类型错误后对字符串等非法值调用 `sum`。
- Stage 30 target `BANK_CLEARING/SINGLE_SIDE_MISSING` 在 baseline 和 after 都必须恰好为 10 cases；即使
  两侧同步改为 9 并在其他 bucket 补回总数，也必须 `trusted=false`、`success=false`。
- 现有 bucket key 集合、唯一性、before/after count equality、总和等于 matrix case count 的门禁保持。
- 新增负向测试至少覆盖：字符串 `case_count`、字符串 metric、空 bucket identity、负 count、
  `miss_count > case_count`、target 两侧同步为 9 且总数仍为 120；每例断言不抛异常且 fail closed。
- 当前真实 Stage 30 comparison 仍为 trusted rejection，10 个非目标 bucket delta 均为 0。

### Verification Commands

```bash
uv run pytest tests/test_v1_1_eval_rag_report.py -q
uv run ruff check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
uv run ruff format --check scripts/eval_rag.py tests/test_v1_1_eval_rag_report.py
```

### Report Back Requirements

- Changed Files
- Schema Validation Contract
- No-Exception Evidence：列出原 `TypeError` case 的修复后报告结果
- Target Count Evidence：同步 9-case 篡改的修复前/后 trust 结果
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-30.12`

---

## TASK-30.13 — 复验最终 comparison 与 Stage/PR evidence

**Status**: pending
**Spec Ref**: `Regression`、`Observability and Honesty`、全部 Acceptance Criteria
**ADR Ref**: `ADR-30.1`

### Goal

在 TASK-30.11–30.12 完成后，用已有 baseline/after artifact 复验 comparison 字节可复现性，并更新
最终 `verification.md`。本 task 不修改代码、指标或实验结论。

### Precondition

- `tasks.md` 的 TASK-30.7–30.13 规划必须已由 plan owner 单独提交。
- `git status --short` 不得显示未提交的 `tasks.md`；否则停止并报告，不得把规划混入本 task commit。

### Files to Modify

- Modify: `docs/stages/stage-30-rag-query-optimization/verification.md`

### Do Not Touch

- `src/`、`scripts/`、`tests/`、`rules/`、`data/`、`reports/`
- spec、tasks、ADR、README、架构/PRD 和 frontend

### Out of Scope

- 覆盖 tracked comparison 来掩盖不可复现差异；若 `/tmp` 输出不同，停止并报告。
- 重跑真实 embedding、改变 report 数值、恢复 candidate 或修改实现。
- 格式化无关 repo 文件、自行批准 inherited format exception。
- push、PR、merge 或 stage closeout。

### Acceptance Criteria

- 使用已有 baseline/after JSON 将 comparison 重建到 `/tmp`，JSON 与 Markdown 分别和 tracked artifact
  字节一致；若不一致，本 task 失败且不覆盖 tracked report。
- comparison 保持 `trust.trusted=true`、`success=false`、target 10 cases、10 个非目标 bucket 全部 delta=0。
- `verification.md` 增加 TASK-30.11–30.12 evidence，并删除对不完整 OR-only detection 的过度声明。
- 完整运行并记录 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、
  `git diff --check main...HEAD`、diff scope 和 `git status --short`。
- `git diff --check main...HEAD` 必须通过；planning 文件已提交且工作区无意外改动。
- repo-wide format baseline 若仍失败，必须如实保留 failed 状态及 main 对照，不得写成 passed。
- 明确区分最终实验状态 `experiment rejected` 与 Stage/PR gate 状态。
- 不修改 comparison、baseline/after、代码、测试、accepted spec/ADR 或 tasks 状态。

### Verification Commands

```bash
uv run python -m scripts.eval_rag \
  --optimization-baseline-json reports/rag_quality_matrix_stage30_baseline.json \
  --optimization-after-json reports/rag_quality_matrix_stage30_after.json \
  --optimization-backend bge_m3 \
  --optimization-mode dense \
  --optimization-target-scenario BANK_CLEARING \
  --optimization-target-error-type SINGLE_SIDE_MISSING \
  --optimization-report /tmp/stage30-comparison-review.md \
  --optimization-json /tmp/stage30-comparison-review.json

cmp -s reports/rag_optimization_comparison.json /tmp/stage30-comparison-review.json
cmp -s reports/rag_optimization_comparison.md /tmp/stage30-comparison-review.md
uv run pytest
uv run ruff check .
uv run ruff format --check .
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

### Report Back Requirements

- Changed Files
- Comparison Reproducibility
- Final Experiment State
- Stage/PR Gate State
- Full Gate Results：逐条命令、退出码、passed/failed
- Scope/Secret/Large-file Check
- Deviations From Spec
- Risks/Follow-up
- Commit：`docs: record second stage 30 review verification`，body 包含 `Refs: TASK-30.13`
