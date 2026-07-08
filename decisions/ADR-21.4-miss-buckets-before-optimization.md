# ADR-21.4: Miss buckets 是本阶段交接产物，优化延后

**Slug**: `miss-buckets-before-optimization`
**Status**: accepted
**Date**: 2026-07-08

### Context

后续补全清单把 Stage C 的 "Real embedding RAG matrix" 与 Stage D 的
"RAG before/after optimization" 分开。ADR-EH.5 也要求先建立 baseline，再用同一 eval set
做 metric-gated optimization。如果把 matrix 生成和 query rewrite、chunk 调整、rerank 参数调优或
relabeling 混在同一阶段，会污染 baseline。

本阶段应该识别真实 embedding 检索仍然 miss 的位置，而不是立刻修复这些 miss。

### Options Considered

- Option A: 生成 matrix 后立即调 query/chunk/reranker，直到指标提升。
  Pros: 可能在一个阶段内得到更好的数字。
  Cons: 混合诊断与修复；在 miss pattern 被审查前就有过拟合风险。
- Option B: 基于最佳 measured real backend/mode，按 scenario 和 error type 生成 miss buckets，并把修复延后到下一阶段。
  Pros: 保留干净 baseline，并为 Stage D 提供明确优化候选。
  Cons: 本阶段可能带着已知 miss 收尾。
- Option C: 通过 relabel 或删除 missed cases 让 matrix 更好看。
  Pros: 指标提升最快。
  Cons: 违反 ADR-087 的 label independence rule，破坏 eval set 可信度。

### Decision

采用 Option B。

本阶段输出应包含基于最佳 measured real backend/mode 的 miss buckets，并按 scenario 与 error type
分组。报告应指出薄弱分组，并在可行时指向 case-level misses；但本阶段的实现任务不得调整 labels、
queries、chunks、thresholds、retrieval defaults 或 reranker behavior，除非后续 ADR 明确修订范围。

### Consequences

- Positive: Stage D 可以从 measured misses 中选择小优化目标，而不是凭感觉猜。
- Positive: Real embedding matrix 保持为干净 baseline。
- Negative: 已知检索弱点会保留到下一阶段。
- Negative: 看到 misses 后可能会期待立即修复；本阶段需要明确为什么停在诊断。
- Constraint: 后续 before/after 对比必须保留相同 eval set 和 case ids。
