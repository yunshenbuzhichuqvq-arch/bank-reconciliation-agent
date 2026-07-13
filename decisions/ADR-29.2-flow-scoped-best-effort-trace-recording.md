# ADR-29.2: 使用显式 flow-scoped recorder 并隔离 Trace 写入失败

**Slug**: `flow-scoped-best-effort-trace-recording`
**Status**: accepted
**Date**: 2026-07-13

### Context

当前工作流是 plain-Python 同步 flow，Tool、Agent 与 Guard 由确定性代码顺序调用。Stage 28 已冻结
`ToolCallResult` 的安全投影和 bounded attempts，Stage 26 已冻结 LLM transport retry、structured
repair、token 与 fallback summary。Stage 29 需要把这些稳定事实投影为统一 spans，同时不得改变
Tool Executor、Agent 或 provider 的公共 contract。

`ReconciliationService` 目前在 `run_item()` 外层捕获允许的 Agent 处理异常，并安全构造
`PENDING_HUMAN` fallback state。如果 recorder 只在 `run_item()` 内部创建，异常抛出后外层无法补全
Fallback 和根 span。另一方面，若每个 span 结束即同步写数据库，Trace 基础设施会向核心工作流引入
大量小事务和新的失败耦合。

### Options Considered

- **Option A：外层显式 flow-scoped recorder + 内存收集 + 核心事务后按 flow 批量写（采纳）**
  - Pros：生命周期和租户上下文明确；外层 fallback 可补全 Trace；不改变 Tool/Agent API；Trace 写入
    与业务事务隔离；一次 flow 不会留下半条 timeline。
  - Cons：进程在 flow 完成并落库前崩溃时会丢失该 flow 的未持久化 spans；需要在 workflow 调用
    边界显式包裹节点。
- **Option B：使用全局 singleton/contextvars 自动传播 recorder，并在 span 结束时立即写库**
  - Pros：调用点代码较少；中途崩溃前可能已保存部分 spans。
  - Cons：并发 task 容易串上下文；Trace DB 故障进入主流程；会产生半条 timeline 和大量小事务；
    测试隔离困难。
- **Option C：执行完成后从 agent log 与 SSE 事件反推 Trace**
  - Pros：不需要在工作流节点增加 recorder。
  - Cons：现有日志字段与语义不完整；无法可靠恢复 parent-child、开始顺序、未发出的事件和 Tool/LLM
    attempt 摘要；会产生看似完整但并非执行事实的 Trace。

### Decision

采用 **Option A**。

- `ReconciliationService` 在每个 eligible flow 进入工作流前创建 `TraceRecorder` 和根
  `WORKFLOW` span，并将 recorder 显式放入当前 `ReconciliationState`。
- `run_item()` 只记录 Route、Tool、Agent 和 Guard 节点，不拥有 recorder 的最终关闭权。单元测试
  直接调用 `run_item()` 时可显式传入测试 recorder；未传入时使用 no-op recorder，不产生数据库
  副作用。
- Workflow 在现有调用边界外使用 recorder/context manager。不得把 recorder 注入 prompt、
  Stage 28 `ToolExecutor.execute()`、Agent 公共 contract 或 provider API。
- Tool span 从 `ToolCallResult` 与 `safe_tool_projection()` 读取稳定状态、attempt、recovery、
  error/fallback、result count 和 evidence IDs；不得保存 Tool args/result。
- Agent span 从现有 `last_llm_summary/last_llm_result` 投影 model、实际 token、cache、attempt、
  structured repair 与稳定 failure/fallback；不得保存 prompt 或模型正文。
- 已被现有 `AGENT_PROCESSING_ERRORS` 捕获并转人工的异常，由外层记录 `FALLBACK`、关闭根 span，
  并保留完整 Trace。未被业务边界捕获、导致整个 task 失败的基础设施异常不得伪造成已安全完成的
  flow Trace；Stage 25 task failure 仍是权威状态。
- recorder context manager 不吞业务异常。节点异常先将当前 span 标为 `FAILED`，再按原有 workflow
  contract 继续传播或 fail closed。
- recorder 自身异常不得改变业务控制流。当前 Trace 被禁用并产生安全 warning；不得为了补 Trace
  修改业务结果或异常类型。
- flow 完成后先生成不可变、通过结构不变量校验的 snapshot。核心 ledger、queue、task stats 事务
  成功后，Trace 使用独立事务按一个 flow 批量写入 `t_trace_span`。
- 一个 flow 的 Trace 要么整批写入，要么完全不写。Trace 写入失败不得回滚核心业务事务、修改任务
  终态或从 agent log 临时拼装 fallback Trace。
- 每个失败批次将 process-local `trace_write_failure_count` 加 1，并输出结构化 warning；成功批次
  增加 `trace_write_success_count`。counter 的 `source` 固定为 `runtime_memory`，不得宣称跨 worker
  聚合。
- warning 只允许记录 `task_id`、`flow_id`、`trace_id`、稳定错误类型和预计 span 数，不记录 SQL、
  traceback、连接信息或 span payload。
- 现有 structlog workflow context 的 `trace_id` 改为真实 execution `trace_id`，并单独保留
  `task_id + flow_id`。logging contextvars 只用于日志关联，不承担 recorder 传播或业务控制。
- 现有 context-free Tool attempt logger 保持不变，不合并请求级 `user_id/trace_id`；Tool span 仍由
  workflow 通过安全投影生成。
- `TraceAgent` 保留现有名称和业务职责。文档必须明确 Business `TraceAgent` 与 Execution Trace
  的区别；Stage 29 不重命名 Agent、prompt 或相关历史测试。
- Stage 29 不承诺在进程于 flow 执行中崩溃时恢复未落库的部分 spans，也不建设 durable streaming
  tracing 或跨线程 recorder propagation。

### Consequences

- 正面：Trace 生命周期与业务 flow 一一对应，外层错误收口也能生成真实 Fallback Trace。
- 正面：数据库或 recorder 故障不会反向破坏金额、状态、权限或核心业务事务。
- 正面：Stage 26/28 的稳定 attempt、token 和 evidence contract 被复用，不需要修改其公共接口。
- 负面：持久化前的进程崩溃会丢失当前 flow Trace；本 Stage 只保证已完成 flow 的 batch persistence。
- 负面：process-local counter 不能提供 backend/worker 集群汇总，需要依赖结构化日志定位具体进程。
- 约束：本决策不引入异步 tracing framework、消息队列、后台 flush worker、Prometheus 或新的
  resilience 依赖。
