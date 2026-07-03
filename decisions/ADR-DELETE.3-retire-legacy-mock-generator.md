# ADR-DELETE.3: 收敛 mock 数据生成入口

> 归档自 stage-delete-code scratchpad `ADR.md`。

**Slug**: `retire-legacy-mock-generator`

**Status**: accepted

**Date**: 2026-07-02

### Context

当前 `scripts/generate_mock_excel.py` 同时保留旧版 `generate_mock_excel()` 和当前 MVP1 场景生成入口 `generate_mvp1_mock_excel()`。仓库中也同时跟踪:

- `mock_data/bank_transactions.xlsx`
- `mock_data/clear_transactions.xlsx`
- `mock_data/mvp1_bank.xlsx`
- `mock_data/mvp1_clear.xlsx`

README 与现有主流程更偏向 `mvp1_*` 固定样本。旧版 `bank_transactions.xlsx` / `clear_transactions.xlsx` 与当前场景化命名并存,会增加测试入口和样本口径的歧义。

### Options Considered

- Option A: 退役旧版生成入口和旧版 Excel 样本,统一使用 `generate_mvp1_mock_excel()` 与 `mvp1_*` 文件。
  - Pros: 样本命名与场景化方向一致;减少测试夹具重复;降低脚本维护面。
  - Cons: 需要迁移仍引用旧文件名或旧函数的测试;旧文件名不再可用。
- Option B: 保留两套样本,只补文档说明差异。
  - Pros: 无需迁移测试。
  - Cons: 继续保留重复入口;使用者仍需要判断哪套才是当前标准样本。
- Option C: 删除所有 Excel 样本,测试全部运行时生成。
  - Pros: 仓库更轻。
  - Cons: 改动过大;会影响固定样本可审查性;不符合本 stage 的删除冗余目标。

### Decision

采用 Option A。

本 stage 将旧版 `generate_mock_excel()`、`mock_data/bank_transactions.xlsx`、`mock_data/clear_transactions.xlsx` 视为冗余。实现任务应先迁移仍依赖旧入口的测试,再删除旧函数和旧样本文件。

当前 stage 不改变 clearing 场景样本,不重写 mock 数据分布算法,不引入新的数据生成依赖。

### Consequences

- 正向: mock 数据入口减少到当前主线;测试和 README 对样本文件的说明更一致。
- 正向: 删除旧 Excel 样本可减少仓库中固定二进制文件数量。
- 负向: 由于 Excel 是二进制文件,删除和测试迁移需要仔细核对 diff 和回归命令。
- 负向: 如果仍有外部脚本依赖旧文件名,需要改用 `mvp1_bank.xlsx` / `mvp1_clear.xlsx`。
