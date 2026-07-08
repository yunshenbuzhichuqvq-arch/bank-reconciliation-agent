# Stage 21 — Real Embedding RAG Matrix Architectural Decisions

## ADR-21.1: Real embedding matrix 只作为诊断证据，不改变运行默认值

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

## ADR-21.2: bge_small 是最低真实 backend 要求，bge_m3 best-effort

**Slug**: `bge-small-minimum-real-backend-bge-m3-opportunistic`
**Status**: accepted
**Date**: 2026-07-08

### Context

后续补全清单中的最低要求是至少跑通一个真实 embedding backend，例如 `bge_small`，并与 hash
比较。历史 real-vs-hash 证据显示 `bge_small` 和 `bge_m3` 都在 weighted ranking metrics
上优于 hash，但 `bge_m3` 更大，更容易受本地资源、模型缓存和 CPU 性能影响。ADR-088 也明确
真实 embedding 路径是 opt-in 且与环境有关。

本阶段需要一个有价值但不过度脆弱的验收口径。

### Options Considered

- Option A: 要求 `bge_small` 和 `bge_m3` 都 measured，本阶段才算通过。
  Pros: 对比最完整。
  Cons: 阶段成败被最重模型绑定；即使项目已能证明一个真实语义 backend，`bge_m3` 缓存或资源问题
  仍会阻塞。
- Option B: 要求 `hash` 加至少 `bge_small`；`bge_m3` 尽力运行，并在报告中记录 measured 或
  unavailable。
  Pros: 满足最低真实 embedding 要求，同时保留比较更强 backend 的机会。
  Cons: 如果 `bge_m3` 不可用，报告无法完成所有目标真实 backend 对比。
- Option C: 所有真实 backend 都可选，接受 hash-only matrix。
  Pros: 总能运行。
  Cons: 重复当前 `real_backend_policy=skip` 缺口，无法支撑 real embedding quality claim。

### Decision

采用 Option B。

Matrix 必须始终测量 `hash`。要满足本阶段，必须至少产出一个 measured non-hash row，其中
`bge_small` 是最低真实 backend 要求。`bge_m3` 在本地环境支持时应尝试运行，但如果 `bge_small`
已 measured，`bge_m3` 的 unavailable row 不作为 blocking，前提是报告写清原因。

### Consequences

- Positive: 阶段可以在现实本地开发环境中完成。
- Positive: 报告仍能证明 harness 不只是 hash，而是能使用真实语义 embedding backend。
- Negative: 如果只有 `bge_small` measured，报告可能低估或遗漏 `bge_m3` 行为。
- Negative: Reviewer 必须读取 status metadata，不能假设每个 backend row 都 measured。
- Constraint: `bge_small` 或 `bge_m3` fallback 到 hash，不满足 non-hash backend 要求。

## ADR-21.3: 只有 requested backend 等于 effective backend 的矩阵行才可信

**Slug**: `trusted-effective-backend-status-metadata`
**Status**: accepted
**Date**: 2026-07-08

### Context

ADR-089 通过 effective backend 统一 collection naming、embedding dimensions 和 dense floor，修复了
fallback 后名实不符的问题。评测报告必须遵循同一原则。后续补全清单明确要求：如果 real embedding
fallback 到 hash，不能把结果宣称为 real embedding 指标。

因此 matrix 需要 row-level trust semantics，而不是只输出聚合指标。

### Options Considered

- Option A: 只记录 requested backend 和 metrics。
  Pros: 表格更简单。
  Cons: fallback 行可能静默冒充 real embedding 结果。
- Option B: 每行都记录 requested backend、effective backend、status 和 reason。
  Pros: fallback、skip、environment unavailable 都可见。
  Cons: 报告格式更冗长，部分行没有 metrics。
- Option C: 真实 backend 一旦 fallback 就 hard error。
  Pros: 不可能误读 fallback 为成功。
  Cons: 违背现有 graceful-degrade 设计，也会阻止 hash/bge partial report 产出。

### Decision

采用 Option B。

每个 backend row 必须分类为：

- `measured`: requested backend 等于 effective backend，该行 metrics 对 requested backend 有效。
- `not_run`: 根据策略有意跳过。
- `unavailable`: 已请求但不可信，通常是 effective backend 与 requested backend 不一致。

Markdown 与 JSON 报告必须包含 requested backend、effective backend、status 和 reason。`best_real_backend`
和 miss buckets 只能使用 `measured` non-hash rows。

### Consequences

- Positive: Real embedding claims 可审计，不会和 fallback 混淆。
- Positive: Environment gap 可以显式暴露，同时不阻塞 hash baseline 生成。
- Negative: 缺少模型缓存会导致 matrix 只有部分行有指标。
- Negative: 下游 triage 必须处理 `not_run` 和 `unavailable`，不能假设每行都有 metrics。
- Constraint: effective backend 为 `hash` 的行，绝不能被汇总为 real embedding measurement。

## ADR-21.4: Miss buckets 是本阶段交接产物，优化延后

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
