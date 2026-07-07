# ADR-17.2: RAG evidence uses backend-by-mode matrix with trusted backend metadata

**Slug**: `rag-real-embedding-matrix-evidence`
**Status**: accepted
**Date**: 2026-07-07

## Context

现有 RAG 证据有两类：

- hash baseline 已测得 `hybrid_rerank` 约为 Recall@5=0.658、MRR=0.568、NDCG@5=0.553，低于 PRD 目标。
- 历史 real embedding 报告证明 `bge_small` / `bge_m3` 在 dense 模式下优于 hash，但还不能完整回答“real embedding × hybrid/rerank 的组合是否更好”。

ADR-RQT.2 已要求 RAG quality matrix 分离 CI hash baseline 和 opt-in real embeddings。本阶段需要把这份矩阵变成简历可引用证据，而不是只作为内部诊断。

## Options Considered

- Option A: 只引用 hash baseline。Pros: 默认环境稳定、可复跑。Cons: hash embedding 不是语义检索质量的代表，简历上只写 hash 指标会削弱 RAG 说服力。
- Option B: 只跑 best real backend 的单一模式。Pros: 输出简单。Cons: 无法说明 dense / hybrid / rerank 的真实贡献，也无法和 hash baseline 公平对比。
- Option C: 固定使用 backend-by-mode matrix，并保留 effective backend / status metadata（采纳）。Pros: 能同时比较 backend 与 retrieval mode；fallback 到 hash 或未运行会被显式暴露。Cons: 跑全矩阵可能慢，`bge_m3` 对本地资源要求更高。

## Decision

采用 Option C。

RAG benchmark contract：

- Eval set 固定为 `data/rag_eval_set.json`，case count 以报告 metadata 为准，当前目标是 120 cases。
- Backends: `hash`, `bge_small`, `bge_m3`。
- Modes: `dense`, `hybrid`, `hybrid_rerank`。
- Metrics: `hit_at_1`, `recall_at_5`, `mrr`, `ndcg_at_5`。
- Ranking-quality 测量保持 `min_score=0.0`，延续 ADR-RQT.2。
- 报告必须包含 `requested_backend`、`effective_backend`、`status`、`selected_mode` 和 `reason`。
- 不能为了提升指标修改 eval labels、删除 miss case 或改写 query 到适配当前输出。
- 不因 real embedding 指标更好而自动切换生产默认或默认 DoD。

## Consequences

- 正向：可以形成“hash baseline vs bge_small/bge_m3 real embedding”的清晰数据表，适合写进简历和 PR。
- 正向：如果 real embedding 不可用，报告仍能把缺口归类为 environment gap。
- 负向：完整矩阵可能运行时间长；`bge_m3` 可能受本地模型缓存、CPU 性能和内存影响。
- 负向：如果 `hybrid_rerank` 在某些 real backend 下不提升，报告必须如实记录，不能只展示最好看的行。
