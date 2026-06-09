# ADR-009: 增强 RAG 重模型策略 —— 接口抽象 + 轻量默认实现

- Status: Accepted (2026-06-08)
- Deciders: 用户(拍板,决策 A), Claude Code(提案)
- Related: system-prd.md §11.1, AGENTS.md 红线4, decisions/ADR-005(Provider 模式), rag/embedding.py, rag/rerank.py

## Context

PRD §11.1 字面指定 Embedding = BGE-large-zh-v1.5、Reranker = BGE-Reranker-v2-m3(各约 1–2GB,需 `torch` / `sentence-transformers` / `FlagEmbedding`)。但存在三重约束冲突:

- PRD 的 pyproject 计划依赖片段(§附录)只列 `jieba`、`rank-bm25`,未列任何 BGE/torch 依赖。
- AGENTS.md 红线 4「不引入未在 spec 注明的新依赖」、红线「本地资源不足时主链路仍可运行」。
- DoD 须 `uv run pytest` 在无 GPU、SQLite 测试库下跑绿。
- 现状 Dense 用 `HashEmbeddingFunction`(128 维确定性占位),非真语义向量。

## Options

- **A. 接口抽象 + 轻量默认实现** — Pros: 不引重依赖、DoD 可跑绿、守红线 4、对齐 ADR-005 的 Provider 模式;检索质量提升来自 Hybrid + RRF 的结构化召回。Cons: 未验证真 BGE 的语义检索质量,「显著优于纯 dense」主要靠 BM25 贡献而非语义向量升级。
- **B. 真引入 BGE 双模型,默认开** — Pros: 对齐 PRD 字面、语义检索质量最高。Cons: 2–3GB 模型下载、CI/本地慢、违红线 4、DoD 难在无 GPU 跑绿。
- **C. BGE 作为 optional extra,默认关** — Pros: 可演示真模型 + 默认可跑绿。Cons: 维护轻/重两套代码路径,复杂度高,2a-2 阶段收益不抵成本。

## Decision

采用 **A**。本 stage 新增依赖仅 `jieba`、`rank-bm25`。定义两个 Protocol:

- `EmbeddingProvider`:默认实现 = 把现有 hash embedding 包装为 `HashEmbeddingProvider`。
- `Reranker`:默认实现 = 确定性轻量实现 `LexicalReranker`(基于 query↔doc token 重叠 / 召回分数的单调归一打分)。
- BGE 实现仅预留接口位置 + TODO 注释,不写实现、不加依赖(留 V1/V2)。

## Consequences

- 「增强后命中率/相关度显著优于纯 dense」的验收,需在评测中体现 Hybrid + RRF 相对单路 dense 的提升,而非依赖语义向量升级。
- `LexicalReranker` 分数语义判别力弱于 cross-encoder;PRD §11.1 的 reranker 阈值需按轻量实现的分数分布校准。
- 未来切真 BGE 只需新增 Provider 实现 + optional extra,不动管线编排(受益于 ADR-010 的分层)。
