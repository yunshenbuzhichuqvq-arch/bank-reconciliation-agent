# ADR-021: Hook 链建模为 plain-Python 双挂载点管线

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: services/hooks.py, services/workflow.py(run_item / memory_hook / _apply_post_hooks), services/reconciliation.py(upload / start), api/dependencies.py, decisions/ADR-006, decisions/ADR-025

## Context

MVP-2b 要把散落的校验/路由收敛为统一 Hook 链(PRD §8 六件套:Auth/Validation/Memory → Schema/Constraint/Decision)。现状:鉴权在 api/dependencies.py(仅校验 X-User-ID 值,未做 user_id↔task_id 归属);字段/类型/金额精度校验散在 reconciliation.upload;逐笔执行在 workflow.run_item;无 Schema/Constraint/Decision 概念。需要不依赖图引擎的 Hook 抽象,并定其挂载位置。ADR-006 已推迟 LangGraph,本 stage 续推迟(ADR-025)。

## Options

- **A. plain-Python 可组合 callable + 双挂载点(采纳)** — Pre-Hooks(Auth/Validation)挂请求入口边界,失败 403/400;逐笔 Hooks(Memory→Schema→Constraint→Decision)挂 run_item 内。Pros: 零新依赖、契合 ADR-006、与现有分层一致、Post-Hook 紧贴 AuditDecision 输出。Cons: 两挂载点需 spec 画边界。
- **B. 单一直线管线(含 Auth)整体包 run_item 外** — Pros: 概念统一。Cons: Auth/Validation 要返 HTTP 码、塞逐笔循环不自然且与现有鉴权重复一层。
- **C. LangGraph 节点建模 Hook** — Pros: 与 PRD 字面一致。Cons: 依赖 ADR-006 毕业(本 stage 推迟);2b-1 退化为纯重构、零新增能力、高回归。Rejected。

## Decision

采用 A。Hook = plain-Python callable,双挂载点。MemoryHook 在 2b-1 为占位降级(跳过记忆,仅 System Prompt),2b-2 接 MemoryManager.build_context()。AuthHook 在 require_demo_user 基础上补 user_id↔task_id 归属校验(强化「业务查询按 user_id 过滤」红线),归属不符 403。Hook 熔断器(PRD §8.2.2)推迟 2b-2(本 stage MemoryHook no-op、RAG 自带 fallback,无需熔断的外部依赖)。

## Consequences

- 正面:零依赖、低风险、立起 Hook 抽象供 2b-2/2b-3 挂载;节点/状态契约更稳,降未来 LangGraph 平移成本。
- 负向:双挂载点需 spec 显式画边界,防后人把 Auth 塞进 Post 链;MemoryHook 占位是半成品,2b-2 不补则记忆能力为空。
- 落地补遗:auth_hook 对不存在的 task 返回 403(原 start 为 404),为归属校验副作用,留待与 main 同步时确认是否保留。
