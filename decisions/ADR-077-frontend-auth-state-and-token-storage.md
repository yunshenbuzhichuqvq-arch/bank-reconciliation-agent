# ADR-077: 前端登录态与 token 存储 —— localStorage + Bearer

- Status: Accepted (2026-06-22)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/api/client.ts(Bearer 注入/401 拦截/getDefaultHeaders/login), frontend/src/composables/useAuth.ts(localStorage token), frontend/src/router/index.ts(beforeEach 守卫), frontend/src/pages/LoginPage.vue, frontend/src/components/AppShell.vue(当前用户+登出), decisions/ADR-040(getDefaultHeaders 注入点), decisions/ADR-076(SSE 带 token)

## Context

前端 `client.ts` 写死 `{X-User-ID: demo_user}` 注入每请求;有 vue-router 但无登录页/守卫,`AppShell` 顶栏写死 `demo_user`。需求 F7 前端要求登录页、当前用户展示、登出。需定 token 存哪/怎么带、守卫粒度、401 处理、用户态来源。约束:前端不引新依赖、跨域走 Vite proxy。

## Options Considered

- **(a) token 存储与携带**:localStorage + `Authorization: Bearer`(契合既有 header 注入、改动最小、可直读登录态;XSS 可读)vs httpOnly cookie(防 XSS 但需 CSRF / withCredentials / `/me` 接口,改动大,已否决)。
- **(b) 路由守卫粒度**:全局 `beforeEach`(一处拦截,新页自动覆盖)vs 逐页(易漏、重复)。
- **(c) 401 处理**:`client.ts` 拦截统一处理(一处兜底,需排除登录接口)vs 各页处理(分散易漏)。

## Decision

localStorage + Bearer:登录存 token,`client.ts` 注入 `Authorization`、移除 `X-User-ID`,SSE 走 `getDefaultHeaders`。登录页 `/login`(Element Plus)。全局 `beforeEach` 守卫,公开白名单仅 `/login`。`client.ts` 拦截非登录接口 401 → 清 token 跳 `/login`。`AppShell` 顶栏显当前用户 + 登出。用户名来自 token 解 `sub`(前端轻量解析,不验签)。

## Consequences

- 正面:复用既有 header 注入与 fetch 架构,改动集中;token 过期有统一兜底;满足 F7 前端三要求。
- 负面:localStorage token 受 XSS 威胁(演示可接受);无 refresh 过期需重登;路由守卫需维护公开白名单。

## 实现注记 (2026-06-22 stage-jwt 收尾)

- `useAuth.ts`:localStorage key `auth_token`,`currentUsername` 解 base64url JWT payload(处理 padding / url-safe + try/catch 容错),`storage()` 处理 SSR `window` undefined。
- `client.ts`:request 拦截器有 token 才注入;response 401 且 `url !== "/auth/login"` → `clearToken` + 动态 `import("../router")` 跳转(避免循环依赖)。
- 最小行为闸:`client.spec` 验 Bearer 注入 + 非登录 401 清 token 跳转;router 守卫重定向。
- **已知小债(#3,未修)**:`AppShell` 用裸 `route.path;` 制造 reactive 依赖刷新用户名,依赖"登录后必跳转",略脆弱;留作 follow-up。
