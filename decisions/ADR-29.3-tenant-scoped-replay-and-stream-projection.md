# ADR-29.3: 使用 tenant-scoped Replay API 与统一 SSE 投影

**Slug**: `tenant-scoped-replay-and-stream-projection`
**Status**: accepted
**Date**: 2026-07-13

### Context

现有 SSE 使用进程内 emitter 展示实时事件，浏览器断开后不能回放；现有事件 payload 也不是统一
`TraceSpan` contract。Stage 29 需要让用户在任务完成后按异常 flow 查询持久化执行证据，并在实时
SSE 中复用同一组 span 语义，同时保持现有 `task_progress`、`agent_decision`、`fallback` 和
`item_done` 行为兼容。

Replay 查询涉及 flow、Trace 历史和 evidence metadata。若只按 `task_id` 或 `trace_id` 查询而不先
验证 JWT user ownership，会泄露其他用户的 span 数量、节点名称、错误类型和 evidence IDs。前端
当前 `WorkbenchPage` 负责上传和实时流，没有稳定的 `task_id + flow_id` 历史查询上下文；差错台账
详情已经具备这两个业务关联键。

### Options Considered

- **Option A：一个 tenant-scoped Replay endpoint + canonical TraceSpan 的 API/SSE 投影（采纳）**
  - Pros：默认最新与历史执行共用一个 contract；DB、API 与 SSE 语义一致；可以复用 span ID 去重；
    租户隔离集中在服务边界。
  - Cons：需要升级 SSE schema 并增加前端 Replay 页面；实时流和持久化仍有不同可用性边界。
- **Option B：Replay API 与 SSE 各自维护独立 schema**
  - Pros：可以最少改动现有 SSE event payload。
  - Cons：同一节点会出现两套 status、error、token 和 evidence 口径；前端无法可靠去重或刷新恢复。
- **Option C：只提供历史 Replay，不增加 SSE TraceSpan 事件**
  - Pros：实现范围更小；不改变 SSE version。
  - Cons：无法满足实时与持久化使用同一 span 语义的目标；现有 Workbench 继续只能展示自由事件。

### Decision

采用 **Option A**。

- 新增唯一只读 endpoint：
  `GET /api/v1/traces/{task_id}/flows/{flow_id}?trace_id=<optional>`。
- endpoint 沿用 JWT 与现有 `ApiResponse`。未传 `trace_id` 时选择该 flow 最新一次执行；传入时选择
  指定历史执行。响应包含 `replay_status`、`selected_trace_id`、`execution_count`、精简 runs 列表和
  已按 `sequence_no` 排序的 spans。
- `replay_status` 是封闭枚举：`AVAILABLE`、`IN_PROGRESS`、`TRACE_NOT_AVAILABLE`。任务仍在处理且
  尚无完整 flow Trace 时返回 `IN_PROGRESS + spans=[]`；当前用户拥有 task/flow、任务已结束但 Trace
  因 side-effect 失败等原因缺失时返回 `TRACE_NOT_AVAILABLE`。
- 查询必须先使用 JWT `user_id` 验证 task ownership，再限定 `user_id + task_id + flow_id`，指定
  `trace_id` 时继续使用四字段联合限定。task 不存在与属于其他用户统一返回
  `404 TASK_NOT_FOUND`；flow/trace 不存在与不属于该上下文统一返回 `404 TRACE_NOT_FOUND`。
- Replay API 不返回 `user_id`、完整 evidence、业务输入输出或异常原文。Stage 29 不提供全局 Trace
  列表、搜索、删除、重跑、两次执行 diff 或 Evidence API。
- 现有 `AgentStreamEvent` schema 从 v1.1 升为 v1.2，新增 `trace_span` event type。现有 event types
  与 payload contract 保持兼容，不被 TraceSpan 替换或删除。
- span 结束时发送一条 `trace_span` SSE 事件，不发送 `span_started`。SSE payload 由同一个严格
  `TraceSpan` model 生成安全投影，并复用持久化记录的 `trace_id`、`span_id`、`parent_span_id`、
  `sequence_no`、类型、状态、outcome、耗时、attempt、token、error/fallback 和 evidence IDs。
- SSE envelope 已包含 `task_id + flow_id`，payload 不重复发送 `user_id`。浏览器断开只影响实时
  事件，不影响 flow 完成后的持久化；刷新后以 Replay API 为事实源，并按 `span_id` 去重。
- `AgentStreamEvent.seq` 与 `TraceSpan.sequence_no` 独立维护：前者是 task SSE 事件顺序，后者是
  单个 `trace_id` 内的 span 开始顺序。不得用 SSE 断号判断 Trace completeness。
- Stage 29 不实现 `Last-Event-ID`、SSE 断点续传、跨 backend 广播或分布式 Trace。
- 前端新增独立只读路由 `/traces/:taskId/:flowId` 和 `TraceReplayPage`，由差错台账详情提供“查看执行
  轨迹”入口。页面支持最新/历史 run 选择、loading/error/empty 状态和只读 `TraceTimeline`。
- `WorkbenchPage` 继续负责上传与实时 SSE；新的 `trace_span` 可在现有事件时间线中展示，但 Stage
  29 不把历史查询表单塞入 Workbench，也不重构现有实时工作台。
- Timeline 按 `sequence_no` 展示实际 spans，可用 parent 关系做轻量缩进；Stage 29 不建设拓扑图、
  甘特图或复杂 Trace Explorer。
- evidence IDs 只显示为只读、可复制的安全 ID，不加载正文、不自动拼接链接。无 evidence 时显示无
  引用状态，不生成占位 ID。

### Consequences

- 正面：浏览器断开后仍可从数据库回放完整 flow Trace，且实时与历史字段语义一致。
- 正面：所有查询在 tenant + task + flow 边界内执行，跨用户不能探测 span metadata 或 evidence。
- 正面：现有 SSE 消费方保持兼容，前端可以通过 span ID 将实时事件与历史事实源去重。
- 负面：SSE 仍是单 backend 进程内实时通道，不支持断点续传或水平扩展广播。
- 负面：独立 Replay 页面增加一条前端路由和台账入口，但有意不发展为全局 Trace 搜索平台。
- 约束：Stage 29 只做 observation replay，不执行 Tool/LLM/Guard，不提供 evidence 正文解析或业务
  数据编辑能力。
