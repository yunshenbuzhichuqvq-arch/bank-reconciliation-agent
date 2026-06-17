# Stage V1-3 — Architectural Decisions

> 收官 stage。范围:① 任务看板实时(PRD §4.2)② 量化指标仪表板(PRD §4.8)。
> Backlog(本 stage 不做):Redis / JWT / Celery / Docker 部署 / 报表审计页 / MCP / 复核超时推送 / 手续费样例。
> 编号延续全局序列(V1-2 收尾止于 ADR-044),本 stage 为 ADR-045..048。

---

## ADR-045: 看板实时执行模型——start 后台驱动 + by-taskId SSE 结果推送

**Slug**: `dashboard-live-start-background-and-by-taskid-sse`
**Status**: accepted (revised 2026-06-16, V1-3 review)
**Date**: 2026-06-16

> **Revision (V1-3 review)**:初稿 Context 误判"start 同步阻塞跑对账"。实际对账在 `upload` 完成,`start_live` 之后无执行过程可推,看板"实时"诚实降级为"启动后 SSE 推一次最终结果快照"(非进度过程)。下文已就地订正,保留教训留痕。

### Context

PRD §4.2 要求任务看板"V1 改为 SSE 实时更新";V1-2 的 ADR-043 已把"看板真·实时"显式延到 V1-3,是 V1-2 唯一明确欠下的债。

现状(**V1-3 review 订正**):初稿以为 `start` 同步阻塞跑对账。实际:**对账(匹配/异常分类/落台账)在 `upload` 阶段已完成,`start`/`start_live` 仅把状态翻成 AI_RUNNING**。因此 `start_live` 之后没有"对账执行过程"可推——看板"实时"的本质是把 upload 已算好的最终统计**推一次**,把"手动刷新"升级为"启动后自动 SSE 推送一次结果"(收 ADR-043 欠债),但**不是"实时进度过程"**。

可复用资产:`stream.py`(ADR-036)已验证"后台驱动 + `QueueEmitter` + SSE 边跑边 yield"。但它是 **multipart 一次性请求内、per-request** 的 emitter;看板是对**已存在 task** 的进度订阅,天然**跨请求**(start 请求触发执行、SSE 请求订阅进度),现有 per-request emitter 不能直接复用。

约束(延续项目一贯切片):不引 Celery/Redis(已划入 backlog);银企/清算两场景 + 现有同步路径零回归。

### Options Considered

- **A. 后端异步驱动 + by-taskId SSE 进度流(采纳)** — `start` 改进程内后台驱动(asyncio,沿用 `stream.py` 模式)立即返回、任务进 RUNNING;进程内维护 `task_id → emitter` 注册表,`start` 创建并注册 emitter + 后台执行;新增 `GET /reconcile/{task_id}/events`(SSE)按 task_id 取 emitter 订阅,终态清理注册表项。
  - Pros: 真·SSE 实时、兑现 PRD §4.2、收 ADR-043 欠债;复用已验证机制;不引新基础设施。
  - Cons: 执行模型由同步改后台驱动(回归面中等);引入跨请求进程内注册表(需处理生命周期/清理/单进程假设);沿用 `stream.py` 后台驱动反模式技术债。
- **B. 前端轮询** — `start` 改后台返回后,看板 `setInterval` 每 2–3s 轮询 `status`/`exceptions` 到终态。
  - Pros: 最简。Cons: 非 SSE(偏离 PRD §4.2 明文)、伪实时、信号弱;仍需 `start` 异步化才能轮询(并未省掉核心改造)。
- **C. 全局 pub-sub 事件总线** — `QueueEmitter` 升级为 `task_id → 多订阅者`,看板/工作台统一订阅。
  - Pros: 架构最正、统一订阅源。Cons: 改动最大、收官 stage 过重、超出当前"看板单订阅"需求(YAGNI)。

#### 子决策:start 异步化的回归边界(已定:A1 双路径)

- **A1. 双路径(采纳)** — 保留现有同步 `start` 端点语义(现有 `DashboardPage` 调用方 / 现有测试零回归)+ 新增异步驱动入口(新端点或 `start` 加显式异步开关),看板实时走异步入口。对齐 ADR-030/036/044 双路径零回归哲学。Cons: 两套 `start` 语义、概念重复。
- **A2. 直接改异步** — `start` 一律改后台驱动立即返回,现有调用方/测试适配。Pros: 单一执行模型、更简洁。Cons: 破坏现有 `start`"返回即完成"语义,回归面大(现有前端 `startReconciliation` 后立即 `getTaskStatus` 会拿到未完成态)。

### Decision

采用 **A**(后台驱动 + `task_id → emitter` 注册表 + by-taskId SSE 端点);回归边界采用 **A1 双路径**——保留现有同步 `start` 端点零回归,新增异步驱动入口供看板实时订阅。

**实时语义(V1-3 review 校正)**:因对账在 upload 完成,`start_live` emit 一帧最终统计快照(`task_progress`,processed=total)+ `task_done`;看板由"手动刷新"升级为"启动后 SSE 自动推送一次结果"。这是**实时结果推送**,非实时进度过程——后者需把对账过程挪到 start 之后(已评估为大改、回归高,本 stage 不做)。

### Consequences

- 正面:看板从手动刷新升级为 SSE 自动推送(收 ADR-043 欠债);复用 `stream.py` 机制;零新基础设施。(实时语义见 Decision 校正:结果推送而非进度过程)
- 负面:
  - 进程内 `task_id → emitter` 注册表假设**单进程**(多 worker 不共享)——生产化需 SSE-over-Redis,登记技术债(与 ADR-036 同源)。
  - 沿用 `stream.py` 后台驱动反模式(`asyncio` 嵌套 / 跨线程),不在收官 stage 做大重构。
  - 若采纳 A1,留两套 `start` 语义。
  - 后台任务**异常/超时/清理**须明确:任务跑挂时 emitter 如何清理、SSE 如何收尾(终帧 + 注册表移除),否则泄漏。
  - **现状误判教训(V1-3 review)**:初稿未核实 `start`/`upload` 的真实分工(对账在 upload),致"实时进度"建立在不存在的"start 后执行过程"上,最终诚实降级为"实时结果推送"。Codex 在错误前提下实现合理(读已落数据 emit 一帧),但撞到"无中途过程"矛盾时未按红线停下标注——设计方与实现方流程均有可改进处。

### 防降级硬约束(从 V1-1 SSE 回放 gap 提炼)

V1-1 的真实时曾静默退化为一次性回放(见 ADR-036 Implementation Note)。by-taskId 跨请求架构**新增一条 V1-1 没有的、更隐蔽的回放路径**:`events` 端点读 `agent_log` 表"边读边推",能骗过"首帧早于完成"断言。故立硬约束:

1. **数据源唯一**:`events` 的帧只能来自注册表的 live emitter,**禁止读 `agent_log`/DB 回放**。
2. **订阅边界不得降级**:订阅时 emitter 不存在(未 start-live / 已 unregister)→ 明确报错或空流收尾,**不得 fallback 读 DB**。
3. **测试锁数据源 + 端点流式转发**:断言(a)`events` 数据来自 live emitter,落库为空/no-op 时仍推帧(不靠 DB);(b)端点**流式转发不缓存**——首帧在 `task_done` 前即可取得(防 V1-1 整体 drain 回放)。注:`start_live` 实际只 emit 一帧 `task_progress`(对账在 upload 完成),"边算边推的中途多帧"不适用;端点流式转发可用手喂多帧验证"不缓存",但**不得据此声称验证了 start_live 的实时进度**(它没有进度过程)。

违反 1/2 即等价于把真实时降级为回放——这是 ADR-045 的红线,非可选优化。

---

## ADR-046: 看板进度事件契约——扩展 ADR-037,新增任务级进度/统计事件

**Slug**: `dashboard-progress-event-contract-extends-adr037`
**Status**: accepted
**Date**: 2026-06-16

### Context

ADR-037 已定义 `stream.py` 的 SSE 事件契约(versioned schema):面向工作台的 per-item / agent_decision / item_done 等**单流水 Agent 执行细节**。

看板要展示的是**任务级**进度与聚合统计(已处理 N/总 M、`auto_fixed`/`pending_human`/异常分布的实时变化),粒度不同。需决定:看板事件扩展现有契约,还是另起一套。

### Options Considered

- **A. 扩展 ADR-037 契约,新增任务级事件类型(采纳)** — 在现有 versioned schema 上加 `TASK_PROGRESS`(任务级计数/统计快照)事件;与 per-item 事件**同源**(同一 emitter、同一 seq 序列、同一 schema 版本演进)。看板按 `event_type` 过滤渲染任务级事件、忽略 per-item;工作台两类都渲染。
  - Pros: 单一契约 / 单一 Schema 符合性测试入口;口径一致;前端复用现有事件解析(ADR-042 TS 投影);事件与 `agent_log` 落库口径一致(延续 ADR-036 同源原则)。
  - Cons: 契约承载两种粒度,schema 略膨胀;需 schema 版本号向后兼容演进。
- **B. 看板另起独立事件契约/端点 schema** — Pros: 看板/工作台契约解耦。Cons: 两套 schema / 两套符合性测试、口径易分叉(ADR-036 警告的"串流 vs 落库两套口径"升级版)、前端两套解析。
- **C. SSE 直接推完整 status 快照 JSON(不走结构化事件)** — Pros: 最简。Cons: 脱离 ADR-037 versioned schema 体系、无法纳入 Schema 符合性测试、与工作台不一致。

### Decision

采用 **A**:扩展 ADR-037,新增任务级进度/统计快照事件,同源同契约,schema 版本**向后兼容**演进(V1-2 工作台事件不变)。

### Consequences

- 正面:单一事件契约、口径一致、复用前端 TS 投影与 Schema 符合性测试。
- 负面:契约承载两种粒度需清晰文档化(哪些 `event_type` 给看板 / 哪些给工作台);schema 演进须有**向后兼容断言**,防止 V1-2 工作台回归。

---

## ADR-047: 指标仪表板数据源分层——线上聚合 + 离线评测快照 + 诚实缺口标注

**Slug**: `metrics-dashboard-data-source-layering-and-honest-gaps`
**Status**: accepted
**Date**: 2026-06-16

### Context

PRD §4.8 量化指标仪表板列 8 类指标。数据源盘点(已核对 `schema.sql` + `scripts/`):

| 档 | 指标 | 来源 |
|---|---|---|
| ① 线上可聚合 | 自动平账率、人工复核触发率、异常类型分布、Fallback 层级、Token 消耗 + 成本、置信度分布 | `t_reconciliation_task` / `t_*_ledger` / `t_human_review` 直接有字段 |
| ② 离线评测产物(静态) | RAG Recall@5/MRR/NDCG、Schema 符合率 | `scripts/eval_rag.py` / Schema 符合性测试输出 |
| ③ 无真实数据源 | 单笔时延 P50/P95/P99、Agent 审计准确率 | 无 latency 落库(仅疑似硬编码 fake 的 `bench_agent_latency`);准确率需 ground truth |

项目反复出现"有 UI/能力但数据是空壳/fake/静默降级"的坑(ADR-043 看板空壳、V1-1 SSE 回放降级、2b 静默退化)。指标板若摆 fake P99 会重蹈覆辙。

### Options Considered

- **A. 线上聚合 + 离线快照,诚实标注缺口(采纳)** — 新增 `GET /metrics/dashboard` 聚合①的线上真实统计;②离线指标读最近一次评测产物快照并标注评测时间;③无数据源指标在 UI 显式标注"暂无线上埋点 / 数据缺口",不计算、不 fake。
  - Pros: 覆盖 PRD §4.8 大部分;数据真实可追溯;诚实边界是工程亮点。
  - Cons: 仪表板有显式"空位",不如全绿好看;离线快照有时效性(非实时)。
- **B. 只做线上聚合指标** — 仅展示①,②③一律不进仪表板(在评测报告文件里看)。Pros: 最干净无争议。Cons: 丢失 V1-1 已有评测产物的展示价值、PRD §4.8 覆盖度低。
- **C. 全指标 + 补 latency 埋点** — 为 P50/P95/P99 加 `t_agent_execution_log.duration_ms` 字段 + 执行路径埋点。Pros: 最全。Cons: 改 schema + 执行路径(回归面)、收官 stage 偏重;Agent 准确率仍无 ground truth,解决不了。

#### 子决策:离线快照对接方式(写入 spec)

评测脚本(`eval_rag` / schema)输出一份**结构化 JSON**(在现有 markdown 报告外旁路增加),`/metrics` 后端读该 JSON。避免解析 markdown(脆弱)。若当前仅有 markdown,本 stage 加 JSON 输出旁路(小改,不动评测核心逻辑)。

### Decision

采用 **A**:线上真实聚合 + 离线评测 JSON 快照 + 无数据源指标诚实标注"暂无"。latency/准确率**不在本 stage 补埋点**(留 V2,对应 PRD §3.6 离线分析)。

### Consequences

- 正面:数据真实、覆盖度合理、诚实标注是可复用的工程 narrative。
- 负面:仪表板有显式"暂无"项;离线快照非实时(须标注 `@ 评测时间`);评测脚本需加 JSON 输出旁路(轻量改动)。

---

## ADR-048: 指标可视化方案——ECharts 引入 vs 轻量自绘

**Slug**: `metrics-visualization-echarts-vs-lightweight`
**Status**: accepted
**Date**: 2026-06-16

### Context

指标仪表板要展示分布(异常类型 / Fallback / 置信度)、趋势(Token 消耗)、占比(平账率)。前端当前**未装图表库**(`package.json` 仅 element-plus + axios + vue)。

张力:`overall-architecture.md` §2.1 写明技术栈含 **ECharts**;但本项目前端有明确**最小依赖**倾向——ADR-040 手写 SSE 客户端(不引 EventSource 库)、ADR-041 不引 Pinia。引入 ECharts 与该倾向冲突。

### Options Considered

- **A. 引入 ECharts**(裸 echarts 或 vue-echarts,按需引入控体积) — Pros: 图表表现力强、贴 PRD 架构原文、"作品版"观感好、分布/趋势图开箱即用。Cons: 新增较重前端依赖(体积大),打破最小依赖一致性(ADR-040/041),需按需 import 控体积。
- **B. Element Plus 卡片 + 进度条 + 表格 + 轻量自绘(SVG/CSS)** — Pros: 零新依赖、与 ADR-040/041 一致、足够展示数值型指标。Cons: 分布/趋势图表现力弱(柱状/折线需手写 SVG 或进度条近似)、视觉冲击不如 ECharts。
- **C. 极轻量图表库(uPlot / unovis 等)** — Pros: 体积远小于 echarts、有真图表。Cons: 再引一个非 PRD 原文的库、生态/示例少、收官 stage 不值得评估新库。

### Decision

采用 **A**:引入 ECharts,**按需引入**(仅 import BarChart/LineChart/PieChart + 必要的 Grid/Tooltip/Legend 等组件,避免全量)。指标仪表板是 §4.8 核心高光、ECharts 是 PRD 架构明文,作品版值得这一个依赖;以按需引入控制体积,局部打破前端最小依赖一致性(ADR-040/041)是有意识的取舍。

### Consequences

- 正面:分布/趋势图表现力强、贴 PRD 架构原文、作品版观感强。
- 负面:前端依赖变重(echarts 体积),需按需引入控体积;局部打破 ADR-040/041 最小依赖一致性(已接受)。
- 被否的 B(轻量自绘)价值:零依赖、风格一致,但图表表现力/视觉冲击不足,不匹配 §4.8 高光定位。

---

## ADR-049: 前端行为测试基础设施——引入 @vue/test-utils + happy-dom(dev-only)

**Slug**: `frontend-behavior-test-utils-happy-dom`
**Status**: accepted
**Date**: 2026-06-17

### Context

V1-3 看板防空壳闸(T6 change request → T3.9)要求"点击启动审计按钮 → 断言 `startLiveReconciliation` 被调"的**真行为**测试。但现状:vitest 跑默认 **node 环境**(`vite.config.ts` 无 `test` 块),且未装 `@vue/test-utils` / DOM 模拟库——现有所有页测试都用 `createSSRApp` + `renderToString`(SSR,无法交互)。**标准 `mount`+`trigger` 在当前工具链下根本跑不起来。**

T3.9 首版(commit `0c57f77`)为绕开此限制,手搓了 200 行无依赖 headless renderer(自实现 `createRenderer` + `@vue/compiler-sfc` 重编译 SFC + 正则改写编译产物 + `new Function` 执行 + 多个 stub)。行为虽真,但**强耦合 compiler-sfc 输出格式**(Vue 升级即可能 crash)、维护负债重,且违反 T6 "只留一条最小行为闸、不要重写成大测试"的约定。

张力:项目有最小依赖倾向(ADR-040 手写 SSE 客户端、ADR-041 不引 Pinia)。需厘清该倾向**是否约束测试依赖**。

### Options Considered

- **A. 引入 @vue/test-utils + happy-dom(dev-only,采纳)** — `vite.config.ts` 加 `test.environment = "happy-dom"`,看板闸用标准 `mount`+`trigger`(~10 行)。
  - Pros: 业界标准、不脆弱;dev-only 不进生产 bundle,不触 ADR-040/041 关心的运行时体积;项目自此具备 DOM 交互测试能力,后续页可复用。
  - Cons: +2 个 devDependencies;首次引入 DOM 测试环境,需确认现有 SSR 测试零回归。
- **B. 零依赖,放弃模拟点击** — 不渲染模板,直接验 `startAudit` 调用链。
  - Pros: 零依赖。Cons: 丢"点按钮"交互语义(测函数非按钮);`<script setup>` 下需把逻辑暴露为可测,反而要动组件。
- **C. 维持 headless renderer** — 保留 200 行自搓方案。
  - Pros: 绝对零依赖。Cons: 脆弱(耦合编译产物格式)、维护负债、违反"最小一条"约定。

### Decision

采用 **A**:引入 `@vue/test-utils` + `happy-dom` 作为 **devDependencies**,`vite.config.ts` 配 `test.environment`。明确边界:**ADR-040/041 的最小依赖倾向针对运行时依赖(bundle 体积 / SSR 复杂度),不约束 dev-only 测试依赖**。与 ADR-048(为 §4.8 高光破例引 ECharts)对称——此处为"可靠的行为闸"破一次 dev 依赖之例。

### Consequences

- 正面:看板闸回归 ~10 行标准写法,删 200 行脆弱基础设施;项目获得 DOM 交互测试能力供后续复用;厘清了"最小依赖只管运行时"的边界(可复用判据)。
- 负面:+2 devDependencies;node → happy-dom 环境切换须确认现有 `renderToString` SSR 测试零回归(T3.9 DoD 锁全套绿)。
- 选 happy-dom 而非 jsdom:更轻更快、API 覆盖足够本项目断言;若遇兼容缺口可换 jsdom(同为 `environment` 配置项,迁移成本低)。
- **流程教训**:T3.9 指令写"`mount`+trigger"时设计方未核实工具链能否支撑(node env + 无 test-utils),给了落不了地的指令;Codex 撞到"无 mount 能力"时未按 tasks.md 红线停下标注,而是自行决策搞 workaround——与 ADR-045 现状误判教训同构。
