# ADR-21.3: 只有 requested backend 等于 effective backend 的矩阵行才可信

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
