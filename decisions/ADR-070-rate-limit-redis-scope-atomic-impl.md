# ADR-070: 作用域、算法与原子实现 —— Redis 分布式 + 原生命令,fakeredis 测试边界

- Status: Accepted (2026-06-21)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/rate_limit.py(_acquire_rpm / _acquire_concurrency 原生命令), tests/test_llm_rate_limit.py(同步 fakeredis), decisions/ADR-056(ARQ/Redis 选型), decisions/ADR-059(Redis 用途边界), decisions/ADR-061(fakeredis 测试策略), decisions/ADR-066(同步 redis client)

## Context

LLM 调用横跨 **FastAPI web 进程(同步 upload 路径,ADR-007 提到单次 audit 15~25s)+ ARQ worker 进程**(ADR-056),进程内 `asyncio.Semaphore` 只能限单进程、无法全局节流;ADR-059 已把限流登记为 Redis 用途。但分布式限流的原子"读-改-写"常用 Lua,而 ADR-061 指出 fakeredis 的 Lua / 过期精度与真 Redis 有差异,且 DoD 要求离线可复跑。算法与原子实现需一并定。

## Options Considered

- **A. Redis 分布式 + 原生原子命令(避自定义 Lua):RPM 用固定窗口 `INCR`+`EXPIRE`,并发用 `INCR`/`DECR` 计数键(带 TTL 兜底);fakeredis 作测试主体 + 真 Redis 手工 smoke**
  - Pros:跨 web/worker 全局节流;原生命令 fakeredis 支持好、DoD 离线可复跑;与 ADR-059/061 一致。
  - Cons:固定窗口有边界突刺(窗口切换瞬间最多 ~2 倍);并发计数依赖进程正常 `DECR`,进程崩溃会泄漏 → 需键 TTL 兜底,非强一致。
- **B. Redis + Lua 原子脚本(如 token bucket)**
  - Pros:原子性强、算法平滑突发。
  - Cons:fakeredis Lua 支持差 → 自动化测试盲区(放大 ADR-061 风险);实现与调试复杂度高。
- **C. 进程内 `asyncio.Semaphore`(不依赖 Redis)**
  - Pros:最简、零外部依赖。
  - Cons:web/worker 多进程各自为政,全局速率 = 单进程限 × 进程数,失去全局节流意义;与 ADR-059 背离。

## Decision

选 **A**:Redis 分布式 + 原生原子命令;RPM 固定窗口(`INCR`+`EXPIRE`)、并发计数键带 TTL 防崩溃泄漏;固定窗口突刺以"限到配额的留 margin 比例"缓解。fakeredis 作自动化测试主体,真 Redis 留可选手工 smoke 记入 PR.md(对齐 ADR-061),不进 DoD 必跑。

## Consequences

- 正面:跨进程全局节流;离线可测、DoD 不依赖真 Redis;实现简单可维护。
- 负面:固定窗口边界突刺(登记,靠 margin 容忍,DeepSeek 防配额场景可接受);并发计数靠 TTL 兜底而非强一致(极端崩溃下可能短暂少算);fakeredis 与真 Redis 残余语义差异靠手工 smoke 兜底(诚实登记,非已消除)。

## 实现注记 (2026-06-21 收尾 review)

- 并发键 TTL = `max(60, ceil(max_wait_seconds) + 60)` 秒(默认 76s),每次 `INCR` 后刷新;`DECR` 配对归还,崩溃漏 `DECR` 由 TTL 兜底。
- RPM 固定窗口键 `llmratelimit:rpm:{window_start}`(`window_start = now - now % window_seconds`),`count == 1` 时设 `EXPIRE`。
- 被拒请求锁 `denied_window`、**同窗口内不再 `INCR`**(防被拒计数虚高累积),等窗口滚动才重试 —— 比朴素固定窗口更稳。
- 真 Redis 8.8.0 手工 smoke 验证 RPM 超限等待、并发占满等待、等待超时、停机 fail-open(记入 PR.md)。
