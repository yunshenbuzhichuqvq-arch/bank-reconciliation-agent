# Stage 29 Spec: TraceSpan 与任务回放

**Stage**: `stage-29-trace-replay`
**Branch**: `stage-29-trace-replay`
**Status**: accepted
**Date**: 2026-07-13

## Stage Goal

为每一次进入异常处理工作流的 flow 建立有序、可关联、可持久化、按用户隔离且可只读回放的
Execution Trace，统一覆盖实际执行的 Route、Tool/RAG、Agent、Guard 和 Final/Fallback 节点。

Stage 29 的 Replay 只展示已经发生的执行证据，不重新执行 Tool、RAG、LLM、Guard 或业务写入。
浏览器或 SSE 断开不得影响已完成 flow 的持久化 Trace；同一 flow 被 force requeue 或重新处理时，
必须保留每次独立执行的历史。

## Builds On

- Stage 25：ARQ job attempt、retry exhaustion、FAILED 终态和 force requeue contract。
- Stage 26：LLM transport retry、structured repair、token/cache 和稳定 failure/fallback summary。
- Stage 27：backend、worker、frontend、MySQL、Redis 五服务 Compose，双路径 smoke 和 hosted CI。
- Stage 28：固定只读 Tool、`ToolCallResult`、安全 attempt projection、tenant context 和 evidence IDs。
- 现有 plain-Python `run_item()` 工作流、进程内 SSE emitter、`t_agent_execution_log` 和差错台账页面。

## Architecture Impact

**Architecture Impact**: Yes
**ADR Required**: Yes

Accepted ADRs：

- `decisions/ADR-29.1-persistent-execution-trace-model.md`
- `decisions/ADR-29.2-flow-scoped-best-effort-trace-recording.md`
- `decisions/ADR-29.3-tenant-scoped-replay-and-stream-projection.md`

这些 ADR 冻结专用持久化模型、recorder 生命周期、失败隔离、tenant-scoped Replay API、SSE 投影和
前端入口。实现与 task 不得修改其边界；若发现无法实现或与现有代码冲突，必须停止并回到 ADR/spec
修订。

## In Scope

1. 定义严格、版本化的 `TraceSpan` schema 和相关 Replay response schema。
2. 在现有 MySQL/SQLite 中新增 `t_trace_span`，作为 Replay 唯一事实源。
3. 为每次 eligible flow 执行创建独立 `trace_id`，append-only 保存历史执行。
4. 实现显式 flow-scoped `TraceRecorder`，记录实际执行的七类逻辑节点。
5. 将 Stage 26 LLM summary 和 Stage 28 Tool safe projection 映射为统一 span 字段。
6. 核心业务事务成功后，按 flow 使用独立事务批量写入完整 Trace。
7. Trace recorder/validation/write 失败时保持业务结果不变，并提供安全 warning 与 process-local
   success/failure counters。
8. 停止旧本地 JSON Trace 写入，删除 `TraceWriter` 和 `TRACE_DIR` 配置。
9. 新增一个 tenant-scoped Replay GET endpoint，默认返回最新执行并支持按 `trace_id` 查看历史执行。
10. 将 SSE contract 升级到 v1.2，新增由 canonical `TraceSpan` 生成的 `trace_span` 安全投影。
11. 新增独立 Trace Replay 页面、只读 Timeline 和差错台账入口。
12. 生成确定性、零密钥的 JSON + Markdown Trace evidence 报告。
13. 窄范围同步 `README.md`、`system-prd.md`、`overall-architecture.md` 和 `.env.example` 的 Trace
    当前事实。
14. 新增或更新必要的后端、API、SSE、tenant isolation、前端和证据脚本测试。

## Out of Scope

- execution replay：重新运行 Tool、RAG、LLM、Guard、工作流或任何业务写入。
- 普通 `AUTO_FIXED` 行、文件上传/解析、任务调度、人工复核、报表、Dashboard 和普通 CRUD tracing。
- LangFuse、Jaeger、OpenTelemetry Collector、日志搜索集群、Prometheus 或新的 Trace 数据库。
- 分布式 Trace、跨服务采样、跨线程 recorder propagation、后台 flush worker 或 durable streaming
  tracing。
- SSE `Last-Event-ID`、断点续传、跨 backend 实例广播或水平扩展事件总线。
- 全局 Trace 列表、搜索、分页、删除、两次执行 diff、重跑或 Trace Explorer。
- evidence 正文加载、统一 Evidence API、自动链接或业务数据编辑。
- Trace TTL、自动清理、归档、删除授权和完整生产数据治理。
- Alembic、自制 migration framework 或新的版本化迁移系统。
- 重命名现有业务 `TraceAgent`、改变 Agent prompt 或重构无关工作流。
- 改变 Stage 26 LLM provider contract、Stage 28 Tool Executor API、业务算法、金额计算或权限模型。
- 真实 DeepSeek、真实 embedding 下载、生产 SLA 或集群级可用性声明。

## Terminology

- **Execution Trace**：一次异常 flow 实际执行产生的一组 spans。它与业务 `TraceAgent` 不同。
- **Trace run**：由一个 `trace_id` 标识的一次 flow execution。
- **Eligible flow**：进入异常处理工作流、不是普通 `AUTO_FIXED` 的 flow。
- **Observation replay**：读取并展示已持久化 Trace，不触发重新执行。
- **Logical call span**：一次逻辑 Tool/Agent 调用的汇总；物理 retry 不单独生成 span。
- **Canonical TraceSpan**：数据库、Replay API 与 SSE 安全投影共享的权威字段与语义。

## Inputs and Outputs

### Runtime Inputs

- 已认证或可信 job payload 中的 `user_id`、`task_id`、`flow_id`。
- 当前异常 flow 的 `exception_branch` 与实际 workflow control flow。
- Stage 28 `ToolCallResult` 和 `safe_tool_projection()`。
- Stage 26 Agent 的 `last_llm_summary`、`last_llm_result` 与稳定 failure/fallback token。
- Guard、Final/Fallback 的确定性结果。

### Runtime Outputs

- 每个 eligible flow execution 的一个完整、已校验 `TraceSpan` batch。
- `t_trace_span` 中 append-only 的持久化 rows。
- 实时 `trace_span` SSE 安全事件。
- tenant-scoped Replay API response。
- 前端只读 Timeline。
- process-local Trace write metrics 与结构化 warning。

### Offline Outputs

- `reports/trace_replay_evidence.json`：机器可审查事实源。
- `reports/trace_replay_evidence.md`：由同次 JSON 数据生成的人类可读报告。

## TraceSpan Contract

### Schema Version

- `TraceSpan.schema_version` 初始固定为 `1.0`。
- Pydantic model 必须 `extra="forbid"` 或等价 fail-closed 行为。
- API 和持久化必须使用同一 model；不得为数据库、API、SSE 分别维护可漂移的自由 schema。

### Required Identity and Ordering Fields

| Field | Contract |
| --- | --- |
| `trace_id` | 每次 flow execution 新生成的不透明 UUID |
| `span_id` | 当前 span 的不透明 UUID |
| `parent_span_id` | 根 span 为 `null`；其他 span 指向同一 Trace 内已存在的 span |
| `user_id` | 持久化与查询隔离字段；不返回给前端 |
| `task_id` | 当前任务 ID |
| `flow_id` | 当前异常 flow ID |
| `sequence_no` | 在 span 开始时分配；单个 Trace 内从 1 连续、唯一、单调递增 |
| `span_type` | 七类封闭枚举之一 |
| `name` | 代码定义的稳定节点名，不接受用户输入 |
| `started_at` | UTC 时间 |
| `ended_at` | UTC 时间，且不得早于 `started_at` |
| `duration_ms` | monotonic clock 计算的非负值 |
| `status` | `SUCCEEDED/FAILED/CANCELLED` |
| `outcome` | 按 `span_type` 校验的可空封闭枚举 |

### Optional Safe Observation Fields

- `attempt`：逻辑调用内实际物理 attempt 数；非调用节点使用 1。
- `retry_recovered`：是否在当前逻辑调用内经 retry 后恢复。
- `recovered_error_type`：恢复前的稳定错误 token；未恢复或无 retry 时为 `null`。
- `structured_repair_attempted` / `structured_repair_succeeded`：只对 Agent span 有意义。
- `model_name`：只对 Agent span有意义，不包含 endpoint、key 或部署秘密。
- `prompt_tokens` / `completion_tokens`：当前 Agent 逻辑调用所有实际非缓存 provider calls 的聚合。
- `cached_calls`：当前 Agent 逻辑调用的 cache hit 数。
- `result_count`：Tool 安全投影中的结果数量，不保存结果正文。
- `error_type`：Stage 26/28 原始稳定 token 或本 Stage 明确新增的 Guard/Workflow token。
- `fallback_reason`：稳定机器 token，不保存自由文本 reason。
- `evidence_ids`：允许的脱敏 IDs；无 evidence 时为空列表。

### Span Types and Outcomes

| `span_type` | `name` | Allowed `outcome` |
| --- | --- | --- |
| `WORKFLOW` | 稳定根节点名 | `AUTO_FIXED/PENDING_HUMAN/UNRESOLVED` |
| `ROUTE` | 稳定 `exception_branch` | `null` |
| `TOOL` | `search_rules/load_confirmed_cases/lookup_t1_context` | `RESULT/EMPTY/null` |
| `AGENT` | 固定 Agent 类名 | `null` |
| `GUARD` | 固定 Guard 名称 | `PASSED/BLOCKED` |
| `FINAL` | 固定终止节点名 | `AUTO_FIXED/PENDING_HUMAN/UNRESOLVED` |
| `FALLBACK` | 固定 fallback 节点名 | `PENDING_HUMAN` |

Tool 技术失败使用 `status=FAILED + outcome=null + error_type/fallback_reason`。正常空结果使用
`status=SUCCEEDED + outcome=EMPTY`。Safety Guard 正确拦截使用
`status=SUCCEEDED + outcome=BLOCKED`。安全转人工的根 Workflow 和 Fallback 均可为 `SUCCEEDED`。

### Structural Invariants

- 每个 Trace 恰好一个 `WORKFLOW` 根 span，且其 `sequence_no=1`。
- 每个完整 Trace 恰好一个 `FINAL` 或 `FALLBACK`，不得同时存在。
- 只记录实际进入的节点；未执行节点不得生成 `SKIPPED` span。
- `sequence_no` 在同一 Trace 内连续且唯一。
- 所有 `parent_span_id` 指向同一 Trace 内存在的 span，不允许跨 Trace parent。
- 仅 `AGENT` spans 可以保存非零 token/model/cache/structured repair 字段。
- 根 Workflow 不复制子节点 token；Trace token 总数由 Replay service 对 Agent spans 求和。
- evidence IDs 只允许：规则 `chunk_id`、历史案例 `flow_id`、T+1 匹配 `flow_id`。
- schema validation failure 必须使整个 batch 不可写，不得部分降级或丢弃单个非法 span 后继续。

### Forbidden Data

Trace 不得包含：

- 任意自由 `attributes`、`input_payload`、`output_payload`。
- 完整 prompt、模型输出、RAG query、规则正文或历史审计意见。
- 金额、原始/脱敏流水内容、摘要、备注、文件内容或 Tool args/result。
- traceback、异常原文、SQL、数据库连接信息、JWT、API key、cookie、headers。
- 未经 allowlist 的 evidence、用户输入或动态节点名称。

## Data Model Impact

### New Table: `t_trace_span`

新增 SQLAlchemy Core `Table` 与对应 MySQL DDL。字段必须覆盖 canonical TraceSpan；SQLite 可使用
`with_variant` 延续仓库现有跨库约定。`evidence_ids` 可使用 MySQL JSON + SQLite Text，但进入/离开
持久化边界时必须通过严格 schema validation。

最少约束与索引：

- 自增内部主键 `id`，不作为 API identity。
- `UNIQUE(trace_id, span_id)`。
- `UNIQUE(trace_id, sequence_no)`。
- tenant replay 查询索引至少覆盖 `user_id + task_id + flow_id` 与执行时间/identity。
- 不设置跨表外键；ownership 由现有 task/transaction/ledger 服务和查询 filter 明确验证。

必须同步：

- service 顶层 SQLAlchemy `Table`。
- `src/bank_reconciliation_agent/db/schema.sql`。
- fresh SQLite/MySQL schema tests。
- existing MySQL/Compose 数据卷显式重放更新后 `schema.sql` 的验证步骤。

`_ensure_initialized()` 只允许延续 local/test 行为；非 local 环境不得依赖它隐藏生产 schema 变更。
本 Stage 不新增 migration framework。

### Existing Data Models

- `t_agent_execution_log` 保持现有审计汇总语义，不改造成 span 表，不作为 Replay fallback。
- 核心 ledger、queue、task、transaction、review 和 RAG log contract 不因 Trace 改变。
- 停止本地 JSON Trace 后，`TRACE_DIR` 与相关配置、测试和文档必须移除。

## Recorder and Persistence Flow

1. `ReconciliationService` 为每个 eligible flow 创建 `TraceRecorder`、新的 `trace_id` 和根
   `WORKFLOW` span。
2. recorder 显式进入当前 `ReconciliationState`；`run_item()` 未收到 recorder 时使用 no-op。
3. Workflow 在实际 Route、Tool、Agent、Guard 边界创建逻辑 spans。
4. Tool span 只消费 Stage 28 safe projection；Agent span 只消费 Stage 26 safe summary/result metadata。
5. 正常返回时外层写入 `FINAL` 或 `FALLBACK` 并关闭根 span。
6. 现有允许的 Agent 异常被外层转人工时，外层补充 `FALLBACK` 并关闭根 span。
7. recorder 生成不可变 snapshot，并在内存中验证全部结构不变量。
8. 核心 ledger/queue/task stats 事务先提交。
9. Trace 按 flow 使用独立事务批量插入；一个 batch 要么全部成功，要么完全失败。
10. 写入失败只记录安全 warning 和 process-local counter；不得回滚或修改业务结果。

Recorder/context manager 不吞业务异常。recorder 自身失败时禁用当前 Trace，但不得改变原业务控制流。
未被现有业务边界捕获、导致 task 失败的基础设施异常不伪造成完整成功 Trace。

## Tool and LLM Projection

### Tool

- 一个 `ToolExecutor.execute(...)` 逻辑调用对应一个 `TOOL` span。
- 不为最多两次物理 Tool attempts 生成子 spans。
- 映射 `tool_name`、最终 status/outcome、总 duration、attempt、retry recovery、恢复前错误、最终
  error/fallback、result count 和 evidence IDs。
- 不保存 `retryable`、backoff、breaker 状态序列、args 或完整 result。
- `search_rules` 同时表达 RAG 检索，不再重复创建 RAG span。

### Agent / LLM

- 一个逻辑 Agent 调用对应一个 `AGENT` span；structured repair 和 transport retry 不生成子 spans。
- token 聚合所有实际非缓存 provider calls；cache hit 只增加 `cached_calls`。
- `prompt_tokens + completion_tokens` 是当前 Agent span 的可计费 token 总数；不使用 attempt 倍乘。
- Fake provider token 只用于离线确定性验证，不作为真实 DeepSeek 成本证据。
- Stage 26/28 error token 保持原大小写和命名；报告按 `span_type + error_type` 聚合。

## Replay API Contract

### Endpoint

```http
GET /api/v1/traces/{task_id}/flows/{flow_id}?trace_id=<optional>
Authorization: Bearer <JWT>
```

- 不传 `trace_id`：选择该 flow 最新一次 Trace。
- 传 `trace_id`：选择指定历史 execution。
- endpoint 只读，不产生 Trace、业务写入或重新执行。

### Response

沿用 `ApiResponse`，`data` 至少包含：

- `replay_status`：`AVAILABLE/IN_PROGRESS/TRACE_NOT_AVAILABLE`。
- `selected_trace_id`：无可选 Trace 时为 `null`。
- `execution_count`：当前 user/task/flow 的历史 Trace run 数量。
- `runs`：按最新优先排列的精简 `trace_id/started_at/status/outcome` 列表。
- `spans`：选定 Trace 的安全视图，按 `sequence_no` 升序。
- `prompt_tokens`、`completion_tokens`、`total_tokens`：从选定 Trace 的 Agent spans 计算，不持久化
  重复汇总列。

### Status and Errors

- task 不存在或属于其他用户：`404 TASK_NOT_FOUND`，两者语义相同。
- task 属于当前用户，但 flow 不属于该 task：`404 TRACE_NOT_FOUND`。
- 指定 Trace 不属于当前 `user_id + task_id + flow_id`：`404 TRACE_NOT_FOUND`。
- task/flow 合法且 task 仍在处理，但无完整 Trace：`200 IN_PROGRESS + spans=[]`。
- task/flow 合法、task 已结束但 Trace 不可用：`200 TRACE_NOT_AVAILABLE + spans=[]`。
- 有完整 Trace：`200 AVAILABLE`。

查询顺序必须是 JWT user → task ownership → flow ownership → optional trace ownership。任何跨用户路径
不得泄露 execution count、span metadata、error/fallback 或 evidence IDs。

## SSE Contract

- `AgentStreamEvent.schema_version` 从 `1.1` 升级为 `1.2`。
- 新增 `trace_span` event type；现有 event types 和 payload contract 保持兼容。
- span 结束时发送一条 event，不发送 `span_started`。
- payload 来自 canonical `TraceSpan` 安全投影，不包含 `user_id` 或 forbidden data。
- SSE envelope `seq` 是 task 实时事件顺序；payload `sequence_no` 是单个 Trace 内 span 开始顺序。
  两者独立维护，不互相替代。
- 浏览器断开只影响实时事件；持久化继续由 flow 完成后的 batch write 决定。
- 前端刷新后以 Replay API 为事实源，按 `span_id` 去重实时与持久化数据。

## Frontend Contract

- 新增 route：`/traces/:taskId/:flowId`。
- 差错台账详情为当前 row 提供“查看执行轨迹”入口。
- `TraceReplayPage` 负责 Replay API、run 选择、loading/error/empty/not-available 状态。
- `TraceTimeline` 只读展示实际 spans，按 `sequence_no` 排序，可按 parent 做轻量缩进。
- 每个节点至少展示 type/name、status/outcome、duration、attempt/recovery；存在时展示 token、稳定
  error/fallback 和 evidence ID 标签。
- evidence ID 只读、可复制，不加载正文、不拼接链接；空列表明确显示无引用状态。
- 不显示 `user_id`、forbidden fields 或后端未返回的数据，不虚构执行节点。
- Workbench 保留现有上传和实时事件职责；只按需要支持 `trace_span` event card，不加入历史查询表单。
- 页面需具备 keyboard focus、可读状态文案和现有响应式布局约定；金额展示约定不适用，因为 Trace
  不返回金额。

## Failure Semantics

- Trace recorder、validation、SSE projection 或持久化失败不得修改金额、ledger、queue、task status、
  Agent decision 或 fallback 结果。
- Trace batch validation/write 失败时整批丢弃，不允许半条 timeline。
- 不允许用 agent log、SSE 缓存或旧 JSON 拼装替代 Trace。
- `trace_write_failure_count` 统计失败的 flow batch，而非 span 数量。
- warning 只允许 `task_id`、`flow_id`、`trace_id`、稳定错误类型和预计 span 数。
- process-local metrics 至少包含：
  - `source=runtime_memory`
  - `trace_write_success_count`
  - `trace_write_failure_count`
- backend 与 worker counters 不聚合；文档和报告不得称其为集群级指标。

## Security and Data Isolation

- 所有数据库写入显式携带可信 `user_id + task_id + flow_id`。
- 所有业务查询显式按 JWT `user_id` 隔离；不得只靠 `trace_id` 访问。
- task 不存在与跨用户 task 使用相同 404，flow/trace 不存在与越界使用相同 404。
- Trace table、API、SSE、日志、离线报告和前端均执行同一 forbidden-data policy。
- evidence IDs 不赋予额外读取权限；Stage 29 不增加 evidence 解析接口。
- Trace schema 中即使持久化 `user_id`，API/SSE 也不得返回该字段。
- 不提交密钥、`.env`、原始文件、缓存、构建产物或包含敏感 marker 的报告。

## Amount Precision and Business Safety

- Trace 不参与金额计算，不保存金额，不影响 `Decimal` 业务路径。
- LLM 不因 Trace 获得新的 Tool 选择、执行、重放或财务决策权限。
- Tool `EMPTY/FAILED`、RAG 无 evidence、Safety Guard 和现有 fail-closed 行为保持不变。
- Stage 29 不扩大任何写 API、事务 contract、Agent 权限或自动平账路径。

## Backward Compatibility and Schema Provisioning

- 现有 SSE event types 保持兼容；唯一版本变化是 v1.2 增加 `trace_span`。
- 现有 `t_agent_execution_log`、RAG log、ledger 与报告 API 保持行为兼容。
- 旧 JSON Trace 输出有意退役，不提供双写兼容期；文档与测试必须同步删除旧事实。
- fresh database 必须通过更新后的 `schema.sql` 创建 `t_trace_span`。
- existing Compose 数据卷必须显式重放更新后的 `schema.sql`；该过程必须进入验证记录。
- 不允许声称 SQLAlchemy `create_all()` 会在非 local 环境完成生产 schema migration。

## Offline Evidence Contract

新增确定性、零密钥 evidence runner，固定使用 SQLite、Fake provider、hash embedding 和可复现故障
注入。至少覆盖：

1. 一条完整成功路径。
2. Tool timeout/failed 后 Fallback。
3. LLM structured repair 最终失败后 Fallback。
4. Safety Guard 拦截后 Fallback。
5. 跨用户 Replay 被拒绝。
6. Trace batch write failure 不影响业务结果。

`trace_completeness_rate` 定义为：

```text
满足结构不变量且成功持久化的 eligible flow traces
/
本次 evidence 运行中进入异常工作流的 eligible flows
```

报告至少输出：

- completeness numerator、denominator 和 rate。
- 每个场景的实际 span 顺序与终止类型。
- 各 `span_type/name` 的 P50/P95 duration。
- `span_type + error_type` distribution。
- fallback distribution。
- token by Agent node。
- Trace write success/failure counts。
- 环境、Fake/hash 边界和非生产 SLA 声明。

JSON 是唯一机器事实源；Markdown 必须从同次 JSON 数据生成，不得手填或独立计算指标。

## Acceptance Criteria

### Trace Model and Persistence

- [ ] 每个 eligible flow execution 生成新的 `trace_id`；同一 flow 多次执行保留独立历史。
- [ ] 成功和失败路径只包含实际执行 spans，并满足 root、terminal、sequence、parent 与时间不变量。
- [ ] Tool/RAG、Agent、Guard、Final/Fallback 使用已定义的统一 status/outcome/error 语义。
- [ ] retry、structured repair、cache 和 token 投影与 Stage 26/28 事实一致，无物理 attempt 子 span。
- [ ] token 汇总等于 Agent spans 的实际非缓存 provider token 总和，无父子重复。
- [ ] forbidden data 不进入 schema、数据库、日志、SSE、API、报告或前端 fixture。
- [ ] `t_trace_span` SQLAlchemy 与 MySQL DDL 对齐，SQLite/MySQL 行为通过测试。
- [ ] 旧 JSON Trace 不再生成，`TraceWriter` 和 `TRACE_DIR` 已移除。

### Business Isolation

- [ ] Trace recorder/validation/write 故障不回滚或修改核心业务结果。
- [ ] 一个 flow batch 要么完整持久化，要么完全缺失，不存在部分 timeline。
- [ ] 已捕获 Agent 异常安全转人工时仍生成完整 Fallback Trace。
- [ ] Tool/RAG 无 evidence、安全 Guard 和现有业务 fallback 行为无回归。
- [ ] 金额仍只由 `Decimal` 确定性代码处理，Trace 不保存或计算金额。

### Replay API and Tenant Safety

- [ ] endpoint 默认返回最新 execution，并可按 `trace_id` 返回指定历史 execution。
- [ ] runs、execution count、selected trace、spans 和 token totals 与数据库一致。
- [ ] `AVAILABLE/IN_PROGRESS/TRACE_NOT_AVAILABLE` 状态按 contract 返回。
- [ ] 跨用户 task/flow/trace 查询不能泄露存在性、span metadata、error 或 evidence IDs。
- [ ] API 不返回 `user_id` 或 forbidden fields，不从其他存储 fallback 拼装 Trace。

### SSE and Frontend

- [ ] SSE v1.2 新增 `trace_span`，现有 event types 行为与测试无回归。
- [ ] SSE `seq` 与 Trace `sequence_no` 独立且语义正确。
- [ ] 浏览器断开不影响持久化；刷新后 Replay API 可恢复完整 Timeline。
- [ ] 独立 Replay 页面可从差错台账进入，支持最新与历史 execution 选择。
- [ ] Timeline 按真实顺序展示 status/outcome、耗时、retry、token、error/fallback 和 evidence IDs。
- [ ] evidence IDs 不展开正文、不生成未授权链接；空、加载、失败和不可用状态可区分。

### Evidence and Documentation

- [ ] deterministic evidence 覆盖一条成功和至少三类失败/拦截路径及跨租户/写失败场景。
- [ ] `trace_completeness_rate` 与结构校验事实一致，不以 recorder 自报事件替代持久化证明。
- [ ] JSON 与 Markdown 报告来自同次运行，携带 Fake/hash/offline claim boundary。
- [ ] `README.md`、`system-prd.md`、`overall-architecture.md` 与当前 DB/API/SSE/JSON 退役事实一致。
- [ ] 不引入未在 ADR/spec 声明的新依赖或外部服务。

## Verification Strategy

Task 级命令由 `tasks.md` 按文件范围细化。Stage/PR Gate 至少包含：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
cd frontend && npm run test && npm run typecheck && npm run build
```

Stage evidence 还必须真实执行确定性 Trace runner，并验证 fresh schema 与 existing Compose schema 重放。
所有结果随后记录到本 Stage 的 `verification.md`；在命令真实运行前不得标记 passed。

## Risks

- Trace 在 flow 结束并批量落库前遭遇进程崩溃时可能缺失；本 Stage 不提供 durable partial tracing。
- process-local warning counters 无法跨 backend/worker 聚合，真实生产需要独立观测方案。
- append-only Trace 无 retention/delete，会持续增长；进入真实生产前必须补充数据治理决策。
- existing MySQL 数据卷若未显式应用更新后的 DDL，Replay 将不可用但业务仍可能完成。
- 前端同时接收旧 SSE events 和 `trace_span`，若未按 `span_id` 去重可能重复展示。
- 离线 P50/P95 受本机、缓存和 fake/hash 环境影响，只能作为本地观察证据，不是生产 SLA。

## Open Questions

None。Stage 29 的关键设计分支已通过 grilling 确认，并由三份 accepted ADR 冻结。
