# Stage 22 — Architectural Decisions

## ADR-22.1: 以 Stage 21 最弱真实检索桶作为优化目标

**Slug**: `target-weakest-real-rag-miss-bucket`
**Status**: accepted
**Date**: 2026-07-08

### Context

`docs/interview/eval-harness-next-steps.md` 将 Stage D 定义为 RAG before/after 优化闭环：先基于失败类型选择一个小步优化方向，再用同一评测集复跑，记录 baseline、修改点、after 指标和副作用。

Stage 21 已完成 real embedding RAG matrix，并把 Stage D 的入口证据留在 `reports/rag_quality_matrix.md`：

- 最佳真实组合：`best_real_backend = bge_m3`，`best_real_mode = hybrid`。
- 全局指标：Hit@1 = 0.5583，Recall@5 = 0.7542，MRR = 0.6675，NDCG@5 = 0.6552。
- 最弱 miss bucket：`BANK_CLEARING / SINGLE_SIDE_MISSING`，10 cases，7 misses，Recall@5 = 0.4000。

历史 ADR 约束：

- ADR-EH.5 要求 baseline → metric-gated optimization → re-evaluation，且 before/after 必须使用同一数据集和同一评测口径。
- ADR-087 要求保持评测集标注独立，不得按检索结果重标以改善指标。
- ADR-21.4 明确 Stage 21 只交接 miss buckets，优化延后到下一阶段。

### Options Considered

- Option A: 直接优化全局 RAG 指标。
  Pros: 如果成功，简历数字更好看。
  Cons: 范围过大，难以解释是哪类失败被修复；容易同时改 chunk、query、rerank 和 threshold，污染 before/after 因果关系。
- Option B: 优先优化 `BANK_CLEARING / SINGLE_SIDE_MISSING`。
  Pros: 这是 Stage 21 真实 measured backend 下最弱 bucket；目标清晰，case 数可控，能形成“发现最弱点 → 小步修复 → 复测”的叙事。
  Cons: 可能只改善局部问题，不能保证全局 Recall@5 达到 PRD 目标。
- Option C: 优先优化 `BANK_ENTERPRISE / AMOUNT_MISMATCH`。
  Pros: 银企对账是主场景，业务相关性更直接。
  Cons: 该 bucket 不是最弱项；跳过最弱 bucket 会削弱 Stage 21 miss bucket 交接的价值。

### Decision

采用 Option B。

Stage 22 的主优化目标限定为 `BANK_CLEARING / SINGLE_SIDE_MISSING`。Baseline 固定引用 Stage 21 的 `bge_m3 / hybrid` 结果，不重标 `data/rag_eval_set.json`，不删除 case，不改变 case id，不用新的评测集证明优化效果。

Stage 22 可以在报告中记录其他 bucket 的副作用，但不把其他 bucket 的提升作为主成功口径。

### Consequences

- Positive: 优化目标来自真实 measured miss buckets，而不是凭感觉挑方向。
- Positive: Scope 足够小，适合拆成可验证 task。
- Positive: 可以直接支撑面试叙事：先定位最弱检索类型，再做单变量优化和复测。
- Negative: 本阶段即使成功，也可能只改善清算单边检索，不代表整体 RAG 达到 PRD 目标。
- Negative: 如果局部提升伴随全局指标回退，需要诚实记录副作用，不能只摘取单个 bucket 的好数字。
- Constraint: Stage 22 不允许通过修改 expected labels、删 case 或替换 eval set 来制造提升。

## ADR-22.2: 首个优化杠杆采用可搜索 chunk 上下文增强

**Slug**: `searchable-chunk-context-enrichment`
**Status**: accepted
**Date**: 2026-07-08

### Context

当前 `scripts/build_rule_chunks.py` 按 Markdown `##` section 切 chunk，但写入 `content` 时只保留 section body，不包含 `section_title`、`source_name` 或 `business_tags`。RAG dense 与 BM25 检索主要基于 `content`，因此一些已经存在于 metadata 的高价值路由信号没有进入可搜索文本。

对 `BANK_CLEARING / SINGLE_SIDE_MISSING` 来说，这个缺口很明显：

- `clearing_single_side_playbook.md` 的标题包含“非日切窗口单边核查”“证据留存要求”，但这些标题不进入 `content`。
- `clearing_query_reply_playbook.md` 的标题包含“查询发起条件”“查复所需字段”“查复回执归档”“超时未复处理”，但这些标题也不进入 `content`。
- Stage 21 miss samples 中，多条 query 正在询问“非日切”“单边缺失”“证据”“查复字段”“回执归档”等标题级语义。

### Options Considered

- Option A: 调整 eval query 或 expected labels。
  Pros: 指标可能快速变好。
  Cons: 违反 ADR-087 和 ADR-21.4；会破坏评测独立性，不能作为优化闭环证据。
- Option B: 调整 runtime threshold、RRF 参数或 reranker 行为。
  Pros: 不改知识源内容，可能影响全局排序。
  Cons: Stage 21 显示 `bge_m3 / hybrid_rerank` 已弱于 `bge_m3 / hybrid`；先调 reranker/threshold 风险较高，也更难证明只修复了哪类 miss。
- Option C: 增加 scenario/error_type 专用 filter 或 boost。
  Pros: 可以精准扶正目标 bucket。
  Cons: 当前 `RagSearchRequest` 不携带 `error_type`；引入 filter/boost 会扩大 API contract 和运行时行为，不适合作为第一步小优化。
- Option D: 在 chunk 构建阶段把已有 metadata 中的标题、来源名和业务标签压缩进可搜索 content。
  Pros: 不新增依赖，不改 API contract，不改变 eval labels；让 dense/BM25 使用已经存在的业务上下文；可通过 rebuild chunks 和同一评测集复测。
  Cons: 会影响所有 chunk 的 searchable text，可能带来全局副作用；如果上下文前缀过长，会稀释正文语义。

### Decision

采用 Option D。

Stage 22 的第一优化杠杆是“可搜索 chunk 上下文增强”：在规则 chunk 生成时，把 compact context prefix 纳入 `content`，至少覆盖 `source_name`、`section_title` 和 `business_tags` 这类已存在 metadata。该 prefix 必须是稳定、通用、由源文档元数据派生的内容，不能复制 `data/rag_eval_set.json` 的 query 文本，也不能为单个 case 硬编码关键词。

本决策只允许改 chunk 生成与由其派生的 `data/rag/rule_chunks_*.jsonl` 产物；不改运行默认 backend、不改 RAG threshold、不改 reranker 规则、不改 eval labels。

### Consequences

- Positive: 优化原因可解释：之前标题/标签只可展示，不可检索；现在让检索器看到这些稳定业务信号。
- Positive: 不扩大 API contract，适合小步 before/after。
- Positive: 对 hash、real embedding、BM25 都是同一份可复现输入变化。
- Negative: 这是全局 chunk 内容变化，不是只影响目标 bucket；必须检查其他 bucket 是否回退。
- Negative: metadata prefix 可能让短 chunk 的正文权重下降，尤其在真实 embedding 下可能带来语义噪声。
- Constraint: 不能把 eval query 原句或 expected chunk id 写入 raw source 或 chunk content。

## ADR-22.3: before/after 报告必须同时记录局部提升和全局副作用

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
