# ADR-041: 前端流式状态——composable,不引 Pinia

- Status: Accepted (2026-06-15)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/composables/useReconcileStream.ts, frontend/src/api/stream.ts(ADR-040), decisions/ADR-043(看板不消费本 composable)

## Context

工作台要维护一串实时事件(events)+ 当前任务终态(result)+ 连接状态(idle/streaming/done/error)。现有 app 没有 Pinia(状态在组件/composable,如 `useTheme.ts`)。架构 §2.1 提过 Pinia 但未落地。

## Options

- **A. composable `useReconcileStream`(采纳)** — 返回 reactive events/status/result/error + start/abort;状态生命周期同页面。Pros: 遵循现有无-Pinia 模式;单页局部状态无需全局 store;零新依赖;可独立单测。Cons: 状态不跨页面共享(本 stage 不需要)。
- **B. 引 Pinia 建 stream store** — Pros: 全局可共享、devtools。Cons: 为单页状态引全局依赖(YAGNI);现有 app 无 Pinia,引入是架构面新增。

## Decision

采用 **A**。`useReconcileStream` 持有 events/status/result/error(readonly 暴露)+ `start`/`abort`,内部用 ADR-040 的 fetch+流解析。不引 Pinia。

## Consequences

- 正面:遵循现有模式、零新依赖、状态隔离可测。
- 负面:若后续多页面需共享流式状态,composable 不够,届时再引 Pinia。

## Implementation Note (V1-2 收尾)

`useReconcileStream` 返回 readonly refs + `start(params)`/`abort()`;`start` 内建 `AbortController`,onEvent push、onDone 写 result + status=done、onError 写 error + status=error;abort → status=idle。`useReconcileStream.spec.ts` 覆盖事件累积 / 错误态 / abort。**当前唯一消费方是 `WorkbenchPage`**——看板原计划复用(初稿 ADR-043),但 ADR-043 修订后看板不接流(见 ADR-043 Implementation Note),故 composable 不被看板使用。
