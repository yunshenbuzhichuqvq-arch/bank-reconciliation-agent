# ADR-045: 看板实时执行模型——start 后台驱动 + by-taskId SSE 结果推送

- Status: Accepted (2026-06-16, revised in V1-3 review)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/live_registry.py, src/bank_reconciliation_agent/services/reconciliation.py, src/bank_reconciliation_agent/api/v1/reconcile.py, decisions/ADR-036(后端双路径 SSE / QueueEmitter), decisions/ADR-043(看板同步、实时留 V1-3)

> Revision (V1-3 review):初稿 Context 误判"start 同步阻塞跑对账"。实际对账在 `upload` 完成,`start_live` 之后无执行过程可推,看板"实时"诚实降级为"启动后 SSE 推一次最终结果快照"(非进度过程)。下文已就地订正,保留教训留痕。

## Context

PRD §4.2 要求任务看板"V1 改为 SSE 实时更新";V1-2 的 ADR-043 已把"看板真·实时"显式延到 V1-3,是 V1-2 唯一明确欠下的债。

现状(V1-3 review 订正):初稿以为 `start` 同步阻塞跑对账。实际:对账(匹配/异常分类/落台账)在 `upload` 阶段已完成,`start`/`start_live` 仅把状态翻成 AI_RUNNING。因此 `start_live` 之后没有"对账执行过程"可推——看板"实时"的本质是把 upload 已算好的最终统计推一次,把"手动刷新"升级为"启动后自动 SSE 推送一次结果"(收 ADR-043 欠债),但不是"实时进度过程"。

可复用资产:`stream.py`(ADR-036)已验证"后台驱动 + QueueEmitter + SSE 边跑边 yield"。但它是 multipart 一次性请求内、per-request 的 emitter;看板是对已存在 task 的进度订阅,天然跨请求(start 请求触发执行、SSE 请求订阅进度),现有 per-request emitter 不能直接复用。

约束(延续项目一贯切片):不引 Celery/Redis(已划入 backlog);银企/清算两场景 + 现有同步路径零回归。

## Options

- **A. 后端异步驱动 + by-taskId SSE 进度流(采纳)** — `start` 改进程内后台驱动(asyncio,沿用 `stream.py` 模式)立即返回、任务进 RUNNING;进程内维护 `task_id → emitter` 注册表,`start` 创建并注册 emitter + 后台执行;新增 `GET /reconcile/{task_id}/events`(SSE)按 task_id 取 emitter 订阅,终态清理注册表项。
  - Pros: 真·SSE 实时、兑现 PRD §4.2、收 ADR-043 欠债;复用已验证机制;不引新基础设施。
  - Cons: 执行模型由同步改后台驱动(回归面中等);引入跨请求进程内注册表(需处理生命周期/清理/单进程假设);沿用 `stream.py` 后台驱动反模式技术债。
- **B. 前端轮询** — `start` 改后台返回后,看板 `setInterval` 每 2–3s 轮询 `status`/`exceptions` 到终态。
  - Pros: 最简。Cons: 非 SSE(偏离 PRD §4.2 明文)、伪实时、信号弱;仍需 `start` 异步化才能轮询(并未省掉核心改造)。
- **C. 全局 pub-sub 事件总线** — `QueueEmitter` 升级为 `task_id → 多订阅者`,看板/工作台统一订阅。
  - Pros: 架构最正、统一订阅源。Cons: 改动最大、收官 stage 过重、超出当前"看板单订阅"需求(YAGNI)。

### 子决策:start 异步化的回归边界(已定:A1 双路径)

- **A1. 双路径(采纳)** — 保留现有同步 `start` 端点语义(现有调用方/测试零回归)+ 新增异步驱动入口,看板实时走异步入口。对齐 ADR-030/036/044 双路径零回归哲学。Cons: 两套 `start` 语义、概念重复。
- **A2. 直接改异步** — `start` 一律改后台驱动立即返回,现有调用方/测试适配。Pros: 单一执行模型。Cons: 破坏现有 `start`"返回即完成"语义,回归面大。

## Decision

采用 A(后台驱动 + `task_id → emitter` 注册表 + by-taskId SSE 端点);回归边界采用 A1 双路径——保留现有同步 `start` 端点零回归,新增异步驱动入口供看板实时订阅。

实时语义(V1-3 review 校正):因对账在 upload 完成,`start_live` emit 一帧最终统计快照(`task_progress`,processed=total)+ `task_done`;看板由"手动刷新"升级为"启动后 SSE 自动推送一次结果"。这是实时结果推送,非实时进度过程——后者需把对账过程挪到 start 之后(已评估为大改、回归高,本 stage 不做)。

## Consequences

- 正面:看板从手动刷新升级为 SSE 自动推送(收 ADR-043 欠债);复用 `stream.py` 机制;零新基础设施。(实时语义见 Decision 校正:结果推送而非进度过程)
- 负面:
  - 进程内 `task_id → emitter` 注册表假设单进程(多 worker 不共享)——生产化需 SSE-over-Redis,登记技术债(与 ADR-036 同源)。
  - 沿用 `stream.py` 后台驱动反模式(asyncio 嵌套/跨线程),不在收官 stage 做大重构。
  - 留两套 `start` 语义(A1)。
  - 后台任务异常/超时/清理须明确(终帧 + 注册表移除),否则泄漏。
  - 现状误判教训(V1-3 review):初稿未核实 `start`/`upload` 的真实分工(对账在 upload),致"实时进度"建立在不存在的"start 后执行过程"上,最终诚实降级为"实时结果推送"。Codex 在错误前提下实现合理(读已落数据 emit 一帧),但撞到"无中途过程"矛盾时未按红线停下标注——设计方与实现方流程均有可改进处。

## 防降级硬约束(从 V1-1 SSE 回放 gap 提炼)

V1-1 的真实时曾静默退化为一次性回放(见 ADR-036 Implementation Note)。by-taskId 跨请求架构新增一条 V1-1 没有的、更隐蔽的回放路径:`events` 端点读 `agent_log` 表"边读边推",能骗过"首帧早于完成"断言。故立硬约束:

1. 数据源唯一:`events` 的帧只能来自注册表的 live emitter,禁止读 `agent_log`/DB 回放。
2. 订阅边界不得降级:订阅时 emitter 不存在(未 start-live / 已 unregister)→ 明确报错或空流收尾,不得 fallback 读 DB。
3. 测试锁数据源 + 端点流式转发:断言(a)`events` 数据来自 live emitter,落库为空/no-op 时仍推帧(不靠 DB);(b)端点流式转发不缓存——首帧在 `task_done` 前即可取得(防 V1-1 整体 drain 回放)。注:`start_live` 实际只 emit 一帧 `task_progress`(对账在 upload 完成),"边算边推的中途多帧"不适用;端点流式转发可用手喂多帧验证"不缓存",但不得据此声称验证了 start_live 的实时进度(它没有进度过程)。

违反 1/2 即等价于把真实时降级为回放——这是 ADR-045 的红线,非可选优化。
