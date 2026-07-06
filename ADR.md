# Stage Eval Optimize — 架构决策

## ADR-EO.1: 只优化基线已证明薄弱的指标

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

## ADR-EO.2: RAG 优化使用模式对比，避免 hash 过拟合

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

## ADR-EO.3: Agent 风险修复聚焦确定性高风险语义

**Slug**: `agent-risk-high-risk-semantics`
**Status**: accepted
**Date**: 2026-07-07

### Context

Agent Eval 有 1 个明确的 risk mismatch：

- Case：`agent-high-risk-001`
- Error type：`DUPLICATE_BOOKING`
- Branch：`BE-R008`
- Expected risk：`HIGH`
- Baseline actual risk：`MEDIUM`

`AuditAgent.decide()` 已经在 `BRANCH_PROFILE` 中把 `BE-R008` 映射为 `HIGH`，
但 fake LLM 路径返回了通用 `MEDIUM` risk。由于默认 Agent Eval 使用
`FakeLLMProvider`，这个 miss 是确定性 test-provider 语义缺口，而不是真实
DeepSeek 风险模型结果的证据。

### Options Considered

- Option A：把该 eval case 的期望值改成 `MEDIUM`。
  - 优点：最快让 `risk_accuracy=1.0`。
  - 缺点：隐藏真实的高风险业务预期，并与 duplicate-booking branch profile
    冲突。
- Option B：在 Agent Eval 结果后处理阶段覆盖该 case 的 risk level。
  - 优点：改动局限在 eval script。
  - 缺点：让 evaluator 替 provider 行为兜底，可能夸大 runtime quality。
- Option C：让 deterministic fake provider 或 deterministic fallback path 尊重
  已知高风险 branch / error semantics，然后重新运行 Agent Eval。
  - 优点：保持 case label 诚实，并让 fake baseline 对齐既有 branch risk
    contract。
  - 缺点：可能需要更新那些假设 fake provider 永远返回 `MEDIUM` 的测试；
    真实 DeepSeek 质量仍然未被测量。

### Decision

采用 Option C。

Agent optimization task 应让 deterministic local evaluation 将 `BE-R008` /
`DUPLICATE_BOOKING` 识别为 `HIGH` risk，同时不得削弱既有 safety gates：

- `unsafe_auto_fix_rate` 必须保持 `0.0`。
- `hard_constraint_violation_rate` 必须保持 `0.0`。
- `decision_accuracy` 不得回退。
- Fake provider 必须保持 network-free，且不能声称代表真实 DeepSeek quality。

Real provider behavior 仍为 opt-in，不能从 fake-provider metrics 推断。

### Consequences

- 正向：Agent Eval 可以在保留高风险标签的同时，针对已知 deterministic miss
  达到 `risk_accuracy=1.0`。
- 正向：该修复强化 fake baseline，而不是为了适配当前输出去修改 evaluation
  labels。
- 负向：结果仍不能证明真实 LLM risk accuracy。
- 约束：不得为了提升指标而放松 `must_not_auto_fix`、evidence 或 hard-constraint
  rules。
