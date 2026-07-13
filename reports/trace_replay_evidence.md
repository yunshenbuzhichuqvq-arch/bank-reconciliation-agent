# Trace Replay Evidence Report

**Environment**: offline | **Provider**: fake | **Embedding**: hash | **Database**: sqlite_local

> This report is generated from a single deterministic run using a fake LLM provider, hash embedding and local SQLite. Latency figures are local-only and must not be interpreted as production SLAs.

## Completeness
- **Rate**: 83.33%
- **Numerator (eligible flows persisted)**: 5
- **Denominator (eligible flows executed)**: 6
- **Scenario pass count**: 6/6

## Scenarios
### complete_success
- Passed: True
- Eligible execution: True
- Persistence expected/actual: True/True
- Terminal: FINAL
- Span count: 6
- Sequence: `WORKFLOW → ROUTE → TOOL → AGENT → GUARD → FINAL`
- decision: `AUTO_FIXED`

### tool_failed_fallback
- Passed: True
- Eligible execution: True
- Persistence expected/actual: True/True
- Terminal: FALLBACK
- Span count: 4
- Sequence: `WORKFLOW → ROUTE → TOOL → FALLBACK`
- decision: `PENDING_HUMAN`

### agent_repair_failure_fallback
- Passed: True
- Eligible execution: True
- Persistence expected/actual: True/True
- Terminal: FALLBACK
- Span count: 10
- Sequence: `WORKFLOW → ROUTE → TOOL → AGENT → TOOL → AGENT → AGENT → AGENT → GUARD → FALLBACK`
- failed_agent_spans: `3`
- structured_repair_attempted: `True`
- structured_repair_succeeded: `False`
- error_type: `schema_invalid`
- fallback_reason: `structured_output_invalid`
- non_cached_agent_tokens: `360`
- decision: `PENDING_HUMAN`

### guard_blocked_fallback
- Passed: True
- Eligible execution: True
- Persistence expected/actual: True/True
- Terminal: FALLBACK
- Span count: 6
- Sequence: `WORKFLOW → ROUTE → TOOL → AGENT → GUARD → FALLBACK`
- guard_outcome: `BLOCKED`

### cross_tenant_replay_rejection
- Passed: True
- Eligible execution: True
- Persistence expected/actual: True/True
- Terminal: FINAL
- Span count: 6
- Sequence: `WORKFLOW → ROUTE → TOOL → AGENT → GUARD → FINAL`
- owner_http_status: `200`
- owner_replay_status: `AVAILABLE`
- non_owner_http_status: `404`
- non_owner_error_code: `TASK_NOT_FOUND`
- non_owner_payload_leaked: `False`
- storage_empty_read: `True`

### trace_write_failure_isolation
- Passed: True
- Eligible execution: True
- Persistence expected/actual: False/False
- Terminal: None
- Span count: 0
- business_call_succeeded: `True`
- ledger_committed: `True`
- queue_committed: `True`
- task_stats_committed: `True`
- final_decision: `PENDING_HUMAN`
- trace_rows: `0`
- failure_counter_incremented: `True`

## Duration (P50 / P95)
- **WORKFLOW**: P50=0ms  P95=23ms
- **ROUTE**: P50=0ms  P95=0ms
- **TOOL**: P50=0ms  P95=0ms
- **AGENT**: P50=0ms  P95=0ms
- **GUARD**: P50=0ms  P95=0ms
- **FINAL**: P50=0ms  P95=0ms
- **FALLBACK**: P50=0ms  P95=0ms

## Error Distribution
- `AGENT.schema_invalid`: 3
- `TOOL.CIRCUIT_OPEN`: 1

## Fallback Distribution
- `RAG_CIRCUIT_OPEN`: 1
- `structured_output_invalid`: 3

## Token by Agent
- **AuditAgent**: prompt=300, completion=60, total=360
- **TraceAgent**: prompt=0, completion=0, total=0

## Write Counters
- Success: 5
- Failure: 1
- Source: `runtime_memory`
