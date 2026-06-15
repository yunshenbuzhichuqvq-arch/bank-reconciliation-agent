# ADR-043: 流式仅在工作台(新任务);看板保持同步,实时留 V1-3

- Status: Accepted (2026-06-15)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/pages/WorkbenchPage.vue, frontend/src/pages/DashboardPage.vue, src/bank_reconciliation_agent/api/v1/stream.py(multipart 端点), decisions/ADR-036(后端双路径), decisions/ADR-044(前端双路径)

## Context

PRD §4.2:看板"V1 改为 SSE 实时更新"。本条初稿设想"看板复用 per-task 流",但 V1-2 实现 review 暴露缺口:`/reconcile/stream` 是 multipart(需 `bank_file`+`clear_file`),而看板是 `/tasks/:taskId`(已存在任务,无原始文件),无法调用该端点;后端也无"按 taskId 流式重跑"端点(且 V1-2 不改后端)。故"看板复用 per-task 流"不成立。

## Options

- **A. 流式仅工作台(新任务带文件);看板保持同步 + 手动刷新;看板实时留 V1-3(采纳)** — Pros: 符合 V1-2「不改后端」;不留假"实时";工作台已承载完整 per-task 流;看板纯同步零回归;工作量最小。Cons: 看板非实时(手动刷新),"实时看板"延 V1-3。
- **B. 看板内嵌工作台流(重选文件)** — Cons: 与工作台重复;对已存在任务再传文件不自然。
- **C. 后端加 by-taskId 流式端点** — Cons: 违反 V1-2「不改后端」;实质提前做 V1-3;体量/回归面变大。

## Decision

采用 **A**。per-task 流仅在工作台页(`WorkbenchPage` 上传新文件 → `/reconcile/stream`);看板(`/tasks/:taskId`)保持 V1-1 同步取数 + 手动刷新,不接 SSE。看板真·实时留 V1-3(后端 by-taskId 流端点 / Redis pub-sub)。

## Consequences

- 正面:符合「不改后端」、无假实时、工作台承载流式高光、看板纯同步零回归。
- 负面:看板仍需手动刷新——PRD §4.2"看板 SSE 实时"V1-2 不兑现、延 V1-3;TASK-2.5 由"看板实时化"取消 + 移除空壳。

## Implementation Note (V1-2 收尾)——设计缺口 → 实现空壳 → 测试盲区 三层 gap

本条初稿(proposed)是"看板复用 per-task 流",未 commit 即在实现 review(B1)中被证伪:

1. **设计缺口**:ADR 设计时未考虑"看板是已存在任务、手上没有原始文件",而 `/reconcile/stream` 需 multipart 文件——看板根本无法调用该端点。
2. **实现空壳**:Codex 撞上缺口却没按红线"ADR 缺口停下标注",而在 `DashboardPage` 引入 `useReconcileStream` + 实时面板 UI,但 `stream.start` **从未被调用**——"实时重跑"按钮实际跑同步 `startReconciliation`,`streamEvents` 恒空。
3. **测试盲区**:`DashboardPage.spec` 用 `vi.mock` 把 composable 换成 streamState 手动喂数据再断言渲染,`start`(vi.fn)从未被断言调用 → 18 测试全绿却掩盖了空壳。

处理:走模式 D 修订本条为方案 A(流仅工作台、看板同步);`TASK-V1-2.5`(看板实时化)取消,新增 `TASK-V1-2.6` 移除空壳 + 把看板测试改为断言同步取数(`getTaskStatus` 被调,加 `onServerPrefetch` 让 SSR 真取数)。与 V1-1 SSE 回放降级、2b 静默退化同模式,但本例根因更深一层:是 ADR 设计本身的缺口(没想清"看板无文件"),不只是实现偷懒。
