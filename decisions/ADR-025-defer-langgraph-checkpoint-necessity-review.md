# ADR-025: 本 stage 继续推迟 LangGraph,登记 Checkpoint 必要性评估

- Status: Accepted (2026-06-09)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/workflow.py, services/reconciliation.py(DB-state HumanReview), decisions/ADR-006

## Context

ADR-006 把 LangGraph 毕业条件定在「出现 Checkpoint(断点续跑)或 Agent 并行需求(2b)」。MVP-2b PRD §3.4 字面要求 LangGraph SqliteSaver Checkpoint(HumanReviewNode 断点挂起/恢复)与条件并行。但现状:HumanReview 已用 DB 状态实现——upload/start 同步遍历队列,每笔 run_item 跑到终态(AUTO_FIXED/PENDING_HUMAN)即落库,PENDING_HUMAN 行留 DB 等人工经 review API 处理,**不在单笔执行中途挂起**。故「为 HumanReview 引入 Checkpoint」很可能与现有 DB-state 设计重复,需辩证而非照 PRD 字面默认引入。

## Options

- **A. 2b-1 续推迟,把必要性评估明确推到 2b-3(采纳)** — 2b-1 只做 Hook/约束/事务(均不依赖图引擎);2b-3 先验证「现有 DB-state HumanReview 是否已满足 Checkpoint 需求」,满足则用 ADR 登记续用 plain-Python,仅当真出现单笔中途挂起 / Agent 并行(有延迟数据支撑)才迁移。Pros: 2b-1 风险最低、与确认范围一致。Cons: 与 PRD §3.4 字面偏离,需登记;若 2b-3 判定要迁移,一次性成本仍在。
- **B. 2b-1 即迁移 LangGraph** — Pros: 结构先行。Cons: 2b-1 退化纯重构、零新增能力、高回归;并行需求无延迟数据支撑;与已确认范围冲突。

## Decision

采用 A。2b-1 续 plain-Python,不引 LangGraph。LangGraph/Checkpoint 去留作为 2b-3 首要 ADR 决策,决策前先验证现有 DB-state HumanReview 是否等价满足 Checkpoint 语义。

## Consequences

- 正面:2b-1 聚焦低风险;避免无真实挂起/并行需求时背图引擎复杂度。
- 负向:与 PRD §3.4 字面持续偏离(本条登记,留 main 同步);若 2b-3 判定迁移,plain-Python 改写 StateGraph 的一次性成本仍要付。
