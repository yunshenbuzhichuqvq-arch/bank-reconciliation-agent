# ADR-30.1: 指标门禁下的 branch-aware query enrichment

- **Status**: accepted
- **Date**: 2026-07-13
- **Stage**: `stage-30-rag-query-optimization`
- **Deciders**: 用户（2026-07-13 确认）、Codex（提案）
- **Related**: `decisions/ADR-011-query-rewrite-llm-integration-and-fallback.md`、
  `decisions/ADR-22.1-target-weakest-real-rag-miss-bucket.md`、
  `decisions/ADR-22.3-rag-before-after-side-effect-reporting.md`、
  `docs/interview/what-todo-next.md`

## Context

Stage 30 是一次允许失败的受控 RAG 实验。当前可信但尚未按 Stage 30 重新冻结的报告
`reports/rag_quality_matrix.json` 显示：

- requested/effective backend 均为 `bge_m3`，selected mode 为 `dense`；
- 全局 Recall@5 为 `0.8250`，MRR 为 `0.7353`，NDCG@5 为 `0.7209`；
- `BANK_CLEARING / SINGLE_SIDE_MISSING` 有 10 条 case、8 个 miss、Recall@5 为 `0.3500`；
- Stage 22 的 chunk-context enrichment 已得到可信 `success=false`，不能重复同一变量。

现有运行时和评测路径存在一个必须在设计层解决的边界差异：

- 运行时由 `ReconciliationService._build_rag_query()` 基于 `ReconciliationMatchResult` 构造查询，
  清算单边对应运行时 `error_type=CLEARING_SINGLE_SIDE`、`exception_branch=BC-R001`；
- 离线评测的 `EvalCase` 使用质量分类 `error_type=SINGLE_SIDE_MISSING`，
  `RagSearchRequest` 当前只携带 `query` 与 `scenario_type`，不携带 branch context；
- 若把 `error_type/exception_branch` 直接加入 `RagSearchRequest` 并在 retriever 内处理，会同步扩大
  `/api/v1/rag/search` 的公共输入 contract；
- 若运行时和评测各自维护关键词拼接逻辑，则 before/after 不能证明候选逻辑就是实际运行时逻辑。

因此需要决定 branch-aware enrichment 的唯一归属、配置方式以及实验失败后的处理规则。

## Options Considered

### Option A: 扩展 `RagSearchRequest`，在 `RuleRetriever` 内统一 enrichment

优点：所有 retriever caller 自动走同一逻辑，集中度最高。

缺点：扩大公共 API/schema contract；所有现有 caller 都需要理解新的业务上下文；Stage 30 的单桶实验
会侵入通用 retriever 边界。

### Option B: 在 query construction 边界使用共享的确定性 enrichment helper

运行时在构造 `rag_query` 时调用 helper；离线评测在构造 `RagSearchRequest` 前调用同一 helper。
helper 从 tracked YAML 读取受控 profile，以 `scenario_type` 加 `error_type` 或
`exception_branch` 匹配，只对目标 profile 追加业务检索词。

优点：运行时与评测复用同一行为；不改公共 API；只影响 query-side；配置可审查、可测试、无 LLM
和新依赖。

缺点：两个入口都必须显式调用 helper；需要用测试防止其中一个入口漏接。

### Option C: 把检索词直接加入现有 reconciliation rule model

优点：`BC-R001` 的路由结果可以直接携带检索词。

缺点：把确定性对账路由和实验性 RAG 检索策略耦合；离线 eval case 没有运行时
`exception_branch`，仍需第二套适配；实验失败时回滚会触及核心 rule contract。

### Option D: 再次修改 chunk、embedding、threshold 或 reranker

优点：可能从其他杠杆改善指标。

缺点：违反 Stage 30 的单变量约束；chunk enrichment 已在 Stage 22 被可信证据否定；无法归因。

## Decision

采用 **Option B**。

1. 建立一个共享、确定性的 query enrichment helper，并使用一个 tracked YAML 保存 profile。
2. Stage 30 只允许一个 profile：`BANK_CLEARING / SINGLE_SIDE_MISSING`。该 profile 同时识别：
   - eval taxonomy：`error_type=SINGLE_SIDE_MISSING`；
   - runtime taxonomy：`error_type=CLEARING_SINGLE_SIDE`；
   - runtime branch：`exception_branch=BC-R001`。
3. 匹配语义为：`scenario_type` 必须匹配，且 `error_type` 或 `exception_branch` 至少一个匹配；
   未匹配时严格返回原 query。
4. enrichment 只追加由业务规则与知识库标题归纳的类别级检索词。禁止包含 eval query 原句、case id、
   expected chunk id 或单 case 答案式词串。
5. 运行时和离线评测必须调用同一 helper；不扩展 `RagSearchRequest`、HTTP API、Tool Executor 或
   retriever 公共 contract。
6. 不调用 LLM，不修改 ADR-011 的 LLM `QueryRewriter`，不新增依赖。
7. baseline 与 candidate 必须使用同一 eval set、chunk corpus、requested/effective backend、mode 和
   top-k；comparison 必须校验对应 hash 与 trust metadata，并记录各自 Git revision 与 candidate
   profile hash 以支持失败实验回放。
8. 只有可信 comparison 同时满足以下条件，candidate 才能保留在运行时：
   - target Recall@5 严格上升；
   - target miss count 至少下降 1；
   - 全局 MRR 与 NDCG@5 的绝对回退均不超过 `0.0200`；
   - 所有非目标 bucket 的副作用已完整输出。
9. 任一 gate 失败时，Stage 仍可用 `success=false` 诚实收尾，但最终代码树必须移除 candidate 的
   运行时接入与 target profile；评测可信度改进、before/after 报告、失败结论和包含 candidate 的
   Git 历史保留，不继续第三轮调参。报告必须指向 candidate revision，使失败实验仍可复现。
10. 若 baseline requested/effective backend 不是同一个 `bge_m3`、状态不是 `measured`，或 hash/trust
    metadata 不完整，则记录 environment gap 并暂停 candidate 实现；不得用 hash fallback 代替。

## Consequences

### Positive

- 单变量因果边界清楚，运行时与离线评测共享同一候选行为。
- 不扩大公共 API、Tool Executor、数据模型或权限边界。
- 成功和失败都有预先定义的可审计交付物，不会因指标不好继续扩大范围。
- tracked YAML 使业务检索词可审查，并能阻止关键词散落在 prompt 或多个 Python caller 中。

### Negative

- 需要在 runtime/eval 两个 query construction 入口各接一次 helper。
- baseline 必须在本机真实 `bge_m3` 可用时重新生成；环境不足会阻塞 candidate 实现。
- eval taxonomy 与 runtime taxonomy 不同，需要 profile 显式维护受控 alias。

### Constraints

- 不修改 `data/rag_eval_set.json`、expected labels、raw knowledge、chunk artifacts、embedding、mode、
  threshold、top-k、fusion 或 reranker 来迁就 candidate。
- 不把 `success=false` 包装成优化成功。
- 不因本实验引入 feature-flag framework、通用 query DSL 或新的配置系统。
