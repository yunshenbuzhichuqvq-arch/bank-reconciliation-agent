# ADR-020: workflow 分支→Agent 路由泛化与零回归保障

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: services/workflow.py(TRACE_BRANCHES / run_item), services/reconciliation.py, agents/trace_agent.py, agents/audit_agent.py(trace_context), decisions/ADR-007, decisions/ADR-017

## Context

`workflow.run_item` 写死银企特判:`TRACE_BRANCHES = {"BE-R005", "BE-R006"}` 触发 TraceAgent;`exception_branch == "BE-R004"` + `REVERSAL_HINTS` 触发 ExtractionAgent。清算 BC-R003 需 TraceAgent(T+1 追溯,承 ADR-017),BC-R001 走 RAG+AuditAgent。若沿用写死集合,BC-* 不会触发既有 Agent 路由。同时必须保证银企行为零漂移(承 2a-2 零回归原则)。

## Options

- **A. 分支→Agent 路由集合化(采纳)** — 把「哪些分支触发 TraceAgent / ExtractionAgent」提为按分支的声明式集合;BE-* 映射保持不变,新增 BC-R003→TraceAgent。Pros: 银企零漂移、清算复用同一编排、可扩展。Cons: 引入一层路由配置(新「真相源」)。
- **B. 在 run_item 里并列追加 BC-* 的 if 分支** — Pros: 最少抽象。Cons: 硬编码继续膨胀、双轨味重。
- **C. 每场景独立 workflow** — Cons: 编排复制,违通用引擎。

## Decision

采用 **A**。`TRACE_BRANCHES` 扩为 `{"BE-R005", "BE-R006", "BC-R003"}`,reversal 特判仍限 `BE-R004`(清算本 stage 无 ExtractionAgent 分支)。三级 Fallback(ADR-007)与 L3 TraceAgent 链不变,仅「入口分支集合」泛化。BC-R003 命中时 T+1 候选经 `state.t1_candidate` 透传 TraceAgent(`cutoff_t1_context` 入参)并入 AuditAgent `trace_context`,驱动「已配对 / 待补齐」叙述。缺省 / 银企路径行为与 2a-2 完全一致。

## Consequences

- 负向:路由集合(`TRACE_BRANCHES`)成为新「真相源」,新增分支须同步登记否则不触发对应 Agent。
- 银企既有测试全绿作为零回归门禁(DoD 含全量 `uv run pytest`)。
- 清算 BC-R003 复用 TraceAgent + L3 Fallback,无需新增 Agent。
