# ADR-074: JWT 鉴权方案与依赖选型 —— HS256 + access-only + PyJWT + bcrypt

- Status: Accepted (2026-06-22)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/security.py(create_access_token/decode_token/hash_password/verify_password), src/bank_reconciliation_agent/core/config.py(jwt_secret_key/jwt_algorithm/jwt_access_token_expire_minutes), pyproject.toml(pyjwt/bcrypt), decisions/ADR-075(凭据来源与 env 注入), decisions/ADR-076(verify_jwt 消费 decode_token)

## Context

现状 `require_demo_user` 直接信任 `X-User-ID == demo_user`,无签发/验签/过期(MVP-0 演示鉴权)。需求 F7 要求 JWT 登录鉴权,§8.2 要求线上接口 JWT 保护。需定 token 机制、签名算法、JWT 库、密码哈希库;项目无任何现成 auth 依赖,均为新增。

## Options Considered

- **(a) Token 机制**:access-only(单 token 带 exp,无服务端存储,实现最小)vs access+refresh(体验顺但需 refresh 存储/轮换/撤销,当前 scope 属 over-engineering)。
- **(b) 签名算法**:HS256(对称单密钥,配置最简,密钥泄露即可伪造)vs RS256(私签公验,适合多服务/第三方,单体无收益)。
- **(c) JWT 库**:PyJWT(主流轻量、维护活跃)vs python-jose(功能更全但维护弱、冗余)。
- **(d) 密码哈希**:bcrypt 直接调用(依赖层薄,无 passlib↔bcrypt 版本告警)vs passlib[bcrypt](统一抽象但多一层、单算法不需要)。

## Decision

**access-only + HS256 + PyJWT + bcrypt**。`create_access_token(sub)` / `decode_token(token)` 用 HS256,密钥与有效期从 `Settings`;`sub` = `username`(即 `user_id` 语义);默认有效期 720 分钟(12h)可配;新增依赖 PyJWT、bcrypt。

## Consequences

- 正面:无服务端会话;单密钥单算法配置最简;依赖层薄;`sub=username` 使下游 `user_id` 零偏差。
- 负面:token 无法主动撤销(登出仅前端清,exp 前仍有效);HS256 单密钥泄露即可伪造,secret 必须 env 注入且生产必改;无 refresh,过期需重登。

## 实现注记 (2026-06-22 stage-jwt 收尾)

- `core/security.py` 落地四函数;`create_access_token` 用 `datetime.now(UTC)+timedelta` 避免 naive datetime。
- **设计-实现差异(已修)**:spec 给的开发默认 `jwt_secret_key`("dev-insecure-secret-change-me",29 bytes)< HS256 推荐 32 bytes,PyJWT `decode` 抛 `InsecureKeyLengthWarning`;TASK-JWT-6 补到 44 bytes 占位串消除。`test_security` 篡改测试初版"替换末字符"有 ~5% base64url 等价编码假阴性,TASK-JWT-6 改为追加字符的确定性构造。
