# ADR-087: 评测集语义化(承 ADR-034,直面饱和局限)

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.5)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

**Slug**: `eval-set-semantic-rewrite-and-desaturation`
**Status**: accepted
**Date**: 2026-06-23

### Context
- 现 `data/rag_eval_set.json`(ADR-034)query 是**关键词堆砌**(如 be-r002-01..10 十条同义、均指向单一 `unionpay_reconciliation_faq_001`),这是被 hash「只认 token 重合」逼出来的形态。
- ADR-034 已知局限:银企语料仅 6 chunk → `top_k=5` 下 **Recall@5 结构性饱和(恒 1.0)**,判别力靠 Hit@1(0.62)/MRR/NDCG;语料扩到 120+ 才恢复区分力。语料库近期已扩(recon-hardening corpus expansion)。
- 评测脚本 `_evaluate_case` 用 `min_score=0.0`、按 `expected_chunk_ids` 算 Hit@1/Recall@5/MRR/NDCG@5。

### Options Considered
- **A. query 自然语言化 + ground truth 重标 + 去重去饱和(采纳)** — query 改成真实问法(用户/系统会问的自然语言);ground truth 按语义相关重标(允许一 query 对多 chunk);砍重复同义灌水;结合已扩语料评估 Recall@5 是否恢复区分力。Pros: 评测真正测语义召回、与真实嵌入匹配、可对比 hash 暴露差距。Cons: 人工标注成本高、标注质量决定指标可信度(ADR-034 既有风险)。
- **B. 维持关键词 query,仅扩量** — Pros: 省事。Cons: 继续测 token 重合,与换真实嵌入的初衷矛盾。**否决**。
- **C. LLM 生成 query + 人工校验** — 用 LLM 基于语料生成自然语言 query、人工校验标注。Pros: 提效。Cons: 引入 LLM 生成偏差需校验闸;可作为 A 的辅助手段(实现期可选),不单列为方案。

### Decision
采用 **A**(C 作为可选提效手段):评测集 query 自然语言化、ground truth 语义重标、去同义灌水;保留 `scenario_type`/`error_type` 维度与 EvalCase schema。**本 stage 终点是"用语义评测集跑出 hash vs bge-m3 的对比数字、证明真实嵌入召回更优",不锁定召回硬闸**(闸拆后续 stage,避免在数据刚定稿时即锁门柱——重蹈 recon-hardening 推迟召回闸的覆辙)。

### Consequences
- 负向:标注工作量与质量风险(承 ADR-034);自然语言 query 在 hash 后端下分数会更低,但那正是要暴露的真相。
- 负向:若语料规模仍不足,Recall@5 可能仍部分饱和,须以 Hit@1/MRR/NDCG 辅判并诚实记录。
- 正向:评测集脱离 token 重合,成为真实语义召回的可信尺;为后续召回闸提供定稿数据。

### Revision 2026-06-23(真跑暴露 ground truth 错配,补标注准则)
TASK-RE.4 只做了 query 自然语言化,未落实本 ADR 的「砍同义灌水 + ground truth 语义重标」:真跑发现 BANK_ENTERPRISE 60 条中 45 条仍单 chunk 灌水,且大量 query 标到泛 FAQ(`unionpay_faq_*`)而非内容更直接的 `*_playbook_*`,致语义最强的 bge-m3 反被判死(BANK_ENTERPRISE Hit@1=0.0)。补标注准则:
- **标注独立性**:ground truth 依 query 与 chunk 内容的直接相关性标注,**不得参照任何 embedding backend 的检索结果**(防评测集向某模型过拟合)。
- **直接相关优先**:标到内容最直接回答该 query 的 chunk(可多 chunk);不预设 chunk 类型偏好,但 query 描述具体异常处理场景时须核查是否漏标对应 playbook。
- **去灌水上限**:同一 chunk 作为「唯一 expected」的 case 数设上限(建议 ≤3)。
- 标注变更逐条留痕(query / 旧 expected / 新 expected / 理由)供审查。

TASK-RE.9 落地结果:BANK_ENTERPRISE 全部重标、单 chunk 唯一-expected 上限=2;复跑(min_score=0)bge-m3 weighted Hit@1 0.5083 / Recall@5 0.7333,碾压 hash(0.1667 / 0.3875);bge-small 同向碾压(独立模型一致 = 标注未向单一模型过拟合的旁证)。
