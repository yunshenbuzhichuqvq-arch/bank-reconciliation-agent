# ADR-21.1: Real embedding matrix 只作为诊断证据，不改变运行默认值

**Slug**: `real-embedding-matrix-diagnostic-scope`
**Status**: accepted
**Date**: 2026-07-08

### Context

`docs/interview/eval-harness-next-steps.md` 将 "Real embedding RAG matrix" 放在已完成的
Agent Eval 扩容之后。当前缺口不是单一 dense real embedding 能否优于 hash；
`reports/rag_eval_real_vs_hash.md` 已记录 `bge_small` 和 `bge_m3` 在 dense 模式下优于
hash。真正缺口是完整的 backend-by-mode matrix：

- backends: `hash`, `bge_small`, `bge_m3`
- modes: `dense`, `hybrid`, `hybrid_rerank`
- metrics: Hit@1, Recall@5, MRR, NDCG@5

历史 ADR 已限定本阶段边界：

- ADR-083 接受本地真实 embedding 替代 hash 来获得语义检索能力。
- ADR-088 要求默认测试和 CI 仍使用 hash。
- ADR-089 要求 fallback 后以 effective backend 作为唯一事实源。
- ADR-RQT.2 与 ADR-17.2 要求输出 backend-by-mode matrix 证据。
- ADR-086 要求 RAG ranking evaluation 维持 `min_score=0.0`。

当前 `reports/rag_quality_matrix.md` 仍是 `real_backend_policy=skip`，只测量 hash，并把真实
backend 标记为 `not_run`。

### Options Considered

- Option A: 现在就把默认 RAG runtime 和 DoD 切到最佳真实 embedding backend。
  Pros: 运行时行为更贴近语义检索目标。
  Cons: 违反 ADR-088；默认流程会依赖本地模型缓存和 CPU 成本；在 matrix 证明
  backend/mode 组合之前就改变生产行为。
- Option B: 只重跑已有 dense real-vs-hash 报告。
  Pros: 范围小，现有能力已有基础。
  Cons: 仍无法回答真实 embedding 下 hybrid/rerank 是否有效，也无法关闭 Stage C 缺口。
- Option C: 输出 opt-in backend-by-mode 诊断矩阵，同时保持运行默认值不变。
  Pros: 直接补齐证据缺口；保留确定性的默认测试；为下一阶段优化提供 real miss buckets。
  Cons: 产物主要是诊断报告，不会直接改变用户可见运行行为。

### Decision

采用 Option C。

本阶段只把 real embedding RAG matrix 作为 opt-in diagnostic evidence。不得改变 production
RAG default、默认 DoD、CI 假设、RAG threshold 或 eval label。运行时行为继续由既有 settings
和历史 ADR 约束，除非后续 ADR 明确修改默认值。

### Consequences

- Positive: 可以区分 hash baseline 质量与真实语义检索质量，并且比较同一组 retrieval modes。
- Positive: 报告明确 measured backend 和 mode，适合在面试中引用。
- Negative: 本阶段本身可能不提升任何生产指标。
- Negative: 没有本地模型缓存的机器可能只产出 environment gap，而不是完整 real-backend rows。
- Constraint: 任何宣称 real embedding quality 的报告行，都必须显示 effective non-hash backend。
