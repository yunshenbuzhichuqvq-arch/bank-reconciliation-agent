# ADR-069: 限流维度边界 —— RPM + 并发,TPM defer

- Status: Accepted (2026-06-21)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/config.py(llm_rate_limit_* 键), src/bank_reconciliation_agent/core/llm/rate_limit.py, decisions/ADR-059(API 限流 backlog 来源)

## Context

DeepSeek 配额通常含三维:RPM(每分钟请求数)、并发数、TPM(每分钟 token 数)。维度越多越贴近上游真实约束,但 TPM 需在调用前预估本次 token,复杂度与收益需权衡。本 stage 限哪几维要先定边界。

## Options Considered

- **A. RPM + 并发上限,TPM defer**
  - Pros:RPM + 并发是最常见、最易触的两类上游约束;实现只需"窗口计数 + 并发计数",无需预估 token;契合 simplicity-first。
  - Cons:不控 TPM,超大 token 的突发请求仍可能触上游 429(由 ADR-071 的重试/Fallback 兜底)。
- **B. 三维全做(含 TPM)**
  - Pros:最贴近上游配额。
  - Cons:TPM 需在 `complete()` 前估算 prompt token(messages 可估、completion 未知只能猜),估不准则限流要么过紧要么失效;复杂度高,与单 stage 2–4h/task 颗粒度冲突。
- **C. 仅并发上限**
  - Pros:实现最轻(一个并发计数)。
  - Cons:不控速率,短时高频小请求仍会超 RPM,达不到"防超配额"目标。

## Decision

选 **A**:本 stage 限 **RPM + 并发**;**TPM defer 到 backlog**(理由:预估不准 + 复杂度,收益边际)。

## Consequences

- 正面:覆盖主要配额约束,实现可控、可在单 stage 完成。
- 负面:TPM 不受控,超大请求仍可能上游 429(登记 follow-up,由 ADR-071 退避/Fallback 兜底);若未来 DeepSeek 主要瓶颈转为 TPM,需另开 stage 补。
