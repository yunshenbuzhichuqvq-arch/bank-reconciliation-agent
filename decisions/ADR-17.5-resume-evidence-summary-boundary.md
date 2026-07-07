# ADR-17.5: Resume evidence summary must separate measured facts from resume wording

**Slug**: `resume-evidence-summary-boundary`
**Status**: accepted
**Date**: 2026-07-07

## Context

用户明确目标是完善简历 bullet。简历需要短句，但项目报告必须能支撑每个数字。若直接在代码或报告中写“提升显著”“保障金融安全”这类结论，会有两个风险：

- 数字来源不清，面试时无法解释。
- 把 offline eval 结果包装成生产效果，违反项目“不得夸大落地情况”的原则。

## Options Considered

- Option A: 在 README 或 PR 描述里直接写最终简历 bullet。Pros: 快。Cons: 容易和真实报告脱节，也可能提前写入未经验证的数字。
- Option B: 只保留原始报告，不产出简历摘要。Pros: 最严谨。Cons: 用户还需要手工从多个报告提炼 bullet，容易漏掉边界条件。
- Option C: 产出 evidence summary，包含“可引用数字”和“建议简历表述草稿”两个区块（采纳）。Pros: 既保留证据链，又服务简历。Cons: 需要明确草稿不是生产声明，且数字必须来自报告。

## Decision

采用 Option C。

Real Evidence Benchmark 最终报告应包含：

- Source reports：RAG matrix、Agent fake baseline、DeepSeek Agent Eval、performance/cost benchmark。
- Resume-safe facts：逐条列出可引用数字和对应文件。
- Resume bullet draft：把事实改写为 2-4 条简历 bullet 草稿。
- Claim boundary：明确数据集规模、离线/真实 provider、fake provider、environment gap 和 out-of-scope。

任何 bullet 草稿都必须满足：

- 不写“生产”“线上”“真实客户”除非确有线上证据。
- 不写“DeepSeek 实测”除非 `real_provider_call=true`。
- 不写“成本下降”除非有 before/after 成本对比。
- 不写“安全违规率 0”除非对应报告中 `unsafe_auto_fix_rate=0` 且 `hard_constraint_violation_rate=0`。

## Consequences

- 正向：最终产物能直接服务求职，同时不会牺牲证据严谨性。
- 正向：PR reviewer 可以从 bullet 反查报告，避免“简历话术”和代码事实割裂。
- 负向：如果某些结果没跑出来，bullet 草稿会更保守。
- 负向：需要维护一份汇总报告，避免后续报告更新后摘要陈旧。
