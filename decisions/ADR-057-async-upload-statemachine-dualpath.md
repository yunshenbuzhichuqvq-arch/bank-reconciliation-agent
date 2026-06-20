# ADR-057: 异步化对象、任务状态机与回归边界

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/reconciliation.py(upload_async / _execute_reconciliation / run_reconciliation_job), src/bank_reconciliation_agent/api/v1/reconcile.py(/upload-async), src/bank_reconciliation_agent/services/task.py(replace_task status 参数), decisions/ADR-045(start_live 推 DB 快照、emitter 单进程), decisions/ADR-036(双路径 SSE), decisions/ADR-058(SSE 进度边界), decisions/ADR-059(幂等)

## Context

核实后:重活 100% 在 `upload`,`start_live` 只读 DB 快照(零计算)。故异步化对象是 **upload 的对账执行**,不是 `start_live`(避免重蹈 ADR-045 初稿"误判 start 同步阻塞"的覆辙)。异步化后 upload 返回时对账未跑完,任务不再处于 `UPLOADED` 终态;而 `start_live` 现有前置校验 `task.status != "UPLOADED" → 409`(reconciliation.py:254-255)依赖"upload 同步完成"假设。同时存在两条同步 upload 路径:`POST /reconcile/upload`(emitter=None)与 stream.py 的 multipart 边算边推(ADR-036)。

## Options Considered

**主决策:回归边界**
- **A. 双路径零回归(采纳)** — 保留现有同步 `upload`(及 stream.py multipart)端点语义不动(现有测试/前端/演示零回归),新增 `POST /reconcile/upload-async`:存盘 + 建任务(status=`QUEUED`)+ enqueue ARQ job + 立即返回 task_id;worker 跑对账落库、终态翻 `UPLOADED`/`FAILED`。
  - Pros:对齐 ADR-045/036/044 一贯"双路径零回归"哲学;现有同步链路与 SSE 看板语义不破坏;异步为增量入口,风险面可控。
  - Cons:两套 upload 语义并存,概念重复;前端需新增异步上传流程分支。
- **B. 全量改异步** — `upload` 一律改入队立即返回,现有同步调用方/测试/前端适配。
  - Pros:单一执行模型,无概念重复。
  - Cons:破坏现有 "upload 返回即对账完成" 契约,回归面大(波及 stream.py、看板 start_live 时序、大量同步测试);违背切片纪律。

**子决策:任务状态机扩展**
- 现状态:`UPLOADED → AI_RUNNING → COMPLETED/FAILED`。
- 扩展:`QUEUED`(入队待跑)→ `RUNNING`(worker 执行对账)→ `UPLOADED`(对账完成,语义对齐现状"upload 后")→ 复用现有 `start-live → AI_RUNNING → COMPLETED`。异步只在前段插入 QUEUED/RUNNING,后段 SSE 快照链路完全不变。

## Decision

采用 **A(双路径零回归)**(2026-06-20 用户拍板,排除全量改异步 B 的高回归):保留同步 upload + stream.py 不动,新增 `/reconcile/upload-async`;在 upload 前段插入 `QUEUED/RUNNING`,worker 落库后归于现有 `UPLOADED`,start-live/SSE 后段零改动。

## Consequences

- 正面:现有同步 upload + SSE 看板链路零回归;异步入口隔离演进;worker 落库后归一到现有 `UPLOADED`,start-live 推快照逻辑不改。
- 负面:两套 upload 入口长期并存(技术债,文档需写明各自用途);新增 QUEUED/RUNNING 两态牵动看板状态展示与前端轮询;stream.py multipart"边算边推"路径在异步语义下定位为"同步演示专用",不纳入异步化(显式划界,避免 SSE 跨进程问题)。
