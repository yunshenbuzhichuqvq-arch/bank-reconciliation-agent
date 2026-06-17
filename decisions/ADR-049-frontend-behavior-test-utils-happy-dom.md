# ADR-049: 前端行为测试基础设施——引入 @vue/test-utils + happy-dom(dev-only)

- Status: Accepted (2026-06-17)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/package.json, frontend/vite.config.ts, frontend/tests/DashboardPage.spec.ts, decisions/ADR-040(手写 SSE 客户端), decisions/ADR-041(不引 Pinia), decisions/ADR-048(为 ECharts 破例)

## Context

V1-3 看板防空壳闸(T6 change request → T3.9)要求"点击启动审计按钮 → 断言 `startLiveReconciliation` 被调"的真行为测试。但现状:vitest 跑默认 node 环境(`vite.config.ts` 无 `test` 块),且未装 `@vue/test-utils` / DOM 模拟库——现有所有页测试都用 `createSSRApp` + `renderToString`(SSR,无法交互)。标准 `mount`+`trigger` 在当前工具链下根本跑不起来。

T3.9 首版(commit `0c57f77`)为绕开此限制,手搓了 200 行无依赖 headless renderer(自实现 `createRenderer` + `@vue/compiler-sfc` 重编译 SFC + 正则改写编译产物 + `new Function` 执行 + 多个 stub)。行为虽真,但强耦合 compiler-sfc 输出格式(Vue 升级即可能 crash)、维护负债重,且违反 T6 "只留一条最小行为闸、不要重写成大测试"的约定。

张力:项目有最小依赖倾向(ADR-040 手写 SSE 客户端、ADR-041 不引 Pinia)。需厘清该倾向是否约束测试依赖。

## Options

- **A. 引入 @vue/test-utils + happy-dom(dev-only,采纳)** — `vite.config.ts` 加 `test.environment = "happy-dom"`,看板闸用标准 `mount`+`trigger`(~10 行)。
  - Pros: 业界标准、不脆弱;dev-only 不进生产 bundle,不触 ADR-040/041 关心的运行时体积;项目自此具备 DOM 交互测试能力,后续页可复用。
  - Cons: +2 个 devDependencies;首次引入 DOM 测试环境,需确认现有 SSR 测试零回归。
- **B. 零依赖,放弃模拟点击** — 不渲染模板,直接验 `startAudit` 调用链。
  - Pros: 零依赖。Cons: 丢"点按钮"交互语义(测函数非按钮);`<script setup>` 下需把逻辑暴露为可测,反而要动组件。
- **C. 维持 headless renderer** — 保留 200 行自搓方案。
  - Pros: 绝对零依赖。Cons: 脆弱(耦合编译产物格式)、维护负债、违反"最小一条"约定。

## Decision

采用 A:引入 `@vue/test-utils` + `happy-dom` 作为 devDependencies,`vite.config.ts` 配 `test.environment`。明确边界:ADR-040/041 的最小依赖倾向针对运行时依赖(bundle 体积 / SSR 复杂度),不约束 dev-only 测试依赖。与 ADR-048(为 §4.8 高光破例引 ECharts)对称——此处为"可靠的行为闸"破一次 dev 依赖之例。

## Consequences

- 正面:看板闸回归 ~10 行标准写法,删 200 行脆弱基础设施;项目获得 DOM 交互测试能力供后续复用;厘清了"最小依赖只管运行时"的边界(可复用判据)。
- 负面:+2 devDependencies;node → happy-dom 环境切换须确认现有 `renderToString` SSR 测试零回归(T3.9 DoD 锁全套绿)。
- 选 happy-dom 而非 jsdom:更轻更快、API 覆盖足够本项目断言;若遇兼容缺口可换 jsdom(同为 `environment` 配置项,迁移成本低)。
- 流程教训:T3.9 指令写"`mount`+trigger"时设计方未核实工具链能否支撑(node env + 无 test-utils),给了落不了地的指令;Codex 撞到"无 mount 能力"时未按 tasks.md 红线停下标注,而是自行决策搞 workaround——与 ADR-045 现状误判教训同构。

## Implementation Note (V1-3 收尾)

返工 commit `eff8fc8`:删净 headless renderer,`DashboardPage.spec.ts` 改标准 `mount(DashboardPage, { global: { plugins: [router] } })` + `flushPromises` + `findAll("button").find(文本)` + `trigger("click")` + 兜底 `mockClear`。依赖 `@vue/test-utils ^2.4.11` + `happy-dom ^20.10.5`,`vite.config.ts` 配 `test.environment="happy-dom"`。全套 27 passed + `npm run build` 绿,node→happy-dom 切换零回归。连带:`WorkbenchPage.spec.ts` 因环境切换把 `readFileSync` 改为 `?raw` 导入(happy-dom 下 `import.meta.url` 路径解析失效),其源码字符串匹配断言属 pre-existing 技术债,未在本 task scope 内处理。
