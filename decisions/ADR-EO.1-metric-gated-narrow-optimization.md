# ADR-EO.1: 只优化基线已证明薄弱的指标

**Slug**: `metric-gated-narrow-optimization`
**Status**: accepted
**Date**: 2026-07-07

### Context

`stage-eval-harness` 已进入 `main`，提供了
`decisions/ADR-EH.5-baseline-metric-gated-optimization-reeval.md` 要求的优化基线。

当前 combined baseline：

- System Eval：`classification_accuracy=1.0`, `branch_accuracy=1.0`,
  `unsafe_auto_fix_rate=0.0`, `hard_constraint_violation_rate=0.0`.
- RAG Eval：`Hit@1=0.1667`, `Recall@5=0.3875`, `MRR=0.2750`,
  `NDCG@5=0.2824`，运行条件为 `embedding_backend=hash`。
- Agent Eval：`decision_accuracy=1.0`, `risk_accuracy=0.8333`,
  `unsafe_auto_fix_rate=0.0`, `hard_constraint_violation_rate=0.0`.

基线只指向两个明确薄弱点：RAG 排序质量，以及 1 个 Agent 风险等级误判。
System Eval 已经通过；没有新证据时，不应修改 System Eval 行为。

### Options Considered

- Option A：本 stage 同时优化三层评测。
  - 优点：可能带来更多表面指标提升。
  - 缺点：System Eval 已经通过；继续修改会在缺少基线证据的情况下扩大范围，
    并增加回归风险。
- Option B：只优化 RAG，因为它的指标最低。
  - 优点：最聚焦于数值上最明显的短板。
  - 缺点：会留下一个已知且清晰定位的 Agent 风险等级误判，即使该问题范围很小。
- Option C：只优化 RAG 排序与 Agent 风险准确率，然后重新运行同一套
  baseline / comparison reports。
  - 优点：符合 ADR-EH.5，把范围限制在 1-2 个定向改动，并能形成
    before / after 对比。
  - 缺点：不处理延迟、成本、真实 LLM 质量、线上采纳率，也不扩展 Agent
    解释质量。

### Decision

采用 Option C。

本 stage 仅限于：

1. 使用同一份 `data/rag_eval_set.json` 与可比指标，做 RAG 排序优化和复评。
2. 修正已知高风险样本的 Agent 风险等级误判，然后重新运行 Agent Eval 和
   combined harness。

范围外：

- 不修改 System Eval 行为。
- 不做前端改动。
- 不修改 API contract。
- 不做数据库 schema migration。
- 不引入 LLM-as-Judge。
- 默认 DoD 不依赖网络。
- 不引入新的第三方依赖。

### Consequences

- 正向：本 stage 可以展示清晰的 baseline → targeted fix → re-eval 闭环。
- 正向：范围足够小，opencode 可以在不大规模扰动生产链路的前提下实现和验证。
- 负向：一些已知真实缺口仍不测量，尤其是真实 LLM 质量、线上人工 override
  行为、延迟和成本。
- 约束：before / after 数字必须来自同一份 eval set 和 seed；如果某个指标来自
  不同 evaluation contract，不能宣称它相对基线提升。
