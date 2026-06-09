# ADR-010: 增强 RAG 管线分层与可开关编排

- Status: Accepted (2026-06-08)
- Deciders: 用户(确认), Claude Code(提案)
- Related: system-prd.md §11, schemas/rag.py, rag/retriever.py, rag/{sparse,fusion,rerank,query_rewrite}.py, decisions/ADR-009

## Context

现状 `RuleRetriever.search()` = 单段 ChromaDB dense 查询。需扩展为 `Query Rewrite → Dense + BM25 双路 → RRF → Reranker Top-5`,且每段可开关(PRD:Reranker / Query Rewrite 必须可开关,本地资源不足时主链路仍可运行)。`schemas/rag.py` 已占位 `enable_rewrite` / `enable_hybrid`(default `False`)。约束:现有 `tests/test_rag_ingestion.py` 必须不回归。

## Options

- **A. 单体 retriever 内 if-else 堆叠** — Pros: 改动集中。Cons: `search()` 膨胀、各段难独立单测、违简洁与单一职责。
- **B. 分层组件编排** — `QueryRewriter` / `DenseRetriever` / `SparseRetriever(BM25)` / `fuse_rrf` / `Reranker`,`RuleRetriever` 作编排入口。Pros: 每段单一职责、可独立单测、开关即「跳过某段」、向后兼容。Cons: 文件数增加。
- **C. 策略模式 + 注册表** — Pros: 极致可扩展。Cons: 2a-2 无多策略需求,过度设计。

## Decision

采用 **B**。`rag/` 下新增:`query_rewrite.py`、`sparse.py`(BM25)、`fusion.py`(RRF)、`rerank.py`。`RuleRetriever.search()` 升级为编排:`rewrite?(可选)→ dense Top-N ∥ bm25 Top-N(enable_hybrid)→ RRF 融合 → rerank Top-5(enable_reranker)→ 阈值过滤`。新增 `enable_reranker` 开关(`config` + `RagSearchRequest`)。所有开关默认值保持「关闭 = MVP-0 纯 dense 行为」,保证 `test_rag_ingestion` 不回归。

## Consequences

- `search()` 契约保持(入参 `RagSearchRequest`、出参 `RagSearchResponse`),仅 item 增可选 hybrid 分数字段(见 ADR-013)。
- BM25 索引与 ChromaDB 必须同源同步(同一 `rule_chunks` 集合),同步点在 ingestion;否则双路召回的 chunk 集合不一致。
- 开启增强路径需 `jieba` / `rank-bm25` 就绪;未安装时开关强制视为关闭并 structlog 告警(降级,不崩)。
