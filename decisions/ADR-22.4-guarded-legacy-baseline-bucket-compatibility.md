# ADR-22.4: 对 Stage 21 旧格式 baseline 采用受保护 bucket 兼容读取

**Slug**: `guarded-legacy-baseline-bucket-compatibility`
**Status**: accepted
**Date**: 2026-07-09

### Context

TASK-22.6 修复了 before/after comparison 的一个真实口径问题：`reports/rag_quality_matrix.json`
顶层 `miss_buckets` 只代表 `best_real_backend / best_real_mode`，不能无条件当作任意 requested
`backend/mode` 的 bucket 指标。修复后，after matrix 为每个 measured mode 输出
`rows[backend]["modes"][mode]["bucket_metrics"]`。

但 Stage 21 baseline 是旧格式报告，尚未包含 per-mode `bucket_metrics`。它只包含顶层
`miss_buckets`。Stage 21 同时明确记录：

- `best_real_backend = bge_m3`
- `best_real_mode = hybrid`
- Stage 22 requested comparison 也是 `backend=bge_m3`, `mode=hybrid`

因此旧 baseline 的顶层 `miss_buckets` 在这个特定组合上语义上等同于
`bge_m3 / hybrid` 的 bucket metrics；问题是必须防止这种兼容逻辑被泛化到 after matrix 或其他 mode。

### Options Considered

- Option A: 拒绝所有旧格式 baseline，要求未来 stage 重新生成 baseline。
  Pros: 实现最严格，避免任何兼容分支。
  Cons: 当前 Stage 22 无法完成同一评测口径的可信 failure artifact；需要把已完成的真实 after 证据推迟到未来 stage。
- Option B: 无条件从顶层 `miss_buckets` 回退读取。
  Pros: 最省事，能恢复报告。
  Cons: 会重新引入 TASK-22.6 修复的 mode-mixing bug；当 `best_real_mode != requested mode` 时会产生错误对比。
- Option C: 仅当 `best_real_backend == requested backend` 且 `best_real_mode == requested mode` 时，允许旧格式顶层 `miss_buckets` 作为 baseline bucket metrics。
  Pros: 既能使用 Stage 21 真实 baseline，又用元数据 gate 阻止 mode 混用；after 新格式仍优先使用 per-mode bucket metrics。
  Cons: 增加一个 legacy compatibility 分支和测试；仅适用于包含可信 `best_real_backend/best_real_mode` 元数据的旧 matrix。

### Decision

采用 Option C。

`build_optimization_comparison_report(...)` 的 bucket metrics 来源顺序为：

1. 优先读取 `rows[backend]["modes"][mode]["bucket_metrics"]`。
2. 如果缺失，仅当 `matrix["best_real_backend"] == backend` 且 `matrix["best_real_mode"] == mode` 时，允许读取顶层 `matrix["miss_buckets"]`。
3. 其他情况必须让 `trust.trusted == false`，并写明缺少 requested mode bucket metrics 或 legacy top-level bucket 与 requested mode 不匹配。

该兼容只用于 before/after comparison 的报告读取，不改变 matrix 生成逻辑、不改变检索行为、不改变 eval labels。

若 corrected comparison `trust.trusted == true` 但 `success == false`，Stage 22 可以作为“可信失败优化尝试”收尾；不能称为 target bucket optimization success，但可以交付失败原因、全局副作用和下一步优化依据。

### Consequences

- Positive: Stage 22 可以继续使用 Stage 21 已归档的真实 `bge_m3 / hybrid` baseline，而不是伪造或重标 baseline。
- Positive: 兼容路径有明确 metadata gate，不会再次混用 selected mode 和 requested mode。
- Positive: 可信失败结果仍可作为工程闭环证据：优化假设被同一口径否定。
- Negative: 报告逻辑需要同时支持新旧两种 matrix 形态，测试复杂度增加。
- Negative: 如果旧 baseline 缺少或误写 `best_real_backend/best_real_mode`，comparison 必须拒绝信任，不能自动猜测。
- Constraint: 兼容读取不能用于 after matrix 的任意 mode 兜底；只有 metadata 精确匹配 requested backend/mode 时才可使用顶层 `miss_buckets`。
