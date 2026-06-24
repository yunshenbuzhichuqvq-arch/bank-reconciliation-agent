# ADR-086: dense 阈值按真实嵌入重新校准(承 ADR-082)

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.4)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

**Slug**: `dense-threshold-recalibration-for-real-embedding`
**Status**: accepted
**Date**: 2026-06-23

### Context
- ADR-082 把 `rag_dense_min_score` 校准到 **0.341**,明确这是 **hash 占位口径**(实测有据 0.35–0.43、正交≈0.33);架构 §6.7 的 **0.5 是真实语义嵌入口径**,并预告「floor 待真实嵌入随闸复校」。
- bge-m3 / bge-small 的分数分布(余弦/距离→score 经 `_score_from_distance`)与 hash 完全不同口径,0.341 对真实模型无意义。
- floor 影响主链路「无据→PENDING_HUMAN」护栏(§6.7 / ADR-082)与 SSE 断言 `_has_readable_decision_and_evidence`。

### Options Considered
- **A. 每后端独立 floor + 实测校准(采纳)** — `rag_dense_min_score` 随 backend 取值(hash 保留 0.341;bge-m3 / bge-small 各自实测校准)。Pros: 各后端口径正确、护栏在真实嵌入下才真正成立。Cons: 配置项随后端分叉,须实测取值并留痕。
- **B. 单一 floor 沿用 0.341** — Pros: 不动配置。Cons: 对真实模型是错值,误杀或漏挡,使护栏失真。**否决**。
- **C. 本 stage 不接 floor(min_score=0)** — Pros: 省校准。Cons: 退回 ADR-082 修复前的「护栏形同虚设」,倒退。**否决**。

### Decision
采用 **A**:floor 随 `embedding_backend` 取值;bge-m3/bge-small 的校准值由实测定(量「正确命中规则最低分」与「完全无关 query 基线」,取其间),实测数据在实现期留痕。**不迁就 SSE 断言**:真实嵌入下有据场景 evidence 应自然非空、断言自然过(承 ADR-082 立场,改断言接受空 evidence=掩盖退化,否决)。同步更新 `test_mvp2a2_schema_config.py` 的阈值断言(`eval_rag` 评测口径见下方 Revision:dense floor 仅生产 / SSE 护栏,召回评测维持 `min_score=0.0`、不施 floor 过滤)。

实测落地值(TASK-RE.8/RE.9 复校):`rag_dense_min_score`=0.341(hash)、`rag_dense_min_score_bge_small`=0.507、`rag_dense_min_score_bge_m3`=0.510;均落在「无关 query 最高分」与「正确命中最低分」之间,接近架构 §6.7 的 0.5。

### Consequences
- 负向:多一组按 backend 的阈值,须文档化每个值的实测来源。
- 负向:真实嵌入下若 §6.7 的 0.5 经实测仍偏高/偏低,需以实测为准并在 ADR/spec 记录与 §6.7 的差异。
- 正向:「无据不判定」首次建立在真实语义分数上,不再只是「挡近正交」。

### Revision 2026-06-23(review 发现的口径歧义)
原 Decision 末句「同步更新 ... 与 `eval_rag` 口径」措辞含糊,被实现解读为「`eval_rag._evaluate_case` 改用 backend floor 过滤」(hash=0.341 / bge=0.5),与 ADR-RE.5 Context 及 spec 记录的「`_evaluate_case` 用 `min_score=0.0` 测排序质量」冲突。澄清:
- **召回评测(`eval_rag`)测排序质量**(Hit@1 / Recall@5 / MRR / NDCG),维持 `min_score=0.0`,**不施 dense floor 过滤**。
- **dense floor 仅作生产主链路 / SSE 护栏**(workflow 取 backend floor 不变)。
- 分离理由:施 floor 会让 hash(0.341)与真实 backend(0.5 / 实测)在对比中用不同门槛 → 不同口径,污染本 stage「证明真实嵌入碾压 hash」的核心结论;并使 `reports/rag_eval.md` 分数混入过滤成分、被误读为召回崩盘。
