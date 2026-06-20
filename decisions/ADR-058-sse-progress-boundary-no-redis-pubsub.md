# ADR-058: SSE 实时进度边界 —— 不引 SSE-over-Redis,维持 DB 快照推送

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/live_registry.py(不改), src/bank_reconciliation_agent/services/reconciliation.py(start_live/_run_live_task 不改), decisions/ADR-045(start-live 推 DB 快照), decisions/ADR-050(emitter 进程内 registry、events 禁回放红线), decisions/ADR-057(异步化对象)

## Context

对账挪到 ARQ worker(独立进程)后,worker 执行中的细粒度进度若要推给前端,需跨进程通道(Redis pub/sub),因为 emitter registry 是 web 进程内单进程内存对象(ADR-050)。但现有 SSE 看板语义本就是"worker 无关":start-live 在 web 进程查 DB emit 最终快照(ADR-045 校正语义)。

## Options Considered

- **A. 维持 DB 快照语义,不引 SSE-over-Redis(采纳)** — worker 跑完落库;前端在任务转 `UPLOADED` 后走现有 start-live 推最终快照;worker 执行中前端只见 `QUEUED/RUNNING` 任务状态(轮询 status),无中途逐帧进度。
  - Pros:进程内 emitter 链路(stage-fix 刚修通)零触碰,不碰 ADR-050 红线;回归面最小;延续 ADR-045"不引 SSE-over-Redis"切片。
  - Cons:worker 执行中无逐帧实时进度(实时性仍是"状态 + 完成快照",非过程)。
- **B. SSE-over-Redis pub/sub** — worker emit 真实进度,经 Redis 广播,web 进程 events 端点转发。
  - Pros:兑现 ADR-045/050 登记的 SSE-over-Redis 债,真·跨进程实时进度。
  - Cons:范围大;直接改动刚修通的红线 SSE 链路,回归高;需同时落地 ADR-050 deferred 的"命中/404 + 实时 vs 回放"结构化日志(其红线前置条件),进一步放大 stage。
- **C. 前端轮询任务状态** — 不做 SSE 进度,前端轮询 status 到终态。
  - Pros:最简。Cons:与既有 SSE 看板并存显冗余。

## Decision

采用 **A**。SSE-over-Redis(B)显式划为 backlog,继续挂账(不恶化、不偿还);本 stage 不触碰 ADR-050 进程内 emitter 红线链路。

## Consequences

- 正面:异步化与现有 SSE 解耦,回归可控;红线链路不动。
- 负面:worker 执行期前端实时性弱(状态级,非逐帧);ADR-045/050 的 SSE-over-Redis 技术债继续存在。本 ADR 显式登记其触发条件:未来做 worker 逐帧进度时,必须连带落地 ADR-050 deferred 的"命中/404 + 实时 vs 回放"结构化日志。
