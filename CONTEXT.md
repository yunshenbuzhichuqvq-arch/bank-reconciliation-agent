# Bank Reconciliation Agent

本上下文定义对账 Agent 运行时契约中的项目专用术语，避免把受控业务能力与 LLM 自主工具调用混为一谈。

## Language

**Tool**:
由确定性工作流选择、在固定 registry 中注册并通过统一执行边界调用的只读业务能力。LLM 可以消费 Tool 结果，但不能选择、组合或自主调用 Tool。
_Avoid_: LLM function calling, autonomous tool, plugin

**T1 Context**:
针对当前用户、对账任务和清算流水，从已持久化流水中重新查询并按现有 T+1 匹配规则确定的次日到账上下文。
_Avoid_: precomputed T1 candidate, cached upload candidate

**Tool Outcome**:
一次 Tool 调用的业务结果状态，仅允许 `SUCCEEDED`、`EMPTY` 或 `FAILED`；正常无结果属于 `EMPTY`，不属于执行失败。
_Avoid_: success-only result, not-found error

**Tool Context**:
由已认证请求或可信任务载荷建立的 Tool 调用上下文，携带当前用户、对账任务、流水、场景和异常分支；业务参数不得覆盖其中的身份与归属信息。
_Avoid_: caller-supplied user ID, tool arguments as authorization
