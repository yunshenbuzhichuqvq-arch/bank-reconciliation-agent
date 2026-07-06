# ADR-EH.1: 三层离线评测体系边界

**Slug**: `three-layer-offline-eval-harness`
**Status**: accepted
**Date**: 2026-07-06

### Context

本 stage 的目标不是先补齐全部 Agent Runtime Control、Tool Adapter、Memory 或安全优化，而是先建立可信的 baseline：系统评测、RAG 评测、Agent 评测三条线分别回答不同问题。

- 系统评测回答：一批 Excel 流水进来，最终对账结果是否正确。
- RAG 评测回答：给定业务 query，检索是否召回正确规则片段。
- Agent 评测回答：给定结构化异常、RAG evidence 和工具结果，Agent 决策是否守住 schema、证据和安全边界。

现有基础包括 `scripts/eval_rag.py`、`data/rag_eval_set.json`、`reports/rag_eval.md`、`tests/test_v1_1_agent_schema_conformance.py`、`tests/test_mvp2b3_decision_regression.py`、`scripts/generate_mock_excel.py`。本 stage 应复用这些资产，避免重造一套脱离项目现状的评测框架。

### Options Considered

- **Option A: 只做端到端系统评测**
  - Pros: 最贴近用户可见结果，简历表达直接。
  - Cons: 不能定位问题来自匹配规则、RAG 召回还是 Agent 决策；优化会变成盲改。
- **Option B: 只做 RAG / Agent 单点评测**
  - Pros: 实现快，能展示 AI 评测指标。
  - Cons: 不能证明完整对账链路有效，容易变成“模型玩具指标”。
- **Option C: 三层离线评测并行建设，系统 / RAG / Agent 各自有数据集与指标（采纳）**
  - Pros: 可定位短板；能支撑“先评测、再优化、再复测”的工程叙事；与 PRD/架构中的可观测性与评测层一致。
  - Cons: 初始工作量比单点评测更大；三套指标需要清晰口径，避免报告堆砌。

### Decision

采用 **Option C**。建立三层离线评测体系：

- **System Eval**：Excel / DataFrame 批次输入，校验最终状态、异常分类、分支、危险自动处理等。
- **RAG Eval**：query + expected chunks/tags，输出 Hit@1、Recall@5、MRR、NDCG@5。
- **Agent Eval**：结构化异常 case + evidence/tool context，输出 schema pass rate、decision accuracy、evidence citation rate、hard constraint violation rate、unsafe auto-fix rate、consistency。

三层评测均为离线脚本或 pytest 可运行入口，不接入线上 API 路径，不改变现有业务运行行为。评测产物输出 Markdown + JSON 快照，口径延续 ADR-047 的“线上聚合 + 离线快照 + 诚实缺口标注”原则。

### Consequences

- 正向：能把“系统是否有效”和“AI 子能力哪里弱”分开度量；后续优化有依据；简历和面试可以讲清指标来源。
- 负向：短期会多出评测数据、报告和测试维护成本；如果 case 标注质量低，指标仍会失真。
- 约束：没有评测报告的指标不能写成实测结论；只能写目标或设计口径。
