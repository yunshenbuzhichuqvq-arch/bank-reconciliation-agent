# ADR-036: SSE 交付策略与执行边界

- Status: Accepted (2026-06-12)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: api/v1/stream.py, services/stream_emitter.py, services/workflow.py(emitter 透传), services/reconciliation.py(stream_seq 跨 item), decisions/ADR-030(新能力双路径), decisions/ADR-023(事务/副作用分离), decisions/ADR-037(事件契约)

## Context

PRD §4.3 要求 SSE 实时展示 Agent 执行事件(Pre/Post Hook 状态、异常分支、RAG 检索分数、Fallback 层级、决策)。现状:`reconcile/upload` 同步批跑——`reconciliation` 把所有 item 跑到终态、落 `agent_log`(DB)+ `trace`(JSON)后才返回,执行中途无对外窗口。要「实时」必须在执行过程中串流。约束(用户切片):不引 Celery/Redis;不破坏现有同步 upload(零回归,沿用 ADR-030 双路径)。

## Options

- **A. 回放已落库 `agent_log`/`trace`(只读 SSE,不碰执行)** — Pros: 零执行风险、最简。Cons: 非真·实时(任务已在 upload 跑完才有数据),signal 弱、与 PRD「实时」偏离。
- **B. 专用 live streaming 端点 + 进程内事件发射,同步 upload 保留(采纳)** — 新增 SSE 端点(FastAPI `StreamingResponse`),把 per-item 执行的现有日志点(`workflow` 里 `agent_logs.append` 处)接事件发射器,边跑边 yield;现有同步 `upload` 原样保留=零回归。纯进程内,不引队列/Redis。
  - Pros: 真·实时、贴 PRD、高信号;双路径=银企/清算零回归;无新基础设施依赖;为后续 Vue 工作台铺事件源。
  - Cons: 执行路径要暴露「事件发射」抽象(中等改动);单 HTTP 连接内串流,长任务占用连接(本地 demo 可接受,非生产并发方案)。
- **C. 重构 `upload` 为单一流式路径** — Cons: 高回归;与「同步 upload 保留」冲突。

## Decision

采用 **B**。专用 SSE 端点 + 进程内事件发射,同步 `upload` 保留。用 `StreamingResponse`(不引 sse-starlette,手工 SSE 帧);不引 Celery/Redis。事件发射抽象接现有 `workflow` 日志点,与 `agent_log` 落库同源(见 ADR-037)。

## Consequences

- 正面:真·实时 Agent 事件流、零回归(双路径)、无新基础设施依赖、为 V1 后续前端铺事件源。
- 负面:执行路径引入事件发射抽象——技术债:发射点须与 `agent_log` 落库点一致,避免「串流事件」与「落库日志」两套口径分叉;单连接串流不适合生产高并发(生产化留 V1 后续队列/SSE-over-Redis 切片);若 live 串流被证明需大改 `workflow`,降级到 A(回放)作 fallback(本条登记)。

## Implementation Note (V1-1 收尾)

最终落地选项 B(真·实时):`api/v1/stream.py` 经 `asyncio.create_task` 后台驱动 upload、async 生成器从 `QueueEmitter` 边收边 yield(首帧 `TASK_STARTED` 早于任务完成,由 `test_stream_reconcile_returns_before_upload_finishes` 锁定)。workflow 侵入度可控(日志点机械包成 `_append_agent_log` + emitter 透传,控制流未动),**fallback(降级到 A)未触发**。seq 跨 item 全局单调由 `reconciliation` 维护 `stream_seq` + 透传 `stream_seq_start` 保证;同步 upload 走 `NullEmitter`,`stream_seq` 不落库=零回归。

> 过程坑(已修复):首版实现是 `await upload()` 跑完 + `emitter.drain()` 一次性回放,即被否决的选项 A 行为,且 e2e 测试因读 `response.text` 整流读完而测不出该降级。review 抓出后补成真·实时 + 加首帧时序断言。

残留技术债:后台驱动用 `asyncio.to_thread(lambda: asyncio.run(upload(...)))` 嵌套 event loop(为复用现有 async upload 不改它)+ UploadFile 跨线程,属反模式,生产化的 SSE-over-Redis 切片会重写。
