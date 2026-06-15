# ADR-044: 前端双路径并存——保留同步 upload,新增流式工作台

- Status: Accepted (2026-06-15)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/pages/WorkbenchPage.vue, frontend/src/pages/UploadPage.vue, frontend/src/router/index.ts, decisions/ADR-036(后端双路径), decisions/ADR-043

## Context

现有前端有完整同步流程:Upload 页(upload→start)+ 看板/台账/复核页(MVP-1 已验收)。V1-2 新增流式工作台(走 SSE)。要决定流式路径与现有同步路径的关系。后端 ADR-036 已确立"同步 upload 保留 + 新增流式端点"双路径哲学。

## Options

- **A. 双路径并存,同步页零回归(采纳)** — 现有页不动;新增独立 Agent 工作台页 + 路由(流式路径);场景选择对 Upload 页增量。Pros: 镜像后端 ADR-036;现有页零回归;工作台独立高光页;两套互不干扰。Cons: 上传入口出现两处,需 UI 说明区分。
- **B. 用流式工作台替换现有 Upload/看板** — Cons: 破坏现有页(回归风险);与后端"同步零回归"不对称;推翻 MVP-1 已验收页。
- **C. 同步页内嵌流式(同页两模式)** — Cons: 单页职责膨胀、状态耦合、组件边界差。

## Decision

采用 **A**。新增独立工作台页 + 路由(流式);Upload/看板/台账/复核同步页保留,仅对 Upload 页加场景选择;看板保持同步(ADR-043)。前端"同步零回归 + 新流式路径",对齐 ADR-036。

## Consequences

- 正面:现有页零回归、双路径对称、工作台独立高光、组件边界清晰。
- 负面:两处上传入口需 UI 说明;两套路径少量概念重复(demo 可接受)。

## Implementation Note (V1-2 收尾)

新增 `WorkbenchPage.vue` + `/workbench` 路由 + AppShell 导航项;`EventTimeline`/`EventCard` 渲染事件流。Upload 页加场景选择(`SCENARIO_META` 两场景 + 字段模板提示 + 传 `scenario_type`),同步 upload 行为零回归(默认 `BANK_ENTERPRISE`)。现有 4 页 + `client.spec.ts` 零回归。过程坑(review B2):工作台初版场景写死 `BANK_ENTERPRISE`(单 radio + ref 字面量类型),清算无法流式;`TASK-V1-2.6` 修复为复用 `SCENARIO_META` 两场景 + 透传。
