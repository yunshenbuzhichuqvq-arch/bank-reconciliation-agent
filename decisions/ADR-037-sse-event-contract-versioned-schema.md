# ADR-037: SSE 事件契约(versioned event schema)

- Status: Accepted (2026-06-12)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: schemas/stream.py, services/stream_emitter.py(to_stream_event/_payload_from_row), services/agent_log.py(字段语义同源), decisions/ADR-036

## Context

SSE 事件要被已存在的 `frontend/` Vue app 消费,格式须是稳定契约而非 ad-hoc dict。现有 `agent_log.build_row` / `trace` payload 已有字段语义(`step`、`agent_name`、`prompt_version`、`decision`、`confidence`、`fallback_level`、RAG 分数等),事件契约应与之同源,避免两套口径。

## Options

- **A. 定义 versioned Pydantic 事件契约,复用 `agent_log`/`trace` 字段语义(采纳)** — `AgentStreamEvent{schema_version, event_type, seq, task_id, flow_id, ts, payload}`;`event_type` 枚举(`task_started`/`hook`/`rag_retrieved`/`agent_decision`/`fallback`/`item_done`/`task_done`),`payload` 按类型;带 `schema_version`。
  - Pros: 前端可依赖、事件可测、与持久化日志同口径(ADR-036 发射点呼应)。
  - Cons: 多一层契约,须与 `agent_log` schema 协同演进。
- **B. 直接透传 `agent_log` dict / 裸 dict** — Cons: 无稳定契约、前端易碎、无版本号。

## Decision

采用 **A**。versioned Pydantic 事件契约,字段复用 `agent_log`/`trace` 语义,单一来源。`event_type` 枚举与 `payload` 形状在实现定死,docstring 列明各类型 payload 字段(`rag_retrieved` 为 `chunk_ids`/`best_score`/`query`)。

## Consequences

- 正面:前端稳定消费、事件可测可回放、与落库日志同口径。
- 负面:event schema 与 `agent_log` schema 须协同演进(改一个查另一个);枚举扩展要顾后端/前端兼容(故带 `schema_version`)。

## Implementation Note (V1-1 收尾)

`schemas/stream.py` 落契约;`to_stream_event` 在 `workflow` 日志点把 agent_log 行映射成事件,落库经 `agent_log_service.build_row` 白名单提取(`output_payload`/`stream_seq` 等流式专用字段不进库,零回归)。契约 docstring 与实际 emit 字段已对齐(收尾清理:删除从未发射的 `ITEM_STARTED` 枚举值,`rag_retrieved` 字段名修正为复数 `chunk_ids`)。
