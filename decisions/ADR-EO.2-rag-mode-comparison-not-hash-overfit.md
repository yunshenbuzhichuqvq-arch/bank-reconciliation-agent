# ADR-EO.2: RAG 优化使用模式对比，避免 hash 过拟合

**Slug**: `rag-mode-comparison-not-hash-overfit`
**Status**: accepted
**Date**: 2026-07-07

### Context

combined baseline 使用 `embedding_backend=hash`，因为默认 DoD 必须本地、
确定性、CI 友好。历史 real-embedding 报告已经显示，在同一份 120-case
eval set 上，`bge_m3` 与 `bge_small` 明显优于 hash：

- hash weighted：`Hit@1=0.1667`, `Recall@5=0.3875`, `MRR=0.2750`,
  `NDCG@5=0.2824`.
- bge_m3 weighted：`Hit@1=0.5083`, `Recall@5=0.7333`, `MRR=0.6349`,
  `NDCG@5=0.6271`.
- bge_small weighted：`Hit@1=0.5417`, `Recall@5=0.6667`, `MRR=0.6389`,
  `NDCG@5=0.6045`.

当前 `scripts/eval_rag.py` 的完整 eval-set 路径只发起普通 `RagSearchRequest`，
即 `enable_hybrid=False` 且 `enable_reranker=False`。旧 smoke 路径可以对比
`dense` 与 `hybrid_rerank`，但 120-case 报告没有暴露完整 eval-set 的
mode comparison。

### Options Considered

- Option A：调 hash embeddings 或 eval labels，直到 hash 指标上升。
  - 优点：可能快速提升默认基线数字。
  - 缺点：有对最弱 backend 过拟合的风险，也会破坏 ADR-087 建立的语义
    eval-set 完整性。
- Option B：把默认 DoD 和 combined baseline 切到 real embeddings。
  - 优点：RAG 指标更强，也更贴近语义检索。
  - 缺点：违反 ADR-088；默认测试会依赖大型本地模型和潜在下载，不适合 CI。
- Option C：保留 hash 作为确定性默认值，为现有检索模式增加完整 eval-set
  对比，并把 real embedding 保持为 opt-in / manual evidence。
  - 优点：提升可观测性；只有当同一 eval set 证明某个模式更好时，本 stage
    才采纳该模式，同时不改变 CI 假设。
  - 缺点：如果现有 hybrid / rerank 模式没有提升指标，本 stage 必须如实记录
    RAG 无提升，而不是强行制造提升。

### Decision

采用 Option C。

RAG task 应扩展 evaluation / reporting，使 120-case eval set 至少可以对比：

- `dense` / 当前 plain retrieval。
- `hybrid` / Dense + BM25 + RRF.
- `hybrid_rerank` / Dense + BM25 + RRF + 现有 lexical reranker。

默认 DoD 继续使用 `embedding_backend=hash`，并保持 network-free。Real embedding
运行仍为 opt-in，且必须写入带 backend metadata 的独立报告。只有当同一 eval set
显示 `Hit@1`、`MRR` 或 `NDCG@5` 明确提升，且不降低 safety gates 时，本 stage
才可以选择 after-baseline RAG mode。

### Consequences

- 正向：RAG 优化变成 evidence-driven，避免 relabeling 或 hash-specific hacks。
- 正向：comparison report 可以解释薄弱点来自 hash backend、retrieval mode，
  还是两者都有。
- 负向：增加 mode comparison 会提高报告和测试复杂度。
- 负向：现有 lexical reranker 可能无法提升语义质量；这种结果必须如实记录，
  不能隐藏。
- 约束：不能仅为了提高离线数字就修改生产 RAG defaults；除非 task 明确证明
  runtime behavior 仍然安全，且 config boundary 仍为 opt-in / env-driven。
