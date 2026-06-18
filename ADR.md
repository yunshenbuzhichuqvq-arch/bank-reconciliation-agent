# Fix: SSE Live Emitter Lifecycle — Architectural Decisions

> 单条聚焦决策。本 fix 只解决 `start-live → events` 两段式 SSE 的竞态 404,不引入新功能,故 1 条 ADR(非 ≥3)。

## ADR-050: SSE 实时事件 emitter 生命周期(保留期 + 完成标记)
**Slug**: `sse-emitter-lifecycle`
**Status**: accepted
**Date**: 2026-06-18

### Context
两段式 SSE 看板(ADR-045 background start + by-taskId SSE):
- `POST /{task_id}/start-live`:`register(task_id)` 注册 emitter → `asyncio.create_task(_run_live_task)` fire-and-forget → 立即返回 200(reconciliation.py:259-261)。
- 后台 `_run_live_task`:`_emit_live_progress`(一次 DB 查询)→ emit(progress)→ emit(task_done)→ `finally: unregister(task_id)`(reconciliation.py:291)。
- `GET /{task_id}/events`:`get_emitter(task_id)`,为 None 即 404(reconcile.py:77-79)。

真实浏览器时序下,浏览器在 start-live 返回**之后**才订阅 events,而后台任务只做一次轻量 DB 查询 + 两次内存 emit,几毫秒内跑完 `finally` 销毁 emitter。于是 events 订阅时 emitter 常已不存在 → `get_emitter` 返回 None → **404,几乎稳定复现**。看板实时链路(主链路最后一步)因此不通。

根因:**emitter 生命周期由生产者(后台任务)按"自己干完"单方面销毁,与消费者(events 订阅)的连接时机解耦,形成竞态。** 现有单元测试均以"手动 register / start 后同步复用引用 / 不调 events"绕过了真实时序,故全绿但线上失败(e2e 盲区)。

本决策修正 ADR-045 的**实现层生命周期**,不改变其两段式架构方向(非 supersede)。

### Options Considered
**A. 消费者驱动工作流**:start-live 只标记 running;events 连上后才驱动后台发事件。
- Pros:从根上消除竞态;无需 TTL。
- Cons:改 start-live/events 职责分工,前端可能需适配;重连 / 多消费者语义变复杂;改动面最大。

**B. emitter 保留期 + 完成标记(选定)**:后台结束不立即 unregister,标记 finished 并保留 queue 缓冲;events 消费完或 TTL 超时回收。
- Pros:保留两段式 API,前端零改动;晚连接也能 drain 到缓冲事件,不丢事件;改动集中在 registry 生命周期。
- Cons:需 TTL 防内存泄漏;"后台结束即清理"旧契约失效(需改测试);并发二次订阅边界需定义。

**C. events 缺 emitter 时回退 DB 回放**:emitter 不存在时不 404,从任务最终状态回放 progress/done。
- Pros:改动最小;已完成任务也能看。
- Cons:回放非真·实时;单独使用是掩盖而非修复竞态。

### Decision
选 **B**。保留现有两段式 API 与"实时"语义、对前端透明、事件不丢,且直接消除竞态根因(过早销毁)。**C 作为可选 follow-up 兜底**(已完成任务回放),不在本次必做;A 改动面大且涉及前端,留待未来若需"纯连接驱动"再议。

### Consequences
正向:
- 看板实时链路在真实浏览器时序下不再 404;晚连接的 events 也能 drain 到 progress + task_done。

负向 / 成本:
- emitter 不再随后台结束即销毁 → **必须 TTL 兜底回收**防泄漏(finished 后约 60s,或消费完即回收;惰性 sweep)。
- 旧契约"后台结束即清理 emitter"失效 → `test_start_live_marks_running_emits_task_progress_and_cleans_registry`(:63-64)清理断言需更新为新契约(有意变更,非破坏)。
- 二次订阅边界:emitter 被消费 / 回收后再订阅仍 404;若需"已完成可重看",叠加 C(follow-up)。
- registry 从纯 dict 增加 created_at / finished 状态与惰性 sweep。

可观测(防回归历史 SSE 静默降级 gap):events 端点对"命中 live emitter"路径打结构化日志;未来若叠加 C,必须显式区分"实时 vs DB 回放",不得静默降级。
