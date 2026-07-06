# ADR-EH.5: Baseline → Metric-Gated Optimization → Re-evaluation

**Slug**: `baseline-metric-gated-optimization-reeval`
**Status**: accepted
**Date**: 2026-07-06

### Context

用户当前目标是尽快形成求职材料和面试可讲内容。最有价值的工程叙事不是“一次性实现所有深度优化”，而是：

1. 先建立 baseline。
2. 用指标定位最弱点。
3. 只做 1-2 个边界清晰的优化。
4. 用同一套数据复跑，展示 before/after。

如果在 baseline 前预先实现 Runtime Control、Tool Adapter、Historical Case Store、Untrusted Boundary 等全部优化，会耗费大量时间，且无法证明优化确实改善了哪个指标。

### Options Considered

- **Option A: 先实现完整工程深度优化，再统一评测**
  - Pros: 最终系统更完整。
  - Cons: 工期长，求职冲刺不划算；缺少 baseline 对照，优化价值难证明。
- **Option B: baseline 后根据最弱指标选择小优化（采纳）**
  - Pros: 时间可控；每个优化都有指标依据；面试叙事清晰。
  - Cons: 需要在 baseline 报告后增加一次任务调整或 review gate。
- **Option C: 只做 baseline，不做优化**
  - Pros: 最快形成数据。
  - Cons: 缺少“发现问题并改进”的工程闭环。

### Decision

采用 **Option B**。本 stage 的实施顺序固定为：

1. 建立三层 baseline eval。
2. 输出 baseline report。
3. Codex 根据 baseline 报告选择最多 1-2 个小优化方向，并更新 spec/tasks；若涉及新的非平凡设计取舍，先修订 ADR。
4. opencode 实现选定优化。
5. 使用同一 eval set、同一 seed、同一 case id 复跑。
6. 输出 comparison report。

优化选择规则：

- 如果 System Eval 分类/分支指标最弱，优先优化异常路由、生成数据覆盖或规则分支。
- 如果 RAG Hit@1/MRR 最弱，优先优化 query、chunk/tag 或 rerank 配置。
- 如果 Agent Eval 出现安全红线失败，优先优化 hard constraints、无证据转人工或 prompt evidence contract。
- 如果耗时/成本问题突出，再考虑 cache、减少 Agent 调用或批处理；非本 stage 默认重点。

不在 baseline 前预设具体优化实现，不在本 stage 一次性落完 Runtime Control、Tool Adapter、Historical Case Store、Untrusted Boundary 全量方案。

### Consequences

- 正向：能形成“评测驱动优化”的闭环，适合简历 bullet 和面试追问。
- 负向：baseline 之后可能需要修订 `ADR.md` / `spec.md` / `tasks.md`；stage 中间会有一个人工 review gate。
- 约束：before/after 对比必须来自同一数据集和同一评测口径；不能用不同数据集的数字证明优化效果。
