# ADR-EH.2: 系统评测使用可复现批次 + Ground Truth Manifest

**Slug**: `system-eval-ground-truth-manifest`
**Status**: accepted
**Date**: 2026-07-06

### Context

用户希望生成约 1000 条测试流水来模拟真实批次。纯随机数据不适合评测，因为无法稳定知道每条流水的正确结果；现有 `scripts/generate_mock_excel.py` 已按 ADR-090/091/093 形成“正常多数 + 异常少数”的可复现批次生成器，但当前固定样本规模较小，且 ground truth 主要存在于 `EXPECTED_BRANCHES` 这类异常子集映射中，不足以支撑系统级指标。

系统评测需要同时满足：

- 数据像真实对账批次：正常流水占多数，异常类型按比例注入。
- 结果可复现：固定 seed，同一输入多次生成完全一致。
- 每条 case 有明确预期：状态、异常类型、异常分支、是否允许自动平账、是否必须转人工。

### Options Considered

- **Option A: 纯随机生成 1000 条 Excel 后观察系统输出**
  - Pros: 看起来数据量大，实现直觉简单。
  - Cons: 缺少 ground truth，无法算准确率；每次随机变化会导致结果不可复现。
- **Option B: 手写 1000 条固定 Excel**
  - Pros: 标注可控。
  - Cons: 成本高，数据不自然，后续扩展困难。
- **Option C: 控制随机生成 + ground truth manifest（采纳）**
  - Pros: 兼顾真实感、规模、可复现和可评测；沿用现有 Faker/seed/场景化生成器设计。
  - Cons: 需要维护 manifest schema；生成逻辑比小 fixture 复杂。

### Decision

采用 **Option C**。系统评测数据由可复现生成器产出，同时产出 ground truth manifest。manifest 至少记录：

- `case_id` / `flow_id`
- `scenario_type`
- `expected_status`
- `expected_error_type`
- `expected_exception_branch`
- `should_auto_fix`
- `should_require_human`
- `risk_label`
- `notes` 或 `source_rule`

批次规模通过参数控制。默认评测批次目标为 1000+ 条总流水，比例建议从保守业务分布开始：正常自动平账多数，金额不一致、银行未到账、企业未入账、摘要/户名不一致、跨日切、手续费/税费差异、重复记账作为异常少数。具体比例放入 spec/task，不在 ADR 固化为不可调整常量。

System Eval 指标至少包括：

- `auto_fix_rate`
- `classification_accuracy`
- `branch_accuracy` 或 `macro_f1`
- `pending_human_rate`
- `fallback_trigger_rate`
- `unsafe_auto_fix_rate`，门禁目标为 0
- `hard_constraint_violation_rate`，门禁目标为 0

### Consequences

- 正向：1000+ 数据量可以成为可信的简历证据；每个指标都能追溯到 manifest。
- 负向：manifest 与生成器必须同步演进，否则会出现“数据改了、标签没改”的假失败或假通过。
- 约束：系统评测不得依赖纯随机；所有随机必须由 seed 固定；报告必须记录 seed、规模和异常分布。
