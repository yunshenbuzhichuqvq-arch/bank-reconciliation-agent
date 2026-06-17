# ADR-046: 看板进度事件契约——扩展 ADR-037,新增任务级进度/统计事件

- Status: Accepted (2026-06-16)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/schemas/stream.py, decisions/ADR-037(SSE versioned 事件契约), decisions/ADR-042(前端事件契约 TS 投影)

## Context

ADR-037 已定义 `stream.py` 的 SSE 事件契约(versioned schema):面向工作台的 per-item / agent_decision / item_done 等单流水 Agent 执行细节。

看板要展示的是任务级进度与聚合统计(已处理 N/总 M、`auto_fixed`/`pending_human`/异常分布的实时变化),粒度不同。需决定:看板事件扩展现有契约,还是另起一套。

## Options

- **A. 扩展 ADR-037 契约,新增任务级事件类型(采纳)** — 在现有 versioned schema 上加 `TASK_PROGRESS`(任务级计数/统计快照)事件;与 per-item 事件同源(同一 emitter、同一 seq 序列、同一 schema 版本演进)。看板按 `event_type` 过滤渲染任务级事件、忽略 per-item;工作台两类都渲染。
  - Pros: 单一契约 / 单一 Schema 符合性测试入口;口径一致;前端复用现有事件解析(ADR-042 TS 投影);事件与 `agent_log` 落库口径一致(延续 ADR-036 同源原则)。
  - Cons: 契约承载两种粒度,schema 略膨胀;需 schema 版本号向后兼容演进。
- **B. 看板另起独立事件契约/端点 schema** — Pros: 看板/工作台契约解耦。Cons: 两套 schema / 两套符合性测试、口径易分叉、前端两套解析。
- **C. SSE 直接推完整 status 快照 JSON(不走结构化事件)** — Pros: 最简。Cons: 脱离 ADR-037 versioned schema 体系、无法纳入 Schema 符合性测试、与工作台不一致。

## Decision

采用 A:扩展 ADR-037,新增任务级进度/统计快照事件,同源同契约,schema 版本向后兼容演进(V1-2 工作台事件不变)。

## Consequences

- 正面:单一事件契约、口径一致、复用前端 TS 投影与 Schema 符合性测试。
- 负面:契约承载两种粒度需清晰文档化(哪些 `event_type` 给看板 / 哪些给工作台);schema 演进须有向后兼容断言,防止 V1-2 工作台回归。
