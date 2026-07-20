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
| RUN-002 | 2026-07-16 12:37:34–12:38:51 +08:00 | `8131a5b7ba95` + source diff | `TASK_6a5e0f671f64` | 34 | 8.435s | 15.569s | 286.785s（并发累计） |
| RUN-003 | 2026-07-16 21:24:27–21:24:49 +08:00 | `8131a5b7ba95` + source diff | `TASK_6a5e0f671f64` | 34 | 1.792s | 10.032s | 60.911s（并发累计） |
| RUN-004 | 2026-07-16 22:26:14–22:26:26 +08:00 | `8131a5b7ba95` + concurrency=6 diff | `TASK_6a5e0f671f64` | 34 | 1.757s | 10.148s | 59.722s（并发累计） |
| RUN-005 | 2026-07-16 22:30:37–22:30:49 +08:00 | `8131a5b7ba95` + source diff | `TASK_6a5e0f671f64` | 34 | 1.715s | 9.338s | 58.298s（并发累计） |

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

## RUN-002 — 4 路有界 Flow 并发优化实测

### 记录身份

| 字段 | 值 |
|---|---|
| Record ID | `RUN-002` |
| Recorded at | `2026-07-16 12:41:47 +08:00` |
| Client execution window | `2026-07-16 12:37:34.586933–12:38:51.231926 +08:00` |
| Task execution window | `2026-07-16 12:37:34–12:38:51 +08:00` |
| Workflow root envelope | `2026-07-16 12:37:35–12:38:51 +08:00` |
| Branch | `main` |
| Git HEAD | `8131a5b7ba95013d03de7cb837f1d04a2e0afb05` |
| Uncommitted source diff SHA-256 | `bad38db16b773d67cc76906675337e9e6b1c332737af6ab4f1db95f25f7c97e1` |
| Task ID | `TASK_6a5e0f671f64` |
| User ID | `demo_user` |
| Scenario | `BANK_ENTERPRISE` |
| Evidence source | client monotonic timer；`t_reconciliation_task`；该轮每个 flow 最新一次 `t_trace_span` |
| Evidence completeness | 34/34 Trace snapshot 重新加载并通过结构校验；217/217 Span 为 `SUCCEEDED` |
| Boundary | local demo runtime；真实 DeepSeek/bge_m3；单次运行；not production SLA |

本轮运行使用未提交的性能优化源码，因此 Git HEAD 不能单独标识被测代码。上表额外记录了
`.env.example` 与 8 个被测 source 文件相对 HEAD 的 diff SHA-256；测试、报告以及用户原有的
`.gitignore` / `AGENTS.md` 改动不计入该 source diff。

任务表最终持久化状态仍为 `UPLOADED`。Trace 的 `started_at` / `ended_at` 在 MySQL 中以 UTC
naive datetime 保存，本记录展示时统一换算为 Asia/Shanghai `+08:00`。

### 输入身份

| 输入 | 行数 | 文件大小 | SHA-256 |
|---|---:|---:|---|
| `mock_data/bank_enterprise_500_bank.xlsx` | 526 | 98,042 bytes | `1105f8b9a3a8fa610b04c95bed3ee5667ba29f4e47b975ade9c85e500960f3b8` |
| `mock_data/bank_enterprise_500_book.xlsx` | 522 | 87,628 bytes | `7b94da87b6669937aca2d19cd2ac7335f0df0485383c4eba4ae1a0787e011465` |

两个文件的路径、行数、大小和 SHA-256 与 RUN-001 完全一致。

### 运行时身份

| 字段 | 值 |
|---|---|
| LLM provider | `deepseek`（本轮显式环境覆盖） |
| Trace-observed model | `deepseek-v4-flash`；47/47 Agent Span 一致 |
| Configured model | `deepseek-v4-flash` |
| Embedding backend | `bge_m3`（本轮显式环境覆盖；Trace 未持久化 backend 名称） |
| RAG mode | dense；新进程冷启动 |
| LLM cache | `false` |
| LLM rate limit | `false` |
| Configured timeout | 30s |
| Configured max attempts | 3 |
| Reconciliation max concurrency | 4 |
| Observed maximum root concurrency | 4 |
| Observed retry recovery / `attempt > 1` | 0 / 0 |
| Observed cached calls | 0 |
| Structured repair attempted / succeeded | 0 / 0 |

### 任务结果

| 指标 | 值 |
|---|---:|
| HTTP status | 200 |
| Task status | `UPLOADED` |
| Bank rows | 526 |
| Enterprise/book rows | 522 |
| Auto-fixed rows | 500 |
| Unresolved rows | 34 |
| AI-processed rows | 34 |
| Pending AI rows | 6 |
| Pending human rows | 28 |
| Fallback L2 rows | 11 |
| Fallback L3 rows | 0 |
| Prompt tokens | 94,631 |
| Completion tokens | 22,075 |
| Total LLM tokens | 116,706 |
| Recorded LLM cost | 0.0604 |
| Ledger final `PENDING_HUMAN` | 34/34 |

Fallback path 分布为 `L1=17`、`L1->L2->HUMAN=11`、`HUMAN=6`。RUN-001 的 L2 为 15；
本轮 L2 为 11，但 34 个最终安全状态、行级业务统计、Agent 调用结构和 Trace 完整性没有改变。
该差异属于真实 LLM 输出的非确定性，不作为并发优化改变业务语义的证据。

### 批次级性能与并发证据

| 指标 | RUN-002 | 说明 |
|---|---:|---|
| Client wall-clock | 76.646s | 同步 `/api/v1/reconcile/upload` monotonic timer |
| Task `created_at → updated_at` | 77s | MySQL 秒级时间戳 |
| Workflow root envelope | 76s | 首个 root start → 最后 root end |
| Workflow duration sum | 286.785s | 并发后的总工作量，不等于用户等待时间 |
| 并发因子 `sum / envelope` | 3.773 | 4-worker 的实际重叠程度 |
| 最大观测 root 并发 | 4 | 未超过配置 cap 4 |

### 总体性能

所有耗时单位均为毫秒；P90/P95 延续 RUN-001 的 nearest-rank 统计口径。

| 指标 | 样本数 | 总耗时 | 平均 | 中位数 | 最小 | P90 | P95 | 最大 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Workflow | 34 | 286,785 | 8,435 | 8,143 | 4,195 | 13,915 | 15,569 | 15,923 |
| `AuditAgent` | 34 | 202,776 | 5,964 | 5,790 | 3,853 | 7,924 | 8,684 | 8,991 |
| RAG `search_rules` | 34 | 29,413 | 865 | 86 | 25 | 6,696 | 6,750 | 6,791 |
| 其他流程开销 | 34 | 54,596 | 1,606 | 16 | 3 | 4,332 | 6,457 | 7,918 |

RAG 累计耗时异常升高来自可解释的冷启动排队：首批 4 个 Workflow 同时启动，共享锁中的首次
bge_m3 模型/索引初始化约 6.7s，等待该锁的另外 3 个 `search_rules` Span 也把等待计入自己的
duration。第 5 个 Flow 起恢复到百毫秒附近，全部 34 个样本的中位数为 86ms。该累计值不能解释为
34 次都进行了 865ms 的真实检索，也不应被隐藏；后续应在打开 Flow 并发前预热 RAG。

### 按异常类型统计

| 类型 | 数量 | Workflow 平均 | 中位数 | 最快 | 最慢 | AuditAgent 平均 | RAG 平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `AMT` | 5 | 13.154s | 15.569s | 4.821s | 15.923s | 7.644s | 5.421s |
| `BONLY` | 5 | 11.415s | 10.630s | 9.366s | 13.915s | 6.176s | 118ms |
| `DUP` | 8 | 4.824s | 4.555s | 4.195s | 5.817s | 4.745s | 72ms |
| `EONLY` | 5 | 9.432s | 8.995s | 8.418s | 11.912s | 5.765s | 55ms |
| `FUZZ-B` | 3 | 6.344s | 6.357s | 5.022s | 7.652s | 6.254s | 86ms |
| `FUZZ-E` | 3 | 7.392s | 7.167s | 7.036s | 7.973s | 7.329s | 57ms |
| `NAR` | 5 | 7.396s | 8.312s | 5.216s | 9.595s | 5.229s | 87ms |

`AMT` 的 RAG 平均被首批 4 个冷启动/锁等待样本拉高，不能用于推断该异常类型本身的检索更慢。

### Span 汇总

| Span | 调用数 | 总耗时 | 平均 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|---:|
| `WORKFLOW / reconciliation_workflow` | 34 | 286.785s | 8.435s | 8.143s | 4.195s | 15.923s |
| `AGENT / AuditAgent` | 34 | 202.776s | 5.964s | 5.790s | 3.853s | 8.991s |
| `AGENT / TraceAgent` | 10 | 43.600s | 4.360s | 3.175s | 2.458s | 7.908s |
| `AGENT / ExtractionAgent` | 3 | 10.358s | 3.453s | 3.749s | 2.296s | 4.313s |
| `TOOL / search_rules` | 34 | 29.413s | 865ms | 86ms | 25ms | 6.791s |
| `TOOL / load_confirmed_cases` | 11 | 61ms | 6ms | 4ms | 3ms | 11ms |

### 逐笔数据

| # | Flow ID | 开始时间 | Workflow | AuditAgent | RAG | 其他 | Audit 占比 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `BE-AMT-001` | 12:37:35 | 13,721 | 6,927 | 6,773 | 21 | 50.5% |
| 2 | `BE-AMT-002` | 12:37:35 | 15,569 | 8,684 | 6,750 | 135 | 55.8% |
| 3 | `BE-AMT-003` | 12:37:35 | 15,736 | 8,894 | 6,696 | 146 | 56.5% |
| 4 | `BE-AMT-004` | 12:37:35 | 15,923 | 8,991 | 6,791 | 141 | 56.5% |
| 5 | `BE-AMT-005` | 12:37:49 | 4,821 | 4,722 | 95 | 4 | 97.9% |
| 6 | `BE-BONLY-001` | 12:37:51 | 9,366 | 6,400 | 297 | 2,669 | 68.3% |
| 7 | `BE-BONLY-002` | 12:37:51 | 10,630 | 7,470 | 43 | 3,117 | 70.3% |
| 8 | `BE-BONLY-003` | 12:37:51 | 12,861 | 5,206 | 85 | 7,570 | 40.5% |
| 9 | `BE-BONLY-004` | 12:37:54 | 10,303 | 5,880 | 91 | 4,332 | 57.1% |
| 10 | `BE-BONLY-005` | 12:38:00 | 13,915 | 5,922 | 75 | 7,918 | 42.6% |
| 11 | `BE-DUP-001-A` | 12:38:02 | 5,233 | 5,138 | 90 | 5 | 98.2% |
| 12 | `BE-DUP-001-B` | 12:38:04 | 5,817 | 5,705 | 103 | 9 | 98.1% |
| 13 | `BE-DUP-002-A` | 12:38:04 | 4,630 | 4,554 | 67 | 9 | 98.4% |
| 14 | `BE-DUP-002-B` | 12:38:07 | 5,657 | 5,549 | 101 | 7 | 98.1% |
| 15 | `BE-DUP-003-A` | 12:38:09 | 4,195 | 4,149 | 41 | 5 | 98.9% |
| 16 | `BE-DUP-003-B` | 12:38:10 | 4,338 | 4,290 | 42 | 6 | 98.9% |
| 17 | `BE-DUP-004-A` | 12:38:12 | 4,480 | 4,387 | 89 | 4 | 97.9% |
| 18 | `BE-DUP-004-B` | 12:38:13 | 4,241 | 4,191 | 45 | 5 | 98.8% |
| 19 | `BE-EONLY-001` | 12:38:14 | 11,912 | 5,430 | 25 | 6,457 | 45.6% |
| 20 | `BE-EONLY-002` | 12:38:14 | 9,208 | 5,874 | 91 | 3,243 | 63.8% |
| 21 | `BE-EONLY-003` | 12:38:17 | 8,628 | 6,082 | 82 | 2,464 | 70.5% |
| 22 | `BE-EONLY-004` | 12:38:17 | 8,418 | 5,339 | 34 | 3,045 | 63.4% |
| 23 | `BE-EONLY-005` | 12:38:23 | 8,995 | 6,100 | 44 | 2,851 | 67.8% |
| 24 | `BE-FUZZ-B-001` | 12:38:25 | 6,357 | 6,239 | 113 | 5 | 98.1% |
| 25 | `BE-FUZZ-B-002` | 12:38:26 | 7,652 | 7,549 | 100 | 3 | 98.7% |
| 26 | `BE-FUZZ-B-003` | 12:38:26 | 5,022 | 4,973 | 44 | 5 | 99.0% |
| 27 | `BE-FUZZ-E-001` | 12:38:31 | 7,167 | 7,076 | 86 | 5 | 98.7% |
| 28 | `BE-FUZZ-E-002` | 12:38:32 | 7,973 | 7,924 | 43 | 6 | 99.4% |
| 29 | `BE-FUZZ-E-003` | 12:38:32 | 7,036 | 6,987 | 43 | 6 | 99.3% |
| 30 | `BE-NAR-001` | 12:38:33 | 8,338 | 3,853 | 166 | 4,319 | 46.2% |
| 31 | `BE-NAR-002` | 12:38:38 | 5,520 | 5,458 | 51 | 11 | 98.9% |
| 32 | `BE-NAR-003` | 12:38:39 | 8,312 | 4,470 | 86 | 3,756 | 53.8% |
| 33 | `BE-NAR-004` | 12:38:40 | 5,216 | 5,118 | 88 | 10 | 98.1% |
| 34 | `BE-NAR-005` | 12:38:42 | 9,595 | 7,245 | 43 | 2,307 | 75.5% |

### 与 RUN-001 的可比变化

| 指标 | RUN-001 | RUN-002 | 绝对变化 | 百分比变化 |
|---|---:|---:|---:|---:|
| Task 时间窗 | 332s | 77s | -255s | -76.8% |
| Workflow root envelope | 331s | 76s | -255s | -77.0% |
| Workflow 累计工作量 | 330.767s | 286.785s | -43.982s | -13.3% |
| Workflow 平均 | 9.728s | 8.435s | -1.293s | -13.3% |
| Workflow P95 | 18.126s | 15.569s | -2.557s | -14.1% |
| Workflow 最大 | 23.572s | 15.923s | -7.649s | -32.4% |
| `AuditAgent` 累计 | 253.706s | 202.776s | -50.930s | -20.1% |
| `TraceAgent` 累计 | 58.065s | 43.600s | -14.465s | -24.9% |
| `ExtractionAgent` 累计 | 16.148s | 10.358s | -5.790s | -35.9% |
| RAG `search_rules` 累计 | 2.567s | 29.413s | +26.846s | +约 1046% |
| Prompt tokens | 94,631 | 94,631 | 0 | 0.0% |
| Completion tokens | 27,132 | 22,075 | -5,057 | -18.6% |
| Total tokens | 121,763 | 116,706 | -5,057 | -4.2% |
| Recorded cost | 0.0648 | 0.0604 | -0.0044 | -6.8% |

RUN-001 没有单独记录 client monotonic wall-clock，因此不把 RUN-002 的 76.646s 与一个不同口径的
基线强行计算百分比。可比的 Task 时间窗和 root envelope 分别改善 76.8% 与 77.0%。Workflow
累计工作量只下降 13.3%，而批次等待下降约 77%，两者差异正是并发重叠产生的主要收益。

### 运行质量与验收结论

- Trace runs：34；Trace Spans：217。
- `SUCCEEDED`：217；失败 Span：0；34 个 Workflow outcome 全为 `PENDING_HUMAN`。
- 34/34 snapshot 从 MySQL 重新加载后通过 `validate_trace_snapshot()`。
- Agent 调用 47 次，与 RUN-001 相同：Audit 34、Trace 10、Extraction 3。
- Tool 调用 45 次，未增加：`search_rules` 34、`load_confirmed_cases` 11。
- 重试恢复、`attempt > 1`、structured repair、cache hit 均为 0。
- CircuitBreaker 没有 open；未观察到 rate-limit 或 HTTP 失败。
- 批次 `76.646s <= 166s`，达到至少缩短 50% 的保留门禁。
- Workflow P95 `15.569s <= 21.751s`，没有以恶化单 Flow 延迟换取批次速度。
- Total tokens `116,706 <= 127,851`，未超过 RUN-001 的 105% 上限。
- 业务统计仍为 500 auto-fixed、34 AI processed、6 pending AI、28 pending human。

**结论：保留 4 路有界 Flow 并发优化。** 本次真实运行已经证明性能目标可达，但只有一个样本，
不应上升为长期 SLA。后续应至少重复 3 次同身份运行，报告中位数与方差；同时优先预热 RAG，
再独立评估 Audit 输出 contract 瘦身和安全分支确定性短路。

## RUN-003 — Rule-first 与 LLM allowlist 优化实测

### 记录身份

| 字段 | 值 |
|---|---|
| Record ID | `RUN-003` |
| Recorded at | `2026-07-16 21:24:49 +08:00` |
| Client execution window | `2026-07-16 21:24:27.497896–21:24:49.375536 +08:00` |
| Task execution window | `2026-07-16 21:24:27–21:24:49 +08:00` |
| Workflow root envelope | `2026-07-16 21:24:28–21:24:49 +08:00` |
| Branch | `main` |
| Git HEAD | `8131a5b7ba95013d03de7cb837f1d04a2e0afb05` |
| Uncommitted runtime source diff SHA-256 | `eec0aab804bfffdad1ae1e12b94565e264f4eee2763c79095378eb1a6de7e4e8` |
| Task ID | `TASK_6a5e0f671f64` |
| User ID | `demo_user` |
| Scenario | `BANK_ENTERPRISE` |
| Evidence source | client monotonic timer；`t_reconciliation_task`；本轮开始时间后的 34 个 root 与 207 个 `t_trace_span` |
| Evidence completeness | 34/34 Trace snapshot 重新加载并通过结构校验；207/207 Span 为 `SUCCEEDED` |
| Boundary | local demo runtime；真实 DeepSeek/bge_m3；单次运行；not production SLA |

本轮仍运行在未提交源码上。source diff 哈希覆盖 `.env.example` 及本轮实际 runtime 相关的 9 个
Python source 文件；测试、脚本、报告，以及用户已有的 `.gitignore` / `AGENTS.md` 改动不计入。

### 输入与运行时身份

| 字段 | 值 |
|---|---|
| Bank input | `mock_data/bank_enterprise_500_bank.xlsx`；526 行；98,042 bytes；SHA-256 `1105f8b9a3a8fa610b04c95bed3ee5667ba29f4e47b975ade9c85e500960f3b8` |
| Book input | `mock_data/bank_enterprise_500_book.xlsx`；522 行；87,628 bytes；SHA-256 `7b94da87b6669937aca2d19cd2ac7335f0df0485383c4eba4ae1a0787e011465` |
| Provider / model | `deepseek / deepseek-v4-flash`；6/6 Agent Span 一致 |
| Embedding | `bge_m3`；dense；新进程启动、复用已有持久化 collection fingerprint |
| Cache / rate limit | `false / false` |
| Timeout / max attempts | `30s / 3` |
| Reconciliation concurrency | 配置 4；最大观测 root 并发 4 |
| Retry / repair / cache hit | `0 / 0 / 0` |

两个输入文件与 RUN-001、RUN-002 的路径、行数、大小和哈希完全一致。

### 本轮实现策略

- `BE-R007 / FUZZY_MATCH_CANDIDATE` 的 6 条模糊候选继续调用 `AuditAgent`，保留 LLM 语义确认。
- 其余 28 条银企异常使用既有 `AuditAgent.decide()` 规则和同一份 RAG evidence，结果继续
  fail-closed 到 `PENDING_HUMAN`；Trace 记录为 `ROUTE / RuleAudit`，不伪装成 Agent 调用。
- `BE-R005`、`BE-R006` 不再调用结果未被消费的 `TraceAgent`。
- `BE-R004` 的显式冲正关键词用确定性解析代替 `ExtractionAgent`；3 条记录为
  `ROUTE / RuleExtraction`。
- Audit 模型输入只保留实际决策需要的 evidence 字段；最终持久化仍保留完整 evidence。
- RAG collection 使用“规则内容 + schema + scenario + embedding backend” fingerprint；内容未变化时
  跳过全量 upsert/re-embedding。

### 任务结果

| 指标 | RUN-003 |
|---|---:|
| HTTP status | 200 |
| Task status | `UPLOADED` |
| Bank / book rows | 526 / 522 |
| Auto-fixed / AI processed | 500 / 34 |
| Pending AI / pending human | 6 / 28 |
| Ledger final `PENDING_HUMAN` | 34/34 |
| Fallback paths | `RULE=28`；`HUMAN=6` |
| Fallback L2 / L3 | 0 / 0 |
| Prompt / completion / total tokens | 13,860 / 4,920 / 18,780 |
| Recorded cost | 0.0103 |

`RULE=28` 是本轮主动引入的执行路径变化，不是模型随机性：规则分支不再进入 L2/L3，但最终状态没有
放宽，仍全部进入人工复核。该变化减少了模型生成的 reason/confidence 个性化，不改变 auto-fix 边界。

### 批次级性能

| 指标 | RUN-003 |
|---|---:|
| Client wall-clock | 21.878s |
| Task `created_at → updated_at` | 22s |
| Workflow root envelope | 21s |
| Workflow duration sum | 60.911s |
| 并发因子 `sum / envelope` | 2.901 |
| 最大观测 root 并发 | 4 |

### 总体性能

所有耗时单位均为毫秒；P90/P95 使用 nearest-rank。

| 指标 | 样本数 | 总耗时 | 平均 | 中位数 | 最小 | P90 | P95 | 最大 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Workflow | 34 | 60,911 | 1,792 | 110 | 24 | 9,320 | 10,032 | 11,866 |
| `AuditAgent`（仅 allowlist） | 6 | 56,844 | 9,474 | 9,357 | 7,876 | 11,816 | 11,816 | 11,816 |
| RAG `search_rules` | 34 | 3,419 | 101 | 105 | 22 | 154 | 201 | 245 |
| `RuleAudit` | 28 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `RuleExtraction` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

毫秒级 Rule Span 被数据库整数毫秒字段记录为 0，表示低于 1ms，不表示没有执行。Workflow 的 P95
仍由 6 条真实 LLM 模糊候选决定；其余 28 条的 Workflow 中位数约为百毫秒量级。

### 按异常类型统计

| 类型 | 数量 | Workflow 平均 | 中位数 | 最快 | 最慢 |
|---|---:|---:|---:|---:|---:|
| `AMT` | 5 | 282ms | 295ms | 151ms | 379ms |
| `BONLY` | 5 | 136ms | 139ms | 108ms | 158ms |
| `DUP` | 8 | 99ms | 107ms | 81ms | 112ms |
| `EONLY` | 5 | 82ms | 81ms | 81ms | 84ms |
| `FUZZ-B` | 3 | 9.115s | 9.320s | 7.992s | 10.032s |
| `FUZZ-E` | 3 | 10.025s | 9.570s | 8.639s | 11.866s |
| `NAR` | 5 | 40ms | 25ms | 24ms | 101ms |

### Span 与调用结构

| Span / 调用 | RUN-003 |
|---|---:|
| Trace runs / total spans | 34 / 207 |
| Workflow / Route / Tool / Guard / Final / Agent | 34 / 65 / 34 / 34 / 34 / 6 |
| `RuleAudit` / `RuleExtraction` | 28 / 3 |
| `AuditAgent` / `TraceAgent` / `ExtractionAgent` | 6 / 0 / 0 |
| `search_rules` / `load_confirmed_cases` | 34 / 0 |
| Failed spans | 0 |

### 逐笔数据

| # | Flow ID | Workflow | Agent | RAG | 其他 |
|---:|---|---:|---:|---:|---:|
| 1 | `BE-AMT-001` | 249 | 0 | 245 | 4 |
| 2 | `BE-AMT-002` | 295 | 0 | 118 | 177 |
| 3 | `BE-AMT-003` | 379 | 0 | 201 | 178 |
| 4 | `BE-AMT-004` | 335 | 0 | 158 | 177 |
| 5 | `BE-AMT-005` | 151 | 0 | 147 | 4 |
| 6 | `BE-BONLY-001` | 158 | 0 | 154 | 4 |
| 7 | `BE-BONLY-002` | 139 | 0 | 135 | 4 |
| 8 | `BE-BONLY-003` | 138 | 0 | 134 | 4 |
| 9 | `BE-BONLY-004` | 139 | 0 | 136 | 3 |
| 10 | `BE-BONLY-005` | 108 | 0 | 105 | 3 |
| 11 | `BE-DUP-001-A` | 109 | 0 | 106 | 3 |
| 12 | `BE-DUP-001-B` | 112 | 0 | 108 | 4 |
| 13 | `BE-DUP-002-A` | 110 | 0 | 107 | 3 |
| 14 | `BE-DUP-002-B` | 108 | 0 | 104 | 4 |
| 15 | `BE-DUP-003-A` | 106 | 0 | 102 | 4 |
| 16 | `BE-DUP-003-B` | 82 | 0 | 78 | 4 |
| 17 | `BE-DUP-004-A` | 81 | 0 | 78 | 3 |
| 18 | `BE-DUP-004-B` | 82 | 0 | 78 | 4 |
| 19 | `BE-EONLY-001` | 81 | 0 | 79 | 2 |
| 20 | `BE-EONLY-002` | 81 | 0 | 78 | 3 |
| 21 | `BE-EONLY-003` | 84 | 0 | 78 | 6 |
| 22 | `BE-EONLY-004` | 81 | 0 | 78 | 3 |
| 23 | `BE-EONLY-005` | 82 | 0 | 78 | 4 |
| 24 | `BE-FUZZ-B-001` | 10,032 | 9,921 | 107 | 4 |
| 25 | `BE-FUZZ-B-002` | 9,320 | 9,210 | 107 | 3 |
| 26 | `BE-FUZZ-B-003` | 7,992 | 7,876 | 111 | 5 |
| 27 | `BE-FUZZ-E-001` | 8,639 | 8,518 | 116 | 5 |
| 28 | `BE-FUZZ-E-002` | 9,570 | 9,503 | 61 | 6 |
| 29 | `BE-FUZZ-E-003` | 11,866 | 11,816 | 44 | 6 |
| 30 | `BE-NAR-001` | 101 | 0 | 96 | 5 |
| 31 | `BE-NAR-002` | 27 | 0 | 24 | 3 |
| 32 | `BE-NAR-003` | 25 | 0 | 23 | 2 |
| 33 | `BE-NAR-004` | 24 | 0 | 22 | 2 |
| 34 | `BE-NAR-005` | 25 | 0 | 23 | 2 |

### 与 RUN-001、RUN-002 的变化

| 指标 | RUN-001 | RUN-002 | RUN-003 | RUN-002 → 003 |
|---|---:|---:|---:|---:|
| Task 时间窗 | 332s | 77s | 22s | -71.4% |
| Root envelope | 331s | 76s | 21s | -72.4% |
| Client wall-clock | 未单记 | 76.646s | 21.878s | -71.5% |
| Workflow 累计 | 330.767s | 286.785s | 60.911s | -78.8% |
| Workflow 平均 | 9.728s | 8.435s | 1.792s | -78.8% |
| Workflow P95 | 18.126s | 15.569s | 10.032s | -35.6% |
| `AuditAgent` 调用 / 累计 | 34 / 253.706s | 34 / 202.776s | 6 / 56.844s | 调用 -82.4%；耗时 -72.0% |
| `TraceAgent` 调用 / 累计 | 10 / 58.065s | 10 / 43.600s | 0 / 0 | -100% |
| `ExtractionAgent` 调用 / 累计 | 3 / 16.148s | 3 / 10.358s | 0 / 0 | -100% |
| RAG 累计 | 2.567s | 29.413s | 3.419s | -88.4% |
| Prompt tokens | 94,631 | 94,631 | 13,860 | -85.4% |
| Completion tokens | 27,132 | 22,075 | 4,920 | -77.7% |
| Total tokens | 121,763 | 116,706 | 18,780 | -83.9% |
| Recorded cost | 0.0648 | 0.0604 | 0.0103 | -82.9% |

相对最初 RUN-001，任务时间窗从 332s 降至 22s，缩短 93.4%，约为原来的 1/15.1。相对只做
并发的 RUN-002，客户端等待又从 76.646s 降至 21.878s，缩短 71.5%，约提升 3.5 倍。

### 扩容估算与结论

本轮端到端吞吐为 `34 / 21.878 = 1.554` 条异常/秒。只按同一异常类型比例和相同运行环境做线性
估算，500 条异常约需 `322s`，即约 `5.4 分钟`，不再是半小时起步；如果是 5,000 条普通流水且
异常率仍约为本批的 6.5%，异常处理部分约为 3.5 分钟。该数字不是 SLA：模糊候选占比、provider
延迟、匹配阶段复杂度和多批次竞争都会改变结果。

**结论：保留 RUN-003 优化。** 34 条异常的真实端到端时间已经降到 21.878s，业务行统计不变，
34/34 仍 fail-closed 到人工复核，且 token/cost 同步下降约 84%/83%。

### RUN-002 RAG 归因更正

复查后，RUN-002 首批约 6.7s 不应只描述成“模型/索引初始化”。更准确的原因是新进程打开
collection 后仍无条件执行了 91 条规则的 full upsert/re-embedding；并发首批的另外 3 个 Flow
还把共享锁等待计入各自 Span。RUN-003 的 fingerprint 命中后跳过重复构建，34 次检索累计恢复为
3.419s、最大 245ms。

## RUN-004 — 6 路 Flow 并发单变量实测

### 身份与边界

| 字段 | 值 |
|---|---|
| Client window | `2026-07-16 22:26:14.701048–22:26:26.672001 +08:00` |
| Task window / root envelope | 12s / 12s |
| Git HEAD | `8131a5b7ba95013d03de7cb837f1d04a2e0afb05` |
| Runtime change vs RUN-003 | 仅默认及显式 `RECONCILIATION_MAX_CONCURRENCY: 4 → 6` |
| Exact RUN-004 source diff hash | `not captured`；由上述单变量变更、RUN-003 hash 和 Trace 身份界定 |
| Input / provider / embedding | 与 RUN-003 完全一致；`deepseek-v4-flash / bge_m3` |
| Prompt | `audit_v3`；6/6 Agent Span |
| Cache / rate limit / attempts | `false / false / 1` |
| Trace | 34 runs；207 spans；207/207 `SUCCEEDED`；34/34 snapshot 校验通过 |

RUN-004 在 Audit v4 修改前完成，因此与 RUN-003 的唯一 runtime 变量是并发上限 4→6。由于当时未在
修改 Audit v4 前捕获完整 diff byte stream，本记录不补造 source hash，明确标记 `not captured`。

### 结果

| 指标 | RUN-003 | RUN-004 | 变化 |
|---|---:|---:|---:|
| Client wall-clock | 21.878s | 11.971s | -45.3% |
| Task window | 22s | 12s | -45.5% |
| Root envelope | 21s | 12s | -42.9% |
| 最大观测并发 | 4 | 6 | +2 |
| Workflow 累计 | 60.911s | 59.722s | -2.0% |
| Workflow 平均 / 中位数 | 1.792s / 110ms | 1.757s / 161ms | 平均 -2.0% |
| Workflow P95 / max | 10.032s / 11.866s | 10.148s / 10.768s | P95 +1.2%；max -9.3% |
| Audit 累计 / 平均 / max | 56.844s / 9.474s / 11.816s | 54.086s / 9.014s / 10.621s | 累计 -4.9% |
| RAG 累计 / 中位数 | 3.419s / 105ms | 4.665s / 141ms | provider 外局部波动 |
| Prompt / completion tokens | 13,860 / 4,920 | 13,860 / 4,534 | completion -7.8% |
| Total tokens / cost | 18,780 / 0.0103 | 18,394 / 0.0100 | -2.1% / -2.9% |

业务结果保持 526/522 输入、500 auto-fixed、34 AI processed、6 pending AI、28 pending human；
fallback 为 `RULE=28 / HUMAN=6`，34/34 最终 `PENDING_HUMAN`，0 retry、0 repair、0 cache hit。

**结论：保留默认并发 6。** 6 条 LLM 模糊候选从两波变为同一波执行，client wall-clock 降到
11.971s；单 Flow P95 只波动 +1.2%，没有通过恶化单笔尾延迟换取批次速度。

## RUN-005 — Audit v4 输出 contract 单变量实测

### 身份与实现

| 字段 | 值 |
|---|---|
| Client window | `2026-07-16 22:30:36.965921–22:30:49.283815 +08:00` |
| Task window / root envelope | 12s / 12s |
| Git HEAD | `8131a5b7ba95013d03de7cb837f1d04a2e0afb05` |
| Runtime source diff SHA-256 | `e4dae47600de167dfdab37eff9c2d2157272c36c83d4bd0b135b66bbde2441c0` |
| Input / provider / embedding | 与 RUN-004 完全一致；`deepseek-v4-flash / bge_m3` |
| Prompt | `audit_v4`；6/6 Agent Span |
| Concurrency | 6；最大观测 6 |
| Trace | 34 runs；207 spans；207/207 `SUCCEEDED`；34/34 snapshot 校验通过 |

Audit v4 删除内部 `LLMAuditDecision.evidence`，因为模型生成该字段后代码从不消费，最终
`AuditDecision.evidence` 始终使用可信的原始 RAG evidence。Prompt 同时要求 reason 为简短单句、
`ai_suggestion` 为短动作；没有设置可能截断 JSON 的 `max_tokens`。外部 AuditDecision schema、
RAG 证据链、安全 Hook、auto-fix 和人工复核边界不变。

### 结果

| 指标 | RUN-004（v3） | RUN-005（v4） | 变化 |
|---|---:|---:|---:|
| Client wall-clock | 11.971s | 12.318s | +2.9% |
| Workflow 累计 | 59.722s | 58.298s | -2.4% |
| Workflow 平均 / 中位数 | 1.757s / 161ms | 1.715s / 163ms | 平均 -2.4% |
| Workflow P95 / max | 10.148s / 10.768s | 9.338s / 11.161s | P95 -8.0%；max +3.6% |
| Audit 累计 / 平均 / max | 54.086s / 9.014s / 10.621s | 52.461s / 8.744s / 10.987s | 累计 -3.0% |
| Prompt tokens | 13,860 | 14,034 | +1.3% |
| Completion tokens | 4,534 | 3,978 | -12.3% |
| Total tokens / cost | 18,394 / 0.0100 | 18,012 / 0.0096 | -2.1% / -4.0% |
| Retry / structured repair / cache | 0 / 0 / 0 | 0 / 0 / 0 | 不变 |

业务与 Trace 结果继续完全满足门禁：500 auto-fixed、34 AI processed、6/28 pending、34/34
`PENDING_HUMAN`、207/207 succeeded。RUN-005 client 比 RUN-004 慢 0.347s，属于单次 provider
尾延迟波动，不能宣称 v4 改善了 wall-clock；但 Workflow/Audit 累计下降，completion tokens
下降 12.3%，成本下降 4.0%，且没有 repair，因此保留 v4 的依据是更小、更诚实的输出 contract
和可观测成本收益，不是未经重复验证的延迟收益。

### 当前总结果

| 指标 | RUN-001 | 当前 RUN-005 | 总变化 |
|---|---:|---:|---:|
| Task window | 332s | 12s | -96.4% |
| Workflow 累计 | 330.767s | 58.298s | -82.4% |
| Workflow P95 | 18.126s | 9.338s | -48.5% |
| Agent 调用 | 47 | 6 | -87.2% |
| Total tokens | 121,763 | 18,012 | -85.2% |
| Recorded cost | 0.0648 | 0.0096 | -85.2% |

当前端到端吞吐为 `34 / 12.318 = 2.760` 条异常/秒。仅按相同异常结构线性估算，500 条异常约
181s，即约 3.0 分钟。该值仍不是生产 SLA。

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
