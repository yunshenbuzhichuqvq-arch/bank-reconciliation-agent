# ADR-076: 鉴权依赖替换边界与集成点 —— 完全替换、无后门

- Status: Accepted (2026-06-22)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/api/dependencies.py(verify_jwt), src/bank_reconciliation_agent/api/v1/router.py(全局 Depends(verify_jwt)), src/bank_reconciliation_agent/api/v1/auth.py(登录豁免+审计日志), src/bank_reconciliation_agent/main.py(auth_router 平级挂载), tests/auth_helpers.py(demo_bearer_headers), decisions/ADR-040(SSE fetch+ReadableStream 复用 getDefaultHeaders), decisions/ADR-074(decode_token), decisions/ADR-075(seed 账号)

## Context

全站鉴权单点:`router.py` 给 `api_router` 挂全局 `Depends(require_demo_user)`。替换为 JWT 须处理四边界:① 登录接口自身不能要 token;② ARQ worker 不走 HTTP;③ SSE 能否带 token;④ 现有 19 个 API 测试用 `X-User-ID` 如何适配。需求 F7 要求接口访问控制 + 日志记录。

## Options Considered

- **(a) 替换策略**:完全替换 `verify_jwt` + 不留 `X-User-ID` 后门 + 不加 auth toggle(语义单一诚实、无可绕过路径)vs 保留兼容/toggle(平滑但留后门=安全隐患,与真实保护矛盾)。
- **(b) 登录豁免实现**:登录路由挂在全局依赖之外(边界显式)vs 全局依赖内 `if` 豁免路径(字符串判断脆弱,反模式)。
- **(c) 测试适配**:conftest/helper 走真实登录拿 token(覆盖真实链路、诚实)vs 测试保留 header 后门(与完全替换矛盾)。

## Decision

完全替换 `require_demo_user` → `verify_jwt`(解析 Bearer、验签+验 exp、取 `sub` 存 `request.state.user_id`;失败 401);`get_current_user_id`/`CurrentUserId` 不变,下游 services 零改动。登录接口 `POST /auth/login` 挂全局依赖**之外**,失败统一 401 不区分(防枚举)。ARQ worker `user_id` 沿用 job 参数不引入 JWT。SSE 经 fetch+ReadableStream(ADR-040)用 `getDefaultHeaders` 注入 `Authorization`。测试用 `auth_helpers` 收敛 Bearer 头。登录成功/失败用 structlog 审计(username+结果,**不记密码**)。

## Consequences

- 正面:鉴权语义单一无后门;下游 services 与 worker 零改动;SSE 因既有 fetch 架构天然兼容;登录可审计。
- 负面:测试改动面大(19 文件经 helper 适配);无 toggle 意味所有环境强制登录(本地靠 seed 兜底);`/auth/login` 豁免须随路由结构维护,漏挂全局依赖会越权,需 review 把关。

## 实现注记 (2026-06-22 stage-jwt 收尾)

- `verify_jwt` 对缺失 / 非 Bearer / 验签失败 / 过期 / sub 空五类统一 401。
- 豁免落地:`main.py` 把 `auth_router` 与 `api_router` 平级 include(prefix 同为 `api_v1_prefix`),`auth_router` 不挂依赖;`/health` 本就是 `app.get` 天然豁免。
- **SSE 零改源码**:`getDefaultHeaders` 改返回 `{Authorization: Bearer}`,`stream.ts` 复用注入点——ADR-040 当初否决原生 `EventSource` 恰好使 SSE 能带自定义头。
- 测试迁移:19 文件 `X-User-ID` → `tests/auth_helpers.demo_bearer_headers()`;审计日志经 caplog 实测 password 不入日志;`X-User-ID` 在 src/tests/frontend 归零。
