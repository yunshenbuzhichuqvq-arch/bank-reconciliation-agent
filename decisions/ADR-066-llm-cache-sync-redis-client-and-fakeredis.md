# ADR-066: Redis 客户端边界与测试策略

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/cache.py(同步 redis 客户端), src/bank_reconciliation_agent/core/llm/provider.py(redis.Redis.from_url + ping), src/bank_reconciliation_agent/services/queue_client.py(arq ArqRedis 异步池), tests/test_llm_cache.py(FakeStrictRedis), decisions/ADR-056(arq+redis 选型)/ADR-059(Redis 用途边界)/ADR-061(fakeredis 测试策略)

## Context
`provider.complete()` 是**同步**调用(对账核心 `run_reconciliation_job` / `_execute_reconciliation` 均同步;live 路径用 `asyncio.to_thread` 把同步核心丢线程)。而 ADR-056 引入的 arq `ArqRedis` 池是**异步**、只服务入队幂等(`queue_client.py`)。LLM 缓存落在同步路径上。ADR-061 定了测试用 fakeredis、不连真 Redis。

## Options Considered
- **缓存用哪个 Redis 客户端**:
  - 复用 arq 异步池。Pros:单一连接来源;Cons:要把缓存做成 async,侵入同步 `provider.complete` 及其所有同步调用栈,改动面巨大。
  - 为缓存单开同步 `redis.Redis.from_url(settings.redis_dsn)`。Pros:贴合同步 provider,零侵入;Cons:进程内多一个 Redis 连接来源,需文档说明两套客户端用途。
- **测试**:连真 Redis(违背 ADR-061)vs `fakeredis.FakeStrictRedis`(同步变体,延续 ADR-061)。

## Decision
- LLM 缓存用**独立同步 `redis.Redis.from_url(settings.redis_dsn)`**,与 arq 异步池**物理分离**(同一 Redis 实例、不同客户端、不同用途)。
- 测试用 `fakeredis.FakeStrictRedis`(同步),延续 ADR-061 不连真 Redis 策略。
- 本 ADR 是 ADR-059「Redis 用途边界」的扩展:Redis 用途现 = 入队幂等(异步池)+ LLM 结果缓存(同步客户端)。

## Consequences
- 正面:不污染同步 provider 路径,零侵入;测试无需真 Redis;Redis 用途边界清晰留痕。
- 负面:同步 / 异步两套 Redis 客户端并存,需在注释/文档说明各自职责,避免后人误用;`fakeredis` 已在测试依赖内(ADR-061 已引),复用无新增依赖。
