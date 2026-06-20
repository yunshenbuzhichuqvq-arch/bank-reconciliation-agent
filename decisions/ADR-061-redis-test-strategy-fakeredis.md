# ADR-061: 本地开发与测试的 Redis 依赖策略

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: tests/conftest.py(fakeredis fixture), tests/test_async_queue_client.py, tests/test_async_reconciliation.py, tests/test_async_idempotency.py, tests/test_worker.py, tests/test_worker_retry.py, decisions/ADR-056(选型)

## Context

项目 DoD 要求可复制运行、离线复跑(每 task DoD 跑全套)。引入 Redis 后 pytest 不能裸依赖外部 Redis 守护进程,否则 CI/本地不带 Redis 时全套挂掉。ARQ + Redis 的测试需要可控替身。

## Options Considered

- **A. fakeredis 作测试主体(采纳)** — 单元/集成测试用 fakeredis(纯内存)注入,worker 逻辑用 ARQ 直跑函数或 fakeredis 队列验证;DoD 全程无需真 Redis 守护进程。
  - Pros:离线可复跑、快、零外部依赖;契合现有 DoD 风格。Cons:fakeredis 与真 Redis 行为差异(Lua/过期精度/部分命令)需留意;真实集成覆盖需另补 smoke。
- **B. testcontainers 起真 Redis** — 每次测试拉真 Redis 容器。
  - Pros:贴近生产。Cons:需 Docker、慢;违背"离线可复跑"DoD。
- **C. ARQ 同步/eager 直跑 + 真 Redis 仅手工 smoke** — 自动化测试不经队列,真 Redis 留手工冒烟。
  - Pros:测试简单。Cons:不覆盖入队/worker 路径,异步链路测试盲区(重蹈历史 smoke gap)。

## Decision

采用 **A**:fakeredis 作自动化测试主体(单元 + 集成),DoD 命令离线可复跑(`uv run pytest -m "not live"`);真 Redis 集成留少量可选手工 smoke(记入 PR.md 测试章节,不进 DoD 必跑)。

## Consequences

- 正面:DoD 离线可复跑、CI 不依赖外部 Redis;异步入队/worker 路径有自动化覆盖。
- 负面:fakeredis 与真 Redis 语义差异可能掩盖问题;真 Redis 行为只靠手工 smoke 兜底,存在"本地 fake 过、真环境差异"的残余风险(诚实登记,非已解决)。
