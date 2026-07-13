# Stage 29 Tasks: TraceSpan 与任务回放

**Stage**: `stage-29-trace-replay`
**Branch**: `stage-29-trace-replay`
**Spec**: `docs/stages/stage-29-trace-replay/spec.md`
**Status**: completed
**Date**: 2026-07-13

## Execution Rules

- opencode 每次只执行一个 task，开始前必须阅读 `AGENTS.md`、Stage 29 spec、当前 task 和引用 ADR。
- 每个 task 先增加能够失败的行为测试，确认失败原因与当前缺口一致，再完成最小实现并运行指定门禁。
- `Files to Modify` 是该 task 的允许边界；确需扩大范围时停止并报告，由 Codex 修订 task 后继续。
- 不修改 `spec.md`、`tasks.md`、accepted ADR 或其他规划文件适配实现。
- 不引入新依赖，不改变金额、权限、Tool、Agent、LLM、业务 API 或事务 contract。
- 每个 task 完成后检查 `git diff`，创建只引用该 task 的 Conventional Commit；不得 push 或 merge。
- task 状态由 Codex review 后更新；opencode 不自行修改本文件状态。

## Dependency Order

```text
TASK-29.1 Trace schema/storage
  → TASK-29.2 TraceRecorder
    → TASK-29.3 Workflow integration and JSON retirement
      → TASK-29.4 Replay API
      → TASK-29.5 SSE v1.2 projection
        → TASK-29.6 Frontend Replay timeline
          → TASK-29.7 Deterministic evidence
            → TASK-29.8 Documentation fact sync
```

TASK-29.4 与 TASK-29.5 都依赖 TASK-29.3；执行顺序仍固定为 29.4 → 29.5，避免并行修改
`schemas/trace.py`、`services/trace.py` 和相关 contract。

---

## TASK-29.1 — 建立严格 Trace schema 与持久化存储边界

**Status**: done
**Spec Ref**: `TraceSpan Contract`、`Data Model Impact`、`Security and Data Isolation`
**ADR Ref**: `ADR-29.1`

### Goal

定义 canonical Trace/Replay Pydantic schema，并在现有 MySQL/SQLite 中新增 tenant-scoped、
append-only 的 `t_trace_span` 存储原语；本 task 不接入运行时工作流。

### Files to Modify

- Create: `src/bank_reconciliation_agent/schemas/trace.py`
- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `src/bank_reconciliation_agent/db/schema.sql`
- Create: `tests/test_trace_schema.py`
- Create: `tests/test_trace_storage.py`

为保证 task 独立可合并，旧 `TraceWriter` 可在本 task 临时保留，但不得扩展或产生新的依赖；它必须
在 TASK-29.3 删除。

### Do Not Touch

- `src/bank_reconciliation_agent/services/reconciliation.py`
- `src/bank_reconciliation_agent/services/workflow.py`
- `src/bank_reconciliation_agent/api/`
- `src/bank_reconciliation_agent/schemas/stream.py`
- `frontend/`
- `scripts/` 与 `reports/`
- `src/bank_reconciliation_agent/core/llm/`
- `src/bank_reconciliation_agent/services/tool_executor.py`

### Out of Scope

- TraceRecorder、workflow instrumentation、SSE、HTTP API、frontend。
- 旧 JSON Trace 退役或 `TRACE_DIR` 删除。
- Runtime metrics、evidence runner、retention/delete。
- Alembic 或任何 migration framework。

### Acceptance Criteria

- `TraceSpan` 与 Replay 相关 models 使用严格 extra-forbid validation，并实现 spec 中的封闭枚举。
- schema 验证 identity、UTC 时间、非负 duration、sequence、type-specific outcome、token 字段和
  forbidden field rejection。
- `t_trace_span` SQLAlchemy Core `Table` 与 MySQL DDL 字段、nullable、类型、unique constraints 和
  tenant query indexes 对齐。
- 存储 service 可在一个独立事务内批量插入一条完整 Trace，并按
  `user_id + task_id + flow_id + optional trace_id` 读取 runs/spans。
- 同一 `task_id + flow_id` 可保存多个 `trace_id`；同一 Trace 的重复 `span_id` 或
  `sequence_no` 被数据库约束拒绝。
- 所有读方法显式接收并过滤 `user_id`；不得提供只按 `trace_id` 的非租户读取入口。
- MySQL JSON/SQLite Text 的 `evidence_ids` 进入和离开持久化边界时都通过 schema validation。
- 测试覆盖 schema 正反例、SQLite insert/query/order、多 run 历史、跨用户空结果和 batch rollback。
- 不改变现有 runtime Trace 写入行为；现有测试除新增门禁外保持通过。

### Verification Commands

```bash
uv run pytest tests/test_trace_schema.py tests/test_trace_storage.py -q
uv run ruff check src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py tests/test_trace_schema.py tests/test_trace_storage.py
uv run ruff format --check src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py tests/test_trace_schema.py tests/test_trace_storage.py
```

### Report Back Requirements

- Changed Files
- Schema/Table Summary：字段、unique constraints、indexes、SQLite/MySQL variant
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：特别说明 existing MySQL schema provisioning
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.1`

---

## TASK-29.2 — 实现 flow-scoped TraceRecorder 与结构不变量

**Status**: done
**Spec Ref**: `TraceSpan Contract`、`Recorder and Persistence Flow`、`Tool and LLM Projection`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`

### Goal

实现无数据库副作用的 flow-scoped `TraceRecorder`，负责 identity、开始顺序、parent stack、duration、
逻辑调用安全投影、snapshot 校验和 no-op 行为；本 task 不接入生产 workflow。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/schemas/trace.py`（仅结构校验确需时）
- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Create: `tests/test_trace_recorder.py`

### Do Not Touch

- `src/bank_reconciliation_agent/services/reconciliation.py`
- `src/bank_reconciliation_agent/services/workflow.py`
- `src/bank_reconciliation_agent/core/logging.py`
- `src/bank_reconciliation_agent/api/`
- `src/bank_reconciliation_agent/schemas/stream.py`
- `frontend/`
- `scripts/` 与 `reports/`

### Out of Scope

- 数据库写入时机、业务事务集成、旧 JSON 退役。
- SSE emitter callback、Replay API、frontend。
- 修改 Tool Executor、Agent 或 LLM provider 公共 contract。
- 物理 attempt 子 spans、跨线程 propagation 或 durable partial tracing。

### Acceptance Criteria

- 每个 recorder 创建新的 UUID `trace_id` 和唯一根 `WORKFLOW` span。
- `sequence_no` 在 span 开始时分配，从 1 连续递增；完成顺序不改变 sequence。
- context manager 正确维护 parent-child，使用 monotonic clock 计算非负 duration，并且不吞业务异常。
- 节点异常将当前 span 标为稳定 `FAILED` 后继续按原异常传播。
- recorder 能记录七类 spans，只允许 spec 定义的 name/outcome/error/evidence/token 字段。
- Tool projection 能把 Stage 28 logical result 映射为一次 span，保留 attempt/recovery/result count/evidence，
  不包含 args/result/attempt 明细。
- Agent projection 能映射 Stage 26 logical summary/result，正确聚合 token/cache/repair/error，且不包含
  prompt 或模型正文。
- snapshot 不可变，并拒绝缺根、多个终止节点、sequence 缺口/重复、跨 Trace parent、非法 token 和
  forbidden data。
- 未提供 recorder 的调用可使用 no-op recorder；no-op 不生成 span、日志或数据库副作用。
- recorder 自身故障可被上层安全禁用，不改变被包裹操作的返回值或异常。
- 测试覆盖正常嵌套、完成顺序不同、Tool retry recovery、LLM repair、Guard blocked、业务异常和
  全部结构不变量失败路径。

### Verification Commands

```bash
uv run pytest tests/test_trace_schema.py tests/test_trace_recorder.py -q
uv run ruff check src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py tests/test_trace_recorder.py
uv run ruff format --check src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py tests/test_trace_recorder.py
```

### Report Back Requirements

- Changed Files
- Recorder Contract Summary：lifecycle、sequence、parent、snapshot、no-op
- Projection Summary：Tool 与 Agent 各映射哪些安全字段
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.2`

---

## TASK-29.3 — 接入异常工作流、隔离持久化失败并退役旧 JSON Trace

**Status**: done
**Spec Ref**: `Recorder and Persistence Flow`、`Failure Semantics`、`Backward Compatibility and Schema Provisioning`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`

### Goal

由 `ReconciliationService` 管理每个 eligible flow 的 recorder 生命周期，记录真实 workflow 节点并在
核心事务成功后按 flow 批量持久化；同时完成失败隔离、日志关联和旧 JSON Trace 退役。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/services/reconciliation.py`
- Modify: `src/bank_reconciliation_agent/services/workflow.py`
- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `src/bank_reconciliation_agent/core/logging.py`
- Modify: `src/bank_reconciliation_agent/core/config.py`
- Modify: `.env.example`
- Modify: `tests/test_agent_log_trace.py`
- Create: `tests/test_trace_workflow.py`
- Modify as required by changed contract only:
  - `tests/test_workflow.py`
  - `tests/test_workflow_fallback.py`
  - `tests/test_reconciliation_agent_fallback.py`
  - `tests/test_reconciliation_upload.py`
  - `tests/test_logging.py`
  - `tests/test_delivery_config.py`

### Do Not Touch

- `src/bank_reconciliation_agent/core/llm/`
- `src/bank_reconciliation_agent/services/tool_executor.py`
- `src/bank_reconciliation_agent/services/tool_adapters.py`
- `src/bank_reconciliation_agent/agents/`
- `src/bank_reconciliation_agent/api/`
- `src/bank_reconciliation_agent/schemas/stream.py`
- `frontend/`
- Project-level README/PRD/architecture docs（由 TASK-29.8 处理）

### Out of Scope

- Replay API、SSE `trace_span`、frontend、evidence runner。
- 改变 existing Tool/LLM retry、fallback、金额、事务或 Agent decision contract。
- 追踪 `AUTO_FIXED` 行、task scheduler、上传解析或人工复核。
- 进程崩溃后的 partial Trace 恢复。

### Acceptance Criteria

- `ReconciliationService` 在每个 eligible flow 外层创建 recorder，并显式传入 `ReconciliationState`。
- `run_item()` 只记录内部实际 Route/Tool/Agent/Guard spans；无 recorder 时使用 no-op。
- 每条完整路径由外层追加且仅追加一个 `FINAL` 或 `FALLBACK`，关闭根 span并生成 snapshot。
- Tool `EMPTY/FAILED` 提前收口时不生成未执行 Agent/Guard 的 `SKIPPED` spans。
- 现有 `AGENT_PROCESSING_ERRORS` 被外层转人工时仍生成完整 Fallback Trace。
- 普通 `AUTO_FIXED` 行不生成 Trace。
- 核心 ledger/queue/task stats 事务先提交；随后每个 flow 使用独立事务批量写入 Trace。
- Trace validation/write failure 不改变任务、ledger、queue 或 fallback 结果；batch 不留下部分 rows。
- `TraceService.metrics_snapshot()` 真实返回 process-local success/failure batch counters，并标注
  `source=runtime_memory`。
- 安全 warning 只含 task/flow/trace ID、稳定错误类型和预计 span 数，不含 traceback、SQL 或 payload。
- 普通 workflow structlog 的 `trace_id` 使用真实 execution ID，并单独保留 task/flow；context-free Tool
  attempt logger 保持原安全边界。
- 停止并删除 `TraceWriter` 和 JSON write side effect；删除 `settings.trace_dir` 与 `.env.example` 的
  `TRACE_DIR`。
- `t_agent_execution_log` 继续写现有审计汇总，不作为 Trace fallback，相关有效测试不得删除。
- 既有 workflow、fallback、tenant isolation、agent log 和 reconciliation 行为测试无回归。

### Verification Commands

```bash
uv run pytest tests/test_trace_workflow.py tests/test_agent_log_trace.py tests/test_workflow.py tests/test_workflow_fallback.py tests/test_reconciliation_agent_fallback.py tests/test_reconciliation_upload.py tests/test_logging.py tests/test_delivery_config.py -q
uv run ruff check src/bank_reconciliation_agent/services/reconciliation.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/core/logging.py src/bank_reconciliation_agent/core/config.py tests/test_trace_workflow.py tests/test_agent_log_trace.py
uv run ruff format --check src/bank_reconciliation_agent/services/reconciliation.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/core/logging.py src/bank_reconciliation_agent/core/config.py tests/test_trace_workflow.py tests/test_agent_log_trace.py
rg -n -uu "TRACE_DIR|trace_dir|TraceWriter|trace_writer" src tests .env.example --glob '!tests/test_delivery_config.py'
```

最后一条 `rg` 预期无输出；`tests/test_delivery_config.py` 若保留字符串断言也必须改为验证
`TRACE_DIR` 已不存在，而不是继续要求该变量。

### Report Back Requirements

- Changed Files
- Runtime Flow Summary：recorder 创建、terminal、snapshot、core transaction 后写入
- Failure Isolation Evidence：注入点、业务结果、Trace rows、counter/warning
- Legacy Retirement Evidence：`rg` 结果与删除配置
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：明确 partial Trace crash boundary 和 process-local metrics
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.3`

---

## TASK-29.4 — 提供 tenant-scoped Replay API

**Status**: done
**Spec Ref**: `Replay API Contract`、`Security and Data Isolation`
**ADR Ref**: `ADR-29.1`、`ADR-29.3`

### Goal

实现一个只读 Replay endpoint，按 JWT user → task → flow → optional trace 顺序验证 ownership，默认
返回最新 execution 并支持历史 run 选择，不泄露跨用户 metadata。

### Files to Modify

- Create: `src/bank_reconciliation_agent/api/v1/trace.py`
- Modify: `src/bank_reconciliation_agent/api/v1/router.py`
- Modify: `src/bank_reconciliation_agent/schemas/trace.py`
- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `src/bank_reconciliation_agent/schemas/common.py`（仅新增稳定 error codes 时）
- Create: `tests/test_trace_replay.py`
- Modify: `tests/test_tenant_isolation.py`

### Do Not Touch

- `src/bank_reconciliation_agent/services/workflow.py`
- `src/bank_reconciliation_agent/services/reconciliation.py`
- `src/bank_reconciliation_agent/schemas/stream.py`
- `src/bank_reconciliation_agent/services/stream_emitter.py`
- `frontend/`
- Tool/LLM/Agent 实现

### Out of Scope

- 写入、删除、重跑、搜索、分页、diff 或 Evidence API。
- SSE event、frontend、Dashboard metrics。
- 从 agent log、JSON、SSE 或其他表拼装 Trace。
- 改变现有 JWT scheme 或添加新权限系统。

### Acceptance Criteria

- endpoint 精确为 `GET /api/v1/traces/{task_id}/flows/{flow_id}`，仅接受可选 `trace_id` query。
- 不传 `trace_id` 时稳定选择最新 run；传入时只选择属于当前 user/task/flow 的指定 run。
- response 沿用 `ApiResponse`，返回 replay status、selected trace、execution count、runs、顺序 spans 和
  从 Agent spans 计算的 token totals。
- runs 最新优先，spans 按 `sequence_no` 升序；API 不返回数据库内部 `id` 或 `user_id`。
- 正确区分 `AVAILABLE`、`IN_PROGRESS`、`TRACE_NOT_AVAILABLE`。
- task 不存在与跨用户 task 统一 `404 TASK_NOT_FOUND`；flow/trace 不存在与越界统一
  `404 TRACE_NOT_FOUND`。
- ownership 查询顺序通过 spy 或可观察测试证明；跨用户响应不泄露 execution count、error、fallback、
  evidence 或 trace existence。
- 当前用户合法的 Trace write 缺失返回 `TRACE_NOT_AVAILABLE`，不得从 agent log fallback。
- API response schema 拒绝 forbidden fields，evidence 只包含 allowlisted IDs。
- 原有 API auth 与 tenant isolation tests 无回归。

### Verification Commands

```bash
uv run pytest tests/test_trace_replay.py tests/test_tenant_isolation.py tests/test_api_auth.py -q
uv run ruff check src/bank_reconciliation_agent/api/v1/trace.py src/bank_reconciliation_agent/api/v1/router.py src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py tests/test_trace_replay.py tests/test_tenant_isolation.py
uv run ruff format --check src/bank_reconciliation_agent/api/v1/trace.py src/bank_reconciliation_agent/api/v1/router.py src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py tests/test_trace_replay.py tests/test_tenant_isolation.py
```

### Report Back Requirements

- Changed Files
- API Contract Summary：path、query、response、status/error matrix
- Tenant Isolation Evidence：不存在与跨用户各路径结果
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.4`

---

## TASK-29.5 — 增加 SSE v1.2 `trace_span` 安全投影

**Status**: done
**Spec Ref**: `SSE Contract`、`TraceSpan Contract`
**ADR Ref**: `ADR-29.2`、`ADR-29.3`

### Goal

将 canonical TraceSpan 的安全视图作为新的 `trace_span` SSE event 实时发出，同时保持全部现有 SSE
事件行为兼容，并严格区分 task event `seq` 与 Trace `sequence_no`。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/schemas/stream.py`
- Modify: `src/bank_reconciliation_agent/services/stream_emitter.py`
- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `src/bank_reconciliation_agent/services/workflow.py`
- Modify only if emitter lifecycle requires it: `src/bank_reconciliation_agent/services/reconciliation.py`
- Modify: `tests/test_stream_schema.py`
- Modify: `tests/test_stream_emitter.py`
- Modify: `tests/test_v1_1_sse_stream.py`
- Modify: `tests/test_v1_1_stream_endpoint.py`
- Modify: `tests/test_trace_workflow.py`

保留已有测试文件名 `test_v1_1_*`；不得仅为版本名称进行无关重命名。

### Do Not Touch

- Replay API contract
- `frontend/`
- Tool/LLM/Agent 公共 contract
- `t_trace_span` schema 与业务事务顺序
- live registry 的跨实例架构

### Out of Scope

- `span_started`、SSE replay、`Last-Event-ID`、跨 backend 广播。
- 用 SSE 作为持久化事实源或 completeness 依据。
- 删除或重命名现有 event types。
- 前端历史 Timeline。

### Acceptance Criteria

- `AgentStreamEvent.schema_version` 为 `1.2`，新增 `trace_span` event type。
- 现有 event types、payload 字段和顺序测试保持通过；不以 `trace_span` 替换旧事件。
- 每个实际 span 结束时最多发出一个 `trace_span`，不发送 start 事件。
- payload 来源于 canonical safe projection，与持久化 span 复用相同 identity/type/status/outcome/metrics
  语义，不包含 `user_id` 或 forbidden fields。
- SSE envelope `seq` 继续按 task event 递增；payload `sequence_no` 保持当前 Trace 内开始顺序。
- 多 flow 同一 task 的 `sequence_no` 可分别从 1 开始，但 envelope `seq` 继续全局递增。
- 浏览器/emitter 断开或 emit 失败不改变 recorder snapshot、业务结果或后续数据库批量写入。
- 现有同步 stream 与 start-live event endpoint 均覆盖 `trace_span`，且无旧 contract 回归。
- 测试证明 SSE 事件与数据库 span 使用相同 `trace_id/span_id`，而非前端或 emitter 重新生成。

### Verification Commands

```bash
uv run pytest tests/test_stream_schema.py tests/test_stream_emitter.py tests/test_v1_1_sse_stream.py tests/test_v1_1_stream_endpoint.py tests/test_trace_workflow.py -q
uv run ruff check src/bank_reconciliation_agent/schemas/stream.py src/bank_reconciliation_agent/services/stream_emitter.py src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/services/workflow.py tests/test_stream_schema.py tests/test_stream_emitter.py
uv run ruff format --check src/bank_reconciliation_agent/schemas/stream.py src/bank_reconciliation_agent/services/stream_emitter.py src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/services/workflow.py tests/test_stream_schema.py tests/test_stream_emitter.py
```

### Report Back Requirements

- Changed Files
- SSE Compatibility Summary：v1.2 新增内容与保持不变内容
- Sequence Evidence：event `seq` 与 span `sequence_no` 的测试结果
- Safe Projection Evidence：禁止字段断言
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：明确进程内 SSE 与断线边界
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.5`

---

## TASK-29.6 — 实现独立 Trace Replay 页面与只读 Timeline

**Status**: done
**Spec Ref**: `Frontend Contract`、`Replay API Contract`、`SSE Contract`
**ADR Ref**: `ADR-29.3`

### Goal

在前端增加可从差错台账详情进入的独立 Replay 页面，支持最新/历史 execution 选择和只读 Timeline；
同时让现有实时事件卡片安全识别 SSE v1.2 `trace_span`。

### Files to Modify

- Create: `frontend/src/api/trace.ts`
- Create: `frontend/src/types/trace.ts`
- Create: `frontend/src/components/TraceTimeline.vue`
- Create: `frontend/src/pages/TraceReplayPage.vue`
- Modify: `frontend/src/components/ledger/LedgerDetailDialog.vue`
- Modify: `frontend/src/components/workbench/EventCard.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/tests/TraceTimeline.spec.ts`
- Create: `frontend/tests/TraceReplayPage.spec.ts`
- Create: `frontend/tests/LedgerDetailDialog.spec.ts`
- Modify: `frontend/tests/stream.spec.ts`
- Modify only if route inventory requires it: `frontend/tests/v1-3-8-pages.spec.ts`

### Do Not Touch

- 后端 API、schema、service、workflow 或 SSE implementation。
- `WorkbenchPage.vue` 的上传/历史查询职责；除非现有 event rendering contract 无法通过
  `EventCard.vue` 完成，否则不得修改。
- 全局导航菜单、Dashboard、Review、Report、Metrics 页面。
- 新状态库、图表库、CSS framework 或其他依赖。

### Out of Scope

- Trace 搜索、删除、重跑、diff、拓扑图、甘特图或 Evidence Explorer。
- evidence 正文请求、自动链接或业务编辑。
- SSE reconnect/Last-Event-ID。
- 修改后端 contract 适配前端偏好。

### Acceptance Criteria

- router 增加 `/traces/:taskId/:flowId`，并继续应用现有 auth guard。
- 差错台账详情使用当前 row 的 task/flow 提供可访问的“查看执行轨迹”入口。
- API client 对 path params 和 optional `trace_id` 正确编码，不发送 `user_id`。
- Replay 页面区分 loading、API error、`IN_PROGRESS`、`TRACE_NOT_AVAILABLE`、空 runs 和
  `AVAILABLE`。
- 默认展示后端选定的最新 run；选择历史 run 后使用其 `trace_id` 重新查询，不在前端拼装历史。
- Timeline 只按后端 `sequence_no` 展示实际 spans，可按 parent 轻量缩进，不推断或补齐缺失节点。
- 每个 span 展示 type/name、status/outcome、duration、attempt/recovery；按存在性展示 token、稳定
  error/fallback 与 evidence IDs。
- evidence 只显示安全、可复制 ID；不加载正文、不拼 URL；无 evidence 明确显示无引用。
- 不显示 `user_id`、数据库内部 id 或不存在字段；数值使用 `tabular-nums`。
- 现有 EventCard 可识别 `trace_span`，但不与历史 Timeline 数据合并或重复生成 identity。
- keyboard focus、状态文本、语义标签和窄屏布局通过组件测试或可验证断言。
- 前端已有 unit tests、typecheck 和 build 全部通过。

### Verification Commands

```bash
cd frontend && npm run test -- TraceTimeline.spec.ts TraceReplayPage.spec.ts LedgerDetailDialog.spec.ts stream.spec.ts
cd frontend && npm run typecheck
cd frontend && npm run build
```

### Report Back Requirements

- Changed Files
- UX State Matrix：loading/error/in-progress/not-available/available/history selection
- Accessibility and Responsive Notes
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.6`

---

## TASK-29.7 — 生成确定性 Trace Replay 证据报告

**Status**: done
**Spec Ref**: `Offline Evidence Contract`、`Acceptance Criteria / Evidence and Documentation`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`、`ADR-29.3`

### Goal

用 SQLite、Fake provider、hash embedding 和确定性故障注入，生成机器可审查 JSON 与同源 Markdown
报告，证明 Trace completeness、失败定位、tenant isolation、token 和写失败隔离。

### Files to Modify

- Create: `scripts/eval_trace_replay.py`
- Create: `tests/test_eval_trace_replay.py`
- Create: `reports/trace_replay_evidence.json`
- Create: `reports/trace_replay_evidence.md`

只有在 runner 暴露真实缺口时，才允许请求 Codex 扩大范围回到对应实现 task；不得在 evidence task
内修改生产代码绕过失败。

### Do Not Touch

- `src/bank_reconciliation_agent/`
- `frontend/`
- 既有 eval datasets、gate thresholds 与历史 reports。
- README/PRD/architecture docs（由 TASK-29.8 处理）。

### Out of Scope

- 真实 DeepSeek、真实 embedding、网络下载或生产数据。
- 性能 pass threshold、生产 SLA 或 Stage 31 性能优化。
- 手工编辑 JSON/Markdown 指标使 gate 通过。
- 扩展 Agent、Tool、RAG 或业务 workflow。

### Acceptance Criteria

- runner 在 import repo RAG/Tool 模块前显式固定 `EMBEDDING_BACKEND=hash`，确保零网络、零模型下载。
- 固定覆盖：完整成功、Tool timeout/failed Fallback、LLM structured repair 最终失败、Safety Guard
  blocked、跨用户 Replay 拒绝、Trace batch write failure。
- 场景使用真实本地 workflow/Trace/API service 边界；仅故障本身使用确定性注入，不手工构造最终
  指标冒充运行结果。
- completeness denominator 是实际进入异常工作流的 eligible flows，numerator 是成功持久化且通过
  全部结构不变量的 Traces。
- JSON 输出 numerator、denominator、rate、场景 span 顺序、P50/P95、error/fallback distribution、
  token by Agent、write success/failure counts 和环境/claim boundary。
- Markdown 只从同次内存结果/JSON 生成，不独立计算或手填指标；两份报告关键数值完全一致。
- P50/P95 算法固定并由测试覆盖；无样本行为明确。
- 报告不包含敏感 markers、prompt、模型正文、query、金额、业务 payload、traceback 或连接信息。
- 报告明确 `offline`、Fake provider、hash embedding、local latency 和非生产 SLA。
- runner 失败返回非零退出码，不覆盖现有有效报告为伪成功结果。
- runner 连续执行两次产生稳定 schema/计数；只允许时间戳和本机 latency 等已声明字段变化。

### Verification Commands

```bash
uv run pytest tests/test_eval_trace_replay.py -q
uv run python -m scripts.eval_trace_replay
uv run python -m scripts.eval_trace_replay
uv run ruff check scripts/eval_trace_replay.py tests/test_eval_trace_replay.py
uv run ruff format --check scripts/eval_trace_replay.py tests/test_eval_trace_replay.py
```

### Report Back Requirements

- Changed Files
- Scenario Coverage Matrix
- Evidence Metrics：直接引用生成 JSON 的实际值
- Determinism Check：两次运行哪些字段相同、哪些允许变化
- Sensitive-data Scan Result
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：强调 offline/local claim boundary
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.7`

---

## TASK-29.8 — 同步 Trace 当前事实与运维边界

**Status**: done
**Spec Ref**: `Backward Compatibility and Schema Provisioning`、`Risks`、`Acceptance Criteria / Evidence and Documentation`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`、`ADR-29.3`

### Goal

在实现与 evidence 已通过后，窄范围同步项目级事实：数据库 Trace、Replay API、SSE v1.2、旧 JSON
退役、schema provisioning 和非生产边界；不改写无关项目叙事。

### Files to Modify

- Modify: `README.md`
- Modify: `system-prd.md`
- Modify: `overall-architecture.md`

`.env.example` 的 `TRACE_DIR` 已由 TASK-29.3 删除，本 task 只核对结果，不重复修改配置。

### Do Not Touch

- `docs/interview/what-todo-next.md`
- Source code、tests、frontend、scripts 和 reports。
- 历史 accepted ADR。
- Stage 30/31 范围、指标门禁或路线图顺序。

### Out of Scope

- README/PRD/architecture 全文重写或格式整理。
- 部署、监控、SLA、retention、Evidence API 或外部 tracing 平台承诺。
- 把 Fake/hash evidence 描述成真实 provider/embedding 或生产证据。

### Acceptance Criteria

- README 给出正确 Replay API/page 入口与 existing schema provisioning 操作边界。
- README 明确 SSE 断线后可通过持久化 Replay 查询，但 SSE 本身仍无断点续传/跨实例广播。
- PRD 将本地 JSON trace 更新为 tenant-scoped DB Trace 与 observation replay，不宣称 execution replay。
- Architecture 删除 `logs/*.jsonl`/本地 JSON 是事实源的旧描述，更新为
  `t_trace_span + TraceRecorder + Replay API + SSE projection`。
- 文档明确 Business `TraceAgent` 与 Execution Trace 不同。
- 文档明确 append-only 无 retention/delete、process-local counters、flow 完成前 crash gap 和
  offline/local evidence 边界。
- 不新增 LangFuse/Jaeger/OTel/Prometheus、生产 SLA 或集群级观测声明。
- 所有 API path、SSE version、service topology、schema file path 与代码/报告事实一致。
- diff 只包含 Trace 相关事实，不顺手修订无关文字。

### Verification Commands

```bash
rg -n "t_trace_span|/api/v1/traces|trace_span|TraceRecorder|TRACE_NOT_AVAILABLE" README.md system-prd.md overall-architecture.md
rg -n "logs/.*jsonl|TRACE_DIR|execution replay" README.md system-prd.md overall-architecture.md .env.example
git diff --check
```

第二条 `rg` 只允许出现在明确否定 execution replay 的上下文；`logs/*.jsonl` 与 `TRACE_DIR` 旧事实
预期无输出。

### Report Back Requirements

- Changed Files
- Fact Sync Summary：每份文档修订的旧事实与新事实
- Claim Boundary Check
- Verification Commands：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.8`

---

## TASK-29.9 — 收紧 Trace 持久化身份、DDL 与 schema provisioning 边界

**Status**: done
**Spec Ref**: `TraceSpan Contract`、`Replay API Contract`、`Backward Compatibility and Schema Provisioning`
**ADR Ref**: `ADR-29.1`、`ADR-29.3`

### Goal

修复 review 发现的持久化身份错配、SQLAlchemy/MySQL DDL 漂移、非本地环境隐式建表和 latest run
排序不稳定问题，使 Trace 写入与 Replay 选择在 tenant 和显式 schema provisioning 边界内 fail closed。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify only if canonical validation requires it: `src/bank_reconciliation_agent/schemas/trace.py`
- Modify: `src/bank_reconciliation_agent/db/schema.sql`
- Modify: `tests/test_trace_storage.py`
- Modify: `tests/test_trace_replay.py`
- Modify only for DDL/Table parity assertions: `tests/test_schema_columns.py`

### Do Not Touch

- `src/bank_reconciliation_agent/services/workflow.py`
- `src/bank_reconciliation_agent/services/reconciliation.py`
- SSE、frontend、evidence runner 和 reports
- Tool/LLM/Agent contract
- README、PRD、architecture 与 accepted ADR

### Out of Scope

- 改变 Replay endpoint 或 response 字段。
- 引入 migration framework、retention/delete 或新数据库依赖。
- 顺手修改现有业务表的 schema provisioning 行为。

### Acceptance Criteria

- `persist_snapshot()`/`save_trace()` 在写入前验证全部 spans 共享同一
  `user_id + task_id + flow_id + trace_id`，且与调用参数完全一致；任一错配整批拒绝并按现有安全
  failure counter/warning 处理，不得重写 span tenant identity 后落库。
- 结构校验覆盖跨 span 的 `user_id/task_id/flow_id` 一致性；测试证明跨租户、跨 task 和跨 flow
  错配均无 rows 写入。
- `t_trace_span` SQLAlchemy Core Table 与 MySQL DDL 的 boolean、datetime/timestamp、nullable、default、
  unique 和 index 定义逐项对齐。
- `_ensure_initialized()` 仅允许现有 local/test SQLite 路径使用 `create_all()`；non-local/MySQL 读写
  不得隐式建表，缺表时按真实数据库错误处理并保持业务 side-effect 隔离。
- 同一 flow 的多个 root `started_at` 相同时，latest run 仍使用持久化顺序的稳定 tie-breaker；API
  默认选择与 `runs[0]` 一致的 execution。
- 不改变 Replay response 的 tenant-safe 字段集合，既有跨用户 404 行为保持通过。

### Verification Commands

```bash
uv run pytest tests/test_trace_storage.py tests/test_trace_replay.py tests/test_schema_columns.py -q
uv run ruff check src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/schemas/trace.py tests/test_trace_storage.py tests/test_trace_replay.py tests/test_schema_columns.py
uv run ruff format --check src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/schemas/trace.py tests/test_trace_storage.py tests/test_trace_replay.py tests/test_schema_columns.py
git diff --check
```

### Report Back Requirements

- Changed Files
- Identity Invariant Evidence：三类参数错配的拒绝结果和 row count
- DDL/Table Parity Summary
- Provisioning Boundary Evidence：SQLite local/test 与 non-local/MySQL 行为
- Latest-run Tie-break Evidence
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：existing MySQL DDL 仍须在 Stage Gate 显式验证
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.9`

---

## TASK-29.10 — 修复 recorder 调用时序与终止语义

**Status**: done
**Spec Ref**: `TraceSpan Contract`、`Recorder and Persistence Flow`、`Tool and LLM Projection`、`Failure Semantics`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`

### Goal

让 Tool/Agent span 在逻辑调用开始时取得 identity、sequence 和 start time，并按真实业务 decision、
fallback 与 recovery 事实结束 Trace；同时修复 Stage 29 引入的全量测试兼容回归。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `src/bank_reconciliation_agent/services/workflow.py`
- Modify: `src/bank_reconciliation_agent/services/reconciliation.py`
- Modify: `tests/test_trace_recorder.py`
- Modify: `tests/test_trace_workflow.py`
- Modify: `tests/test_reconciliation_agent_fallback.py`
- Modify: `tests/test_mvp2a2_workflow_integration.py`
- Modify only if existing workflow contract assertions require it: `tests/test_workflow.py`

### Do Not Touch

- `t_trace_span` Table/DDL 与 Replay API
- SSE schema/emitter 投影（由 TASK-29.11 处理）
- frontend、scripts、reports 和项目级文档
- Stage 26/28 Tool、LLM provider 或 Agent 公共 contract

### Out of Scope

- 物理 attempt 子 spans、并发/跨线程 recorder propagation。
- 改变业务 decision、Guard、fallback 或金额算法。
- 为通过测试删除 recorder 显式传递或放宽结构不变量。

### Acceptance Criteria

- 每次逻辑 Tool/Agent 调用在实际调用前创建 span 并分配 `sequence_no/started_at`；调用结束后使用
  monotonic elapsed time 和 Stage 26/28 safe summary 完成同一 span，不得事后伪造开始时间。
- `started_at/ended_at/duration_ms` 相互一致，异常路径仍完成当前 span 为 `FAILED` 后按原业务边界传播
  或 fail closed。
- LLM transport retry 恢复时，从现有安全 attempt/result 事实投影真实 `recovered_error_type`；未恢复时
  保持 `null`，不得修改 Stage 26 公共 summary contract。
- `TraceRecorder.snapshot()` 自身执行完整结构校验；缺根、缺/多 terminal、identity/sequence/parent
  违规均拒绝，而不是只依赖持久化层补验。
- terminal outcome 保留实际 `AUTO_FIXED/PENDING_HUMAN/UNRESOLVED`；正常完成的
  `PENDING_HUMAN/UNRESOLVED` 使用 `FINAL`，只有已发生安全 fallback 的路径使用 `FALLBACK`，且
  `FALLBACK.outcome` 只允许 `PENDING_HUMAN`。
- `AGENT_PROCESSING_ERRORS`、Tool failure、structured failure 与 Guard blocked 路径仍生成一个真实
  Fallback；普通人工决策不得被误计为 fallback。
- 修复 `tests/test_mvp2a2_workflow_integration.py` 的 recorder-aware test double，完整 `uv run pytest`
  不再出现 unexpected `recorder` keyword 回归；不得通过删除业务断言绕过。

### Verification Commands

```bash
uv run pytest tests/test_trace_recorder.py tests/test_trace_workflow.py tests/test_reconciliation_agent_fallback.py tests/test_mvp2a2_workflow_integration.py tests/test_workflow.py -q
uv run ruff check src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/reconciliation.py tests/test_trace_recorder.py tests/test_trace_workflow.py tests/test_reconciliation_agent_fallback.py tests/test_mvp2a2_workflow_integration.py tests/test_workflow.py
uv run ruff format --check src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/reconciliation.py tests/test_trace_recorder.py tests/test_trace_workflow.py tests/test_reconciliation_agent_fallback.py tests/test_mvp2a2_workflow_integration.py tests/test_workflow.py
```

### Report Back Requirements

- Changed Files
- Span Lifecycle Evidence：开始/结束时间、sequence 与 exception path
- Terminal Matrix：decision、fallback_applied、terminal type、outcome
- LLM Recovery Projection Evidence
- Full-suite Regression Fix Evidence
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.10`

---

## TASK-29.11 — 修复 SSE canonical projection 与 emit 失败隔离

**Status**: done
**Spec Ref**: `SSE Contract`、`Failure Semantics`、`Acceptance Criteria / SSE and Frontend`
**ADR Ref**: `ADR-29.2`、`ADR-29.3`

### Goal

确保每个已完成 canonical span 使用完整安全视图发出至 SSE，实时 identity 与持久化事实一致，并使
projection/emitter 故障只影响实时事件而不打断业务或后续 Trace persistence。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/services/stream_emitter.py`
- Modify: `src/bank_reconciliation_agent/services/workflow.py`
- Modify as required for root/terminal emission only: `src/bank_reconciliation_agent/services/reconciliation.py`
- Modify as required for completed-span handoff only: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `tests/test_stream_schema.py`
- Modify: `tests/test_stream_emitter.py`
- Modify: `tests/test_trace_workflow.py`
- Modify: `tests/test_v1_1_sse_stream.py`
- Modify: `tests/test_v1_1_stream_endpoint.py`

### Do Not Touch

- Replay API 与 `t_trace_span` schema/DDL
- Tool/LLM/Agent contract 和业务 decision
- frontend、evidence runner、reports 和项目级文档
- SSE `Last-Event-ID`、跨实例 registry 或 reconnect 架构

### Out of Scope

- `span_started` 事件、SSE 历史 replay 或跨 backend 广播。
- 用 SSE 作为 persistence/completeness 事实源。
- 修改或删除既有 event types/payload。

### Acceptance Criteria

- workflow 使用 canonical `TraceSpanView`/`to_trace_span_event()` 等价路径，不再把 span model 误送入
  普通 row payload 过滤器；payload 必须包含 `trace_id/span_id/parent_span_id/sequence_no/span_type/name/
  timestamps/duration/status/outcome` 及允许的 optional fields。
- API/SSE 均不包含 `user_id`、内部 `id` 或 forbidden data；SSE identity 与随后持久化 span 完全一致。
- 每个实际完成 span 最多发出一次，包括 `ROUTE/TOOL/AGENT/GUARD/FINAL|FALLBACK/WORKFLOW`；不发送
  start event，不漏 root 或 terminal。
- task event `seq` 与 Trace `sequence_no` 独立递增，多 flow 行为通过端到端测试证明。
- `TraceSpanView` projection、event 构造或 `emitter.emit()` 抛错时，业务 decision、ledger/queue/task
  状态、recorder snapshot 和随后 batch persistence 均保持不变；只记录安全 warning。
- 同步 stream 与 start-live endpoint 测试都验证真实 `trace_span` 完整 payload，不只单测未被生产路径
  调用的 helper；既有 SSE event contract 全部保持通过。

### Verification Commands

```bash
uv run pytest tests/test_stream_schema.py tests/test_stream_emitter.py tests/test_trace_workflow.py tests/test_v1_1_sse_stream.py tests/test_v1_1_stream_endpoint.py -q
uv run ruff check src/bank_reconciliation_agent/services/stream_emitter.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/reconciliation.py src/bank_reconciliation_agent/services/trace.py tests/test_stream_schema.py tests/test_stream_emitter.py tests/test_trace_workflow.py tests/test_v1_1_sse_stream.py tests/test_v1_1_stream_endpoint.py
uv run ruff format --check src/bank_reconciliation_agent/services/stream_emitter.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/reconciliation.py src/bank_reconciliation_agent/services/trace.py tests/test_stream_schema.py tests/test_stream_emitter.py tests/test_trace_workflow.py tests/test_v1_1_sse_stream.py tests/test_v1_1_stream_endpoint.py
```

### Report Back Requirements

- Changed Files
- Canonical Payload Evidence：实时/持久化 identity 与完整字段比较
- Span Emission Matrix：各类型 emit 次数
- Emit Failure Isolation Evidence
- Existing SSE Compatibility Evidence
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：继续明确进程内 SSE 与断线边界
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.11`

---

## TASK-29.12 — 重建可证明持久化与失败语义的 Trace evidence

**Status**: done
**Spec Ref**: `Offline Evidence Contract`、`Acceptance Criteria / Evidence and Documentation`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`、`ADR-29.3`

### Goal

修复 evidence runner 将内存 snapshot 误算为已持久化 Trace 的问题，并通过真实本地 workflow、Trace
service 与 Replay API 边界证明 completeness、structured repair、tenant 404、token 和写失败隔离。

### Files to Modify

- Modify: `scripts/eval_trace_replay.py`
- Modify: `tests/test_eval_trace_replay.py`
- Regenerate: `reports/trace_replay_evidence.json`
- Regenerate: `reports/trace_replay_evidence.md`

### Do Not Touch

- `src/bank_reconciliation_agent/`
- `frontend/`
- 既有 eval datasets、历史 reports 和 gate thresholds
- README、PRD、architecture 与 accepted ADR

### Out of Scope

- 真实 DeepSeek、真实 embedding、网络下载或生产 SLA。
- 修改 production code 适配错误 runner。
- 手工填写 numerator、denominator、token、error 或 scenario pass 状态。

### Acceptance Criteria

- completeness numerator 只统计已由 `TraceService` 成功持久化、重新读取并通过结构不变量的 eligible
  flow；不得以缺省 `trace_persisted=True` 把内存 snapshot 计入成功。
- denominator 精确包含本次 evidence 中实际进入异常工作流的全部 eligible executions；故意注入的
  Trace write failure 仍属于 denominator，不得为保持 100% 排除。
- 报告逐场景输出 persistence/read-back 事实与预期；completeness rate 由真实 numerator/denominator
  计算，允许且必须如实低于 100%。
- structured repair 最终失败通过现有 Fake provider/structured boundary 产生真实安全 summary，Trace
  包含失败 `AGENT` span、repair flags、稳定 error/fallback 和实际 Fake token；不得用普通 RuntimeError
  加手工 `close_root()` 冒充。
- cross-user Replay 通过真实 HTTP API 验证统一 404 与不泄露 payload，不只调用 storage service 得到空
  list。
- Trace write failure 通过实际业务 side-effect 边界证明 ledger/queue/task/decision 保持成功且 Trace rows
  为 0；counter 增量与报告一致。
- JSON 包含可审查的 scenario pass/fail facts；Markdown 仍完全由同次 JSON 生成。
- runner 对任一场景缺字段、语义不符或断言失败返回非零，且不覆盖已有有效报告为伪成功。
- 连续两次运行的 schema、场景、numerator/denominator、distribution 和 token 稳定；允许变化字段明确
  排除在确定性比较外。

### Verification Commands

```bash
uv run pytest tests/test_eval_trace_replay.py -q
uv run python -m scripts.eval_trace_replay
uv run python -m scripts.eval_trace_replay
uv run ruff check scripts/eval_trace_replay.py tests/test_eval_trace_replay.py
uv run ruff format --check scripts/eval_trace_replay.py tests/test_eval_trace_replay.py
git diff --check reports/trace_replay_evidence.json reports/trace_replay_evidence.md
```

### Report Back Requirements

- Changed Files
- Eligible-flow Accounting：逐 execution 的 denominator/numerator 决定
- Structured Repair Evidence：Agent span、repair、error、fallback、token
- Tenant API and Write-failure Isolation Evidence
- Generated Metrics：直接引用 JSON
- Determinism Check
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up：明确 offline/Fake/hash/local 边界
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.12`

---

## TASK-29.13 — 补齐 Replay 页面路由响应性与键盘可访问性

**Status**: done
**Spec Ref**: `Frontend Contract`、`Acceptance Criteria / SSE and Frontend`
**ADR Ref**: `ADR-29.3`

### Goal

修复同一 Replay 页面实例切换 route params 时不重新加载的问题，并让 evidence ID 复制与台账入口具备
真实 router 测试和键盘可操作语义。

### Files to Modify

- Modify: `frontend/src/pages/TraceReplayPage.vue`
- Modify: `frontend/src/components/TraceTimeline.vue`
- Modify only if encoding/navigation requires it: `frontend/src/components/ledger/LedgerDetailDialog.vue`
- Modify: `frontend/tests/TraceReplayPage.spec.ts`
- Modify: `frontend/tests/TraceTimeline.spec.ts`
- Modify: `frontend/tests/LedgerDetailDialog.spec.ts`

### Do Not Touch

- 后端 API/schema/service/workflow/SSE implementation
- 其他 frontend pages、全局导航、状态库和依赖
- scripts、reports 和项目级文档

### Out of Scope

- 新 UI framework、全局 toast 系统或 Timeline 重设计。
- Evidence API、正文加载、自动链接、Trace search/diff/re-run。

### Acceptance Criteria

- `taskId/flowId` 从 reactive route params 派生；同一组件实例导航到另一 task/flow 时清理旧选择并发起
  新请求，不展示旧 Trace。
- path params 与 optional `trace_id` 只编码一次；包含保留字符的 task/flow ID 测试证明请求 path 正确。
- evidence ID 复制控件使用原生可聚焦控件或等价 `role/tabindex/keydown` 语义，Enter/Space 与 click
  行为一致，并保留只读、不加载正文的边界。
- Ledger detail 测试安装真实 test router，点击入口后断言 route；不再以 router injection warning 下的
  静态按钮存在性冒充导航验证。
- loading/error/in-progress/not-available/available/history 状态和窄屏布局既有行为无回归。

### Verification Commands

```bash
cd frontend && npm run test -- TraceReplayPage.spec.ts TraceTimeline.spec.ts LedgerDetailDialog.spec.ts
cd frontend && npm run typecheck
cd frontend && npm run build
```

### Report Back Requirements

- Changed Files
- Route Reactivity and Encoding Evidence
- Keyboard Interaction Evidence
- Router Navigation Test Evidence
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.13`

---

## TASK-29.14 — 关闭 Replay 路由请求竞态并补齐真实交互验证

**Status**: done
**Spec Ref**: `Frontend Contract`、`Acceptance Criteria / SSE and Frontend`
**ADR Ref**: `ADR-29.3`

### Goal

关闭 TASK-29.13 复审发现的三个 Blocking：保证同一 `TraceReplayPage` 实例切换 route params 时只有
最新请求可以提交页面状态；以真实行为测试证明 evidence ID 的 click/Enter/Space 复制语义；并在
router 与 API 序列化边界证明 task/flow path params 和 optional `trace_id` 只编码一次。

本 task 是 TASK-29.13 的窄范围 review-blocker closure，不重新设计 Replay 页面，也不改变后端
Replay contract。

### Files to Modify

- Modify: `frontend/src/pages/TraceReplayPage.vue`
- Modify: `frontend/tests/TraceReplayPage.spec.ts`
- Modify: `frontend/tests/TraceTimeline.spec.ts`
- Modify: `frontend/tests/LedgerDetailDialog.spec.ts`
- Add: `frontend/tests/trace.spec.ts`
- Modify only if the new behavior test proves the current implementation is incorrect:
  `frontend/src/components/TraceTimeline.vue`
- Modify only if the real route assertion fails: `frontend/src/components/ledger/LedgerDetailDialog.vue`
- Modify only if the final serialized request assertion fails: `frontend/src/api/trace.ts` or the directly
  responsible existing API-client test boundary

### Do Not Touch

- 后端 API、schema、service、workflow、SSE implementation 与数据库文件
- `frontend/src/router/index.ts`、其他 frontend pages、全局导航、状态管理和样式系统
- Trace/Replay TypeScript contract；若测试发现 contract 本身错误，停止并报告
- `package.json`、lockfile 和依赖配置
- scripts、reports、spec、tasks、ADR、verification 和项目级文档

### Out of Scope

- 通用请求管理器、全局 cancellation abstraction 或对其他页面的并发请求重构。
- Replay 页面状态机、历史列表、Timeline 布局或视觉样式重设计。
- toast、复制成功提示、Evidence API、正文加载、自动链接、Trace search/diff/re-run。
- 修改 Replay endpoint、response schema、tenant 语义或后端 URL contract。
- 顺手修复本 task 指定文件之外的既有前端问题。

### Acceptance Criteria

#### Latest-request-wins

- 每次发起 Replay 请求时建立页面实例内的最小请求所有权机制；可以使用单调递增 generation/token
  或等价简单方案，不要求引入 `AbortController` 或通用 abstraction。
- route A 的请求仍在进行时导航到 route B，必须立即清空 A 的 selected run 和可见 Trace，并为 B
  发起最新请求。
- B 请求先成功、A 请求后成功时，A 不得覆盖 B 的 `data`、`error` 或 `loading`；页面最终只能显示
  B 的 task/flow/Trace。
- A 请求在 B 之后失败或进入 `finally` 时，同样不得写回错误状态，也不得在 B 仍 pending 时提前
  结束 loading。
- 上述规则同时覆盖默认 latest 请求和历史 run 请求：route 变化必须使旧 route 下尚未完成的
  `selectRun()` 请求失效。
- 测试使用可控 deferred promises 明确安排乱序完成；不得继续使用永不 settle 的 Promise 或只断言
  页面标题中的 route params 来代替竞态验证。

#### Router and Encoding

- Ledger detail 测试安装真实 memory router，点击“查看执行轨迹”后断言
  `router.currentRoute.value` 的 route/path/params；只 spy `router.push()` 入参不算通过。
- 保留字符用例至少覆盖 `/`、`#`、`?`、`&`、`%` 中会暴露 double-encoding 的组合；router params
  必须还原为原始 task/flow ID。
- 在 API 层或等价的真实 URL 序列化边界断言最终请求 URL：task/flow path params 各编码一次，既不
  保留未编码字符，也不出现 `%25xx` 形式的二次编码。
- optional `trace_id` 使用同一用例验证 query serialization，只编码一次；断言必须覆盖最终 URL 或
  等价的 Axios serialization 结果，不能只检查 DOM 文案或 mock 函数收到的原始参数。
- 上述测试不得发出真实网络请求，不改变 production endpoint contract。

#### Evidence Keyboard Interaction

- evidence ID 控件保持原生可聚焦 button，或提供等价、完整的键盘语义；空 evidence 仍只显示
  非交互“无引用”状态。
- 测试挂载真实 `TraceTimeline`，stub `navigator.clipboard.writeText`，分别触发 click、Enter 和 Space；
  三种交互都写入相同的 joined evidence IDs，且每次用户交互至多写入一次。
- 键盘测试必须实际触发组件 handler/clipboard side effect；SSR 字符串中存在 `<button>` 或
  `aria-label` 不能单独作为行为证据。
- 复制仍是只读行为：不得触发 API 请求、导航、正文加载或对 span/evidence 数据的修改。
- clipboard API reject/unsupported 时保持现有安全降级，不让异常冒泡破坏 Timeline。

#### Regression and Scope Hygiene

- 恢复 `LedgerDetailDialog` 既有银行端/企业端金额渲染断言，避免本次导航测试改造削弱无关覆盖。
- 删除本次变更新增的未使用 import、无效 helper 参数和仅为测试通过而存在的冗余代码。
- TASK-29.13 已覆盖的 loading/error/in-progress/not-available/available/history、窄屏布局和只读
  evidence 边界保持不变。
- 不新增依赖，不修改后端或公共 contract；所有 changed lines 均可追溯到本 task。

### Verification Commands

```bash
cd frontend && npm run test -- TraceReplayPage.spec.ts TraceTimeline.spec.ts LedgerDetailDialog.spec.ts trace.spec.ts
cd frontend && npm run test
cd frontend && npm run typecheck
cd frontend && npm run build
```

### Report Back Requirements

- Changed Files
- Request Ownership Strategy：说明 generation/token 如何阻止 stale success/error/finally 写回
- Deferred Race Evidence：列出 A/B 完成顺序及最终页面断言
- Router Navigation Evidence：引用 `currentRoute` 的实际断言
- Encoding Evidence：列出原始 ID、期望最终 path/query 和 single-encoding 断言
- Keyboard Interaction Evidence：click/Enter/Space 的 clipboard 调用参数与次数
- Regression Coverage：说明恢复的金额断言和保留的既有状态测试
- Tests Run：逐条命令与真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.14`

---

## TASK-29.15 — 最终关闭 Trace 运行时真实性与可复现实证缺口

**Status**: done
**Spec Ref**: `TraceSpan Contract`、`Recorder and Persistence Flow`、`Tool and LLM Projection`、
`SSE Contract`、`Failure Semantics`、`Offline Evidence Contract`
**ADR Ref**: `ADR-29.1`、`ADR-29.2`、`ADR-29.3`

### Goal

作为 Stage 29 唯一且最后一轮 repair task，合并关闭 TASK-29.10–29.12 复审后仍存在的核心问题：

1. Tool/Agent span 必须在真实调用开始前取得 identity、sequence 和 start time，并正确投影 LLM retry
   recovery 与 `UNRESOLVED` terminal 语义。
2. SSE 必须安全发出完整 canonical Trace，包括 terminal/root，且 projection/emitter 故障不得影响业务
   结果与随后持久化。
3. deterministic evidence 必须通过真实 Replay HTTP 与 reconciliation side-effect 边界证明 tenant
   isolation、写失败隔离和 completeness，停止输出失真的 `4/4 = 100%`。

TASK-29.9 的 tenant identity、DDL、schema provisioning 与 latest tie-break 修复已通过本轮复审，不在
本 task 重做。TASK-29.13–29.14 的 production route generation guard、只读 Timeline 和基本键盘复制
足以支撑当前 Agent 项目演示；纯前端测试完备度不再作为 Stage 29 Blocking，也不得继续派生 repair
task。完成本 task 后，只按本 task 明列的运行时/evidence 验收与 Stage Gate 判断是否收尾。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/schemas/trace.py`
- Modify: `src/bank_reconciliation_agent/services/trace.py`
- Modify: `src/bank_reconciliation_agent/services/workflow.py`
- Modify: `src/bank_reconciliation_agent/services/reconciliation.py`
- Modify only if canonical event construction itself requires a minimal fix:
  `src/bank_reconciliation_agent/services/stream_emitter.py`
- Modify: `scripts/eval_trace_replay.py`
- Modify: `tests/test_trace_schema.py`
- Modify: `tests/test_trace_recorder.py`
- Modify: `tests/test_trace_workflow.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_stream_emitter.py`
- Modify: `tests/test_v1_1_stream_endpoint.py`
- Modify: `tests/test_eval_trace_replay.py`
- Regenerate: `reports/trace_replay_evidence.json`
- Regenerate: `reports/trace_replay_evidence.md`

### Do Not Touch

- `src/bank_reconciliation_agent/db/schema.sql`、Trace Table/DDL、Replay endpoint 和 tenant query；
  TASK-29.9 已通过，不得重复重构
- Stage 26 `LLMCallSummary`、provider 公共 contract、重试次数和 structured repair 策略
- Stage 28 Tool Executor、Tool result/projection contract 和 breaker/retry 策略
- 金额算法、ledger/queue/task transaction contract、权限模型或业务 decision 规则
- `frontend/` 全目录；本 task 不再追求前端测试或 UI 完美度
- README、PRD、architecture、accepted ADR、其他 reports 与 eval datasets
- `pyproject.toml`、`uv.lock`、`package.json`、lockfile；不得新增依赖
- `spec.md`、`tasks.md`、`verification.md`；这些规划/收尾文件由 Codex 维护

### Out of Scope

- OpenTelemetry、Jaeger、LangFuse、分布式 Trace、跨线程 propagation 或后台 flush worker。
- SSE `span_started`、`Last-Event-ID`、断点续传、跨实例广播或持久化 event bus。
- 改造整个 workflow 为新的执行框架，或为 Trace 引入通用 middleware/observer abstraction。
- 真实 DeepSeek、真实 embedding、网络下载、生产 SLA 或性能优化。
- 前端 final URL serialization、极端保留字符、完整浏览器键盘矩阵和 UI 状态测试补齐。
- repo-wide Ruff format 治理；不得格式化本 task 之外的既有文件。
- 为获得漂亮指标排除失败样本、手填 report、弱化断言或修改 numerator/denominator 定义。

### Acceptance Criteria

#### A. Tool/Agent Call Lifecycle and Terminal Truth

- 每次逻辑 Tool/Agent 调用必须在进入实际 `execute()`/Agent method 前创建同一个待完成 span，并当场
  分配 `span_id`、`sequence_no`、`started_at` 与 parent；调用成功或失败后只完成该 span，不得在返回
  后新建 span 再倒推开始时间。
- `started_at` 不晚于被测调用入口，`ended_at` 不早于调用退出；`duration_ms` 继续由 monotonic clock
  计算且非负。测试必须证明 allocation 发生在调用前，而不只是断言最终时间字段存在。
- Tool/Agent exception 路径将已经开始的 span 完成为 `FAILED`，保留稳定 safe error/fallback token，
  并继续遵守现有业务传播或 fail-closed 边界。
- 删除或替换当前未使用 `mono_start`、仅按 duration 回推墙钟时间的伪 start helper；不得保留名称暗示
  使用 monotonic start、实现却忽略参数的代码。
- 当 Stage 26 summary 表明 `retry_recovered=True` 时，从现有安全 `LLMResult.attempts` 中提取首个失败
  `failure_type` 作为 `recovered_error_type`；无 retry recovery 时保持 `null`。不得为此修改
  `LLMCallSummary` 或 provider 公共 contract。
- 正常 `AUTO_FIXED/PENDING_HUMAN/UNRESOLVED` 分别生成同 outcome 的 `FINAL`；只有真实
  `fallback_applied=True` 的安全转人工生成 `FALLBACK + PENDING_HUMAN`。
- canonical `TraceSpan` 在 schema/snapshot 边界拒绝 `FALLBACK` 携带 `AUTO_FIXED` 或 `UNRESOLVED`，
  防止错误 terminal 进入 DB、Replay 或 SSE。
- 测试至少覆盖：Tool success/failure、Agent success/failure、LLM retry recovered token、普通
  `PENDING_HUMAN`、普通 `UNRESOLVED` 和真实 fallback。

#### B. Complete SSE and Failure Isolation

- 每个实际完成 span 最多发出一个 `trace_span` event；完整 execution 必须包含
  `WORKFLOW/ROUTE/.../FINAL|FALLBACK`，不得继续遗漏 root 或 terminal。
- terminal 在业务 decision 已确定后完成；root 在整个 flow 完成后结束。两者的 SSE payload 复用将要
  持久化 snapshot 的相同 `trace_id/span_id/sequence_no/status/outcome`，即使实时发出顺序与
  `sequence_no` 不同也不得修改 canonical identity。
- `last_completed_span` 读取、`TraceSpanView` projection、event construction、SSE seq 更新和
  `emitter.emit()` 全部位于 best-effort failure boundary 内；任一步抛错都只产生安全 warning。
- projection/emitter 故障不得改变 audit decision、ledger/queue/task 写入、recorder snapshot 或随后
  `TraceService.persist_snapshot()`；不得因实时事件失败禁用本来有效的持久化 Trace。
- production-path 测试通过 `ReconciliationService` 的真实 finalize/persist 路径收集 SSE 与 DB rows，
  断言两侧 span identity 集合和 canonical 字段一致，并证明 root/terminal 各一次、无重复。
- 现有 event types 保持兼容；payload 不包含 `user_id`、内部 DB id、prompt/output/amount 或异常原文。

#### C. Evidence Must Report Facts, Not a Perfect Score

- 六个 evidence 场景均显式记录 `scenario_passed`、`eligible_execution`、期望/实际 persistence、关键
  业务或 API 断言；`trace_persisted` 不再被错误当作所有场景的 pass 条件。
- 本 runner 的六个场景都实际进入异常 workflow，因此 completeness 固定以 6 为 denominator；五条
  成功持久化 Trace 为 numerator，故当前设计的真实结果应为 `5/6`，不得排除故意写失败 execution
  或再次生成 `4/4 = 100%`。
- cross-tenant 场景通过真实 FastAPI HTTP Replay endpoint 发起 owner 与 non-owner 请求，至少记录
  non-owner `404`、稳定 error code/语义和无 Trace payload 泄露；storage-level empty read 只能作为
  补充，不能替代 HTTP 证据。
- Trace write failure 必须经过真实 `ReconciliationService` 核心事务提交后的 Trace side-effect
  边界注入；报告证明 ledger、queue、task stats 和最终 decision 已按预期提交，Trace rows 为 0，业务
  API/调用仍成功，failure counter 增量正确。
- structured repair 场景继续使用真实 Fake provider + structured boundary，报告包含失败 Agent span、
  repair attempted/succeeded、稳定 error/fallback、实际非缓存 token 和最终 Fallback。
- JSON 保留每个场景的可审查事实；`scenario_pass_count` 必须按场景预期判断，六个场景全部满足预期时
  为 `6/6`，同时 completeness 诚实保持 `5/6`。Markdown 完全由同次 JSON 生成并展示相同口径。
- runner 在任一 scenario 断言、report schema 或跨字段一致性失败时返回非零，并在完整校验通过前不
  覆盖已有有效 reports。
- 连续两次运行的 scenario 集合、pass count、numerator/denominator、distribution、token 和 claim
  boundary 一致；trace IDs、timestamps 与 local duration 等允许变化字段明确排除。
- report 继续明确 `offline + Fake provider + hash embedding + local SQLite + non-production SLA`，不得
  包装为真实线上或生产结果。

#### D. Final-scope Boundary

- TASK-29.9 的 identity/DDL/tie-break 测试保持通过，不回归 tenant isolation 或 MySQL 不隐式建表边界。
- 现有 frontend full tests、typecheck 和 build 只作为回归门禁；本 task 不因前端测试细节失败之外的
  improvement suggestion 扩大范围。
- 完成本 task 后不再新增 Stage 29 repair task；若明列的核心验收失败，则 TASK-29.15 保持 `pending`
  并在同一 task 下继续修复，允许多个 commit 均引用 `Refs: TASK-29.15`。

### Verification Commands

```bash
uv run pytest tests/test_trace_schema.py tests/test_trace_storage.py tests/test_trace_recorder.py tests/test_trace_workflow.py tests/test_workflow.py tests/test_stream_emitter.py tests/test_v1_1_stream_endpoint.py tests/test_eval_trace_replay.py -q
uv run python -m scripts.eval_trace_replay
uv run python -m scripts.eval_trace_replay
uv run pytest
uv run ruff check src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/reconciliation.py src/bank_reconciliation_agent/services/stream_emitter.py scripts/eval_trace_replay.py tests/test_trace_schema.py tests/test_trace_recorder.py tests/test_trace_workflow.py tests/test_workflow.py tests/test_stream_emitter.py tests/test_v1_1_stream_endpoint.py tests/test_eval_trace_replay.py
uv run ruff format --check src/bank_reconciliation_agent/schemas/trace.py src/bank_reconciliation_agent/services/trace.py src/bank_reconciliation_agent/services/workflow.py src/bank_reconciliation_agent/services/reconciliation.py src/bank_reconciliation_agent/services/stream_emitter.py scripts/eval_trace_replay.py tests/test_trace_schema.py tests/test_trace_recorder.py tests/test_trace_workflow.py tests/test_workflow.py tests/test_stream_emitter.py tests/test_v1_1_stream_endpoint.py tests/test_eval_trace_replay.py
cd frontend && npm run test && npm run typecheck && npm run build
git diff --check
```

若 repo-wide `uv run ruff format --check .` 仍只命中 Stage 29 开始前已存在的 baseline files，Report
Back 如实记录，不得在本 task 格式化无关文件；changed-path format gate 必须通过。

### Report Back Requirements

- Changed Files
- Review Closure Matrix：逐项对应 TASK-29.10 lifecycle/terminal、TASK-29.11 SSE、TASK-29.12 evidence
- Call-start Evidence：Tool/Agent success 与 failure 的 allocation/close 时序
- LLM Recovery Evidence：attempt facts 与 `recovered_error_type`
- Terminal Matrix：decision、fallback_applied、terminal type、outcome 与 schema rejection
- SSE/Persistence Identity Matrix：每类 span 的 emit count 与 DB identity 对比
- SSE Failure Isolation Evidence：projection/event/emitter 三类故障后的业务与 persistence 结果
- Evidence Scenario Table：六场景 pass、eligible、persistence、HTTP/业务事实
- Generated Metrics：`scenario_pass_count=6/6`、completeness `5/6` 及 JSON/Markdown 一致性
- Determinism Check：两次 runner 的稳定字段比较
- Tests Run：逐条命令与真实结果；未运行或失败必须如实记录
- Deviations From Spec
- Risks/Follow-up：只保留真实外部环境/production boundary，不新增前端 polishing 项
- Commit：Conventional Commit，body 包含 `Refs: TASK-29.15`

---

## Stage Completion Gate

完成 TASK-29.1–29.15 后，Codex 执行 blocker-first review。只有全部 task 为 `done` 或明确
`out-of-scope`、所有 Blocking 已关闭，才运行并填写 `verification.md` 的 Stage/PR Gate。

Stage 完成不包含 push、PR 或 merge；这些操作仍由用户负责。
