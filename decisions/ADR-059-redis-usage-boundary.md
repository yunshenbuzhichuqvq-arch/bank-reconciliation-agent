# ADR-059: Redis 用途边界 —— 本 stage 纳入哪些

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/queue_client.py(SETNX 幂等), src/bank_reconciliation_agent/services/reconciliation.py(upload_async terminal_statuses + force), decisions/ADR-031(终态幂等), decisions/ADR-014(replace 语义), decisions/ADR-056(选型)

> Revision(2026-06-20 收尾 review):入队幂等的"终态可 force 重算"集合最初遗漏 `FAILED`,致失败任务死锁(`force=true` 亦无法重算、`job:{task_id}` 键滞留)。修正:终态集合 = {UPLOADED, COMPLETED, FAILED},FAILED 支持 `force=true` 重算(实现见 TASK-8)。根因为设计侧 spec 遗漏(实现忠实复制),留痕以备复盘。

## Context

PRD §3.3 列 Redis 三用途:LLM 结果缓存 / API 限流 / 幂等去重。一次全上会让 stage 过大(违背单 task 2–4h 颗粒度)。需逐项定 in/defer。task_id 已是文件内容 sha256(内容寻址),`replace_task` 现为"重算覆盖",重复上传同文件会重跑整条 LLM 链路。

## Options Considered（逐用途)

- **入队幂等去重(纳入)** — 同 task_id 已处于非终态时不重复入队(Redis SETNX,job_id=task_id)。
  - Pros:与异步队列强绑定;直接防重复上传触发重复 LLM 烧 token;实现轻。Cons:需定义"已完成是否允许强制重算"的旁路(终态集合见 Revision)。
- **LLM 结果缓存(defer)** — AuditAgent 对同输入缓存判定,键 = `prompt_version + 异常指纹`。
  - Pros:降本/降时延信号。Cons:需定缓存键与失效策略;与 LLM 非确定性、prompt 版本耦合;增 stage 体量。
- **API 限流(defer)** — DeepSeek 调用并发/速率限制。
  - Pros:可靠性信号。Cons:与 ADR-029 circuit breaker(RAG-only)、现有 LLM 有界重试边界需重新协调;相对独立,适合单列后续 stage。

## Decision

**仅纳入【入队幂等去重】**(核心,与队列同生)。**LLM 结果缓存与 API 限流均 defer** 到 backlog(用户 2026-06-20 拍板:本 stage 不实现 LLM 缓存,聚焦异步化 + 幂等,压缩 stage 体量)。force 重算的终态集合 = {UPLOADED, COMPLETED, FAILED}(见 Revision)。

## Consequences

- 正面:幂等去重防重复 LLM 开销(重复上传同文件不重跑整条 LLM 链路);范围聚焦,stage 体量小。
- 负面:LLM 缓存 defer → 本 stage 不降低单次对账的 LLM 成本(仅防重复触发);API 限流 defer → 不解决 DeepSeek 限速(均登记 backlog)。
- Follow-up(收尾 review 登记):`job:{task_id}` 无 TTL → 应加 TTL 或完成后清理防 Redis 堆积(呼应 ADR-050 emitter 泄漏教训)。
