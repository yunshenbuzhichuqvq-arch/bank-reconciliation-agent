# ADR-079: 候选匹配的异常类型与状态语义

**Stage**: stage-recon-hardening
**Status**: accepted
**Date**: 2026-06-22
**Slug**: `fuzzy-candidate-error-type-and-status`

## Context

架构 §2.3.1 阶段2 产出「候选匹配 → 人工/Agent 确认」,这是一个**新的中间态**:既非「已精确平账」,也非「确定单边」,而是「疑似同一笔、待确认」。现有 `error_type` 集合(`AMOUNT_MISMATCH`/`BANK_UNARRIVED`/`BOOK_UNRECORDED`/`NARRATIVE_NAME_MISMATCH`/`DUPLICATE_BOOKING`)均不表达该语义;`_to_match_result` 现仅产 `AUTO_FIXED`/`PENDING_HUMAN` 两态,而 `_summarize_match_results` 却统计 `PENDING_AI`(该状态从未被产出 → **死统计,恒为 0**)。

## Decision

新增 `error_type=FUZZY_MATCH_CANDIDATE` + 规则 `BE-R007`,候选匹配状态走 `PENDING_AI`,进入 AuditAgent 确认(ADR-081)。语义清晰、可追溯、可计量;复用既已存在却悬空的 `PENDING_AI` 状态(顺带修死统计);与「规则优先、AI 补充」一致 —— 确定性层只标候选,判定交 Agent。具体规则 ID/优先级、schema 字段、前端标签为实现细节。

## Consequences

- 负向:新增异常类型牵动「规则 YAML + schema + 台账 + 前端标签」多处,需保持一致(承 AGENTS 红线:schema 双产物同步)。
- 正向:`PENDING_AI` 死统计被激活,看板「待 AI 处理」计数变真实;异常分布多一类可解释信号。

## Alternatives Considered

- **复用 `AMOUNT_MISMATCH` / `NARRATIVE_NAME_MISMATCH`**(不新增类型):那两类的前提是 flow_id 已精确匹配,而候选匹配恰是 flow_id 对不上;复用会语义混淆,污染既有异常分布统计与规则语义。否决。
