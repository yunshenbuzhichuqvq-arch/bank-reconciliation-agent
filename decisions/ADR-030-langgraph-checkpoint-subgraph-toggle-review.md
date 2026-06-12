# ADR-030: LangGraph Checkpoint 子图接入与边界

- Status: Accepted (2026-06-11)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/review_graph.py, services/review.py(approve 开关路由), core/config.py(checkpoint_enabled), decisions/ADR-025, decisions/ADR-023, decisions/ADR-010

## Context

PRD §3.4/§15.4 要求 LangGraph `HumanReviewNode` 支持 Checkpoint 挂起/恢复(`SqliteSaver` 持久化图状态)。ADR-025 把该决策推迟到 2b-3,并要求先验证现有 DB-state HumanReview 是否已等价。现状:`upload` 同步把每笔 `run_item` 跑到终态落库,`PENDING_HUMAN` 留 DB,`review.approve`(plain-Python,走 ADR-023 事务/副作用)处理——**无单笔执行中途挂起**。但本项目以 LangGraph 为技术栈核心,需补图引擎实战,且不能破坏已稳定的 2b-1/2b-2 主链路。

## Options

- **A. 最小 Checkpoint 子图 + 开关接 review(采纳)** — `run_item` 主链路保持 plain-Python 不动;新增 `HumanReviewNode` 子图(LangGraph `StateGraph` + `SqliteSaver`),经 `settings` 开关接入 `review.approve`:默认关=走现有 plain-Python(零回归),开启=走 Checkpoint 路径并有独立测试。引入 `langgraph` + `langgraph-checkpoint-sqlite`。
  - Pros: 补 LangGraph Checkpoint 实战、真实接业务、回归面锁在新增子图与开关内;沿用本项目「新能力加开关、默认关、零回归」传统(ADR-010)。
  - Cons: 引入首个图引擎依赖;开/关两套 approve 路径(技术债,需登记)。
- **B. 完整迁移 `run_item` 为 StateGraph** — Pros: 最兑现 PRD 字面、LangGraph 实战最足。 Cons: 重写已稳定的 Hook/记忆/fallback 接线,高回归;与「主链路不动」冲突。
- **C. 续 plain-Python 纯 ADR 登记(不引 LangGraph)** — Pros: 最 YAGNI、零依赖零回归。 Cons: 项目零 LangGraph 实战(已否决)。
- **D. 独立 demo 子图不接业务** — Cons: 不驱动真实业务、演示性弱(已否决)。

## Decision

采用 **A**。最小 `HumanReviewNode` 子图,经开关接 `review.approve`,默认关。新增依赖 `langgraph`、`langgraph-checkpoint-sqlite`(spec 锁版本)。

## Consequences

- 正面:补上 LangGraph Checkpoint 实战、可演示可讲述;默认关保证银企/清算两场景零回归;回归面收敛在新增子图 + 开关。
- 负面:引入图引擎依赖(`langgraph` 生态,首次);开/关两套 approve 路径属技术债,V1 考虑收敛;`SqliteSaver` 状态库需配独立路径与隔离键(见 ADR-031)。
