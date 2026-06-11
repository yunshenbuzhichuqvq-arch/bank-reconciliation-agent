# ADR-026: 记忆引擎独立 SQLite 存储,与主库解耦

- Status: Accepted (2026-06-10)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/memory/engine.py, services/memory/{short_term,long_term,summary}.py, core/config.py, tests/conftest.py, decisions/ADR-023

## Context

PRD §7 设计原则:记忆引擎全部基于 SQLite(不引 Redis),**生产也是 SQLite**。但现状 `db/session.py:get_engine()` 是单一引擎 = `settings.mysql_dsn`(生产 MySQL;测试 conftest 覆写为临时 sqlite)。主业务表(台账/队列/任务/日志)挂该引擎,用跨库变体写法(`BigInteger().with_variant(Integer,"sqlite")` 等)。记忆三表(短/长/摘要,PRD §6.11-6.13)指定 SQLite-only。需决定记忆表挂哪个引擎、写入如何与现有 MySQL 核心事务(ADR-023)协调。

## Options

- **A. 独立 SQLite 引擎(采纳)** — 新增 `settings.memory_sqlite_path`,记忆走专属 SQLite engine,与 `get_engine()` 解耦;记忆表 SQLite-native(无需 MySQL 变体)。写入走 ADR-023 副作用通道(核心 MySQL 事务**之后**、非阻塞):短期/每次决策后、长期/人工确认(`review.approve`)后、摘要/满 20 笔。隔离:短期+摘要 by `thread_id`、长期 by `user_id`。
  - Pros: 落实 PRD SQLite-only;与主库彻底解耦(记忆故障不污染主事务);测试用临时 sqlite;记忆表写法更简单。
  - Cons: 双存储引擎(MySQL 主 + SQLite 记忆)并存,跨存储无事务一致性——但记忆本就是非阻塞副作用,可接受。
- **B. 复用 `get_engine()`** — 记忆表走主引擎。Pros: 单引擎。 Cons: 生产即 MySQL,违反 PRD「记忆 SQLite-only」;记忆写入进主库,与「非阻塞副作用、故障隔离」冲突。
- **C. 记忆进 MySQL 主库表** — 同 B 的违反,且把易变记忆塞进核心库。

## Decision

采用 **A**。记忆 = 独立 SQLite 存储;写入一律经 ADR-023 副作用通道(事务后、非阻塞、失败仅 WARNING)。

## Consequences

- 正面:SQLite-only 落实;记忆与主链路故障隔离;测试简单。
- 负面:双引擎并存,config 与 conftest 各需配一处 memory 路径;跨存储最终一致(记忆滞后主库一瞬),对非阻塞副作用语义可接受;查询必带隔离键(长期 by user_id、短期/摘要 by thread_id),沿用红线「业务查询按 user_id 过滤」。
