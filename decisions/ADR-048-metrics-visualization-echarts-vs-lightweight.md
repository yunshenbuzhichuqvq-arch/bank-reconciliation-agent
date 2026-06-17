# ADR-048: 指标可视化方案——ECharts 引入 vs 轻量自绘

- Status: Accepted (2026-06-16)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/pages/MetricsPage.vue, frontend/package.json, decisions/ADR-040(手写 SSE 客户端), decisions/ADR-041(不引 Pinia)

## Context

指标仪表板要展示分布(异常类型 / Fallback / 置信度)、趋势(Token 消耗)、占比(平账率)。前端当前未装图表库(`package.json` 仅 element-plus + axios + vue)。

张力:`overall-architecture.md` §2.1 写明技术栈含 ECharts;但本项目前端有明确最小依赖倾向——ADR-040 手写 SSE 客户端(不引 EventSource 库)、ADR-041 不引 Pinia。引入 ECharts 与该倾向冲突。

## Options

- **A. 引入 ECharts**(裸 echarts 或 vue-echarts,按需引入控体积) — Pros: 图表表现力强、贴 PRD 架构原文、"作品版"观感好、分布/趋势图开箱即用。Cons: 新增较重前端依赖(体积大),打破最小依赖一致性(ADR-040/041),需按需 import 控体积。
- **B. Element Plus 卡片 + 进度条 + 表格 + 轻量自绘(SVG/CSS)** — Pros: 零新依赖、与 ADR-040/041 一致、足够展示数值型指标。Cons: 分布/趋势图表现力弱(柱状/折线需手写 SVG 或进度条近似)、视觉冲击不如 ECharts。
- **C. 极轻量图表库(uPlot / unovis 等)** — Pros: 体积远小于 echarts、有真图表。Cons: 再引一个非 PRD 原文的库、生态/示例少、收官 stage 不值得评估新库。

## Decision

采用 A:引入 ECharts,按需引入(仅 import BarChart/LineChart/PieChart + 必要的 Grid/Tooltip/Legend 等组件,避免全量)。指标仪表板是 §4.8 核心高光、ECharts 是 PRD 架构明文,作品版值得这一个依赖;以按需引入控制体积,局部打破前端最小依赖一致性(ADR-040/041)是有意识的取舍。

## Consequences

- 正面:分布/趋势图表现力强、贴 PRD 架构原文、作品版观感强。
- 负面:前端依赖变重(echarts 体积),需按需引入控体积;局部打破 ADR-040/041 最小依赖一致性(已接受)。
- 被否的 B(轻量自绘)价值:零依赖、风格一致,但图表表现力/视觉冲击不足,不匹配 §4.8 高光定位。

## Implementation Note (V1-3 收尾)

V1-3 收尾复审发现 `npm run build` 报 chunk > 500kB(产物 ~1.68MB gzip ~563kB),"按需引入控体积"疑似未完全生效(echarts 可能仍接近全量打入,或与 element-plus 全量叠加)。登记为 open question,留待后续核实 import 粒度与 vite tree-shaking 是否按本 ADR 预期工作(必要时改 manualChunks 或确认仅 import 用到的图表/组件模块)。
