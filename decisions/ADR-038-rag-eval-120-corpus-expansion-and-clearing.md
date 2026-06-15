# ADR-038: RAG 评测扩到 120+——语料扩充 + 清算覆盖

- Status: Accepted (2026-06-12)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: scripts/eval_rag.py, scripts/build_rule_chunks.py, data/rag/raw_sources/{bank_enterprise,bank_clearing}/, data/rag/rule_chunks_*.jsonl, data/rag_eval_set.json, reports/rag_eval.md, decisions/ADR-034(评测 V1 承诺), decisions/ADR-018(清算场景知识分区)

## Context

ADR-034 把「120+ 条评测集 + 清算评测」留 V1。2b-3 实测发现关键问题:银企/清算语料各仅 6 个 chunk,`top_k=5` 下 `Recall@5` 恒饱和(50 条恒 1.0)。只把 query 堆到 120 条而不扩语料,指标照样饱和、测不出区分力。架构 §835 也把清算规则库扩充归在 V1。

## Options

- **A. 扩语料到去饱和规模 + 银企/清算各 ~60 条 query + markdown 报告(采纳)** — 扩 `rule_chunks_*.jsonl`(经 `build_rule_chunks` 从 `raw_sources/*.md`)到每场景 ≥ ~25 chunk(使 `top_k=5` 不再饱和);eval set 扩到 120+ 含清算;`eval_rag.py` 加清算 scenario 聚合 + 输出 `reports/rag_eval.md`。
  - Pros: Recall@5 恢复区分力、清算入评测、有可展示报告产物、兑现 PRD/ADR-034。
  - Cons: 语料 authoring 是本 stage 最大体量(写规则 chunk + 标注 `expected_chunk_ids`);标注质量决定指标可信度。
- **B. 只加 query 到 120 条,不扩语料** — Cons: 2b-3 已证饱和,等于无效扩容(否决)。
- **C. 扩语料但只银企(不含清算)** — Cons: 违背 ADR-034 的 V1 承诺(清算评测)。

## Decision

采用 **A**。语料扩到去饱和规模 + 120+ 含清算 + markdown 报告。去饱和判据:`top_k=5` 下 `Recall@5` 不再恒 1.0;`expected_chunk_ids` 须在重建 chunk 之后对照真实 chunk_id 标注。

## Consequences

- 正面:Recall@5/NDCG@5 恢复区分力、清算入评测、可展示 `reports/rag_eval.md`、兑现 2b 承诺。
- 负面:规则 chunk authoring 是本 stage 最大体量;`expected_chunk_ids` 标注须对照真实 chunk_id;若 authoring 超量,把评测从本 stage 拆出作独立 sub-stage(体量预警)。

## Implementation Note (V1-1 收尾)

实际落地:银企 31 chunk / 清算 26 chunk(均 ≥25)。120 条评测(银企/清算各 60),`test_v1_1_rag_eval_set.py` 硬断言 `expected_chunk_ids` 全部命中真实 chunk(0 缺失)。去饱和达成:银企 Recall@5=0.64(区分力充分)、清算 Recall@5=0.93(脱离饱和),两场景 Hit@1 均 < Recall@5。`eval_rag.py` 退出码 0(非门禁)。authoring 未超量,评测与 SSE 同 stage 收尾(体量预警未触发)。
