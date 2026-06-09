# ADR-013: hybrid 检索字段、日志落库与 best_score 语义

- Status: Accepted (2026-06-08)
- Deciders: 用户(确认;落库=决策 C,best_score 语义采用 Option A), Claude Code(提案)
- Related: system-prd.md §6.9, decisions/ADR-007(三级 Fallback), schemas/rag.py, db/schema.sql, services/rag_log.py, services/fallback.py, rag/scoring.py

## Context

决策 C:hybrid 字段一并落库。现状 `RagSearchItem` 仅 `score`;`t_rag_retrieval_log` 仅 `best_score` / `sources`。PRD §6.9 要求新增 `rewritten_query` / `dense_score` / `bm25_score` / `reranker_score` / `fusion_rank` / `selected_chunk_id`。

关键交互:`fallback.py` 的 `best_rag_score = max(item.score)`、`RAG_LOW_SCORE = 0.5`(硬编码常量)驱动 L1→L2(ADR-007)。增强后「最佳证据分数」语义改变(多路分数 + reranker 精排)。

## Options(best_score 语义)

- **A. representative_score + 单阈值(归一化)** — `representative_score = reranker_score`(reranker 开)`else fusion_score`(hybrid 开)`else dense_score`,统一归一化到 [0,1];`fallback.best_rag_score` 改用之;`RAG_LOW_SCORE` 保持 0.5 单阈值但作用于 representative_score,并从硬编码移到 `config`。Pros: 反映最终精排证据强度;fallback 改动最小。Cons: 轻量 reranker 分数须归一化才能复用 0.5 阈值。
- **B. best_score 始终取 dense_score(保持 ADR-007 不变)** — Pros: 不动 fallback。Cons: 与「reranker 决定最终排序」矛盾,reranker 对 fallback 形同虚设。

## Decision

- 数据模型:`RagSearchItem` 增可选字段 `dense_score` / `bm25_score` / `reranker_score` / `fusion_rank` / `rewritten_query` / `selected_chunk_id`(均 Optional,MVP-0 路径为 `None`,向后兼容)。`t_rag_retrieval_log` 同步新增对应列(`schema.sql` + `rag_log` Table 同改,守红线 7);`RagLogService.build_row` 落 hybrid 字段。
- best_score 语义:采用 **A**。新增 `representative_score(item)`;`fallback.best_rag_score` 改用之;`RAG_LOW_SCORE` 移入 `config`(默认 0.5),作用于 representative_score。

## Consequences

- 触及 ADR-007 的 `fallback.py`(`best_rag_score` / `RAG_LOW_SCORE`),属跨 ADR 演进:扩展 ADR-007 的低分判定为分数维度感知,不改 fallback 状态机结构。
- `RagSearchItem` 新增字段全 Optional,`/api/v1/rag/search` 与前端契约向后兼容。
- 轻量 reranker 分数须归一化到 [0,1] 才能复用 0.5 阈值,否则 L1→L2 触发率失真(实现阶段校准)。
- hybrid 字段全程落库,支撑「增强后命中率优于纯 dense」的验收取数。
- 实现备注:`representative_score` 因 `fusion_score` 未单独入库(见 spec OQ1),落为 `reranker_score > dense_score > item.score` 的回退链。
