# Stage 28 只读 Tool Executor 离线证据

- Stage: `stage-28-readonly-tool-executor`
- Evaluated at: 2026-07-12T15:12:34.138816+00:00
- Case count: 12

## 环境与 Claim Boundary

- Python: 3.11.15
- Platform: macOS-26.5.2-arm64-arm-64bit
- Embedding backend: hash
- Database: sqlite
- 仅本地 SQLite + hash embedding，无外网、无外部凭证、非生产 SLA；latency 仅为本地观察值，不设 pass gate。

## 按 Tool 的 outcome / error / retry / latency

| Tool | Outcomes | Errors | Retry recovered | P50 ms (obs) | P95 ms (obs) | Samples |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `search_rules` | EMPTY=1, FAILED=3, SUCCEEDED=2 | CIRCUIT_OPEN=1, TIMEOUT=1, VALIDATION_ERROR=1 | 1 | 1.259 | 49.075 | 6 |
| `load_confirmed_cases` | EMPTY=1, SUCCEEDED=1 | - | 0 | 0.475 | 0.987 | 2 |
| `lookup_t1_context` | EMPTY=1, FAILED=2, SUCCEEDED=1 | PERMISSION_DENIED=2 | 0 | 0.074 | 1.133 | 4 |

## Case 安全投影

| Label | Tool | Source | Status | Error | Fallback | Attempt | Retry recovered | Result count | Evidence IDs |
| --- | --- | --- | --- | --- | --- | ---: | :---: | ---: | --- |
| search_rules_real_succeeded | `search_rules` | real_adapter | SUCCEEDED | - | - | 1 | no | 5 | clearing_cutoff_t1_guideline_002, clearing_t1_supplement_playbook_004, clearing_t1_supplement_playbook_001, clearing_single_side_playbook_001, clearing_reconciliation_scope_001 |
| search_rules_real_empty | `search_rules` | real_adapter | EMPTY | - | - | 1 | no | 0 | - |
| load_confirmed_cases_real_succeeded | `load_confirmed_cases` | real_adapter | SUCCEEDED | - | - | 1 | no | 1 | CLEAR_CUTOFF |
| load_confirmed_cases_real_empty | `load_confirmed_cases` | real_adapter | EMPTY | - | - | 1 | no | 0 | - |
| lookup_t1_context_real_succeeded | `lookup_t1_context` | real_adapter | SUCCEEDED | - | - | 1 | no | 1 | CORE_T1 |
| lookup_t1_context_real_empty | `lookup_t1_context` | real_adapter | EMPTY | - | - | 1 | no | 0 | - |
| search_rules_validation_error | `search_rules` | real_adapter | FAILED | VALIDATION_ERROR | TOOL_INPUT_INVALID | 1 | no | 0 | - |
| lookup_t1_permission_missing_task | `lookup_t1_context` | real_adapter | FAILED | PERMISSION_DENIED | TOOL_ACCESS_DENIED | 1 | no | 0 | - |
| lookup_t1_permission_cross_user | `lookup_t1_context` | real_adapter | FAILED | PERMISSION_DENIED | TOOL_ACCESS_DENIED | 1 | no | 0 | - |
| search_rules_timeout_exhausted | `search_rules` | fault_injection | FAILED | TIMEOUT | TOOL_TIMEOUT | 2 | no | 0 | - |
| search_rules_retry_recovered | `search_rules` | fault_injection | SUCCEEDED | - | - | 2 | yes | 5 | clearing_cutoff_t1_guideline_002, clearing_t1_supplement_playbook_004, clearing_t1_supplement_playbook_001, clearing_single_side_playbook_001, clearing_reconciliation_scope_001 |
| search_rules_circuit_open | `search_rules` | fault_injection | FAILED | CIRCUIT_OPEN | RAG_CIRCUIT_OPEN | 1 | no | 0 | - |
