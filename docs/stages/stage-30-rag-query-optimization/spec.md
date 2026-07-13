# Stage 30 Spec: RAG 弱桶单变量 query enrichment

- **Stage**: `stage-30-rag-query-optimization`
- **Branch**: `stage-30-rag-query-optimization`
- **Status**: accepted
- **Date**: 2026-07-13
- **Roadmap Source**: `docs/interview/what-todo-next.md`
- **Architecture Impact**: Yes — 确定 branch-aware query enrichment 的职责边界与失败回滚规则
- **ADR Required**: Yes
- **ADR**: `decisions/ADR-30.1-metric-gated-branch-aware-query-enrichment.md` (`accepted`)

## Stage Goal

在当前代码与数据上重新冻结可信 `bge_m3/dense` baseline，然后只改变 query-side 一个变量：对
`BANK_CLEARING / SINGLE_SIDE_MISSING` 使用共享、确定性、branch-aware 的类别级检索词 enrichment。
用同一 120 条 eval set 做 before/after，只有目标桶改善且全局质量无超阈值回退时才保留运行时
candidate；否则保留可信 `success=false` 证据并移除运行时优化。

本 Stage 的成功包括两种合法终态：

1. **Optimization accepted**：可信指标通过全部 gate，运行时保留 candidate；
2. **Experiment rejected**：可信指标未通过 gate，运行时不保留 candidate，但交付可复现的失败报告。

环境不可信不是实验失败，而是 **environment gap**；此时不得进入 candidate 实现或给出成功/失败结论。

## Builds On

- Stage 29 已合并到当前 `main`，当前分支与 `main` 均位于 `8458240`。
- `decisions/ADR-EH.5-baseline-metric-gated-optimization-reeval.md`：baseline → 单变量优化 → 同口径复测。
- `decisions/ADR-087-eval-set-semantic-rewrite-and-desaturation.md`：评测标签独立，不按结果重标。
- `decisions/ADR-22.1-target-weakest-real-rag-miss-bucket.md`：目标限定为
  `BANK_CLEARING / SINGLE_SIDE_MISSING`。
- `decisions/ADR-22.3-rag-before-after-side-effect-reporting.md`：局部提升与全局副作用同时报告。
- `decisions/ADR-22.4-guarded-legacy-baseline-bucket-compatibility.md`：mode-specific bucket metrics 优先，
  legacy fallback 只能受 metadata gate 保护。
- 当前 `reports/rag_quality_matrix.json` 提供进入 Stage 30 的历史依据，但其生成时间早于 Stage 29，
  只能用于选题，不能替代本 Stage 的新 baseline。

## Baseline Entry Gate

修改检索行为前必须先生成：

- `reports/rag_quality_matrix_stage30_baseline.json`
- `reports/rag_quality_matrix_stage30_baseline.md`

baseline 命令固定使用：

```bash
uv run python -m scripts.eval_rag \
  --matrix-backends bge_m3 \
  --matrix-modes dense \
  --real-backend-policy auto \
  --matrix-report reports/rag_quality_matrix_stage30_baseline.md \
  --matrix-json reports/rag_quality_matrix_stage30_baseline.json
```

只有以下条件全部满足，才允许进入 candidate 实现：

- requested backend 为 `bge_m3`；
- effective backend 为 `bge_m3`；
- row status 为 `measured`；
- mode 为 `dense`，top-k 为 `5`；
- case count 为 `120`；
- 报告包含非空 `eval_set_sha256` 与 `chunk_corpus_sha256`；
- `BANK_CLEARING / SINGLE_SIDE_MISSING` 存在 10 条 case 的 mode-specific bucket metrics。

任一条件不满足：在 `verification.md` 记录命令、环境和具体 gap，停止 Stage；不得继续修改检索逻辑、
不得退回 hash、不得复用 2026-07-08 的旧矩阵冒充 Stage 30 baseline。

## In Scope

- 为 matrix artifact 增加可复现 trust metadata：至少包含 eval set 与 chunk corpus 的 SHA-256。
- comparison 同时校验 baseline/after 的 case count、top-k、hash、requested/effective backend、status、
  backend、mode 和 target bucket 是否存在。
- 新增一个共享、确定性的 query enrichment helper 与一个 tracked YAML profile。
- profile 只覆盖目标语义，并显式桥接：
  - eval `SINGLE_SIDE_MISSING`；
  - runtime `CLEARING_SINGLE_SIDE`；
  - runtime `BC-R001`。
- runtime 在现有 query construction 边界调用 helper；eval 在构造 `RagSearchRequest` 前调用同一 helper。
- 未命中 profile 时 query 必须逐字保持不变。
- candidate 只追加类别级业务检索词；词项必须能追溯到现有业务规则或知识库标题。
- 生成同口径 after matrix 与 before/after comparison。
- comparison JSON 输出目标桶、全局指标以及全部非目标 bucket 的 before/after/delta；Markdown 至少提供
  完整副作用表或可直接审查的完整附表。
- 报告 query enrichment 的 per-case latency summary（至少 count、P50、P95、max），该 latency 只作为
  观测证据，不单独决定 success。
- 根据 gate 保留或移除运行时 candidate，并真实记录 `success=true/false`；失败报告必须记录包含
  candidate 的 Git revision，保证最终代码回滚后仍能从历史复现实验。
- 为新增 contract、两个调用入口、trust gate 和 rollback verdict 增加行为测试。

## Out of Scope

- 修改 `data/rag_eval_set.json`、case id、query、expected chunk ids 或标签。
- 修改 raw knowledge、chunk builder、chunk JSONL、embedding model/backend、Chroma collection contract。
- 修改 dense/hybrid/rerank mode、top-k、threshold、RRF、BM25 或 reranker 参数。
- 使用 LLM 做本次 enrichment，修改 prompt，或改变 ADR-011 `QueryRewriter`。
- 扩展 `RagSearchRequest`、`RagSearchResponse`、`/api/v1/rag/search` 或 Tool Executor contract。
- 修改金额计算、确定性路由结果、AuditAgent、安全门禁、Fallback、Trace、权限或数据隔离。
- 引入新依赖、feature-flag framework、通用 query DSL 或第三次调参。
- 将真实 embedding 诊断加入默认 CI，或宣称生产 RAG/SLA 指标。

## Inputs and Outputs

### Inputs

- 固定的 `data/rag_eval_set.json`（120 cases）。
- 固定的当前 rule chunk corpus。
- `scenario_type`、`error_type`、可选 `exception_branch` 与原始 query。
- requested backend=`bge_m3`、mode=`dense`、top-k=`5`。
- tracked query enrichment profile。

### Outputs

- 原 query 或确定性 enriched query。
- Stage 30 baseline/after matrix Markdown 与 JSON。
- `reports/rag_optimization_comparison.md`。
- `reports/rag_optimization_comparison.json`。
- Stage 30 `verification.md`，记录环境、命令、测试、指标和最终 verdict。

## Main Flow

1. 评测脚本计算并写入 eval set 与 chunk corpus hash，不改变检索行为。
2. 生成 baseline，并执行 Baseline Entry Gate。
3. 若 gate 不通过，记录 environment gap 并停止。
4. 若 gate 通过，加载唯一 target profile，并用共享 helper 构造 candidate query。
5. runtime 与 eval 分别接入同一 helper；非目标请求保持 identity behavior。
6. 使用同一 eval set、corpus、backend、mode 和 top-k 生成 after matrix。
7. comparison 校验 trust metadata 后计算 target/global/side-effect deltas。
8. 若全部 success gate 通过，保留 candidate 并标记 `success=true`。
9. 若任一 success gate 失败，标记 `success=false`，移除运行时启用与 target profile，只保留评测改进、
   报告、失败结论和可定位 candidate 的 Git 历史。
10. 运行 task gate 与 Stage/PR gate，把真实结果写入 `verification.md`。

## Function Contracts

### Query Enrichment

共享 helper 的语义 contract：

```text
enrich(query, scenario_type, error_type, exception_branch?) -> query
```

- 输入和输出均为字符串；不得改变公共 HTTP/Pydantic request contract。
- `scenario_type` 必须匹配 target profile，且 `error_type` 或 `exception_branch` 至少一个命中 alias。
- 命中时只在原 query 基础上追加规范化的配置词项，不删除或改写原 query。
- 未命中、空 alias 或非目标 scenario 时返回原 query，保持字节级相同。
- 配置加载必须经过明确 schema validation；非法 tracked config 作为配置错误失败，不静默启用部分 profile。
- 不调用 LLM、网络、数据库、embedding 或 retriever。

具体类名、返回内部数据结构与 YAML 字段名由 opencode 在上述 contract 内选择；不得增加通用框架。

### Matrix Artifact

Stage 30 使用的 matrix JSON 在现有 contract 上至少增加：

- `eval_set_sha256`；
- `chunk_corpus_sha256`；
- 当前 `git_revision`；
- query enrichment 是否启用及 profile identity；
- 启用时的 `query_profile_sha256`；
- query enrichment latency summary；
- 每个 measured mode 的 `bucket_metrics`。

hash 必须根据实际读取字节以稳定顺序计算；baseline 与 after 的两个 hash 必须相同。

### Comparison Artifact

comparison 必须：

- 对 metadata/hash 不匹配 fail closed：`trust.trusted=false`、`success=false` 并列出原因；
- 从 requested `bge_m3/dense` 的 mode-specific metrics 取 global 与 bucket 数据；
- 输出 target before/after/delta；
- 输出全部非目标 bucket 的 before/after/delta，不只列 top 3；
- 输出 global before/after/delta；
- 输出唯一布尔 `success` 与稳定、可读的 `failure_reasons`；
- 不因报告生成命令本身退出码为 0 就把实验标记成功。

## Data Model Impact

None。

- 不新增或修改数据库表、列、索引或 schema。
- 不修改 Pydantic API request/response model。
- YAML 仅为 tracked 本地业务检索策略配置，不包含租户数据、金额或凭据。

## Cross-Cutting Requirements

### Security and Data Isolation

- enrichment 只使用代码给定的 taxonomy/branch token 与 tracked 词项，不读取或持久化用户内容。
- 不改变现有 `user_id` 隔离、鉴权、Tool 或 Trace 语义。
- 报告不得包含原始流水、金额、凭据或真实用户数据。

### Determinism and Reproducibility

- helper 对相同输入与 profile 必须产生完全相同的输出。
- baseline/after 使用相同 eval set/corpus hash、backend/mode/top-k。
- Fake/hash 默认 CI 路径保持不变；真实 `bge_m3` 只作为本 Stage 手动诊断门禁。

### Observability and Honesty

- 报告必须区分 `optimization accepted`、`experiment rejected`、`environment gap`。
- `success=false` 是合法实验结果，不得删报告、换 backend 或改标签制造成功。
- latency 是本地诊断数据，不外推为生产 SLA。

### Backward Compatibility

- 非目标 query 完全不变。
- 公共 API、Tool、retriever、RAG response、RAG log 与 Trace contract 不变。
- 旧 matrix 的 guarded legacy reader 可继续存在，但 Stage 30 新 baseline/after 必须提供 mode-specific metrics
  与 hash，不得走 legacy fallback。

## Acceptance Criteria

### Planning and Entry

- [x] `ADR-30.1` 已由用户确认并改为 `accepted`。
- [ ] 新 baseline 通过全部 Baseline Entry Gate；否则 Stage 以 environment gap 暂停且无 candidate 改动。

### Query Behavior

- [ ] 只有目标 profile 会追加受控检索词；非目标 scenario/error/branch 的 query 字节级不变。
- [ ] eval `SINGLE_SIDE_MISSING` 与 runtime `CLEARING_SINGLE_SIDE/BC-R001` 命中同一 profile。
- [ ] runtime 和 eval 使用同一 helper，且没有第二份硬编码关键词映射。
- [ ] 未修改公共 API、retriever contract、LLM rewrite、chunk、embedding、mode、top-k、threshold 或 reranker。
- [ ] 配置不包含 eval case id、expected chunk id、eval query 原句或答案式单 case 硬编码。

### Trust and Reporting

- [ ] baseline/after 的 eval set hash、chunk corpus hash、case count、top-k、backend 和 mode 完全一致。
- [ ] requested/effective backend 均为 `bge_m3` 且 status=`measured`。
- [ ] comparison 使用 mode-specific `bge_m3/dense` metrics，`trust.trusted=true`。
- [ ] comparison 完整列出目标桶、全局以及全部非目标 bucket 副作用。
- [ ] query enrichment latency summary 包含 count、P50、P95、max。

### Verdict

- [ ] `success=true` 仅当 target Recall@5 严格上升、miss count 至少下降 1、全局 MRR 与 NDCG@5
  各自回退不超过 `0.0200`，且 trust gate 全部通过。
- [ ] 任一 success gate 失败时输出 `success=false` 和具体原因，移除运行时 candidate/profile，且不继续调参。
- [ ] candidate 被回滚时，after/comparison 报告仍记录 candidate Git revision 与 profile hash，可从分支
  历史复现实验。
- [ ] `verification.md` 明确记录最终状态为 `optimization accepted`、`experiment rejected` 或
  `environment gap`，以及所有实际执行命令和结果。

### Regression

- [ ] Stage 30 相关行为测试通过。
- [ ] `uv run pytest` 通过。
- [ ] `uv run ruff check .` 通过。
- [ ] `uv run ruff format --check .` 通过。

## Risks and Open Questions

### R1: 当前历史 baseline 已过期

`reports/rag_quality_matrix.json` 生成于 2026-07-08，早于 Stage 29 合并。它只用于选择目标，不用于
Stage 30 verdict。新 baseline 可能与路线图数字不同，所有 success delta 以新 baseline 为准。

### R2: eval taxonomy 与 runtime taxonomy 不同

离线 `SINGLE_SIDE_MISSING` 与运行时 `CLEARING_SINGLE_SIDE/BC-R001` 必须由一个受控 profile 关联；
禁止通过修改 eval 标签消除差异。

### R3: 本机真实 embedding 环境可能不可用

若 `bge_m3` 下载、模型加载或资源不足导致 fallback/unavailable，只记录 environment gap。该情况不能
用 hash 结果替代，也不能算作可信 `success=false` 实验。

### Open Questions

None。实现中的新架构问题或 scope 冲突必须停止并交回 Codex，不得由 opencode 自行扩大 contract。

## Verification Commands

正式 task 拆分时必须使用仓库中真实存在的测试路径；Stage 级最低门禁为：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

真实 baseline/after 与 comparison 命令会在 `tasks.md` 中按本 spec 固化，不把真实 embedding 加入默认 CI。
