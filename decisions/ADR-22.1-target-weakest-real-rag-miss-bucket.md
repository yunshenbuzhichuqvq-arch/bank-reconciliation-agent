# ADR-22.1: 以 Stage 21 最弱真实检索桶作为优化目标

**Slug**: `target-weakest-real-rag-miss-bucket`
**Status**: accepted
**Date**: 2026-07-08

### Context

`docs/interview/eval-harness-next-steps.md` 将 Stage D 定义为 RAG before/after 优化闭环：先基于失败类型选择一个小步优化方向，再用同一评测集复跑，记录 baseline、修改点、after 指标和副作用。

Stage 21 已完成 real embedding RAG matrix，并把 Stage D 的入口证据留在 `reports/rag_quality_matrix.md`：

- 最佳真实组合：`best_real_backend = bge_m3`，`best_real_mode = hybrid`。
- 全局指标：Hit@1 = 0.5583，Recall@5 = 0.7542，MRR = 0.6675，NDCG@5 = 0.6552。
- 最弱 miss bucket：`BANK_CLEARING / SINGLE_SIDE_MISSING`，10 cases，7 misses，Recall@5 = 0.4000。

历史 ADR 约束：

- ADR-EH.5 要求 baseline → metric-gated optimization → re-evaluation，且 before/after 必须使用同一数据集和同一评测口径。
- ADR-087 要求保持评测集标注独立，不得按检索结果重标以改善指标。
- ADR-21.4 明确 Stage 21 只交接 miss buckets，优化延后到下一阶段。

### Options Considered

- Option A: 直接优化全局 RAG 指标。
  Pros: 如果成功，简历数字更好看。
  Cons: 范围过大，难以解释是哪类失败被修复；容易同时改 chunk、query、rerank 和 threshold，污染 before/after 因果关系。
- Option B: 优先优化 `BANK_CLEARING / SINGLE_SIDE_MISSING`。
  Pros: 这是 Stage 21 真实 measured backend 下最弱 bucket；目标清晰，case 数可控，能形成“发现最弱点 → 小步修复 → 复测”的叙事。
  Cons: 可能只改善局部问题，不能保证全局 Recall@5 达到 PRD 目标。
- Option C: 优先优化 `BANK_ENTERPRISE / AMOUNT_MISMATCH`。
  Pros: 银企对账是主场景，业务相关性更直接。
  Cons: 该 bucket 不是最弱项；跳过最弱 bucket 会削弱 Stage 21 miss bucket 交接的价值。

### Decision

采用 Option B。

Stage 22 的主优化目标限定为 `BANK_CLEARING / SINGLE_SIDE_MISSING`。Baseline 固定引用 Stage 21 的 `bge_m3 / hybrid` 结果，不重标 `data/rag_eval_set.json`，不删除 case，不改变 case id，不用新的评测集证明优化效果。

Stage 22 可以在报告中记录其他 bucket 的副作用，但不把其他 bucket 的提升作为主成功口径。

### Consequences

- Positive: 优化目标来自真实 measured miss buckets，而不是凭感觉挑方向。
- Positive: Scope 足够小，适合拆成可验证 task。
- Positive: 可以直接支撑面试叙事：先定位最弱检索类型，再做单变量优化和复测。
- Negative: 本阶段即使成功，也可能只改善清算单边检索，不代表整体 RAG 达到 PRD 目标。
- Negative: 如果局部提升伴随全局指标回退，需要诚实记录副作用，不能只摘取单个 bucket 的好数字。
- Constraint: Stage 22 不允许通过修改 expected labels、删 case 或替换 eval set 来制造提升。
