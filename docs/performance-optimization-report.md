# 银企对账批处理性能优化报告

## 1. 结论摘要

两轮优化均已完成代码实现、专项测试、全量回归和真实 DeepSeek/bge_m3 复测。

重点优化的不是 RAG 检索本身，而是
`ReconciliationService._build_write_bundle()` 对 34 个独立异常 Flow 的串行调度方式。
RUN-001 中 `AuditAgent` 是最大的单项耗时，占 Workflow 累计耗时 76.7%；与此同时，
34 个 Flow 完全串行，导致这些同步 LLM 等待几乎直接累加为整批等待时间。

第一轮采用“进程级有界 Flow 并发 + 线程私有 Agent/provider + 顺序归并、单线程写库”方案，
默认并发度为 4，可配置范围为 1–8。该方案不修改模型、Prompt、审计决策规则、RAG 证据、
Fallback 语义或单 Flow 调用顺序，目标是在尽量不引入质量变量的前提下显著缩短批次 wall-clock。

代码验证后已完成真实 DeepSeek/bge_m3 RUN-002。可比的任务时间窗从 RUN-001 的约 `332s`
降至 `77s`，缩短 `76.8%`；Workflow 根 Span envelope 从约 `331s` 降至 `76s`，缩短
`77.0%`。客户端同步请求实测为 `76.646s`，最大观测并发为 4，并发因子为 3.773。
34/34 Workflow、217/217 Span 全部成功，最终结果仍全部安全落到 `PENDING_HUMAN`。

第二轮直接优化 RUN-002 中仍存在的 47 次 LLM 调用：只允许 6 条 `BE-R007` 模糊候选进入
`AuditAgent`，其余 28 条异常使用既有确定性规则审计；同时删除 `BE-R005/R006` 未被下游消费的
10 次 `TraceAgent` 调用、用规则解析替代 3 次 `ExtractionAgent` 调用，并通过 RAG fingerprint
跳过重复规则 embedding。真实 RUN-003 的客户端端到端时间进一步降至 `21.878s`，相对 RUN-002
再缩短 `71.5%`，相对 RUN-001 的任务时间窗缩短 `93.4%`。LLM 调用从 47 降到 6，tokens 从
116,706 降到 18,780，成本从 0.0604 降到 0.0103；34/34 最终状态仍为 `PENDING_HUMAN`。

第三轮继续处理剩余 6 条模糊候选关键路径。先用单变量 RUN-004 把并发从 4 提升到 6，使 6 次
LLM 请求由两波变为同一波，客户端时间从 21.878s 降到 11.971s，再缩短 45.3%。随后 Audit v4
删除模型生成但代码从不消费的 evidence 输出，并限制 reason/ai_suggestion 长度。RUN-005 的
client wall-clock 为 12.318s，未证明比 RUN-004 更快，但 completion tokens 下降 12.3%、成本下降
4.0%，无 structured repair，因此保留 v4 的理由是更小的输出 contract 和成本收益。

实施前的 `90.156s` 和 `72.7%` 仍只代表基于 RUN-001 逐 Flow 耗时做的 4-worker
list-scheduling 理论估算；本报告的优化结论以 RUN-002 的真实数据为准。

## 2. RUN-001 瓶颈证据

| 指标 | RUN-001 |
|---|---:|
| 批次任务时间窗 | 332s |
| Workflow 根 Span envelope | 331s |
| Workflow 累计工作量 | 330.767s |
| Workflow 平均 | 9.728s |
| Workflow P95 | 18.126s |
| `AuditAgent` 累计 | 253.706s |
| `AuditAgent` 占 Workflow 累计 | 76.7% |
| `TraceAgent` 累计 | 58.065s |
| `ExtractionAgent` 累计 | 16.148s |
| RAG `search_rules` 累计 | 2.567s |
| 真实处理 Flow | 34 |
| 重试 / cache hit / structured repair | 0 / 0 / 0 |

上述数据说明两件事：

1. 单 Flow 内最重的是 `AuditAgent` 的远程模型生成，不是平均 76ms 的 RAG。
2. 对用户可感知的整批等待而言，更直接的问题是 34 个数据独立 Flow 被完全串行执行。

根据 RUN-001 的 34 个逐 Flow Workflow duration 做同顺序、动态空闲 worker 调度估算：

| worker 数 | 理论批次耗时 | 相对 330.767s 缩短 |
|---:|---:|---:|
| 2 | 171.568s | 48.1% |
| 3 | 118.542s | 64.2% |
| 4 | 90.156s | 72.7% |

4-worker 的理想平均下界为 `330.767 / 4 = 82.692s`。考虑 RAG 串行保护、数据库读取、
provider 竞争和归并开销，实施前的现实预期区间为 90–120s。真实 RUN-002 的 client wall-clock
为 76.646s，优于该区间；原因之一是本轮单 Flow 的模型工作量也比 RUN-001 更低。

## 3. 重点优化模块

### 3.1 批次 Flow 调度

主要修改位置：

- `src/bank_reconciliation_agent/services/reconciliation.py`
- `src/bank_reconciliation_agent/services/workflow.py`

原实现是在 `_build_write_bundle()` 中逐条执行完整 Workflow，再处理下一条异常。新实现把每个
非 `AUTO_FIXED` Flow 的计算和外部调用阶段提交到独立的进程级线程池，并按原始输入顺序回收结果。
所有 Flow 完成后，主线程才归并 ledger、RAG log、Agent log、Trace、token 和 fallback 统计，
随后沿用原事务边界批量写库。

### 3.2 Agent 调用状态隔离

原模块级 `AuditAgent`、`TraceAgent`、`ExtractionAgent` 都通过可变字段
`last_llm_result` / `last_llm_summary` 暂存最近一次调用信息。若直接并发复用单例，Flow A 返回后，
Flow B 可能在 Trace 读取前覆盖这些字段，导致 model、token、attempt 和 retry 信息串线。

新实现为每个 Flow worker 维护线程私有 `WorkflowAgentSuite`。同一 worker 内的三个 Agent 共享该
worker 私有 provider，以复用 HTTP client；不同 worker 之间不共享 Agent 或 provider 实例。

### 3.3 进程级 admission gate

配置项：

```text
RECONCILIATION_MAX_CONCURRENCY=6
```

RUN-002/RUN-003 验证阶段默认值为4；RUN-004 单变量通过后当前默认值提升为6，配置合法范围仍为1–8。

Flow executor、单 Flow、`max_concurrency=1` 和 emitter/SSE 直执行路径全部经过同一个进程级
`BoundedSemaphore`。因此多个同时到达的批次也不会各自创建 4 个不受控调用。

SSE/emitter 路径在单个批次内仍保持串行，继续保证原有 `stream_seq` 单调和事件顺序；它只与其他
批次共享全局 admission 上限。

### 3.4 RAG 与 CircuitBreaker 并发安全

RAG 的共享 Chroma collection、SentenceTransformer 和 lazy index 状态没有原生并发初始化契约。
RUN-001 中 RAG 总耗时只有 2.567s，因此本轮使用小范围锁串行保护 `search_rules`，以很小的性能代价
避免共享模型和 breaker 竞争。

LLM/RAG CircuitBreaker 改为原子 `acquire()`，返回带 generation 的 permit。成功、失败和不计入
breaker 的 neutral 结果只能结算自己获准时的 generation；旧请求的迟到成功或失败不能覆盖后来
已经进入 `OPEN` / `HALF_OPEN` 的状态。`HALF_OPEN` 同时只允许一个 probe。

## 4. 为什么选择这个方案

### 4.1 直接改善用户等待时间

34 个 Flow 之间没有业务数据依赖；本批结果在全部 Workflow join 后才统一写入，不依赖“前一笔先完成”。
远程 LLM 是同步 I/O 等待，使用有界线程可以重叠这些等待，因此理论上可获得接近 worker 数的批次级
加速，而不需要改变单笔业务判断。

### 4.2 质量变量最少

本轮不切换模型、不缩短 Prompt、不删 RAG 证据、不改变确定性规则与 LLM 的职责，也不增加 LLM
调用次数。RUN-002 的 completion tokens 与 fallback 分布确有变化，但 prompt tokens 和调用结构
保持一致，因此主要归因于 provider 本身的非完全确定性，而不是本轮主动改变审计逻辑。

### 4.3 改动边界可验证

并发只覆盖 Flow 的计算和外部调用阶段；数据库持久化、结果顺序和 SSE 单批次顺序仍沿用原边界。
因此可以分别验证并发上限、Agent usage 隔离、Trace 完整性、串并行 canonical 等价与失败无部分写。

### 4.4 默认并发 4 是保守值

4 路足以把理论批次时间从约 331s 压缩到 90s 左右，同时比 8 路更不容易触发 provider 限流、
本机连接池竞争或瞬时资源峰值。配置允许降为 1 做故障排查，也允许在后续容量测试后提高到 8。

## 5. 为什么本轮不采用其他方案

### 5.1 不优先优化 RAG

`search_rules` 平均 76ms、累计仅占 Workflow 0.78%。Stage 31 对单个 BE-R004 的真实测量也显示，
Extraction 与 RAG 并行的理论 P95 改善只有 0.633%。为这一段增加内部并行不会显著改善整批耗时。

### 5.2 不依赖 LLM cache

RUN-001 的 34 个 payload 包含不同 flow_id、金额和证据，首次批处理没有 cache hit。Cache 适合重复
请求或重放，不适合作为这次冷批次的主要优化手段。

### 5.3 不立即缩 Prompt 或限制输出 token

RUN-001 中 Audit completion tokens 与 latency 的 Pearson 相关系数约为 0.908，说明输出长度确实是
下一阶段的重要优化点。但直接设置过低 `max_tokens` 可能截断 JSON，触发 structured repair 或
fail-closed；压缩 reason/evidence 也需要真实质量评测。它值得做 A/B，但不应与首轮调度优化同时引入，
否则无法判断性能和质量变化来自哪一项。

### 5.4 不立即让普通 audit 全部走确定性 fast path

现有 `AuditAgent.decide()` 和分支 profile 可以覆盖 RUN-001 的多个普通分支；理论上只保留 fuzzy
confirmation 的 LLM，可减少大量模型调用。但是这会改变 reason、confidence、L1/L2 fallback 路由
和项目中“AI 审计建议”的表达能力，需要独立 real-agent eval 和人工业务审查。相比之下，Flow 并发
不主动改变决策语义，风险更低。

### 5.5 不切换更快模型

换模型会同时改变延迟、质量、token 统计和成本，无法与 `deepseek-v4-flash` RUN-001 做单变量对比。
模型路由应作为独立实验，并设置决策一致性与高风险召回门禁。

### 5.6 不拆成每 Flow 一个 ARQ 分布式任务

该方案可以跨进程扩展，但需要新增子任务幂等、fan-out/fan-in reducer、部分失败恢复、Trace 聚合、
任务终态和队列容量治理。对当前 34 个 I/O-bound Flow 而言，本地有界线程池能用更小改动验证主要收益。

### 5.7 不迁移到完整 async/await 或 LangGraph 主图

当前 provider、ToolExecutor 和主要服务均为同步 contract。立即迁移会扩大 API、测试和失败取消语义，
超出本轮“用最小改动缩短批次时间”的目标。

## 6. 代码与测试验证

### 6.1 新增验证范围

- 多 Flow 实际并发，active 数不超过进程级 cap。
- 两个批次、多个单 Flow 批次、多个 emitter 批次共享同一 cap。
- `max_concurrency=1` 时跨批次仍严格串行。
- 乱序完成后 ledger、RAG log、Agent log、Trace 和统计仍保持输入顺序。
- 已知 Agent 错误只让当前 Flow fail-closed；非预期错误在持久化前取消待执行项，并等待已启动项结束。
- Flow executor 与 Tool executor 相互独立，不发生嵌套线程池死锁。
- 真链路两 Flow 集成覆盖：
  `_build_write_bundle → _build_flow_bundle → run_item → Agent → Tool/RAG → TraceRecorder → finalize → merge`。
- 每 Flow 的 provider、thread、model、prompt/completion tokens、Trace ID 和 sequence 不串线。
- 串行与并发 canonical bundle 等价。
- CircuitBreaker late success、late failure、HALF_OPEN 单 probe、neutral release 和原子 before/after。

### 6.2 验证结果

| 门禁 | 结果 |
|---|---|
| 并发/CircuitBreaker 专项 | `72 passed` |
| Focused 回归 | `209 passed, 5 warnings` |
| 全量 mock/hash 回归 | `1242 passed, 1 skipped, 6 warnings in 40.61s` |
| RUN-002 后最终定向复跑 | `123 passed, 5 warnings in 2.49s` |
| RUN-003 最终全量 mock/hash 回归 | `1251 passed, 1 skipped, 6 warnings in 39.18s` |
| RUN-004 并发专项 | `61 passed` |
| RUN-005 最终全量 mock/hash 回归 | `1252 passed, 1 skipped, 6 warnings in 39.58s` |
| Changed-path Ruff check | 通过 |
| Repo-wide format-check | 既有 baseline 未通过；80 个文件待格式化，本轮不做无关批量改写 |
| 本次改动 scoped `git diff --check` | 通过 |
| 独立 blocker-first 二次复审 | GREEN；无剩余 P0/P1 |

全量测试显式固定 `LLM_PROVIDER=fake`、`EMBEDDING_BACKEND=hash`、cache/rate-limit disabled，
避免普通回归误调用真实 DeepSeek。该测试证明功能和并发 contract，不代表真实 provider 性能。

## 7. 真实 RUN-002 结果与验收门禁

真实复测必须与 RUN-001 保持以下身份一致：

- 输入：
  - `mock_data/bank_enterprise_500_bank.xlsx`
  - SHA-256 `1105f8b9a3a8fa610b04c95bed3ee5667ba29f4e47b975ade9c85e500960f3b8`
  - `mock_data/bank_enterprise_500_book.xlsx`
  - SHA-256 `7b94da87b6669937aca2d19cd2ac7335f0df0485383c4eba4ae1a0787e011465`
- Scenario：`BANK_ENTERPRISE`
- Provider/model：`deepseek / deepseek-v4-flash`
- Embedding：effective `bge_m3`，dense mode
- Cache/rate limit：`false / false`
- Timeout/max attempts：`30s / 3`
- 并发配置：`RECONCILIATION_MAX_CONCURRENCY=4`

保留优化至少要满足：

| 门禁 | 阈值 |
|---|---:|
| 批次 wall-clock | `<= 166s`，即相对约 332s 至少改善 50% |
| Workflow root envelope | 相对 RUN-001 明显下降，并单独报告 |
| 单 Flow Workflow P95 | `<= 21.751s`，不比 18.126s 恶化超过 20% |
| 业务统计 | 500 auto-fixed、34 AI processed、6 pending AI、28 pending human |
| Trace 完整性 | 34/34；每个 snapshot 结构合法 |
| 失败 | 无新增 FAILED span、breaker open、rate-limit、重试异常 |
| 逻辑调用数 | Agent/Tool 调用数不增加 |
| token/cost | token 不高于 RUN-001 的 105%，即不超过 127,851 |
| 决策 | 34 个 Workflow 继续全部安全落到 `PENDING_HUMAN` |

### 7.1 实测结果

| 指标 | RUN-001 | RUN-002 | 变化 |
|---|---:|---:|---:|
| 任务时间窗 | 332s | 77s | -255s（-76.8%） |
| Workflow 根 Span envelope | 331s | 76s | -255s（-77.0%） |
| 客户端同步请求 | 未单独记录 | 76.646s | 不与不同口径强算变化 |
| Workflow 累计工作量 | 330.767s | 286.785s | -43.982s（-13.3%） |
| Workflow 平均 | 9.728s | 8.435s | -1.293s（-13.3%） |
| Workflow P95 | 18.126s | 15.569s | -2.557s（-14.1%） |
| Workflow 最大 | 23.572s | 15.923s | -7.649s（-32.4%） |
| `AuditAgent` 累计 | 253.706s | 202.776s | -50.930s（-20.1%） |
| 总 LLM tokens | 121,763 | 116,706 | -5,057（-4.2%） |
| 记录成本 | 0.0648 | 0.0604 | -0.0044（-6.8%） |
| 并发因子 `Workflow sum / envelope` | 约 1.00 | 3.773 | 证明等待被有效重叠 |
| 最大观测 Workflow 并发 | 1 | 4 | 符合配置上限 |

RUN-002 的客户端时间窗为 `2026-07-16 12:37:34.586933–12:38:51.231926 +08:00`；
任务表时间窗为 `12:37:34–12:38:51`；根 Span envelope 为 `12:37:35–12:38:51`。
并发后，Workflow sum 是总工作量，不再等于用户等待时间。

本轮 RAG `search_rules` 累计为 29.413s，明显高于 RUN-001 的 2.567s。复查后的准确归因是：
新进程打开 collection 后仍无条件执行了 91 条规则的 full upsert/re-embedding；首批另外 3 个
Flow 还把共享锁等待计入各自 Span，因此累计值被放大。其余 Flow 的 RAG 中位数仍为 86ms。

### 7.2 门禁结论

| 门禁 | 阈值 | RUN-002 | 结果 |
|---|---:|---:|---|
| 批次 wall-clock | `<= 166s` | 76.646s | PASS |
| Workflow root envelope | 明显下降 | 331s → 76s | PASS |
| 单 Flow Workflow P95 | `<= 21.751s` | 15.569s | PASS |
| 业务统计 | 500 / 34 / 6 / 28 | 完全一致 | PASS |
| Trace 完整性 | 34/34，结构合法 | 34/34；217/217 succeeded | PASS |
| 失败与可靠性 | 无新增异常 | 0 failed、0 retry、0 repair、0 cache | PASS |
| 逻辑调用数 | 不增加 | Agent 47 不变；Tool 45，未增加 | PASS |
| token/cost | tokens `<= 127,851` | 116,706 / 0.0604 | PASS |
| 最终决策 | 34 个 `PENDING_HUMAN` | 34 个 `PENDING_HUMAN` | PASS |

Fallback L2 从 15 变为 11，但 34 个最终安全状态、业务行统计和调用结构没有改变。这属于
真实 LLM 输出的非确定性，不应误记为并发带来的业务语义变化。全部性能与安全门禁通过，结论是
**保留本轮优化**。

### 7.3 RUN-003：重点模块、方案与真实结果

第二轮的重点已经从“批次调度”转向 `services/workflow.py` 中的 Agent 路由。RUN-002 的 47 次
LLM 调用里，`AuditAgent` 34 次、`TraceAgent` 10 次、`ExtractionAgent` 3 次；Audit 独占
202.776s 累计耗时和 93.4% 的 token。对 28 条非模糊异常，系统已有明确错误类型、异常分支、
金额差额和 RAG 规则，最终策略又必须进入人工复核，让 LLM 再生成一次相同方向的建议没有改变
处置边界，却承担了绝大部分延迟和费用。

#### 选用的优化方案

1. **Rule-first + LLM allowlist**：仅 `BE-R007 / FUZZY_MATCH_CANDIDATE` 保留 LLM 语义确认；
   其余银企分支调用既有 `AuditAgent.decide()`，保守返回 `PENDING_HUMAN`。
2. **删除无消费调用**：`BE-R005/R006` 的 Trace 输出没有进入后续审计输入，因此跳过 10 次
   `TraceAgent`；`BE-R004` 的显式冲正关键词由确定性 parser 处理，替代 3 次 Extraction。
3. **Audit evidence 投影**：模型输入只保留 `chunk_id/source_name/section_title/score/content`，
   最终 AuditDecision 和持久化仍使用完整原始 evidence。
4. **RAG fingerprint**：规则、schema、scenario、embedding backend 未变化时跳过全量 upsert 和
   embedding；内容变化或 stale ID 仍会重建，初始化失败也不会缓存半成品。

#### 为什么选择该方案

- 它直接消除 RUN-002 中最大且可证明冗余的远程调用，而不是只在外围继续增加线程。
- 决策边界可守住：规则路径不能 auto-fix，28 条仍全部进入人工复核；只有需要候选语义判断的
  模糊分支保留 LLM。
- 既有规则函数、RAG evidence、Constraint/Decision Hook 和 Trace contract 可以复用，代码改动
  小于重新训练模型或重写整个工作流。
- `RuleAudit` / `RuleExtraction` 使用 ROUTE Span 和零 token 记账，避免把规则执行伪装成模型调用，
  后续性能数据仍可审计。

#### 为什么没有采用其他方法

- **不继续盲目提高并发到 8/16**：RUN-002 已达到 4 路并发，但单 Flow 仍有 5–9s LLM 延迟；更高
  并发只能重叠等待，不能减少 47 次调用、tokens 和 provider 限流风险。
- **不全部取消 LLM**：`BE-R007` 需要综合候选交易语义、日期、对手方和证据，纯关键词规则容易把
  假候选当真匹配，因此 6 条仍走模型并最终 fail-closed。
- **不换更快/更小模型**：这会把模型质量和性能同时变成变量，无法判断收益来自路由还是模型；且
  当前真实 provider 已经可用，先消除无价值调用收益更确定。
- **不截断 evidence content 或强设很小 max_tokens**：可能造成 JSON 截断、structured repair 和
  证据缺失，反而放大尾延迟；本轮只删除明确未消费的元数据字段。
- **不做结果缓存代替路由**：流水内容和证据组合高基数，命中率不稳定；审计结论缓存还需要失效、
  规则版本和租户隔离设计。fingerprint 只缓存确定性的规则索引身份，风险更低。
- **不立即迁移 async/分布式 fan-out**：会扩大 provider、Tool、事务、Trace、取消和幂等 contract；
  当前主要浪费在调用本身，先减少调用比重构执行框架更直接。

#### RUN-003 实测

| 指标 | RUN-001 | RUN-002 | RUN-003 |
|---|---:|---:|---:|
| Task 时间窗 | 332s | 77s | 22s |
| Client wall-clock | 未单记 | 76.646s | 21.878s |
| Workflow 累计 | 330.767s | 286.785s | 60.911s |
| Workflow 平均 / P95 | 9.728s / 18.126s | 8.435s / 15.569s | 1.792s / 10.032s |
| Agent 调用 | 47 | 47 | 6 |
| Prompt / completion tokens | 94,631 / 27,132 | 94,631 / 22,075 | 13,860 / 4,920 |
| Total tokens / cost | 121,763 / 0.0648 | 116,706 / 0.0604 | 18,780 / 0.0103 |
| 最终 `PENDING_HUMAN` | 34/34 | 34/34 | 34/34 |

RUN-003 相对 RUN-002 的 client wall-clock 缩短 71.5%，相对 RUN-001 的任务时间窗缩短 93.4%。
本批 500 条正常自动核销流水加 34 条异常的总处理时间为 21.878s。按同一异常类型比例线性外推，
500 条异常约 5.4 分钟，不再是半小时起步；该估算不是生产 SLA。

### 7.4 RUN-004 / RUN-005：剩余关键路径优化

RUN-003 的 6 次 Audit LLM 单次耗时为 7.9–11.8s，但并发上限为 4，因此形成两波等待。RUN-004
只把默认并发改为 6，保持模型、Prompt v3、RAG、调用数和业务逻辑不变：

| 指标 | RUN-003（并发4） | RUN-004（并发6） | 变化 |
|---|---:|---:|---:|
| Client wall-clock | 21.878s | 11.971s | -45.3% |
| 最大观测并发 | 4 | 6 | +2 |
| Workflow P95 | 10.032s | 10.148s | +1.2% |
| 最终 `PENDING_HUMAN` | 34/34 | 34/34 | 不变 |

这证明并发6的收益来自消除第二波排队，而不是降低单次模型耗时。配置范围仍限制为 1–8，所有批次
继续共享进程级 semaphore，避免每个请求各自创建不受控的6路调用。

Audit contract 审计还发现，内部 `LLMAuditDecision.evidence` 要求模型重复生成证据列表，但最终
`AuditDecision` 完全不消费该字段，而是始终保留原始 RAG evidence。Audit v4 删除该无效输出，要求
reason 单句且建议不超过60个中文字符、ai_suggestion 为短动作，不设置容易截断 JSON 的 max_tokens。

| 指标 | RUN-004（v3） | RUN-005（v4） | 变化 |
|---|---:|---:|---:|
| Client wall-clock | 11.971s | 12.318s | +2.9% |
| Audit 累计 | 54.086s | 52.461s | -3.0% |
| Completion tokens | 4,534 | 3,978 | -12.3% |
| Total tokens / cost | 18,394 / 0.0100 | 18,012 / 0.0096 | -2.1% / -4.0% |
| Structured repair | 0 | 0 | 不变 |

RUN-005 单次 client 反而慢0.347s，因此不把 v4 宣传成已证实的延迟优化；provider 尾延迟波动大于
本次 Prompt 收益。v4 仍予保留，因为它删除了不真实的模型职责、减少 completion/cost、没有引入
repair，并保持完整原始证据链。

模糊候选审计发现6条记录实际是3个双边镜像 pair。当前不直接规则化为 AUTO_FIXED，因为这会改变
34/34 人工复核边界；canonical pair single-flight 可把调用6→3，但在6路并发下未必降低 wall-clock，
主要收益将是成本、双边一致性和 provider 压力，必须先补币种、方向、账号碰撞、多候选等负向门禁。

## 8. 有没有更好的优化方案

有。Rule-first、evidence 投影和 RAG fingerprint 已在 RUN-003 落地，下一步应按独立实验推进：

1. **Canonical pair single-flight**：6条模糊记录是3个双边镜像 pair，可让每对只调用一次 LLM，
   双边复用同一判断。它主要减少50%调用和成本；在当前6路并发下未必缩短 wall-clock，且必须补齐
   币种、方向、账号、订单号、多候选和缺字段的负向门禁。
2. **补全 confirm_match 上下文**：当前 `current_transaction` 只传 flow_id 和金额，缺日期、对手方等
   Router 已用过的关键字段，LLM 无法真正完成双边语义比较。应先补上下文，再评估是否允许任何
   AUTO_FIXED；在此之前保持全部人工复核。
3. **批量 LLM 审计**：把同一批 2–4 个灰区候选放进一次结构化请求，可降低网络 round-trip；但必须
   保证逐 Flow schema、失败隔离、token 上限和 Trace 可归属，不能让一条坏输出拖垮整批。
4. **真正的启动 warmup**：fingerprint 已消除重复 embedding，但新进程仍要加载 bge_m3；可在接收
   请求前完成模型与 collection warmup，把启动成本移出首批用户请求，并增加 readiness 门禁。
5. **Audit v4 重复 A/B**：单次 RUN-005 已证明 completion/cost 下降，但没有证明 wall-clock 下降；
   至少重复3次 v3/v4 交错运行，以 client 中位数和 provider 尾延迟判断真实收益。
6. **原生 async provider + semaphore**：长期可减少线程占用，并为连接池、timeout 和 cooperative
   cancellation 提供更清晰的控制，但需要迁移同步 Tool/Agent contract。
7. **自适应并发**：根据 429、timeout、P95 和 provider 限额动态在 2–8 之间调节，而不是固定 6。
8. **跨进程容量治理**：当前 cap 是单进程级；多个 ARQ worker 进程仍会各有一个 cap。生产化时应由
   Redis semaphore/rate limiter 提供实例间全局背压。
9. **自动性能采集器**：新增从 `t_reconciliation_task + t_trace_span` 按本轮时间窗生成 RUN 记录的
   collector，避免相同确定性 task_id 的历史 Trace 混入比较。
10. **重复实测与方差门禁**：各方案仍只有一次真实收费运行；后续至少做3次同身份复测并报告
   client wall-clock 中位数、P95 和方差，避免把 provider 瞬时波动当作稳定收益。

## 9. 已知残余风险

- `_ordered_flow_results` 按输入顺序观察 Future；若后序 Future 先失败，可能要等较慢的前序 Future
  完成后才发现异常。当前保证的是“抛错前等待/取消本批工作且不写部分业务数据”，不是真正 fail-fast。
- Python `Future.cancel()` 只能可靠取消尚未开始的任务，无法强制终止已进入底层同步调用的线程。
  ToolExecutor 超时后，已运行的 adapter 可能短暂继续工作。这是既有同步工具 contract 的限制。
- RAG 为共享状态安全而串行，若未来 RAG 迁移成远程高延迟服务，应重新评估该锁和单独的连接池。
- 当前并发上限是进程级，不是多 worker/多机器的集群级总上限。
- Rule-first 改变了 28 条记录的 reason/confidence 来源和 fallback path（`RULE`），虽然未放宽
  `PENDING_HUMAN`/auto-fix 边界，仍应补充固定黄金集比较高风险召回和解释一致性。
- RUN-003 是一次真实运行，足以验证本批性能和路由机制，但不能代表长期 SLA 或 provider 延迟分布。

## 10. 当前状态

```text
implementation: complete
deterministic_regression: passed
independent_review: green
real_run_002: passed
real_run_003: passed
real_run_004: passed
real_run_005: passed_with_no_latency_claim
history_update: complete
decision: retain optimization
```

RUN-002 至 RUN-005 的运行身份、任务数据和前后对比已追加到
`docs/performance-evaluation-history.md`。
