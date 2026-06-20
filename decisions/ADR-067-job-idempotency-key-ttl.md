# ADR-067: `job:{task_id}` 幂等键 TTL 收口(ADR-059 follow-up)

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/queue_client.py(SET NX EX), src/bank_reconciliation_agent/core/config.py(job_idempotency_ttl_seconds), decisions/ADR-059(本 follow-up 来源 / 终态 force 重算语义)/ADR-057(异步上传状态机,幂等语义协调)

## Context
ADR-059 收尾 follow-up 明确记账:`queue_client.enqueue_reconciliation` 用 `set(job_key, "1", nx=True)` 做入队幂等,**无 TTL**,键会随任务累积、永久滞留(同 ADR-050 emitter 泄漏教训)。本 stage 顺带收口。

## Options Considered
- **TTL 怎么加**:
  - 入队时 `set(job_key, "1", nx=True, ex=TTL)`。Pros:一行收口、与 SETNX 原子;Cons:TTL 选值需覆盖最长任务执行。
  - 任务终态时显式 `delete(job_key)`。Pros:语义精确(完成即释放);Cons:任务崩溃 / 终态漏走则键又滞留,需兜底。
  - 两者结合。Pros:最稳;Cons:本 stage 体量不值,过度工程。
- **TTL 取值**:覆盖单任务执行 + 余量(如 1 小时)vs 与"防重复上传"语义窗口对齐(更长)。

## Decision
- 入队幂等键加 TTL:`set(job_key, "1", nx=True, ex=settings.job_idempotency_ttl_seconds)`,默认 **1 小时**(`3600`,足够覆盖单任务执行,远短于内容寻址语义窗口)。
- **不**动现有 `force` 删除键逻辑(ADR-059 终态可 force 重算的语义保持)。
- 不引入终态 delete(避免崩溃漏走的兜底复杂度,TTL 已足够)。

## Consequences
- 正面:防 Redis 键无界堆积,闭合 ADR-059 follow-up。
- 负面:**幂等窗口从"永久"变"TTL 内"**——TTL 过后同 `task_id`(= 文件 sha256)再次上传会再入队、重算一次。可接受:此时 ADR-062 的 LLM 缓存大概率命中,重算开销小。这是与 ADR-057 异步状态机 / ADR-059 幂等语义的边界协调点。
