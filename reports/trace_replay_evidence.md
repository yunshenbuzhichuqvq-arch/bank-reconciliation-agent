# Trace Replay Evidence Report

**Environment**: offline | **Provider**: fake | **Embedding**: hash | **Database**: sqlite_in_memory

> This report is generated from a single deterministic run using fake LLM provider, hash embedding, and local SQLite. Latency figures are local-only and must not be interpreted as production SLAs.

## Completeness
- **Rate**: 100.00%
- **Numerator**: 4
- **Denominator**: 4

## Scenarios
### complete_success
- Terminal: FINAL
- Span count: 6
- Sequence: `WORKFLOW → ROUTE → TOOL → AGENT → GUARD → FINAL`

### tool_failed_fallback
- Terminal: FALLBACK
- Span count: 4
- Sequence: `WORKFLOW → ROUTE → TOOL → FALLBACK`

### agent_repair_failure_fallback
- Terminal: FALLBACK
- Span count: 4
- Sequence: `WORKFLOW → ROUTE → TOOL → FALLBACK`

### guard_blocked_fallback
- Terminal: FALLBACK
- Span count: 6
- Sequence: `WORKFLOW → ROUTE → TOOL → AGENT → GUARD → FALLBACK`

### cross_tenant_replay_rejection
- Terminal: None
- Span count: 0
- Sequence: ``

### trace_write_failure_isolation
- Terminal: None
- Span count: 0
- Sequence: ``

## Duration (P50 / P95)
- **WORKFLOW**: P50=0ms  P95=0ms
- **ROUTE**: P50=0ms  P95=0ms
- **TOOL**: P50=10ms  P95=10ms
- **AGENT**: P50=0ms  P95=0ms
- **GUARD**: P50=0ms  P95=0ms
- **FINAL**: P50=0ms  P95=0ms
- **FALLBACK**: P50=0ms  P95=0ms

## Error Distribution
- `TOOL.CIRCUIT_OPEN`: 1

## Fallback Distribution
- `RAG_CIRCUIT_OPEN`: 1

## Token by Agent
- **AuditAgent**: prompt=0, completion=0

## Write Counters
- Success: 1
- Failure: 1
- Source: `runtime_memory`
