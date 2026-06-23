# ADR-082: RAG「无据地板」与「弱据 fallback 阈值」分层 —— 接回 §6.7 护栏并修订 ADR-013

**Stage**: stage-recon-hardening
**Status**: accepted
**Date**: 2026-06-22
**Slug**: `rag-no-evidence-floor-vs-fallback-threshold`
**Supersedes (partial)**: ADR-013(`l1_requires_l2` 的「RAG 低分触发 L2」语义)

## Context

架构 §3.3/§6.7 规定:相似度低于阈值(Dense<0.5 ∧ Reranker<0.3)= 无据 → AuditAgent 必须 `PENDING_HUMAN`,且**不触发 Fallback**。但实现存在两条方向相反的低分路径:

1. retriever `_passes_threshold` 过滤 —— 主链路硬传 `min_score=0.0`,且 `enable_rag_reranker` 默认 `False`,dense 分支阈值实为 0;config 的 `rag_dense_min_score=0.5` 定义了却未在主链路使用。
2. `fallback.l1_requires_l2` = `confidence<0.85 OR best_rag_score<rag_low_score(0.5)` —— 承 ADR-007/013,**RAG 低分触发 L1→L2 few-shot 补救**。

现状:`min_score=0` 使低分 hit 不被过滤、进入 `rag_items`;`rag_items` 非空 → 不走 `not rag_items` 的人工闸,转而被 `l1_requires_l2` 的 `score<0.5` 命中走 L2 fallback。**结果:§6.7「无据→人工、不 fallback」被 ADR-007/013「低分→fallback」覆盖,「无据不判定」护栏在默认基础 RAG 路径形同虚设**(hash 伪嵌入下检索几乎总能返回非零分 chunk,无命中仅在结果完全为空时触发)。

## Decision

采用「维度正交:RAG 分数管『有据』、Agent 置信管『准度』」(用户拍板):

- retriever 工作流主链路 `min_score` 接回 `rag_dense_min_score`,低于地板的 hit 被过滤;过滤后为空 → 现有 `not rag_items` 路径 → `PENDING_HUMAN`(§6.7,不触发 fallback)。`_passes_threshold` dense 分支边界 `>` → `>=`(对齐 §6.7「<地板 无据」即 `>=` 地板视为有据)。
- L2 fallback 触发改为**仅 `confidence < CONFIDENCE_THRESHOLD(0.85)`** —— 从 `l1_requires_l2` 移除 `best_rag_score < rag_low_score` 分支。此举**部分修订 ADR-013**:其「RAG 低分触发 L2」语义 superseded(fallback 状态机结构与 L2/L3 链不变,仅触发条件由「分数+置信」收敛为「置信」)。`best_rag_score` 因此 orphan、删除;`rag_low_score` 在 `scripts/eval_rag.py` 口径同步更新。
- 调试 API `/rag/search` 保留传 `min_score=0` 看全部,仅工作流主链路用配置阈值。

**地板值校准(实测驱动)**:实测 hash 占位嵌入(`HashEmbeddingFunction`)下**正确命中规则分数仅 0.35–0.43、正交基线≈0.33**,架构 §6.7 的 0.5 是**真实语义嵌入口径**,直接套用会误杀全部有据、使主链路一概转人工。故 `rag_dense_min_score` 默认值由 0.5 **校准**到 `0.341`(有据最低分与正交基线之间,实测定值;2026-06-23 实测 dense-only 银企 recall@5=0.5667、hybrid=0.7417 留痕),0.5 留作真实嵌入参考。**注**:自动 recall 评测闸已移出本 stage(见 ADR.md RH.6 rejected),floor 值待测试模拟数据定稿后随闸复校。**不改 SSE 断言** `_has_readable_decision_and_evidence`(校准后有据场景 evidence 非空自然通过;改断言去接受空 evidence 等于掩盖「全转人工」退化,已否决)。

## Consequences

- 负向:触及 ADR-007/013 的 fallback 触发逻辑,属跨 ADR 演进,须 superseded 标注 + 全量回归。
- 负向(嵌入局限,实测暴露):hash 占位嵌入无语义、分数压在 0.33–0.43 窄带,「无据地板」区分度有限,只能挡近正交的完全无关,无法干净区分「弱相关」与「无关」。**完整语义级「无据不判定」依赖真实嵌入(增强 RAG,ADR-009 默认关)**;本 stage 在默认基础 RAG 上做到「接回机制 + 校准地板挡完全无关」,并诚实记录此边界;自动 recall 评测兜底移出本 stage。
- 正向:「无据不判定」在默认路径从「形同虚设」恢复为「挡完全无关」;§6.7 与 ADR-007/013 的低分语义冲突被显式厘清。
- 阈值有效性与校准值的自动评测兜底(召回闸)随测试模拟数据定稿后单独 stage 引入(见 ADR.md RH.6 rejected);本 stage 仅以实测留痕。

## Alternatives Considered

- **双阈值分层(floor < low_score)**:引入独立「无据地板 floor」作 retriever `min_score`,与「弱据 fallback 阈值 `rag_low_score=0.5`」分层;§6.7 与 ADR-007 共存、保留 RAG 弱分触发 L2。但需新增并校准一个 floor 阈值、架构 §6.7 判据须改写对齐。语义层次虽清晰,较采纳方案多一个阈值与一处行为路径。未采纳。
- **维持现状 + 改文档**:承认「低分→L2」既定行为,改架构 §6.7 去掉「无据不 fallback」。不改代码、不动 ADR-007/013,但削弱「无据不判定」核心护栏(§3.3),与本 stage 初衷相悖。否决。
