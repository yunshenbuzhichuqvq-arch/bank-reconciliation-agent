# ADR-075: t_user 数据模型、幂等 seed 与凭据来源

- Status: Accepted (2026-06-22)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/auth.py(user_table/AuthService/_ensure_initialized/authenticate), src/bank_reconciliation_agent/db/schema.sql(t_user DDL), src/bank_reconciliation_agent/core/config.py(demo_user_password), src/bank_reconciliation_agent/main.py(开发默认凭据 warning), decisions/ADR-074(hash_password), decisions/ADR-076(username 即 user_id 下游零改动)

## Context

系统无用户表、无密码存储,凭据=硬编码字符串。引入真实登录需持久化账号与密码哈希;本 stage 不做多用户隔离,只需单一预置 `demo_user`。需定:凭据存哪、何时 seed、密码/密钥来源、是否触碰存量业务表。AGENTS 约定 SQLAlchemy Core + 模块级 `Table` + 懒 `create_all`,`db/schema.sql` 与 `Table` 同步(红线6)。

## Options Considered

- **(a) 凭据存储**:新建 `t_user` 表(与现有架构一致、登录=查库验密、扩展就位)vs 配置/env 预置账号(零建表但 hacky、扩展差,已否决)。
- **(b) seed 时机**:service `_ensure_initialized` 懒幂等 seed(沿用懒 `create_all` 惯例)vs 独立 script/migration(项目无 migration 体系,不一致)。
- **(c) 凭据来源**:env 注入 + 开发默认 + 启动 warning(符合 §8.2、本地开箱即用、生产强制改)vs 硬编码(违背 §8.2,否决)。

## Decision

新建 `t_user`(id / username unique / password_hash / created_at,跨库 `with_variant`),`schema.sql` 同步;**`username` 即业务 `user_id`**,`t_user.id` 仅内部主键、业务表不加外键不改动、存量零迁移;`_ensure_initialized` 内 `create_all` 后幂等 seed `demo_user`;新增 Settings `jwt_secret_key` / `jwt_algorithm` / `jwt_access_token_expire_minutes` / `demo_user_password`,开发默认值启动 warning(不 fail-fast)。

## Consequences

- 正面:登录走标准查库验密;`username=user_id` 业务表零改动零迁移;凭据/密钥 env 满足 §8.2;扩多用户表已就位。
- 负面:多一张表与 `schema.sql` 同步项;懒 seed 首次访问触发(非启动);开发默认凭据若带到生产是隐患,仅启动 warning 防御。

## 实现注记 (2026-06-22 stage-jwt 收尾)

- `services/auth.py` 模块级单例 `auth_service`;`_ensure_initialized` 用 `engine.begin()` 事务幂等 seed(select 查在再 insert);`authenticate` 用 `engine.connect()` 只读 + `scalar_one_or_none`。
- `schema.sql` 的 `t_user` DDL 落在文件首部,字段与 `user_table` 一致(红线6 验证通过)。
- TASK-JWT-6 把 `jwt_secret_key` 默认值改 ≥32 bytes 时,**同步**更新了 `main.py` 的 warning 比对字符串(避免改默认值后 warning 不触发,`test_create_app_warns` 保持 2 次)。
