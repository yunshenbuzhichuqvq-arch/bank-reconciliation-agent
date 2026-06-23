# ADR-081: AuditAgent 候选匹配确认契约与回流语义

**Stage**: stage-recon-hardening
**Status**: accepted
**Date**: 2026-06-22
**Slug**: `audit-agent-fuzzy-candidate-confirmation`

## Context

规划问答已定:候选匹配走 AuditAgent 确认(而非直接转人工)。AuditAgent 现仅吃单笔异常 + RAG 证据,输出 `decision ∈ {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED}`(ADR-039 schema、ADR-022 C1–C6)。候选确认是新任务:判「这两笔是否同一笔交易」,需让 Agent 看到**配对的另一笔**,并把确认结果回流到正确分支。ADR-020 已有可复用 pattern:BC-R003 把 `state.t1_candidate` 透传进 `trace_context` 驱动 Agent 叙述。

## Decision

复用 ADR-020 透传 pattern,新增候选确认任务类型:模糊候选把「配对的另一笔」经 state 透传进 AuditAgent 的确认上下文,无需新增 Agent。回流语义:

- 确认同一笔且金额相等 → `AUTO_FIXED`(平账)。
- 确认同一笔但金额不等 → 转 `AMOUNT_MISMATCH` 分支处理。
- 否决(非同一笔)→ 退回真单边(`BANK_UNARRIVED`/`BOOK_UNRECORDED`)。
- Agent 低置信或无据 → `PENDING_HUMAN`(承 ADR-022 C2「无据不判定」与 ADR-082 护栏)。

候选确认须带 evidence(对齐 §3.3)。prompt 文案、state 字段名、路由集合登记为实现细节。

## Consequences

- 负向:AuditAgent 承担第二种任务,prompt 复杂度上升,需版本化(承 ADR-008)与 schema 一致性测试(ADR-039)。
- 正向:模糊候选的判定有 RAG 依据、有置信度、可追溯,直接展示「规则确定性 + AI 语义判断」边界这一核心信号。
- 候选确认回流到 `AMOUNT_MISMATCH` 时会复用既有审计链路,需保证不产生二次 fallback 循环(实现期验证)。

## Alternatives Considered

- **新增独立 MatchConfirmAgent**(专职候选确认):违「主链路只 2 个 Agent」(架构 §2.4),编排复制,过度设计。否决。
