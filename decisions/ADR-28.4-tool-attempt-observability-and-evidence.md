# ADR-28.4: Tool attempt 使用安全投影并生成离线证据报告

**Slug**: `tool-attempt-observability-and-evidence`
**Status**: accepted
**Date**: 2026-07-12

### Context

Stage 28 需要证明 Tool success、validation failure、permission denial、timeout、retry recovery 和
P50/P95 duration，并为 Stage 29 提供稳定的 attempt 输入。如果结果只保留最终 `attempt=2`，就无法解释
第一次失败的类型；如果记录完整 args、query、结果或异常，又会复制金额、历史审计意见、流水信息和
连接细节。

Stage 29 已负责统一 TraceSpan、持久化和回放。Stage 28 不应提前新增 trace 表或前端 timeline，但也
不能把证据只写在测试终端或 PR 文案中。

### Options Considered

- **Option A：顶层摘要 + bounded attempt records + 安全投影 + 双格式离线报告（采纳）**
  - Pros：可以解释 retry recovery；不保存敏感输入输出；JSON 提供机器可审查事实源，Markdown 便于人工 review；Stage 29 可直接投影稳定字段。
  - Cons：结果 schema 比只保留最终状态更大；离线 P50/P95 受机器环境影响，不能直接作为生产性能结论。
- **Option B：只保留最终 Tool 状态并依赖 pytest 输出**
  - Pros：schema 和实现最简单；无需报告脚本。
  - Cons：无法回答首次失败原因；Stage 收尾后缺少可复查统计；P50/P95 和 failure distribution 容易被手工文案替代。
- **Option C：Stage 28 新增完整 Tool attempt 数据表和查询 API**
  - Pros：跨进程持久化和聚合完整；可以直接建设回放页面。
  - Cons：与 Stage 29 的 Trace/Replay 重复，新增 schema、保留策略和 API，扩大当前 Stage 范围。

### Decision

采用 **Option A**。

- `ToolCallResult` 保留最终顶层摘要和最多两条脱敏 attempt records。顶层至少包含 `tool_name`、`status`、派生 `success`、`result`、`error_type`、`retryable`、总 `attempt`、`retry_recovered` 和逻辑调用总 `duration_ms`。
- 每条 attempt record 只包含 1-based `attempt`、`status`、`duration_ms`、稳定 `error_type` 和 `retryable`。不得包含 args、完整 query、完整结果、异常对象、traceback、连接信息或认证数据。
- 最终重试恢复时，顶层状态为 `SUCCEEDED` 或 `EMPTY`、`error_type=None`、`retry_recovered=true`；首条 attempt record 保留最初稳定错误类型。
- 完整 `result` 只供当前工作流消费。结构化日志、现有 Agent execution payload 和未来 Trace 只保存安全投影：状态、耗时、attempt、recovery、error/fallback、result count 和 evidence IDs。
- evidence IDs 仅允许：`search_rules` 的 `chunk_id`、`load_confirmed_cases` 的 `flow_id`、`lookup_t1_context` 的匹配 `flow_id`。不得记录完整 RAG query、规则正文、历史审计意见、原始流水或 Tool 原始参数。
- Stage 28 不新增 Tool/Trace 数据表。Stage 29 复用这些稳定字段形成 TraceSpan，需要详情时按当前用户权限和 evidence ID 查询，不把敏感正文复制进 trace。
- 新增 `scripts/eval_tools.py`，从同一内存结果生成 `reports/tool_executor_evidence.json` 和 `reports/tool_executor_evidence.md`。JSON 是机器可审查事实源，Markdown 不得独立计算或手填指标。
- 证据脚本使用固定 SQLite 数据、hash embedding、本地规则集和确定性故障注入，报告各 Tool 的 outcome/error/retry 分布及 P50/P95 duration。正常与空结果调用真实本地 adapter，permission、timeout 和 recovery 使用可复现故障注入。
- P50/P95 只描述本地离线运行，不设置性能 pass gate，不表述为生产 SLA。CI 运行确定性 schema/计数测试；报告生成进入 Stage DoD，但机器差异导致的延迟变化不阻断 CI。

### Consequences

- 正面：Stage 28 能以可复查报告证明调用、失败和恢复行为；Stage 29 不需要从自由文本日志反推 Tool attempts。
- 正面：敏感业务内容不进入通用日志或未来 trace，降低跨用户泄漏和长期复制风险。
- 负面：安全投影不能单独重建完整 Tool 输入输出；排查业务详情时仍需在授权上下文中按 evidence ID 查询原始来源。
- 负面：离线 latency 受硬件、缓存冷热和本地依赖状态影响，只能作为观察基线；报告必须持续携带环境与 claim boundary。
- 约束：本决策不新增 trace 表、回放 API、前端 timeline、外部观测平台、告警系统或生产性能承诺。
