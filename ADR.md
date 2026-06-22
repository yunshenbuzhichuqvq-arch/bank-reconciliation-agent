# Stage JWT — Architectural Decisions

> 本 stage 把全站"信任 `X-User-ID` header"的演示鉴权(`api/dependencies.py:require_demo_user`)替换为真实 JWT 鉴权,跑通"登录页 → 查库验密 → 签发 token → 带 token 请求 → 后端校验"链路。
> 对齐需求 `requirements-analysis.md` F7(系统管理与安全)+ §8.2(线上接口 JWT 保护、Key 走 env)+ `system-prd.md` §3.3 阶段三可选项。
> Scope:最小真实登录,**不做**多用户数据隔离 / 注册 / 改密 / RBAC / refresh token。单一预置账号 `demo_user`。
> 编号沿用 `decisions/` 全局递增惯例(上一条 ADR-073),非 CLAUDE.md 模板的 `ADR-N.X`。

---

## ADR-074: JWT 鉴权方案与依赖选型
**Slug**: `jwt-auth-scheme-and-deps`
**Status**: proposed
**Date**: 2026-06-22

### Context
现状 `require_demo_user` 直接信任请求头 `X-User-ID` 是否等于硬编码 `demo_user`,无签发、无验签、无过期——属 MVP-0 演示鉴权。需求 F7 要求"JWT 登录鉴权",§8.2 要求"线上接口使用 JWT 保护"。需确定:token 机制、签名算法、JWT 库、密码哈希库。本 stage 无任何现成 auth 依赖,均为新增。

### Options Considered

**(a) Token 机制**
- **access-only(单 token,带 exp)** — Pros: 无服务端会话/存储,实现最小,演示足够。Cons: 无法主动撤销,过期即需重新登录。
- access + refresh — Pros: 短 access + 长 refresh,体验更顺,可轮换。Cons: 需 refresh 存储/轮换/撤销逻辑,本 stage scope 下纯属 over-engineering(无多用户、无长会话诉求)。

**(b) 签名算法**
- **HS256(对称密钥)** — Pros: 单服务单密钥,配置最简,从 `Settings` 读一个 secret 即可。Cons: 签发/验签共用密钥,密钥泄露即可伪造,需保护 secret。
- RS256(非对称) — Pros: 私钥签发、公钥验签,适合多服务/第三方验签。Cons: 需管理密钥对,单体演示项目无收益。

**(c) JWT 库**
- **PyJWT** — Pros: 主流、轻量、维护活跃,API 直接(`jwt.encode/decode`)。Cons: 仅 JWT,不含 OAuth 套件(本项目不需要)。
- python-jose — Pros: 含 JWK/JWE 等更全。Cons: 维护活跃度弱于 PyJWT,功能冗余。

**(d) 密码哈希库**
- **bcrypt(直接调用)** — Pros: 直接 `bcrypt.hashpw/checkpw`,依赖层薄,无 passlib↔bcrypt 版本告警问题。Cons: API 较裸,需自己处理 encode/盐。
- passlib[bcrypt] — Pros: 统一 `CryptContext` 抽象,支持算法迁移。Cons: 多一层依赖;passlib 1.7.x 读取新版 bcrypt 版本号有已知告警;本项目单算法不需要迁移抽象。

### Decision
**access-only + HS256 + PyJWT + bcrypt**。
- JWT 工具新模块封装 `create_access_token(sub)` / `decode_token(token)`,HS256,密钥与有效期从 `Settings` 读。
- `sub` claim = `username`(即现有 `user_id` 语义,字符串 `"demo_user"`),解码后存 `request.state.user_id`,下游 `CurrentUserId` 注入语义不变。
- 默认有效期 **720 分钟(12h)**,可配置。
- 新增后端依赖:`PyJWT`、`bcrypt`(经 `uv add`,版本由 lock 解析)。

### Consequences
- 正面:无服务端会话存储;单密钥单算法配置最简;依赖层薄;`sub=username` 使下游 `user_id` 语义与存量数据零偏差。
- 负面:token 无法主动撤销,登出仅前端清除、token 在 exp 前仍有效(见 ADR-077);HS256 单密钥泄露即可伪造,secret 必须经 env 注入且生产必改(见 ADR-075);过期后需重新登录(无 refresh)。

---

## ADR-075: `t_user` 数据模型、幂等 seed 与凭据来源
**Slug**: `user-table-seed-and-credential-source`
**Status**: proposed
**Date**: 2026-06-22

### Context
系统当前无用户表、无密码存储,凭据等于硬编码字符串。引入真实登录需持久化账号与密码哈希。本 stage 不做多用户隔离,故只需单一预置账号 `demo_user`。需确定:凭据存哪、何时 seed、密码/密钥从哪来、是否触碰存量业务表。AGENTS.md 约定:SQLAlchemy Core(非 ORM)、`Table`+`MetaData`、service 模块级懒 `create_all`、`db/schema.sql` 与 `Table` 必须同步(红线6)。

### Options Considered

**(a) 凭据存储**
- **新建 `t_user` 表(SQLAlchemy Core)** — Pros: 与现有持久化架构一致;登录=查库验密,完整展示标准链路;未来扩多用户表已就位。Cons: 多一张表 + schema.sql 同步成本。
- 配置/env 预置账号(username + bcrypt 哈希串写 Settings) — Pros: 零建表零迁移。Cons: 凭据入配置 hacky、扩展性差、不像真实系统(brainstorm 已否决)。

**(b) seed 时机**
- **service `_ensure_initialized()` 内幂等 seed** — Pros: 沿用项目懒 `create_all` 惯例,首次访问即就绪,无需额外步骤。Cons: seed 在首次 DB 访问时触发(非启动时)。
- 独立 `scripts/seed_user.py` / migration — Pros: 显式、可控。Cons: 项目无 migration 体系(手工 schema.sql + 懒 create_all),引入显式 seed step 与现状不一致。

**(c) 凭据来源**
- **env 注入(`demo_user_password`、`jwt_secret_key`),开发默认值 + 启动告警** — Pros: 符合 §8.2"env 管理密钥";本地开箱即用;生产强制改。Cons: 开发默认若漏改是隐患(用启动 warning 缓解)。
- 硬编码进代码 — Pros: 最省事。Cons: 违背 §8.2,凭据进版本库,直接否决。

### Decision
- 新建 **`t_user`** 表(SQLAlchemy Core,跨库 `with_variant`):`id`(自增主键,`BigInteger().with_variant(Integer,"sqlite")`)、`username`(unique, not null)、`password_hash`(not null)、`created_at`。**同步写入 `db/schema.sql`**(红线6)。
- **`username` 即业务 `user_id`**(字符串);`t_user.id` 仅内部主键,**业务表不加 `t_user.id` 外键、不改动**——存量数据 `user_id="demo_user"` 零迁移。
- 在 auth service `_ensure_initialized()` 内 `create_all` 后**幂等 seed** `demo_user`(已存在则跳过)。
- 新增 Settings:`jwt_secret_key`(开发默认 + 用默认时启动 `warning`)、`jwt_algorithm="HS256"`、`jwt_access_token_expire_minutes=720`、`demo_user_password`(开发默认 + 用默认时启动 `warning`)。

### Consequences
- 正面:登录走标准"查库验密";`username=user_id` 使业务表零改动、存量数据零迁移;凭据/密钥经 env 满足 §8.2;扩多用户的表结构已就位。
- 负面:多一张表与 schema.sql 同步项;懒 seed 在首次访问触发(非启动);开发默认密码/密钥若被带到生产是隐患,仅以启动 warning 防御(不强制 fail-fast,保持本地易用)。

---

## ADR-076: 鉴权依赖替换边界与集成点
**Slug**: `auth-dependency-replacement-boundary`
**Status**: proposed
**Date**: 2026-06-22

### Context
全站鉴权是单点:`api/v1/router.py` 给整个 `api_router` 挂 `Depends(require_demo_user)`。替换为 JWT 校验须处理四个边界:① 登录接口自身不能要求 token;② ARQ worker 不走 HTTP;③ SSE 流式请求能否带 token;④ 现有大量 API 测试用 `X-User-ID` header,如何适配。需求 F7 还要求"接口访问控制 + 日志记录"。

### Options Considered

**(a) 替换策略**
- **完全替换 `require_demo_user` → `verify_jwt`,不留 `X-User-ID` 后门、不加 auth toggle** — Pros: 鉴权语义单一诚实,无"可绕过"路径,符合 §8.2。Cons: 所有调用方(前端 + 测试)必须改带 Bearer,改动面集中但量大。
- 保留 `X-User-ID` 作兼容/加 `auth_enabled` toggle — Pros: 平滑过渡、测试少改。Cons: 留下可绕过鉴权的后门=安全隐患;与"真实保护"目标矛盾;项目其他 toggle 是功能降级,鉴权 toggle 性质不同。

**(b) 登录接口豁免实现**
- **登录路由挂在全局鉴权依赖之外(独立 router / 不继承 `api_router` 的 dependencies)** — Pros: 豁免边界显式、不易漏。Cons: 路由组织略调整。
- 全局依赖内对 `/auth/login` 路径做 if 豁免 — Pros: 路由结构不动。Cons: 路径字符串判断脆弱、易漏、反模式。

**(c) 测试适配**
- **`conftest.py` 提供 `auth_token` / 已认证 client fixture,测试走真实登录拿 token** — Pros: 测试覆盖真实鉴权链路,诚实。Cons: 需改动现有用 `X-User-ID` 的测试(集中在 fixture 收敛)。
- 测试保留 header 后门跳过 JWT — Pros: 测试几乎不改。Cons: 与(a)完全替换矛盾,留后门。

### Decision
**完全替换,不留后门、不加 auth toggle**:
- `require_demo_user` → `verify_jwt`:解析 `Authorization: Bearer`,验签 + 验 exp(失败 401),取 `sub` 存 `request.state.user_id`;`get_current_user_id` / `CurrentUserId` 不变,**下游 services 零改动**。
- **登录接口** `POST {api_v1_prefix}/auth/login` 挂在全局鉴权依赖**之外**;登录失败统一 401、**不区分**"用户不存在/密码错"(防账号枚举)。
- **ARQ worker**:`user_id` 沿用 job 参数(upload 时已鉴权入队),**不引入 JWT 校验**。
- **SSE**:前端 SSE 走 `fetch + ReadableStream`(ADR-040,当初否决原生 `EventSource` 正因其不能带自定义头),`getDefaultHeaders()` 注入 `Authorization` 即可覆盖——**须确认 SSE 请求也带上 token**。
- **测试**:`conftest.py` 增 `auth_token` + 已认证 client fixture,现有用 `X-User-ID` 的 API 测试改走真实登录(收敛在 fixture)。
- **日志(F7)**:登录成功/失败用现有 `structlog` 记审计日志(含 username、结果,**不记密码**)。

### Consequences
- 正面:鉴权语义单一无后门;下游 services 与 worker 零改动;SSE 因既有 fetch 架构天然兼容;登录事件可审计。
- 负面:测试改动面大(所有 API 测试经 fixture 适配);无 auth toggle 意味着所有环境(含本地)强制登录,本地开发依赖 seed 账号(ADR-075 已保证开箱即用);`/auth/login` 豁免必须随路由结构维护,漏挂全局依赖会导致越权,需 review 把关。

---

## ADR-077: 前端登录态与 token 存储
**Slug**: `frontend-auth-state-and-token-storage`
**Status**: proposed
**Date**: 2026-06-22

### Context
前端 `api/client.ts:6` 写死 `{ "X-User-ID": "demo_user" }` 注入每个请求;有 `vue-router` 但无登录页、无路由守卫,`AppShell.vue` 顶栏写死显示 `demo_user`。需求 F7 前端要求:登录页、当前用户展示、登出。需确定:token 存哪/怎么带、路由守卫粒度、401 处理、用户态来源。约束:前端不引新依赖(Element Plus 已有)、跨域走 Vite proxy。

### Options Considered

**(a) token 存储与携带**
- **localStorage + `Authorization: Bearer`** — Pros: 契合 `client.ts` 既有 header 注入模式,改动最小;SPA 最常见;前端可直读登录态。Cons: XSS 可读 token。
- httpOnly Cookie — Pros: 防 XSS 读取。Cons: 需处理 CSRF / CORS withCredentials / 前端无法直读登录态(需 `/me`),改动大(brainstorm 已否决)。

**(b) 路由守卫粒度**
- **全局 `beforeEach` 守卫** — Pros: 一处统一拦截未登录,新增受保护页自动覆盖。Cons: 需维护公开路由白名单(`/login`)。
- 逐页守卫 — Pros: 精确。Cons: 易漏、重复。

**(c) 401 处理**
- **`client.ts` 响应拦截统一处理 401 → 清 token → 跳 `/login`** — Pros: 一处兜底 token 过期/失效。Cons: 需区分登录接口自身的 401(不应再跳转)。
- 各页各自处理 — Pros: 灵活。Cons: 分散易漏。

### Decision
- **localStorage + Bearer**:登录成功存 token 到 localStorage;`client.ts` 读出注入 `Authorization: Bearer`,**移除写死的 `X-User-ID`**;SSE 同源走 `getDefaultHeaders()`(ADR-076)。
- **登录页** `/login`(Element Plus 表单)→ `POST /auth/login` → 存 token → 跳首页。
- **全局路由守卫** `beforeEach`:无 token 访问受保护页 → 跳 `/login`;已登录访问 `/login` → 跳首页;公开白名单仅 `/login`。
- **401 拦截**:`client.ts` 拦截非登录接口的 401 → 清 token → 跳 `/login`。
- **`AppShell.vue`**:顶栏改显当前登录用户名 + **登出按钮**(清 token 跳 `/login`)。
- 用户名来源:登录响应或 token 解出的 `sub`(前端轻量解析,不验签)。

### Consequences
- 正面:复用既有 header 注入与 fetch 架构,改动集中在 `client.ts` + router + 登录页 + AppShell;token 过期有统一兜底;满足 F7 前端三要求。
- 负面:localStorage 中 token 受 XSS 威胁(演示项目可接受);无 refresh,token 过期需重新登录;路由守卫需维护公开白名单,加新公开页时勿漏。
