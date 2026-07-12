# ADR-28.2: Tool 采用三态结果并对关键证据缺失 fail closed

**Slug**: `typed-tool-outcome-and-fail-closed`
**Status**: superseded
**Date**: 2026-07-12

> Superseded by ADR-28.5。三态结果与 fail-closed 语义继续有效；T+1 持久化字段边界由
> ADR-28.5 补充并取代本条中“无需 schema 变更即可复用匹配算法”的隐含前提。

### Context

单一 `success: bool` 无法区分“调用正常完成但没有业务结果”和“依赖、权限或执行失败”。当前
RAG 异常会被压成空检索，历史案例查询直接返回列表，T+1 candidate 则在上传分类阶段从 DataFrame
预先计算；这些差异会让工作流和未来 Trace 错误解释失败率与 fallback 原因。

其中 `lookup_t1_context` 目前不是可独立调用的只读能力：`ExceptionRouter` 在持久化之前计算
`t1_candidate`，后续工作流只消费缓存结果。仅包装该字段无法证明任务归属、跨用户隔离、查询超时或
失败语义。

### Options Considered

- **Option A：`SUCCEEDED / EMPTY / FAILED` 三态 + 真实租户限定 T+1 查询（采纳）**
  - Pros：正常无结果与故障可被稳定区分；三个工具可以使用同一结果信封；T+1 查询能真实验证租户隔离，并复用现有确定性匹配规则。
  - Cons：BC-R003 路径增加一次持久化流水读取；工作流必须为每个 Tool 明确 `EMPTY` 与 `FAILED` 的不同收口行为。
- **Option B：只保留 `success: bool`，T+1 Tool 包装预计算 candidate**
  - Pros：实现最少；几乎不改变现有数据流。
  - Cons：空结果与失败继续混淆；T+1 Tool 只是内存字段读取，无法证明权限、超时或真实查询契约。
- **Option C：所有空结果和错误都通过异常表达**
  - Pros：调用方只处理成功结果或异常；控制流直观。
  - Cons：正常业务无命中被错误计为系统故障；容易触发无意义重试，并破坏 RAG 无证据转人工的业务语义。

### Decision

采用 **Option A**。

- `Tool Outcome` 的权威状态只允许 `SUCCEEDED`、`EMPTY`、`FAILED`。`success` 是由状态派生的兼容字段，不得独立赋值：`SUCCEEDED/EMPTY` 为 `true`，`FAILED` 为 `false`。
- `EMPTY` 表示 Tool 正常执行但没有业务结果，不设置 `error_type`、不触发重试。`FAILED` 必须携带稳定 `error_type` 和 `fallback_reason`。
- 三个 Tool 分别定义 Pydantic 输入和输出 schema；底层返回必须先通过输出 schema 校验，再进入统一结果信封。
- `lookup_t1_context` 对已持久化流水执行真实只读查询，租户范围来自 `Tool Context`。上传分类和 Tool 查询复用同一个确定性 T+1 匹配规则，不复制或改写业务算法；预计算 candidate 不再作为 Tool 的事实来源。
- `search_rules=EMPTY` 时直接进入 `PENDING_HUMAN`，不得在无 evidence 时继续调用 AuditAgent；`search_rules=FAILED` 同样转人工。
- `load_confirmed_cases=EMPTY` 表示低置信度 L1 没有 L2 案例支撑，直接进入 `PENDING_HUMAN`；`FAILED` 同样转人工，不继续消耗下游 Tool 或 LLM。
- `lookup_t1_context=EMPTY` 是“真实查询后没有 T+1 匹配”的业务结果，继续既有无 T+1 candidate 路径；`FAILED` 则直接进入 `PENDING_HUMAN`。
- 除 ADR-28.3 声明需要上抛 ARQ 的基础设施异常外，`FAILED` 都在当前 item 内安全收口，且停止该 item 的后续 Tool 与 LLM 调用。
- 完整 Tool `result` 只在当前工作流内存中传递，不进入通用结构化日志或未来 Trace；持久观测只保存 ADR-28.4 定义的安全投影。

### Consequences

- 正面：业务无结果、权限拒绝和依赖故障具有不同且可查询的语义；RAG 不可用不再被统计为正常无命中。
- 正面：缺失关键证据时不再继续生成 LLM 结论，保持 RAG 无 evidence 转人工和财务决策 fail-closed 红线。
- 负面：RAG 无命中和 L2 无历史案例路径会减少当前存在但最终仍转人工的 LLM 调用，内部调用次数与旧行为不同，相关测试和指标需要同步。
- 负面：真实 T+1 查询增加一次数据库读取，并要求分类路径和查询路径共享同一匹配规则；共享边界若设计不当可能产生耦合。
- 约束：本决策不改变三个底层能力的业务算法，不新增自动处理路径，也不把 `EMPTY` 当作可重试错误。
