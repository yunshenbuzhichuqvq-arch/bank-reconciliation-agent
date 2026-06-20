# Stage async-infra — Architectural Decisions(ARQ + Redis 异步化基建)

> Stage 定位:把 `upload` 请求内同步执行的对账+LLM+RAG 链路挪到后台 worker,上传即时返回 task_id;按需引入 Redis 做幂等去重 / LLM 结果缓存。属"阶段三·作品化"收尾,偿还历史 ADR 反复登记的"不引 Celery/Redis"backlog。
>
> Builds On:
> - 现状(已核实):重活在 `upload`(reconciliation.py:104)同步发生;`start`/`start_live` 仅状态翻转 + DB 快照推送,零重计算(reconciliation.py:243-291)。
> - [[decisions/ADR-045]]:对账在 upload 完成、start_live 推最终快照;进程内 `task_id→emitter` 注册表假设单进程,SSE-over-Redis 登记为技术债。
> - [[decisions/ADR-050]]:emitter 保留期 + 完成标记(进程内 registry);events 禁 DB 回放红线。
> - [[decisions/ADR-036]]:双路径 SSE / QueueEmitter,multipart 边算边推。
> - [[decisions/ADR-031]]:checkpoint 幂等(thread_id=task_id:queue_id,终态跳过)。
> - [[decisions/ADR-029]]:circuit breaker 仅限 RAG。
> - [[decisions/ADR-007]]:三级 Fallback;[[decisions/ADR-023]]:核心事务 vs 事务后副作用边界。
>
> Status 说明:全部 accepted(2026-06-20 用户拍板)。原 ⚠️ 关键分叉的拍板结果见文末「已定稿」。

---

## ADR-056: 异步任务基础设施选型 —— ARQ + Redis
**Slug**: `async-infra-arq-redis`
**Status**: accepted
**Date**: 2026-06-20
**Deciders**: 用户(拍板) · Claude Code(提案)

### Context
`upload`(reconciliation.py:104)在单个 HTTP 请求内同步完成 Excel 解析 → 三阶段匹配 → AuditAgent LLM 调用 + RAG 检索(`_run_workflow_for_result`:761)→ 落库。响应时间 = 整条对账+LLM 时延,客户端全程阻塞;LLM 失败无任务级隔离/重试可见性;单进程内执行,不能水平扩展。PRD §3.3 / architecture-lite §12 把 "ARQ 异步队列 + Redis" 明确列为阶段三未完成核心项。本 stage 还这笔债。

### Options Considered
- **A. ARQ + Redis(提案)**
  - Pros:asyncio 原生(与现有 `async def upload` / FastAPI 同栈,无线程桥接);依赖薄(arq + redis-py);Redis 同时承载后续缓存/幂等;worker 独立进程,任务持久化、可重试、可观测。
  - Cons:新增 Redis 运行时依赖 + 独立 worker 进程;本地/CI 需 Redis 或其替身;部署形态变复杂(为后续 Docker Compose stage 埋点)。
- **B. Celery + Redis/RabbitMQ**
  - Pros:生态成熟、功能全(定时、链式、监控 flower)。
  - Cons:对 asyncio 支持割裂(prefork/线程模型与现有 async 链路阻抗不匹配);配置与概念重(超出本项目演示体量,违背一贯切片纪律)。
- **C. FastAPI BackgroundTasks / 裸 asyncio.create_task**
  - Pros:零新依赖。
  - Cons:进程内、与请求生命周期耦合,进程崩任务即丢、无重试无持久化——正是 `start_live`(reconciliation.py:260)的现状反模式;不解决水平扩展。

### Decision
采用 **A**:引入 ARQ(Redis 后端)作为后台任务队列。Redis 本 stage 承载【队列 + 入队幂等去重】;LLM 缓存 / 限流 defer(见 ADR-059)。

### Consequences
- 正面:upload 解耦为"入队即返回 + worker 执行";任务持久化、可重试;为缓存/幂等/限流提供统一后端;部署可演进到独立 worker。
- 负面:新增 Redis 依赖与 worker 进程,运维面变大;本地/测试需 Redis 替身(见 ADR-061);pyproject 增 arq/redis;config 增 redis 连接配置;Docker Compose(后续 stage)需编排 redis + worker 两个新服务。

---

## ADR-057: 异步化对象、任务状态机与回归边界
**Slug**: `async-upload-statemachine-dualpath`
**Status**: accepted
**Date**: 2026-06-20
**Deciders**: 用户(拍板) · Claude Code(提案)

### Context
核实后:重活 100% 在 `upload`,`start_live` 只读 DB 快照(零计算)。故异步化对象是 **upload 的对账执行**,不是 `start_live`(避免重蹈 [[decisions/ADR-045]] 初稿"误判 start 同步阻塞"的覆辙)。异步化后 upload 返回时对账未跑完,任务不再处于 `UPLOADED` 终态;而 `start_live` 现有前置校验 `task.status != "UPLOADED" → 409`(reconciliation.py:254-255)依赖"upload 同步完成"假设,会被打破。同时存在两条同步 upload 路径:`POST /reconcile/upload`(emitter=None)与 stream.py 的 multipart 边算边推(ADR-036)。

### Options Considered
**主决策:回归边界**
- **A. 双路径零回归(提案)** — 保留现有同步 `upload`(及 stream.py multipart)端点语义不动(现有测试/前端/演示零回归),新增 `POST /reconcile/upload-async`(或 `enqueue`)入口:存盘 + 建任务(status=`QUEUED`)+ enqueue ARQ job + 立即返回 task_id;worker 跑对账落库、终态翻 `UPLOADED`(对账完成,待 start-live 推快照)/`FAILED`。
  - Pros:对齐 ADR-045/036/044 一贯"双路径零回归"哲学;现有同步链路与 SSE 看板语义不破坏;异步为增量入口,风险面可控。
  - Cons:两套 upload 语义并存,概念重复;前端需新增异步上传流程分支。
- **B. 全量改异步** — `upload` 一律改入队立即返回,现有同步调用方/测试/前端适配。
  - Pros:单一执行模型,无概念重复。
  - Cons:破坏现有 "upload 返回即对账完成" 契约,回归面大(波及 stream.py、看板 start_live 时序、大量同步测试);违背切片纪律。

**子决策:任务状态机扩展**
- 现状态:`UPLOADED → AI_RUNNING → COMPLETED/FAILED`。
- 提案扩展:`QUEUED`(入队待跑)→ `RUNNING`(worker 执行对账)→ `UPLOADED`(对账完成,语义对齐现状"upload 后")→ 复用现有 `start-live → AI_RUNNING → COMPLETED`。即异步只在前段插入 QUEUED/RUNNING,后段 SSE 快照链路完全不变。

### Decision
提案 **A(双路径零回归)** + 在 upload 前段插入 `QUEUED/RUNNING` 状态,worker 落库后归于现有 `UPLOADED`,start-live/SSE 后段零改动。⚠️ 回归边界 A vs B 是本 stage 最大分叉,请用户确认(提案 A)。

### Consequences
- 正面:现有同步 upload + SSE 看板链路零回归;异步入口隔离演进;worker 落库后归一到现有 `UPLOADED`,start-live 推快照逻辑不改。
- 负面:两套 upload 入口长期并存(技术债,文档需写明各自用途);新增 QUEUED/RUNNING 两态牵动看板状态展示与前端轮询;stream.py multipart"边算边推"路径在异步语义下定位为"同步演示专用",不纳入异步化(显式划界,避免 SSE 跨进程问题)。

---

## ADR-058: SSE 实时进度边界 —— 不引 SSE-over-Redis,维持 DB 快照推送
**Slug**: `sse-progress-boundary-no-redis-pubsub`
**Status**: accepted
**Date**: 2026-06-20
**Deciders**: 用户(拍板) · Claude Code(提案)

### Context
对账挪到 ARQ worker(独立进程)后,worker 执行中的细粒度进度若要推给前端,需跨进程通道(Redis pub/sub),因为 emitter registry 是 web 进程内单进程内存对象([[decisions/ADR-050]])。但现有 SSE 看板语义本就是"worker 无关":start-live 在 web 进程查 DB emit 最终快照([[decisions/ADR-045]] 校正语义)。

### Options Considered
- **A. 维持 DB 快照语义,不引 SSE-over-Redis(提案)** — worker 跑完落库;前端在任务转 `UPLOADED` 后走现有 start-live 推最终快照;worker 执行中前端只见 `QUEUED/RUNNING` 任务状态(轮询 status),无中途逐帧进度。
  - Pros:进程内 emitter 链路(stage-fix 刚修通)零触碰,不碰 ADR-050 红线;回归面最小;延续 ADR-045"不引 SSE-over-Redis"切片。
  - Cons:worker 执行中无逐帧实时进度(实时性仍是"状态 + 完成快照",非过程)。
- **B. SSE-over-Redis pub/sub** — worker emit 真实进度,经 Redis 广播,web 进程 events 端点转发。
  - Pros:兑现 ADR-045/050 登记的 SSE-over-Redis 债,真·跨进程实时进度。
  - Cons:范围大;直接改动刚修通的红线 SSE 链路,回归高;需同时落地 ADR-050 deferred 的"命中/404 + 实时 vs 回放"结构化日志(其红线前置条件),进一步放大 stage。
- **C. 前端轮询任务状态** — 不做 SSE 进度,前端轮询 status 到终态。
  - Pros:最简。Cons:与既有 SSE 看板并存显冗余。

### Decision
提案 **A**。SSE-over-Redis(B)显式划为 backlog,继续挂账(不恶化、不偿还);本 stage 不触碰 ADR-050 进程内 emitter 红线链路。

### Consequences
- 正面:异步化与现有 SSE 解耦,回归可控;红线链路不动。
- 负面:worker 执行期前端实时性弱(状态级,非逐帧);ADR-045/050 的 SSE-over-Redis 技术债继续存在(本 ADR 显式登记其归属与触发条件:未来做 worker 逐帧进度时,必须连带落地 ADR-050 deferred 日志)。

---

## ADR-059: Redis 用途边界 —— 本 stage 纳入哪些
**Slug**: `redis-usage-boundary`
**Status**: accepted
**Date**: 2026-06-20
**Deciders**: 用户(拍板) · Claude Code(提案)

> Revision(2026-06-20 收尾 review):入队幂等的"终态可 force 重算"集合最初遗漏 `FAILED`,致失败任务死锁(`force=true` 亦无法重算、`job:{task_id}` 键滞留)。修正:终态集合 = {UPLOADED, COMPLETED, FAILED},FAILED 支持 `force=true` 重算。详见 spec §API Contract、TASK-8。根因为设计侧 spec 遗漏(实现忠实复制),留痕以备复盘。

### Context
PRD §3.3 列 Redis 三用途:LLM 结果缓存 / API 限流 / 幂等去重。一次全上会让 stage 过大(违背单 task 2–4h 颗粒度)。需逐项定 in/defer。task_id 已是文件内容 sha256(内容寻址),`replace_task` 现为"重算覆盖",重复上传同文件会重跑整条 LLM 链路。

### Options Considered(逐用途)
- **入队幂等去重(提案纳入)** — 同 task_id 已处于 `QUEUED/RUNNING/UPLOADED` 时不重复入队(Redis SETNX/job_id=task_id)。
  - Pros:与异步队列强绑定;直接防重复上传触发重复 LLM 烧 token;实现轻。Cons:需定义"已完成是否允许强制重算"的旁路。
- **LLM 结果缓存(考虑过;用户 2026-06-20 拍板 defer,本 stage 不实现)** — AuditAgent 对同输入缓存判定,键 = `prompt_version + 异常指纹`。
  - Pros:降本/降时延的 Agent 工程信号,面试可讲;复用 Redis。Cons:需定缓存键与失效策略;与 LLM 非确定性、prompt 版本耦合;增 stage 体量。
- **API 限流(提案 defer)** — DeepSeek 调用并发/速率限制。
  - Pros:可靠性信号。Cons:与 [[decisions/ADR-029]] circuit breaker(RAG-only)、现有 LLM 有界重试边界需重新协调;相对独立,适合单列后续 stage。

### Decision
**仅纳入【入队幂等去重】**(核心,与队列同生)。**LLM 结果缓存与 API 限流均 defer** 到 backlog(用户 2026-06-20 拍板:本 stage 不实现 LLM 缓存,聚焦异步化 + 幂等,压缩 stage 体量)。

### Consequences
- 正面:幂等去重防重复 LLM 开销(重复上传同文件不重跑整条 LLM 链路);范围聚焦,stage 体量小。
- 负面:LLM 缓存 defer → 本 stage 不降低单次对账的 LLM 成本(仅防重复触发);API 限流 defer → 不解决 DeepSeek 限速(均登记 backlog);幂等引入"已完成能否强制重算"的旁路需求,需在 spec 定义。

---

## ADR-060: Job 重试 vs 现有 LLM 有界重试/Fallback 的边界
**Slug**: `job-retry-vs-llm-retry-boundary`
**Status**: accepted
**Date**: 2026-06-20
**Deciders**: 用户(拍板) · Claude Code(提案)

### Context
ARQ 自带 job 级重试。现有链路已有两层失败处理:AuditAgent 结构化输出的有界重试(Schema 校验失败重试)+ 三级 Fallback([[decisions/ADR-007]],RAG 无命中/LLM 失败转人工)。若 ARQ job 对同一任务整体重试,会把"已落库的部分副作用 + LLM 调用"整条重放,与既有重试/fallback 叠加放大失败、重复烧 token、并可能违反 [[decisions/ADR-023]] 事务边界与幂等。

### Options Considered
- **A. Job 重试仅覆盖基础设施瞬时错误(提案)** — ARQ `max_tries` 仅对 Redis/DB 连接类瞬时故障重试;业务/LLM 失败由现有 AuditAgent 有界重试 + 三级 Fallback 处理,失败任务翻 `FAILED`/转人工,**不**由 job 层重放整条对账。
  - Pros:不与既有重试/fallback 叠加;不重复烧 token;副作用幂等边界清晰。Cons:需在 worker 内区分"瞬时基础设施错误"与"业务失败"两类异常。
- **B. Job 整体重试** — 失败即整任务重跑。
  - Pros:实现简单。Cons:重复 LLM 调用与副作用、与既有 fallback 叠加、幂等风险高。
- **C. 关闭 job 重试** — `max_tries=1`,任何失败即 FAILED。
  - Pros:最简、零叠加。Cons:Redis/DB 抖动这类真瞬时错误也不重试,鲁棒性弱。

### Decision
提案 **A**:job 重试只兜底基础设施瞬时错误;LLM/业务失败沿用现有有界重试 + 三级 Fallback,不在 job 层重放。worker 重入须幂等(复用 task_id 内容寻址 + 状态校验,落库前检查终态)。

### Consequences
- 正面:失败处理职责单一、不叠加放大;token 不被重复消耗;与 ADR-007/023 一致。
- 负面:worker 需显式分类异常(瞬时 vs 业务),增实现复杂度;"瞬时错误"判定边界需在 spec 明确,否则易误分类。

---

## ADR-061: 本地开发与测试的 Redis 依赖策略
**Slug**: `redis-test-strategy-fakeredis`
**Status**: accepted
**Date**: 2026-06-20
**Deciders**: 用户(拍板) · Claude Code(提案)

### Context
项目 DoD 要求可复制运行、离线复跑(每 task DoD 跑全套)。引入 Redis 后 pytest 不能裸依赖外部 Redis 守护进程,否则 CI/本地不带 Redis 时全套挂掉。ARQ + Redis 的测试需要可控替身。

### Options Considered
- **A. fakeredis 作测试主体(提案)** — 单元/集成测试用 fakeredis(纯内存)注入,worker 逻辑用 ARQ 直跑函数或 fakeredis 队列验证;DoD 全程无需真 Redis 守护进程。
  - Pros:离线可复跑、快、零外部依赖;契合现有 DoD 风格。Cons:fakeredis 与真 Redis 行为差异(Lua/过期精度/部分命令)需留意;真实集成覆盖需另补 smoke。
- **B. testcontainers 起真 Redis** — 每次测试拉真 Redis 容器。
  - Pros:贴近生产。Cons:需 Docker、慢;违背"离线可复跑"DoD。
- **C. ARQ 同步/eager 直跑 + 真 Redis 仅手工 smoke** — 自动化测试不经队列,真 Redis 留手工冒烟。
  - Pros:测试简单。Cons:不覆盖入队/worker 路径,异步链路测试盲区(重蹈历史 smoke gap)。

### Decision
提案 **A**:fakeredis 作自动化测试主体(单元 + 集成),DoD 命令离线可复跑;真 Redis 集成留少量可选手工 smoke(记入 PR.md 测试章节,不进 DoD 必跑)。

### Consequences
- 正面:DoD 离线可复跑、CI 不依赖外部 Redis;异步入队/worker 路径有自动化覆盖。
- 负面:fakeredis 与真 Redis 语义差异可能掩盖问题(需在 spec 标注已知差异点);真 Redis 行为只靠手工 smoke 兜底,存在"本地 fake 过、真环境差异"的残余风险(诚实登记,非已解决)。

---

## 已定稿(2026-06-20 用户拍板)
1. **ADR-057 回归边界**:双路径零回归(A)—— accepted。
2. **ADR-059 Redis 范围**:仅入队幂等去重;LLM 缓存与 API 限流 defer —— accepted。
3. 其余(056 / 058 / 060 / 061)按提案 accepted。
4. **Backlog(本 stage 不做,显式登记)**:LLM 结果缓存、API 限流、SSE-over-Redis worker 逐帧进度(连带 ADR-050 deferred 的命中/404 + 实时vs回放 结构化日志)。
5. **Backlog(收尾 review 新增)**:瞬时错误重试耗尽时 task 卡 RUNNING → 应兜底翻 FAILED(ADR-060 follow-up);`job:{task_id}` 无 TTL → 加 TTL 或完成后清理防 Redis 堆积(ADR-059 follow-up,呼应 ADR-050 emitter 泄漏教训)。
