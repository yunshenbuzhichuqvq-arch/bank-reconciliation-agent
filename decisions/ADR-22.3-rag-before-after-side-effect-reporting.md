# ADR-22.3: before/after 报告必须同时记录局部提升和全局副作用

**Slug**: `rag-before-after-side-effect-reporting`
**Status**: accepted
**Date**: 2026-07-08

### Context

Stage 22 的目标不是“调到最好看数字”，而是形成可审计的优化闭环。`docs/interview/eval-harness-next-steps.md` 明确要求保留 baseline 指标、miss bucket、修改点、after 指标、是否提升、是否引入副作用。

现有 `scripts/eval_rag.py` 能生成 matrix、mode comparison 和 miss buckets，但缺少一个专门面向 before/after 的 comparison artifact。若只覆盖 `reports/rag_quality_matrix.md`，reviewer 难以看出哪些数字来自 baseline，哪些数字来自 after。

### Options Considered

- Option A: 只覆盖 `reports/rag_quality_matrix.md/json`。
  Pros: 复用现有报告，改动少。
  Cons: baseline 会被 after 覆盖；缺少一眼可见的 before/after delta 和副作用说明。
- Option B: 新增独立 before/after comparison report，同时仍刷新标准 matrix。
  Pros: baseline、after、delta、target bucket、副作用可以并列展示；标准 matrix 仍保持最新状态。
  Cons: 需要扩展评测脚本或新增小型报告脚本。
- Option C: 只在 `PR.md` 或 Report Back 中手写对比。
  Pros: 不改脚本。
  Cons: 容易出错，不可复跑；不能作为稳定工程证据。

### Decision

采用 Option B。

Stage 22 需要产出独立 before/after artifact，例如：

- `reports/rag_optimization_comparison.md`
- `reports/rag_optimization_comparison.json`

Comparison report 至少包含：

- baseline source：Stage 21 `bge_m3 / hybrid`、case_count=120、top_k=5。
- optimization summary：本阶段改动类型和不变项。
- target bucket delta：`BANK_CLEARING / SINGLE_SIDE_MISSING` 的 miss_count、Hit@1、Recall@5、MRR、NDCG@5 before/after。
- global delta：全局 Hit@1、Recall@5、MRR、NDCG@5 before/after。
- side-effect buckets：至少列出回退最大的 3 个 bucket 和提升最大的 3 个 bucket。
- trust metadata：requested backend、effective backend、mode、real_backend_policy。

验收口径：

- target bucket Recall@5 必须高于 baseline 0.4000，且 miss_count 必须低于 baseline 7，才可称为 target bucket improvement。
- 全局 MRR 与 NDCG@5 不得出现超过 0.0200 的绝对回退；若回退超过该阈值，本阶段不能宣称优化成功，只能记录为失败尝试或重新调整。
- effective backend 必须仍为 `bge_m3`；如果 fallback 到 hash，只能记录 environment gap，不能宣称 real embedding after 指标。

### Consequences

- Positive: 报告能直接回答“修了什么、提升多少、有没有副作用”。
- Positive: 避免只展示 after 数字导致 baseline 丢失。
- Positive: 可以作为面试中的真实 evidence，而不是口头描述。
- Negative: 增加报告脚本和测试范围。
- Negative: 如果本地真实 embedding 环境不可用，本阶段可能无法完成 real-backend after 证据。
- Constraint: DoD 必须复跑同一 eval set、同一 top_k、同一 requested backend/mode；不能用 hash after 结果替代 real embedding after 结果。
