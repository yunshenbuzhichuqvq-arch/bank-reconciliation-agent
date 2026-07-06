# Stage eval-harness — Architectural Decisions

## ADR-EH.1: 三层离线评测体系边界

**Slug**: `three-layer-offline-eval-harness`
**Status**: proposed
**Date**: 2026-07-06

### Context

本 stage 的目标不是先补齐全部 Agent Runtime Control、Tool Adapter、Memory 或安全优化，而是先建立可信的 baseline：系统评测、RAG 评测、Agent 评测三条线分别回答不同问题。

- 系统评测回答：一批 Excel 流水进来，最终对账结果是否正确。
- RAG 评测回答：给定业务 query，检索是否召回正确规则片段。
- Agent 评测回答：给定结构化异常、RAG evidence 和工具结果，Agent 决策是否守住 schema、证据和安全边界。

现有基础包括 `scripts/eval_rag.py`、`data/rag_eval_set.json`、`reports/rag_eval.md`、`tests/test_v1_1_agent_schema_conformance.py`、`tests/test_mvp2b3_decision_regression.py`、`scripts/generate_mock_excel.py`。本 stage 应复用这些资产，避免重造一套脱离项目现状的评测框架。

### Options Considered

- **Option A: 只做端到端系统评测**
  - Pros: 最贴近用户可见结果，简历表达直接。
  - Cons: 不能定位问题来自匹配规则、RAG 召回还是 Agent 决策；优化会变成盲改。
- **Option B: 只做 RAG / Agent 单点评测**
  - Pros: 实现快，能展示 AI 评测指标。
  - Cons: 不能证明完整对账链路有效，容易变成“模型玩具指标”。
- **Option C: 三层离线评测并行建设，系统 / RAG / Agent 各自有数据集与指标（采纳）**
  - Pros: 可定位短板；能支撑“先评测、再优化、再复测”的工程叙事；与 PRD/架构中的可观测性与评测层一致。
  - Cons: 初始工作量比单点评测更大；三套指标需要清晰口径，避免报告堆砌。

### Decision

采用 **Option C**。建立三层离线评测体系：

- **System Eval**：Excel / DataFrame 批次输入，校验最终状态、异常分类、分支、危险自动处理等。
- **RAG Eval**：query + expected chunks/tags，输出 Hit@1、Recall@5、MRR、NDCG@5。
- **Agent Eval**：结构化异常 case + evidence/tool context，输出 schema pass rate、decision accuracy、evidence citation rate、hard constraint violation rate、unsafe auto-fix rate、consistency。

三层评测均为离线脚本或 pytest 可运行入口，不接入线上 API 路径，不改变现有业务运行行为。评测产物输出 Markdown + JSON 快照，口径延续 ADR-047 的“线上聚合 + 离线快照 + 诚实缺口标注”原则。

### Consequences

- 正向：能把“系统是否有效”和“AI 子能力哪里弱”分开度量；后续优化有依据；简历和面试可以讲清指标来源。
- 负向：短期会多出评测数据、报告和测试维护成本；如果 case 标注质量低，指标仍会失真。
- 约束：没有评测报告的指标不能写成实测结论；只能写目标或设计口径。

## ADR-EH.2: 系统评测使用可复现批次 + Ground Truth Manifest

**Slug**: `system-eval-ground-truth-manifest`
**Status**: proposed
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

## ADR-EH.3: RAG 评测以去饱和和排序质量为核心

**Slug**: `rag-eval-desaturation-ranking-quality`
**Status**: proposed
**Date**: 2026-07-06

### Context

历史 ADR-034 已记录：早期语料少时 `top_k=5` 下 Recall@5 容易结构性饱和，100% 并不一定代表检索质量足够强。ADR-038 已扩展语料与评测集，使 Recall@5 恢复一定区分力。当前 stage 要避免再次只看 Recall@5，尤其不能把小集合上的 100% 直接写成“RAG 很强”。

RAG 评测应回答两个问题：

- 正确规则有没有进 top-k。
- 正确规则是否排在前面，能否给 AuditAgent 提供高质量 evidence。

### Options Considered

- **Option A: 继续只看 Recall@5**
  - Pros: 指标简单，已有脚本支持。
  - Cons: 容易被小语料/top_k 饱和误导；无法反映排序质量。
- **Option B: 扩 query 集并加入 Hit@1/MRR/NDCG@5（采纳）**
  - Pros: 能区分“召回到了但排得靠后”和“第一条就是正确证据”；适合面试解释。
  - Cons: 标注 expected chunk/tag 的工作量更高。
- **Option C: 引入 LLM-as-Judge 判断 evidence 相关性**
  - Pros: 可以覆盖语义相关但 chunk_id 未标全的情况。
  - Cons: 非确定性、成本高、当前求职冲刺阶段不适合先做。

### Decision

采用 **Option B**。本 stage 复用并扩展现有 RAG eval 口径：

- 保留 `Recall@5`。
- 明确报告 `Hit@1`、`MRR`、`NDCG@5`。
- 报告按 `scenario_type` 和 `error_type` 分组。
- 如果 `Recall@5=1.0`，报告必须同时展示 Hit@1/MRR/NDCG@5，并说明是否存在 top-k 饱和风险。

默认 CI / 常规测试继续使用 hash backend，遵守 ADR-088；真实 embedding backend 的质量评测作为 opt-in 手动报告，不把未运行的真实模型结果写成实测。

### Consequences

- 正向：RAG 指标更可信，不会被 Recall@5 单点数字误导。
- 负向：需要维护更多 query 和 expected 标注；不同 embedding backend 的报告不能混写。
- 约束：报告必须标注 embedding backend、top_k、eval set 版本和评测时间。

## ADR-EH.4: Agent 评测优先规则判定，不先引入 LLM-as-Judge

**Slug**: `agent-eval-rule-based-before-llm-judge`
**Status**: proposed
**Date**: 2026-07-06

### Context

现有 Agent 相关测试主要覆盖 schema conformance、固定 fake provider 决策分布和部分 workflow 行为。它能证明“输出结构合法”，但还不足以证明“决策质量可评估”。Agent 评测需要针对 AuditAgent 的金融安全边界：无证据不能自动判定，非人工决策必须有 evidence，危险自动平账必须为 0。

当前阶段的目标是快速形成可复现、可讲清的评测证据，而不是建立复杂的主观评分体系。

### Options Considered

- **Option A: 只保留 schema conformance**
  - Pros: 已有基础，成本低。
  - Cons: 只能证明 JSON 合法，不能证明决策是否对。
- **Option B: 规则判定 Agent Eval（采纳）**
  - Pros: 确定性强、便于 pytest、能直接覆盖安全红线；适合当前求职冲刺。
  - Cons: 对“解释文字质量”的评价有限。
- **Option C: LLM-as-Judge 多维评分**
  - Pros: 可以评价理由完整性、表达质量和复杂 case。
  - Cons: 非确定性、成本高、需要 judge prompt 和复核机制；本 stage 先不做。

### Decision

采用 **Option B**。Agent Eval case 使用结构化输入和规则化期望，不先引入 LLM-as-Judge。每个 case 至少包含：

- `case_id`
- `error_type`
- `exception_branch`
- `bank_amount`
- `clear_amount`
- `amount_diff`
- `rag_evidence`
- `tool_result` 或 `trace_context`
- `expected_decision`
- `expected_risk_level`
- `must_include_evidence`
- `must_not_auto_fix`

Agent Eval 指标至少包括：

- `schema_pass_rate`
- `decision_accuracy`
- `evidence_citation_rate`
- `no_evidence_to_human_rate`
- `hard_constraint_violation_rate`，门禁目标为 0
- `unsafe_auto_fix_rate`，门禁目标为 0
- `decision_consistency_rate`

真实 provider 下允许统计分布而非断言具体自然语言；fake provider 下作为确定性 baseline。

### Consequences

- 正向：Agent 评测可以直接覆盖面试最容易被追问的安全问题：为什么不会乱自动平账。
- 负向：暂时不能量化“解释是否足够像资深审计员”；这类主观质量留给后续 LLM-as-Judge 或人工 review。
- 约束：任何 `unsafe_auto_fix_rate > 0` 或 `hard_constraint_violation_rate > 0` 都视为 blocking，不允许作为优化成功结果。

## ADR-EH.5: Baseline → Metric-Gated Optimization → Re-evaluation

**Slug**: `baseline-metric-gated-optimization-reeval`
**Status**: proposed
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
