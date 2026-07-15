# Performance Evaluation History

本文档持续记录银企对账真实工作台运行的性能数据，用于后续性能优化前后对比。

## 记录约定

- 历史记录只追加，不覆盖或重写已有测量结果。
- 每次记录必须注明 Git revision、输入文件及哈希、运行时模型、Embedding 后端、缓存与限流状态。
- 缺失或无法验证的环境信息必须标记为 `not verified`，不得根据配置参数推断真实运行身份。
- 只有输入、运行时身份和统计口径一致的记录，才可以计算前后性能变化。
- 本文档记录本地真实工作台运行，不代表生产 SLA，也不替代 Stage 31 的固定 offline benchmark。
- `Workflow` 表示单笔异常的 `WORKFLOW / reconciliation_workflow` 根 Span。
- `其他耗时 = Workflow - AuditAgent - search_rules`，主要包含条件式 `TraceAgent`、
  `ExtractionAgent`、其他 Tool、Hook 与流程调度开销。

## 记录索引

| 记录 | 执行时间 | Git revision | Task | 异常数 | Workflow 平均 | P95 | 串行累计 |
|---|---|---|---|---:|---:|---:|---:|
| RUN-001 | 2026-07-14 21:15:54–21:21:26 +08:00 | `8e79f451ce4a` | `TASK_6a5e0f671f64` | 34 | 9.728s | 18.126s | 330.767s |

## RUN-001 — 第一次真实工作台性能基线

### 记录身份

| 字段 | 值 |
|---|---|
| Record ID | `RUN-001` |
| Recorded at | `2026-07-15 00:22:18 +08:00` |
| Execution window | `2026-07-14 21:15:54–21:21:26 +08:00` |
| Branch | `main` |
| Git revision | `8e79f451ce4a` |
| Task ID | `TASK_6a5e0f671f64` |
| User ID | `demo_user` |
| Scenario | `BANK_ENTERPRISE` |
| Evidence source | `t_reconciliation_task`；每个 flow 最新一次 `t_trace_span` |
| Evidence completeness | 34/34 flow 有完整 Workflow Trace；217/217 Span 为 `SUCCEEDED` |
| Boundary | local demo runtime；Trace-observed DeepSeek model；not production SLA |

任务表最终持久化状态为 `UPLOADED`。本记录以完整 Trace、任务统计和 `updated_at` 为性能完成证据，
不把该状态字段改写为其他终态。

### 输入身份

| 输入 | 行数 | 文件大小 | SHA-256 |
|---|---:|---:|---|
| `mock_data/bank_enterprise_500_bank.xlsx` | 526 | 98,042 bytes | `1105f8b9a3a8fa610b04c95bed3ee5667ba29f4e47b975ade9c85e500960f3b8` |
| `mock_data/bank_enterprise_500_book.xlsx` | 522 | 87,628 bytes | `7b94da87b6669937aca2d19cd2ac7335f0df0485383c4eba4ae1a0787e011465` |

### 运行时身份

| 字段 | 值 |
|---|---|
| LLM provider | `deepseek`（current runtime config） |
| Trace-observed model | `deepseek-v4-flash` |
| Configured model | `deepseek-v4-flash` |
| Embedding backend | `bge_m3`（current runtime config；not persisted in this Trace） |
| LLM cache | `false` |
| LLM rate limit | `false` |
| Configured timeout | 30s |
| Configured max attempts | 3 |
| Observed retry recovery | 0 |
| Observed `attempt > 1` | 0 |
| Observed cached calls | 0 |

### 任务结果

| 指标 | 值 |
|---|---:|
| Bank rows | 526 |
| Enterprise/book rows | 522 |
| Auto-fixed rows | 500 |
| Unresolved rows | 34 |
| AI-processed rows | 34 |
| Pending AI rows | 6 |
| Pending human rows | 28 |
| Fallback L2 rows | 15 |
| Fallback L3 rows | 0 |
| Prompt tokens | 94,631 |
| Completion tokens | 27,132 |
| Total LLM tokens | 121,763 |
| Recorded LLM cost | 0.0648 |

34 个 Workflow 是 Agent 实际处理数；28 条是进入人工复核列表的数量，二者统计口径不同。

### 总体性能

所有耗时单位均为毫秒。

| 指标 | 样本数 | 总耗时 | 平均 | 中位数 | 最小 | P90 | P95 | 最大 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Workflow | 34 | 330,767 | 9,728 | 8,447 | 4,206 | 14,494 | 18,126 | 23,572 |
| `AuditAgent` | 34 | 253,706 | 7,462 | 6,835 | 4,130 | 10,868 | 12,124 | 14,875 |
| RAG `search_rules` | 34 | 2,567 | 76 | 74 | 48 | 84 | 93 | 116 |
| 其他流程开销 | 34 | 74,494 | 2,191 | 10 | 5 | 6,095 | 6,657 | 9,752 |

`AuditAgent` 占 Workflow 串行累计耗时的 76.7%；RAG `search_rules` 占 0.78%。

### 按异常类型统计

| 类型 | 数量 | Workflow 平均 | 中位数 | 最快 | 最慢 | AuditAgent 平均 | RAG 平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `AMT` | 5 | 6.485s | 6.446s | 5.042s | 8.292s | 6.412s | 65ms |
| `BONLY` | 5 | 14.576s | 14.107s | 9.681s | 18.672s | 9.489s | 75ms |
| `DUP` | 8 | 6.016s | 5.220s | 4.206s | 11.980s | 5.941s | 67ms |
| `EONLY` | 5 | 15.543s | 13.827s | 12.567s | 23.572s | 8.848s | 77ms |
| `FUZZ-B` | 3 | 8.936s | 8.602s | 7.249s | 10.958s | 8.846s | 84ms |
| `FUZZ-E` | 3 | 7.685s | 7.009s | 6.829s | 9.217s | 7.595s | 83ms |
| `NAR` | 5 | 9.951s | 8.715s | 5.054s | 14.494s | 6.623s | 88ms |

### Span 汇总

| Span | 调用数 | 总耗时 | 平均 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|---:|
| `WORKFLOW / reconciliation_workflow` | 34 | 330.767s | 9.728s | 8.447s | 4.206s | 23.572s |
| `AGENT / AuditAgent` | 34 | 253.706s | 7.462s | 6.835s | 4.130s | 14.875s |
| `AGENT / TraceAgent` | 10 | 58.065s | 5.806s | 5.552s | 3.463s | 9.745s |
| `AGENT / ExtractionAgent` | 3 | 16.148s | 5.383s | 6.083s | 3.828s | 6.237s |
| `TOOL / search_rules` | 34 | 2.567s | 76ms | 74ms | 48ms | 116ms |
| `TOOL / load_confirmed_cases` | 15 | 69ms | 5ms | 5ms | 4ms | 6ms |

### 逐笔数据

| # | Flow ID | 开始时间 | Workflow | AuditAgent | RAG | 其他 | Audit 占比 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `BE-AMT-001` | 21:15:55 | 6,446 | 6,390 | 48 | 8 | 99.1% |
| 2 | `BE-AMT-002` | 21:16:01 | 8,292 | 8,214 | 68 | 10 | 99.1% |
| 3 | `BE-AMT-003` | 21:16:10 | 6,055 | 5,972 | 72 | 11 | 98.6% |
| 4 | `BE-AMT-004` | 21:16:16 | 6,591 | 6,516 | 69 | 6 | 98.9% |
| 5 | `BE-AMT-005` | 21:16:22 | 5,042 | 4,966 | 70 | 6 | 98.5% |
| 6 | `BE-BONLY-001` | 21:16:27 | 14,107 | 8,751 | 75 | 5,281 | 62.0% |
| 7 | `BE-BONLY-002` | 21:16:41 | 18,126 | 12,124 | 77 | 5,925 | 66.9% |
| 8 | `BE-BONLY-003` | 21:17:00 | 12,294 | 5,567 | 70 | 6,657 | 45.3% |
| 9 | `BE-BONLY-004` | 21:17:12 | 9,681 | 6,128 | 79 | 3,474 | 63.3% |
| 10 | `BE-BONLY-005` | 21:17:22 | 18,672 | 14,875 | 76 | 3,721 | 79.7% |
| 11 | `BE-DUP-001-A` | 21:17:41 | 4,913 | 4,842 | 64 | 7 | 98.6% |
| 12 | `BE-DUP-001-B` | 21:17:46 | 5,451 | 5,375 | 70 | 6 | 98.6% |
| 13 | `BE-DUP-002-A` | 21:17:51 | 4,206 | 4,130 | 71 | 5 | 98.2% |
| 14 | `BE-DUP-002-B` | 21:17:56 | 4,988 | 4,912 | 67 | 9 | 98.5% |
| 15 | `BE-DUP-003-A` | 21:18:01 | 5,786 | 5,710 | 68 | 8 | 98.7% |
| 16 | `BE-DUP-003-B` | 21:18:06 | 4,654 | 4,582 | 66 | 6 | 98.5% |
| 17 | `BE-DUP-004-A` | 21:18:11 | 6,147 | 6,071 | 65 | 11 | 98.8% |
| 18 | `BE-DUP-004-B` | 21:18:17 | 11,980 | 11,904 | 66 | 10 | 99.4% |
| 19 | `BE-EONLY-001` | 21:18:29 | 12,567 | 8,329 | 73 | 4,165 | 66.3% |
| 20 | `BE-EONLY-002` | 21:18:42 | 23,572 | 13,746 | 74 | 9,752 | 58.3% |
| 21 | `BE-EONLY-003` | 21:19:05 | 13,827 | 7,908 | 79 | 5,840 | 57.2% |
| 22 | `BE-EONLY-004` | 21:19:19 | 14,847 | 5,747 | 74 | 9,026 | 38.7% |
| 23 | `BE-EONLY-005` | 21:19:34 | 12,903 | 8,508 | 84 | 4,311 | 65.9% |
| 24 | `BE-FUZZ-B-001` | 21:19:47 | 8,602 | 8,504 | 93 | 5 | 98.9% |
| 25 | `BE-FUZZ-B-002` | 21:19:55 | 10,958 | 10,868 | 84 | 6 | 99.2% |
| 26 | `BE-FUZZ-B-003` | 21:20:06 | 7,249 | 7,167 | 76 | 6 | 98.9% |
| 27 | `BE-FUZZ-E-001` | 21:20:14 | 6,829 | 6,749 | 74 | 6 | 98.8% |
| 28 | `BE-FUZZ-E-002` | 21:20:20 | 7,009 | 6,921 | 81 | 7 | 98.7% |
| 29 | `BE-FUZZ-E-003` | 21:20:27 | 9,217 | 9,116 | 93 | 8 | 98.9% |
| 30 | `BE-NAR-001` | 21:20:37 | 14,494 | 8,181 | 67 | 6,246 | 56.4% |
| 31 | `BE-NAR-002` | 21:20:51 | 7,503 | 7,408 | 84 | 11 | 98.7% |
| 32 | `BE-NAR-003` | 21:20:59 | 8,715 | 4,787 | 90 | 3,838 | 54.9% |
| 33 | `BE-NAR-004` | 21:21:07 | 5,054 | 4,959 | 84 | 11 | 98.1% |
| 34 | `BE-NAR-005` | 21:21:12 | 13,990 | 7,779 | 116 | 6,095 | 55.6% |

### 运行质量

- Trace runs：34。
- Trace Spans：217。
- `SUCCEEDED`：217；失败 Span：0。
- 重试恢复：0；`attempt > 1`：0。
- 缓存调用：0。
- 本次延迟不是失败重试或缓存失效造成的。

### 基线观察与后续优化重点

1. 首要瓶颈是 `AuditAgent`，占 Workflow 串行累计耗时 76.7%。
2. `BONLY` 与 `EONLY` 最慢，原因不只在 `AuditAgent`；条件式 `TraceAgent` 带来明显额外耗时。
3. 3 个需要 `ExtractionAgent` 的样本额外产生 16.148s Span 耗时。
4. RAG `search_rules` 平均仅 76ms，不是当前优先优化对象。
5. 当前 34 笔异常串行执行，因此单笔延迟近似直接累加为整批等待时间。

## 后续记录最小字段

每次后续运行至少追加以下内容：

- Record ID、执行时间、Git revision、Task ID、场景与数据边界。
- 两个输入文件的路径、行数、大小和 SHA-256。
- 实际观测到的 provider/model、Embedding 后端、缓存、限流与重试状态。
- 任务结果、token、成本和 Trace 完整性。
- Workflow、Agent、Tool 的样本数、平均、中位数、P90、P95、最小、最大与累计耗时。
- 全部逐笔数据和异常类型分组数据。
- 相对上一条可比记录的绝对变化与百分比；不可比时明确写明原因。
- 是否保留优化、回滚或继续观察的结论，以及对应证据。
