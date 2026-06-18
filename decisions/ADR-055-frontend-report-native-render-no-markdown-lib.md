# ADR-055: 前端报告渲染 —— 原生组件 + .md 下载,不引 markdown 库 / 不用 v-html

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/pages/ReportPage.vue, frontend/src/api/report.ts, frontend/src/router/index.ts, decisions/ADR-048(指标可视化 ECharts), decisions/ADR-049(前端行为测试 test-utils + happy-dom)

## Context

报告输出是 Markdown,其 narrative 段落是 **LLM 生成内容**;前端当前无 markdown 渲染库。若用 markdown→HTML + `v-html` 渲染 LLM 输出,等于开 XSS 注入口。如何在不引库、不开 XSS 面的前提下满足"展示 Markdown 报告"。

## Options

**A. 原生组件 + 文本 + .md 下载(选定)** —— 后端同时返回结构化 `metrics`(前端用 StatCard/ECharts 原生渲染,同 MetricsPage 套路)+ `narrative` 三段(纯文本段落)+ 完整 `markdown`(复制 / 下载 .md 工件)。不引库、不 `v-html`。
- Pros: 零新依赖、无 XSS 面;复用现有组件与测试范式;契合前端测试最小行为闸的 ROI 取向。
- Cons: 不在页内呈现富格式 Markdown(列 future)。

**B. 引 `marked` + `DOMPurify` 页内渲染 HTML** —— Pros: 富格式好看。Cons: 2 个新依赖 + 必须严谨净化 LLM 输出;XSS 责任面增大。

**C. 整份 Markdown 当 `<pre>` 纯文本贴** —— Pros: 最简。Cons: 可读性差,结构化数字无法用图表呈现。

## Decision

选 A。后端一份响应供三种用途:结构化数字走原生组件、叙述走文本、完整 Markdown 供下载/复制。前端不引 markdown 库、不使用 `v-html`。

## Consequences

正向:
- 零新前端依赖、无 XSS 注入面;复用 ECharts/StatCard 与 happy-dom 行为测试;UI 细节人工验收、自动化只留最小行为闸。

负向 / 成本:
- 页内不渲染富格式 Markdown(列 future enhancement)。
- 下载的 `.md` 与页面展示内容须保持一致(同一后端响应,降低不一致风险)。
