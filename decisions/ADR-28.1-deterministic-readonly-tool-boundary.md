# ADR-28.1: 固定只读 Tool 采用确定性执行边界

**Slug**: `deterministic-readonly-tool-boundary`
**Status**: accepted
**Date**: 2026-07-12

### Context

当前工作流分别直接调用 RAG retriever、已确认历史案例查询和上传阶段计算得到的 T+1
候选，三种能力没有统一的 schema、调用上下文、权限校验、错误语义和观测边界。Stage 29
计划把 Tool、RAG、Agent、Guard 和 Fallback 投影为统一 `TraceSpan`，因此 Stage 28 必须先冻结
Tool 的名称、信任边界和稳定执行契约。

本项目是财务对账 Agent。工具选择必须继续由确定性 `exception_branch` 和 fallback 状态驱动，
不能因为引入统一执行器而扩大 LLM 的权限或增加有副作用能力。

### Options Considered

- **Option A：固定 registry + 确定性 `ToolExecutor`（采纳）**
  - Pros：用最小边界统一 schema、权限、超时、错误和观测；保留现有工作流控制权；三个真实能力可以被一致测试，并为 Stage 29 提供稳定输入。
  - Cons：工作流需要把当前直接调用迁移到统一信封；静态 registry 不支持运行时扩展，增加工具时需要显式修改代码和测试。
- **Option B：使用 LLM function calling 或自主 Tool 选择**
  - Pros：模型可以根据上下文灵活选择和组合工具；更接近通用 Agent 工具平台。
  - Cons：扩大不可预测分支和权限面；难以证明财务场景的 fail-closed；需要额外治理 prompt、工具选择、循环上限和副作用，不符合本 Stage 的最小范围。
- **Option C：保留三个直接调用，只补充局部日志和异常处理**
  - Pros：代码改动最少；不需要新的统一入口。
  - Cons：schema、权限和错误语义继续分散；Stage 29 仍需从不同调用形态反推统一 span，无法形成稳定 Tool contract。

### Decision

采用 **Option A**。

- Tool 固定为 `search_rules`、`load_confirmed_cases`、`lookup_t1_context`，不得在 Stage 28 增加写工具、动态插件或远程工具市场。
- 使用轻量静态 registry 和统一 `ToolExecutor.execute(name, args, context)` 语义；registry 显式绑定工具名、输入/输出 schema、执行适配器、超时策略和允许场景。
- Tool 只能由确定性工作流选择。LLM 可以消费 Tool 结果，但不得选择、组合或自主调用 Tool。
- `Tool Context` 由已认证请求或可信 ARQ job payload 建立，至少承载 `user_id`、`task_id`、`flow_id`、`scenario_type` 和 `exception_branch`。Tool 参数不得携带或覆盖身份与资源归属字段。
- 所有 Tool 调用前先验证任务归属；任务不存在与不属于当前用户使用相同拒绝语义，避免泄露资源是否存在。流水查询必须按 `user_id + task_id + flow_id` 限定。
- registry 使用场景 allowlist：`search_rules` 只允许已支持的对账场景；`load_confirmed_cases` 只允许低置信度 L2 fallback；`lookup_t1_context` 只允许 `BANK_CLEARING + BC-R003`。
- Tool 不新增独立 HTTP API，也不改变现有认证 scheme、业务路由或底层业务算法。

### Consequences

- 正面：Tool 的身份、权限、输入输出和调用控制权变成显式契约；未知名称、非法参数和越权上下文可以在进入底层能力前 fail closed。
- 正面：Stage 29 可以依赖固定工具名和稳定观测字段，不需要再次改变 Tool API。
- 负面：静态 registry 有意放弃动态扩展能力；未来新增 Tool 必须修改 registry、schema、场景策略和测试。
- 负面：所有内部调用都需要构造可信 `Tool Context` 并验证任务归属，会增加少量查询与集成代码。
- 约束：本决策不建设 MCP Server、通用 Agent SDK、工具市场、L2 写库工具、补偿事务或 LLM 自主执行机制。
