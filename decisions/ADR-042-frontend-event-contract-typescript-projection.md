# ADR-042: 事件契约前端投影——手写 versioned TS 类型,与后端同源

- Status: Accepted (2026-06-15)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/types/api.ts, src/bank_reconciliation_agent/schemas/stream.py(后端契约), src/bank_reconciliation_agent/services/stream_emitter.py, decisions/ADR-037(后端 versioned 事件契约)

## Context

后端 `schemas/stream.py` 定义 versioned `AgentStreamEvent` + `StreamEventType` 枚举(ADR-037)。前端解析帧后要类型安全消费 payload——不同 `event_type` payload 形状不同(`rag_retrieved`: chunk_ids/best_score/query;`agent_decision`: decision/confidence/…)。现有 `types/api.ts` 已是手写 TS 类型。

## Options

- **A. 手写 TS 类型镜像后端契约(采纳)** — `types/api.ts` 加 `AgentStreamEvent` + `StreamEventType` + 按 `event_type` 的 payload 类型。Pros: 遵循现有手写模式;类型安全;无构建期生成。Cons: 与后端手动同步,靠 `schema_version` 兜底。
- **B. 从后端 OpenAPI/Pydantic 自动生成** — Cons: SSE 事件不在 OpenAPI response schema(`StreamingResponse` 无结构化 schema);引生成工具链超本 stage。
- **C. payload 用 `Record<string, unknown>`** — Cons: 丢类型安全、消费处到处断言。

## Decision

采用 **A**。手写类型,文件顶部注释登记"改后端 stream schema 须同步此处";前端校验 `schema_version`,不匹配给降级提示。

## Consequences

- 正面:类型安全、遵循现有模式、无生成工具链。
- 负面:前后端契约手动同步(技术债);payload 类型随后端 `event_type` 演进维护。

## Implementation Note (V1-2 收尾)

`types/api.ts` 加 `StreamEventType`(7 值)+ 各 event_type payload 接口 + `StreamPayload` union + `AgentStreamEvent`,顶部注释"Keep aligned with backend schemas/stream.py and services/stream_emitter.py"。实际是松散 union(无 discriminant 字段)+ HookPayload/AgentDecisionPayload 等带 `[key:string]:unknown` index signature,消费处(EventCard)靠 `event_type` 外部判断 + `as Record<string,unknown>` 取值——类型安全弱于严格 discriminated union,务实折中。`TaskDonePayload` 同时纳入端点实际字段(total_bank_rows 等)与 docstring 字段(ai_processed_rows 等;后端 docstring 与端点 emit 不一致的 V1-1 遗留)以兼容。
