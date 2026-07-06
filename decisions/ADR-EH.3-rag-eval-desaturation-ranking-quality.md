# ADR-EH.3: RAG 评测以去饱和和排序质量为核心

**Slug**: `rag-eval-desaturation-ranking-quality`
**Status**: accepted
**Date**: 2026-07-06

### Context

历史 ADR-034 已记录：早期语料少时 `top_k=5` 下 Recall@5 容易结构性饱和，100% 并不一定代表检索质量足够强。ADR-038 已扩展语料与评测集，使 Recall@5 恢复一定区分力。当前 stage 要避免再次只看 Recall@5，尤其不能把小集合上的 100% 直接写成“RAG 很强”。

RAG 评测应回答两个问题：

- 正确规则有没有进 top-k。
- 正确规则是否排在前面，能否给 AuditAgent 提供高质量 evidence。

### Options Considered

- **Option A: 继续只看 Recall@5**
  - Pros: 指标简单，已有脚本支持。
  - Cons: 容易被小语料/top_k 饱和误导；无法反映排序质量。
- **Option B: 扩 query 集并加入 Hit@1/MRR/NDCG@5（采纳）**
  - Pros: 能区分“召回到了但排得靠后”和“第一条就是正确证据”；适合面试解释。
  - Cons: 标注 expected chunk/tag 的工作量更高。
- **Option C: 引入 LLM-as-Judge 判断 evidence 相关性**
  - Pros: 可以覆盖语义相关但 chunk_id 未标全的情况。
  - Cons: 非确定性、成本高、当前求职冲刺阶段不适合先做。

### Decision

采用 **Option B**。本 stage 复用并扩展现有 RAG eval 口径：

- 保留 `Recall@5`。
- 明确报告 `Hit@1`、`MRR`、`NDCG@5`。
- 报告按 `scenario_type` 和 `error_type` 分组。
- 如果 `Recall@5=1.0`，报告必须同时展示 Hit@1/MRR/NDCG@5，并说明是否存在 top-k 饱和风险。

默认 CI / 常规测试继续使用 hash backend，遵守 ADR-088；真实 embedding backend 的质量评测作为 opt-in 手动报告，不把未运行的真实模型结果写成实测。

### Consequences

- 正向：RAG 指标更可信，不会被 Recall@5 单点数字误导。
- 负向：需要维护更多 query 和 expected 标注；不同 embedding backend 的报告不能混写。
- 约束：报告必须标注 embedding backend、top_k、eval set 版本和评测时间。
