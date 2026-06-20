# ADR-056: 异步任务基础设施选型 —— ARQ + Redis

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/queue_client.py, src/bank_reconciliation_agent/worker.py, src/bank_reconciliation_agent/core/config.py, pyproject.toml, decisions/ADR-061(测试替身), decisions/ADR-045(start_live 进程内 asyncio 反模式参照), decisions/ADR-059(Redis 用途边界)

## Context

`upload`(reconciliation.py:104)在单个 HTTP 请求内同步完成 Excel 解析 → 三阶段匹配 → AuditAgent LLM 调用 + RAG 检索(`_run_workflow_for_result`)→ 落库。响应时间 = 整条对账+LLM 时延,客户端全程阻塞;LLM 失败无任务级隔离/重试可见性;单进程内执行,不能水平扩展。PRD §3.3 / architecture-lite §12 把 "ARQ 异步队列 + Redis" 明确列为阶段三未完成核心项。本 stage 还这笔债。

## Options Considered

- **A. ARQ + Redis(采纳)**
  - Pros:asyncio 原生(与现有 `async def upload` / FastAPI 同栈,无线程桥接);依赖薄(arq + redis-py);Redis 同时承载幂等;worker 独立进程,任务持久化、可重试、可观测。
  - Cons:新增 Redis 运行时依赖 + 独立 worker 进程;本地/CI 需 Redis 或其替身;部署形态变复杂(为后续 Docker Compose 埋点)。
- **B. Celery + Redis/RabbitMQ**
  - Pros:生态成熟、功能全。
  - Cons:对 asyncio 支持割裂(prefork/线程模型与现有 async 链路阻抗不匹配);配置与概念重,超出本项目演示体量,违背一贯切片纪律。
- **C. FastAPI BackgroundTasks / 裸 asyncio.create_task**
  - Pros:零新依赖。
  - Cons:进程内、与请求生命周期耦合,进程崩任务即丢、无重试无持久化——正是 `start_live`(reconciliation.py:260)的现状反模式;不解决水平扩展。

## Decision

采用 **A**:引入 ARQ(Redis 后端)作为后台任务队列。Redis 本 stage 承载【队列 + 入队幂等去重】;LLM 缓存 / 限流 defer(见 ADR-059)。

## Consequences

- 正面:upload 解耦为"入队即返回 + worker 执行";任务持久化、可重试;为缓存/幂等/限流提供统一后端;部署可演进到独立 worker。
- 负面:新增 Redis 依赖与 worker 进程,运维面变大;本地/测试需 Redis 替身(见 ADR-061);pyproject 增 arq/redis;config 增 redis 连接配置;Docker Compose(后续 stage)需编排 redis + worker 两个新服务。
