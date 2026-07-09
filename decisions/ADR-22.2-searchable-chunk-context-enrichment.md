# ADR-22.2: 首个优化杠杆采用可搜索 chunk 上下文增强

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
