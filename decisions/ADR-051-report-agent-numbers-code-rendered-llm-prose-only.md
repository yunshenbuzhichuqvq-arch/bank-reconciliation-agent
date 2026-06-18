# ADR-051: ReportAgent guardrail —— 代码渲染数字 + LLM 只写叙述

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/report.py, src/bank_reconciliation_agent/agents/report_agent.py, prompts/report_v1.md, src/bank_reconciliation_agent/services/metrics.py, decisions/ADR-047(线上 SQL 聚合 + 诚实数据源,本 ADR 沿用其"数字只来自 SQL"原则)

## Context

per-task 审计报告要有 LLM 组织的文字(PRD §12.2:"ReportAgent 只负责文字组织,不做数据计算"),但项目铁律是金额/统计不交给 LLM(README 开发约束:金额用 `Decimal`,不交给 LLM 或 float)。核心问题:报告既要有 LLM 叙述、又要数字零幻觉,二者怎么物理隔离。

## Options

**A. 代码渲染数字块 + LLM 只写叙述(选定)** —— metrics 服务出权威数字 dict;概览/异常分布/检索质量/Token 成本等事实区块由**代码**确定性渲染成 Markdown;ReportAgent 的 LLM 调用只返回 `{risk_summary, review_advice, followup}` 三段散文 JSON,prompt 明令不得复述或计算任何数字;代码按固定顺序拼装最终 Markdown。
- Pros: 数字由代码渲染、可证明正确,LLM 物理上碰不到数字区块;LLM 不可用时只输出数字区块即天然降级;"LLM 改不动数字"可写成不变量测试。
- Cons: 报告结构相对固定(非自由长文);LLM 散文里仍可能口头提到数字(靠定性指令缓解,不做强校验)。

**B. 整篇 LLM 生成 + 事后数字校验** —— LLM 拿数字生成整份(含表),再抽数字回校验,不符退模板/重试。
- Pros: 单遍输出更自然、更灵活。
- Cons: 校验自由文本里的数字很脆(格式/取整/对位);静默写错风险高;校验逻辑复杂。

**C. 纯模板、无 LLM** —— 代码填模板,无 LLM 参与。
- Pros: 零幻觉、零成本、全可测。
- Cons: 没了 LLM 叙述,退化成格式化器,与"ReportAgent"立项目标相悖(只能当 A 的降级分支)。

## Decision

选 A。数字事实区块代码渲染、LLM 只产出三段定性散文,把"数字不经 LLM"做成物理隔离而非约定。C 作为 A 的 LLM 降级分支保留(见 ADR-053)。

## Consequences

正向:
- 数字区块与 LLM 输出解耦,数字可追溯到 SQL 聚合;guardrail 由不变量测试守住(塞乱编数字的 stub,断言数字区块逐字节不变 —— 见 `tests/test_report_service.py`)。
- 降级路径天然成立:无 LLM 时仅缺三段散文,报告仍完整。

负向 / 成本:
- 报告版式较固定,牺牲自由长文表达。
- LLM 散文可能口头提及数字而不一致 —— 本 stage **有意只用定性 prompt 指令缓解,不做数字强校验**(接受的小风险,记录在案)。
- 需维护"代码渲染模板 ↔ metrics dict"字段对齐。
