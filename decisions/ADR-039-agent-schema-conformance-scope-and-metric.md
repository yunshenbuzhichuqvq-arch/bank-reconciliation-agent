# ADR-039: Agent Schema 符合性测试——范围与口径

- Status: Accepted (2026-06-12)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: tests/test_v1_1_agent_schema_conformance.py, agents/{extraction,audit,trace}_agent.py, reports/agent_schema_conformance.md, decisions/ADR-033(决策回归——泛化非重复), AGENTS.md 红线#2

## Context

PRD §247 / 架构 §547 要求 Agent Schema 符合性测试(Pytest + Pydantic,统计通过率)。2b-3 已有 `test_mvp2b3_decision_regression`(AuditAgent 结构断言跑 N 次)。需定:测哪些 Agent、跑什么输入、通过率口径、与现有回归测试的关系(泛化而非重复)。

## Options

- **A. 三 Agent × 固定输入跑,统计 Pydantic 解析 + 不变量通过率,泛化 2b-3 回归(采纳)** — 对 `ExtractionAgent`/`AuditAgent`/`TraceAgent` 在一组固定输入(复用 mock fixtures + 评测集异常)上跑,断言输出无强制转换地解析进对应 Pydantic schema 且满足不变量(`decision∈枚举`、`confidence∈[0,1]`、无 RAG 命中→`evidence` 空且转人工不臆造=AGENTS 红线#2);输出通过率统计(report)。fake provider 下确定性基线,真实 provider 留有 key 时跑。
  - Pros: 覆盖三 Agent、口径明确、复用红线、与 2b-3 回归共用断言不重复。
  - Cons: fake provider 下通过率恒 100%(真实随机性暴露留真实 provider)。
- **B. 只测 AuditAgent(≈ 2b-3 回归改名)** — Cons: 覆盖不足、不兑现「Agent Schema 符合性」。

## Decision

采用 **A**。三 Agent + Pydantic 解析 + 不变量 + 通过率 report;不变量集(尤其红线#2「无据不臆造」)在实现定死。

## Consequences

- 正面:三 Agent 输出契约有守门、口径统一、复用 AGENTS 红线#2、可展示通过率。
- 负面:fake provider 下通过率恒满(真实暴露留真实 provider/V1);不变量集需随 schema 演进维护。

## Implementation Note (V1-1 收尾)

`test_v1_1_agent_schema_conformance.py` 覆盖三 Agent,含专门的 `AuditAgent.no_rag_evidence` 用例锁红线#2(`not evidence → decision==PENDING_HUMAN 且 confidence==0`);通过率落 `reports/agent_schema_conformance.md`(fake provider 下 4/4=100%,符合基线)。技术债:ADR 原意「与 2b-3 共用断言工具」未做——2b-3 的断言为 inline,无可复用模块,conformance 测试保留本地 helper 并在文件头注释登记,待第二个调用方出现再抽公共模块(YAGNI)。
