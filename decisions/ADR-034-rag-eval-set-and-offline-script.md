# ADR-034: RAG 评测集与离线评测脚本

- Status: Accepted (2026-06-11)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: scripts/eval_rag.py, data/rag_eval_set.json, rag/retriever.py(rule_retriever), tests/test_mvp2b3_eval_rag.py

## Context

PRD §3.4 行217-220 / §15.4 行1710:RAG 评测集约 50 条(银企对账核心分支各~10)+ `scripts/eval_rag.py` 输出 Recall@5/MRR/NDCG@5,按 `scenario_type`。评测集文件 `data/rag_eval_set.json`。

## Options

- **A. 银企骨架 50 条 + 离线脚本(采纳)** — `data/rag_eval_set.json`:银企 5 核心分支(对应 BE-R002/R004/R005/R006/R008 的 `error_type`)各~10 条 query,每条标注期望命中的 `chunk_id`(基于现有 `rules/` 知识库);`scripts/eval_rag.py` 调 `rule_retriever` 算 Recall@5/MRR/NDCG@5,按 `scenario_type` 分组输出;离线运行,不接主流程、不作 CI 硬门禁。
  - Pros: 对齐 PRD 骨架;为 V1(120+ 条)留扩展;离线零回归。
  - Cons: 造数据需人工标注期望 `chunk_id`;清算评测留 V1。
- **B. 含清算扩展(银企 + 清算)** — Cons: 超 PRD 2b 骨架范围;数据量翻倍。

## Decision

采用 **A**。银企 50 条骨架 + 离线脚本;清算评测、120+ 条留 V1。

## Consequences

- 正面:可量化检索质量、为 V1 扩展铺底、离线不污染主链路。
- 负面:50 条标注质量决定指标可信度;清算评测与扩容留 V1;脚本离线(非自动门禁,需手动跑)。
- 已知局限(2b3.9):现银企语料仅 6 个 chunk,`top_k=5` 下 `Recall@5` 结构性饱和(实测 50 条恒 1.0,无区分力);判别力改看 `Hit@1`(实测 0.62)/`MRR`/`NDCG@5`,脚本 `notes` 字段已注明。语料扩到 120+ 后 `Recall@5` 才恢复区分力(留 V1)。
