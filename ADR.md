# Stage ReportAgent — Architectural Decisions

> scratchpad, tracked。收尾时每条 accepted 拆进 `decisions/ADR-0NN-<slug>.md`,PR 前 `git rm ADR.md`。
> 续 `decisions/` 全局顺序号(现有止于 ADR-050),本 stage 取 ADR-051…055。

---

## ADR-051: ReportAgent guardrail —— 代码渲染数字 + LLM 只写叙述

**Slug**: `report-agent-numbers-code-rendered-llm-prose-only`

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/report.py(新), src/bank_reconciliation_agent/agents/report_agent.py(新), prompts/report_v1.md(新), src/bank_reconciliation_agent/services/metrics.py, decisions/ADR-047(线上 SQL 聚合 + 诚实数据源,本 ADR 沿用其"数字只来自 SQL"原则)

### Context

per-task 审计报告要有 LLM 组织的文字(PRD §12.2:"ReportAgent 只负责文字组织,不做数据计算"),但项目铁律是金额/统计不交给 LLM(README 开发约束:金额用 `Decimal`,不交给 LLM 或 float)。核心问题:报告既要有 LLM 叙述、又要数字零幻觉,二者怎么物理隔离。

### Options

**A. 代码渲染数字块 + LLM 只写叙述(选定)** —— metrics 服务出权威数字 dict;概览/异常分布/检索质量/Token 成本等事实区块由**代码**确定性渲染成 Markdown;ReportAgent 的 LLM 调用只返回 `{risk_summary, review_advice, followup}` 三段散文 JSON,prompt 明令不得复述或计算任何数字;代码按固定顺序拼装最终 Markdown。
- Pros: 数字由代码渲染、可证明正确,LLM 物理上碰不到数字区块;LLM 不可用时只输出数字区块即天然降级;"LLM 改不动数字"可写成不变量测试。
- Cons: 报告结构相对固定(非自由长文);LLM 散文里仍可能口头提到数字(靠定性指令缓解,不做强校验)。

**B. 整篇 LLM 生成 + 事后数字校验** —— LLM 拿数字生成整份(含表),再抽数字回校验,不符退模板/重试。
- Pros: 单遍输出更自然、更灵活。
- Cons: 校验自由文本里的数字很脆(格式/取整/对位);静默写错风险高;校验逻辑复杂。

**C. 纯模板、无 LLM** —— 代码填模板,无 LLM 参与。
- Pros: 零幻觉、零成本、全可测。
- Cons: 没了 LLM 叙述,退化成格式化器,与"ReportAgent"立项目标相悖(只能当 A 的降级分支)。

### Decision

选 A。数字事实区块代码渲染、LLM 只产出三段定性散文,把"数字不经 LLM"做成物理隔离而非约定。C 作为 A 的 LLM 降级分支保留(见 ADR-053)。

### Consequences

正向:
- 数字区块与 LLM 输出解耦,数字可追溯到 SQL 聚合;guardrail 可由不变量测试守住(塞乱编数字的 stub,断言数字区块逐字节不变)。
- 降级路径天然成立:无 LLM 时仅缺三段散文,报告仍完整。

负向 / 成本:
- 报告版式较固定,牺牲自由长文表达。
- LLM 散文可能口头提及数字而不一致——本 stage **有意只用定性 prompt 指令缓解,不做数字强校验**(接受的小风险,记录在案)。
- 需维护"代码渲染模板 ↔ metrics dict"字段对齐。

---

## ADR-052: 报告契约 —— per-task · 按需 · 实时生成不落库

**Slug**: `report-contract-per-task-on-demand-no-persist`

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/api/v1/reconcile.py(新增 endpoint), src/bank_reconciliation_agent/services/report.py(新), decisions/ADR-014(task-ai-stats replace 语义)

### Context

报告以什么为单位、何时生成、是否落库,直接决定 API 形状、要不要新建表、页面交互。

### Options

**A. per-task · 按需 · 实时生成不落库(选定)** —— `GET /reconcile/{task_id}/report` 每次实时聚合 + 生成;不新建表、不缓存。
- Pros: 无新表、无 staleness、实现最小;数字永远最新;契合"按需生成"。
- Cons: 每次请求跑一次 LLM(成本/延迟);无历史报告留存;无缓存。

**B. per-task · 对账完成自动生成并落库** —— 每任务跑完自动生成存 DB,页面直读。
- Pros: 页面零等待。
- Cons: 每任务都烧 LLM;要处理幂等/重生成/历史版本;新增表与写入路径(回归面)。

**C. 全局/批次汇总报告** —— 跨任务聚合一份。
- Cons: 与现有 metrics dashboard 重叠;偏离 PRD §12.1 的 per-task 口径(任务编号/对账日期/处理用户)。

### Decision

选 A。`GET /api/v1/reconcile/{task_id}/report` 实时聚合 + 生成,不落库不缓存。数字本就实时来自 metrics,省掉 staleness/幂等/历史版本的复杂度。

### Consequences

正向:
- 无新表、实现面最小、数字最新。

负向 / 成本:
- 每次点击跑一次 LLM(fake 默认下不显著;真 LLM 下有成本/延迟)。
- 不留历史报告版本(列 future)。
- 高频请求无缓存——YAGNI,未来确有需要再加缓存层。

---

## ADR-053: ReportAgent 失败降级 —— 模板兜底 + schema 校验 + 单次尝试不重试

**Slug**: `report-agent-fallback-template-degrade`

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/agents/report_agent.py(新), src/bank_reconciliation_agent/schemas/(新增 report 叙述 schema), decisions/ADR-005(LLM provider 抽象 + fake 默认 + 测试契约), decisions/ADR-007(三级 fallback), decisions/ADR-022(硬约束 C1–C6 输出校验), decisions/ADR-008(structlog + prompt 版本)

### Context

LLM 超时/不可用/输出 schema 不符时,报告端点不能挂。项目已有 fake-default(ADR-005)、三级 fallback(ADR-007)、输出校验管线(ADR-022)、prompt 版本(ADR-008)等成熟模式,ReportAgent 应复用而非另造。

### Options

**A. 模板降级(选定)** —— ReportAgent 镜像 AuditAgent:provider 注入、fake 默认确定性、Pydantic schema 校验;校验失败 / LLM 不可用即降级为确定性模板叙述,`llm_used=false`(对齐 AuditAgent:单次尝试、不重试)。数字区块照常(代码渲染,不依赖 LLM)。
- Pros: 报告高可用、永远 200;与现有 agent 行为一致;可测(fake 确定性 + 降级路径)。
- Cons: 降级时叙述质量下降(以 `llm_used=false` 显式标注);多一套 report schema 维护。

**B. LLM 失败直接 5xx** —— Cons: 报告链路脆,违背项目"无命中/失败转兜底"基因。

**C. 无限重试** —— Cons: 阻塞请求、放大故障,无界重试是反模式。

### Decision

选 A。复用 ADR-005/007/022/008 既有管线:fake 默认 + schema 校验 + 失败即模板降级(对齐 AuditAgent:单次尝试、不重试) + structlog(带 `prompt_version`)。报告永远可出,降级时诚实标注。

### Consequences

正向:
- 报告链路高可用且可测;与 AuditAgent 行为/测试范式统一。

负向 / 成本:
- 降级叙述质量下降(显式 `llm_used=false`,诚实)。
- 新增一套 report 叙述 schema 与降级模板需维护。

---

## ADR-054: 单任务指标聚合归属 —— 扩展 metrics.py 而非新服务

**Slug**: `per-task-metrics-aggregation-extends-metrics-service`

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/metrics.py, decisions/ADR-047(指标数据源分层:线上 SQL 聚合 + 离线快照), decisions/ADR-014(task-ai-stats replace 语义)

### Context

报告数字需 per-task 聚合(总笔数/金额、自动平账率、异常分布、Agent 决策分布、Fallback 分布、复核数、Token/成本),但 `metrics.py` 现仅有全局 `get_dashboard(user_id)`,无单任务聚合。聚合逻辑放哪。

### Options

**A. 扩展 metrics.py 加 `get_task_report_metrics(user_id, task_id)`(选定)** —— 聚合集中在 metrics 一处,全局与单任务同源同口径。
- Pros: 聚合口径单一可信源,避免两处 SQL 漂移;复用 ADR-047 分层与现有表;report_service 只编排不算数。
- Cons: metrics.py 体量增长(需留意是否过大,过大则拆模块)。

**B. 新建 report 专属聚合服务** —— Cons: 同样的 SQL 聚合散到两个服务,口径易漂(项目已有 schema/口径漂移的教训)。

**C. 在 report_service 里直接写 SQL** —— Cons: 业务编排层混入聚合 SQL,违背现有分层。

### Decision

选 A。新增 `get_task_report_metrics(user_id, task_id)` 到 metrics.py,与 dashboard 共用聚合口径与 `user_id` 过滤;report_service 仅消费,不自行算数。

### Consequences

正向:
- 全局/单任务聚合单一可信源,口径不漂;复用既有表与 replace 语义。

负向 / 成本:
- metrics.py 增长——若超出单文件合理体量,后续按 dashboard / report 聚合拆分。
- 共享聚合代码须保证 `user_id` 过滤在两条路径上都生效(租户隔离红线)。

---

## ADR-055: 前端报告渲染 —— 原生组件 + .md 下载,不引 markdown 库 / 不用 v-html

**Slug**: `frontend-report-native-render-no-markdown-lib`

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/pages/ReportPage.vue(新), frontend/src/api/report.ts(新), frontend/src/router/, decisions/ADR-048(指标可视化 ECharts), decisions/ADR-049(前端行为测试 test-utils + happy-dom)

### Context

报告输出是 Markdown,其 narrative 段落是 **LLM 生成内容**;前端当前无 markdown 渲染库。若用 markdown→HTML + `v-html` 渲染 LLM 输出,等于开 XSS 注入口。如何在不引库、不开 XSS 面的前提下满足"展示 Markdown 报告"。

### Options

**A. 原生组件 + 文本 + .md 下载(选定)** —— 后端同时返回结构化 `metrics`(前端用 StatCard/ECharts 原生渲染,同 MetricsPage 套路)+ `narrative` 三段(纯文本段落)+ 完整 `markdown`(复制 / 下载 .md 工件)。不引库、不 `v-html`。
- Pros: 零新依赖、无 XSS 面;复用现有组件与测试范式;契合前端测试最小行为闸的 ROI 取向。
- Cons: 不在页内呈现富格式 Markdown(列 future)。

**B. 引 `marked` + `DOMPurify` 页内渲染 HTML** —— Pros: 富格式好看。Cons: 2 个新依赖 + 必须严谨净化 LLM 输出;XSS 责任面增大。

**C. 整份 Markdown 当 `<pre>` 纯文本贴** —— Pros: 最简。Cons: 可读性差,结构化数字无法用图表呈现。

### Decision

选 A。后端一份响应供三种用途:结构化数字走原生组件、叙述走文本、完整 Markdown 供下载/复制。前端不引 markdown 库、不使用 `v-html`。

### Consequences

正向:
- 零新前端依赖、无 XSS 注入面;复用 ECharts/StatCard 与 happy-dom 行为测试;UI 细节人工验收、自动化只留最小行为闸。

负向 / 成本:
- 页内不渲染富格式 Markdown(列 future enhancement)。
- 下载的 `.md` 与页面展示内容须保持一致(同一后端响应,降低不一致风险)。
