# ADR-006: 条件路由用纯 Python 编排,LangGraph 推迟到 2b

- Status: Accepted (2026-06-08)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: system-prd.md §9 / §3.3, decisions/ADR-005-llm-provider-and-test-contract.md

## Context

PRD §9 描述 MVP-2a 为"LangGraph 条件路由工作流",但 §3.3 的"依赖新增"清单只列 `openai / jieba / rank-bm25 / structlog`,未列 langgraph——PRD 内部不一致。2a 阶段明确串行执行、无 Checkpoint(§3.3 暂不包含已列出 Checkpoint/并行),LangGraph 的核心价值(StateGraph 持久化、Send 并行、SqliteSaver Checkpoint)在 2a 全部用不上。2a 设计原则(PRD §3.3):"只加让 Agent 变聪明的东西,不加让系统变复杂的东西"。现状工作流是 `services/` 里的普通 Python,无图引擎。

## Options

1. **现在引入 LangGraph,用 StateGraph 实现串行 + 条件路由** — 与 PRD §9 字面一致、为 2b Checkpoint/并行铺路,但 2a 收益未兑现却先吃框架复杂度,新增重框架依赖,与本阶段"不加复杂度"原则冲突,首次引入有学习/调试成本。
2. **纯 Python 编排器(显式函数调用 + `ReconciliationState` TypedDict 透传),LangGraph 推迟到 2b** — 零新框架依赖、契合 2a 设计原则、节点职责与状态结构先固化使 2b 平移 LangGraph 是机械重构,但偏离 PRD §9 字面、2b 接 LangGraph 时要把编排器改写成图(一次性成本)。

## Decision

采用 **Option 2**。
- 编排器(`services/workflow.py` 或 `agents/orchestrator.py`,落点由 spec 定):`PreCheck → ExceptionRouter → 条件分支(决定调 Extraction / Trace / RAG)→ AuditAgent → Fallback 决策 → 事务写入`,串行、显式。
- 状态用 PRD §9.1 的 `ReconciliationState` TypedDict(仅填 2a 用到的字段;`*_memory`/`summary_buffer` 留空占位,2b 填)。节点边界对齐 §9.2,便于 2b 平移 LangGraph。
- 毕业条件:出现 Checkpoint(断点续跑)或 Agent 并行需求(2b)时迁移到 LangGraph。

## Consequences

- 正面:不引框架、不加复杂度;节点/状态契约先稳,2b 迁移成本可控。
- 负向:与 PRD §9 字面偏离(本 ADR 即登记);2b 需把纯 Python 编排改写为 StateGraph(一次性机械成本)。
- PRD §9/§3.3 的字面不一致属 main 自有文档范畴,留待在 main 上同步修订,不在本 stage 分支改。
