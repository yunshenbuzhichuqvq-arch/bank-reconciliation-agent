# ADR-29.1: 使用专用表持久化 append-only 执行 Trace

**Slug**: `persistent-execution-trace-model`
**Status**: accepted
**Date**: 2026-07-13

### Context

当前 `TraceWriter` 将每个异常 flow 的汇总写入
`data/traces/{task_id}/{flow_id}.json`。该文件会被同一 `task_id + flow_id` 的后续执行覆盖，
无法保留 force requeue 历史；在 backend、worker 分离的 Compose 拓扑中，本地文件也不能天然作为
跨服务 Replay 的事实源。

现有 `t_agent_execution_log` 主要保存 AuditAgent 汇总，缺少稳定的 `flow_id`、span identity、
parent-child、执行顺序、起止时间和节点状态。把 Route、Tool、Agent、Guard 和终止结果继续塞入自由
JSON payload，会混淆审计日志与执行轨迹，并扩大敏感数据复制风险。

Stage 29 需要只读回放已经发生的执行证据，而不是重新执行 Tool、RAG、LLM、Guard 或业务写入。
同一 flow 被重新处理时，旧执行证据必须保留。

### Options Considered

- **Option A：在现有业务数据库新增专用 `t_trace_span` 表（采纳）**
  - Pros：backend 与 worker 可共享；可按租户和 flow 稳定查询；支持多次执行历史、顺序与层级校验；
    不引入新的数据库产品或外部平台。
  - Cons：需要新增表并同步 SQLAlchemy 与 MySQL DDL；Trace 数据会持续增长，后续仍需 retention
    治理。
- **Option B：扩展 `t_agent_execution_log` 并复用其 JSON payload**
  - Pros：不新增表；继续使用现有日志服务。
  - Cons：审计汇总与执行 span 语义混杂；现有列无法直接支持 flow、parent-child 和稳定排序；自由
    payload 容易复制敏感输入输出。
- **Option C：继续使用本地 JSON 文件**
  - Pros：改动最少；不涉及数据库 schema。
  - Cons：同一 flow 后续执行会覆盖旧记录；多容器不可共享；无法高效执行 tenant-scoped 查询；会
    与 Replay API 形成第二事实源。

### Decision

采用 **Option A**。

- `t_trace_span` 是 Replay 的唯一事实源。表位于现有 MySQL/SQLite 数据库中，不引入新的 Trace
  数据库、LangFuse、Jaeger、OpenTelemetry Collector 或日志搜索集群。
- 每次异常 flow 执行生成新的不透明 UUID `trace_id`。`task_id + flow_id` 是业务关联键，不充当
  Trace identity；force requeue 或重新处理不得覆盖旧 Trace。
- 一个 `trace_id` 恰好包含一个根 `WORKFLOW` span。span 使用不透明 UUID `span_id`，通过
  `parent_span_id` 表达同一 Trace 内的层级。
- `sequence_no` 在 span 开始时分配，在单个 `trace_id` 内从 1 单调递增。Replay 只按
  `sequence_no` 排序，不依赖自增主键、完成时间或数据库返回顺序。
- `started_at`、`ended_at` 使用 UTC；`duration_ms` 使用 monotonic clock 计算且不得为负。
- `span_type` 是封闭枚举：`WORKFLOW`、`ROUTE`、`TOOL`、`AGENT`、`GUARD`、`FINAL`、
  `FALLBACK`。RAG 检索以 `TOOL(name=search_rules)` 表示，不重复生成 `RAG` span。
- 每条已完成 Trace 恰好有一个 `FINAL` 或 `FALLBACK` 终止 span。只记录实际执行过的节点，不为
  未执行节点伪造 `SKIPPED` span。
- `status` 只表示技术执行结果：`SUCCEEDED`、`FAILED`、`CANCELLED`。正确执行的 fail-closed
  Guard、Fallback 和根 Workflow 可以是 `SUCCEEDED`；业务去向由类型受限的 `outcome` 表达。
- `outcome` 按 `span_type` 校验：Tool 使用 `RESULT/EMPTY`，Guard 使用 `PASSED/BLOCKED`，
  Final/Fallback/Workflow 使用现有权威业务去向 `AUTO_FIXED/PENDING_HUMAN/UNRESOLVED`。
- Trace schema 使用严格字段白名单，至少包含 identity、租户关联、顺序、类型、时间、status、
  outcome、attempt/recovery、model/token、稳定 error/fallback 和 evidence IDs。禁止任意
  `attributes`、`input_payload` 或 `output_payload`。
- 禁止持久化完整 prompt、模型回复、RAG query、金额、流水摘要、备注、规则正文、历史审计意见、
  traceback、异常原文、连接信息、认证 token、Tool 原始参数和完整 Tool 结果。
- evidence IDs 只允许 Stage 28 冻结的安全投影：`search_rules.chunk_id`、
  `load_confirmed_cases.flow_id`、`lookup_t1_context.flow_id`。Stage 29 不解析或复制证据正文。
- 一次逻辑 Tool 或 Agent 调用对应一个 span，不为每次物理 attempt 创建子 span。span 保存
  `attempt`、`retry_recovered`、`recovered_error_type`、structured repair 摘要和实际 token
  聚合。
- 仅 `AGENT` span 保存实际非缓存 provider 调用的 `prompt_tokens`、`completion_tokens` 和
  `cached_calls`。根 span 不复制子节点 token；Trace 总 token 由 API 对 Agent spans 求和。
- `error_type` 直接复用 Stage 26/28 已冻结的稳定 token，不统一改名或大小写；Guard/Workflow
  只补充必要的封闭错误 token。`fallback_reason` 不保存自由文本。
- 只为进入异常处理工作流的 flow 建立 Trace；普通 `AUTO_FIXED` 匹配行、上传解析、任务调度、
  人工复核、报表和普通 CRUD 不在 Stage 29 tracing 范围内。
- 停止并删除旧 `TraceWriter`、本地 JSON Trace 写入和 `TRACE_DIR` 配置；
  `t_agent_execution_log` 继续承担现有审计汇总职责，不作为 Replay fallback。
- SQLAlchemy Core `Table` 与 `db/schema.sql` 必须同步。现有 MySQL/Compose 数据卷通过显式重放
  更新后的 `CREATE TABLE IF NOT EXISTS` DDL 增加表；Stage 29 不引入 migration framework。
- Stage 29 不实现 Trace TTL、自动清理、归档或删除 API。该缺口必须作为进入真实生产前的数据治理
  风险记录。

### Consequences

- 正面：每次 flow 执行都有稳定、可租户隔离、可保留历史的 Trace identity 和结构化 spans。
- 正面：Replay 不再依赖 worker 本地文件，force requeue 前后的执行证据不会相互覆盖。
- 正面：严格 schema 与 evidence allowlist 避免把自由日志 payload 复制成长期敏感数据。
- 负面：新增表需要显式 schema 初始化；旧环境若未应用更新后的 DDL，将无法保存或回放 Trace。
- 负面：append-only 数据会持续增长；本 Stage 不提供 retention/delete，不能宣称满足生产数据治理。
- 约束：Replay 只展示历史执行证据，不重新执行任何节点，也不提供 Trace 搜索平台或 Evidence
  Explorer。
