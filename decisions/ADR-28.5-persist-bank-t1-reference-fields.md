# ADR-28.5: T+1 持久化查询补齐银行流水关联字段

**Slug**: `persist-bank-t1-reference-fields`
**Status**: accepted
**Date**: 2026-07-12

### Context

ADR-28.2 要求 `lookup_t1_context` 从已持久化流水执行真实租户限定查询，并与上传分类复用同一个
确定性 T+1 匹配规则。现有规则同时比较金额、次日 `accounting_date` 和
`reference_no / merchant_order_no / voucher_no` 的交集。

上传阶段的 bank DataFrame 已包含这三个关联字段，但 `t_bank_transaction` 的 SQLAlchemy `Table`、
`db/schema.sql` 和写入映射没有保存它们；clear 表则已经保存。因此，持久化后无法在不丢失判别条件
的前提下复现上传阶段 candidate。仅依赖 bank 表现有列会改变匹配算法，并可能把相同金额、相同日期
但不同业务引用的流水误判为 T+1 candidate。

### Options Considered

- **Option A：为 bank 表补齐三个 nullable 关联字段并同步双 schema（采纳）**
  - Pros：保持现有 T+1 算法和上传/查询结果一致；字段已经存在于标准化输入，不增加新的业务数据源；改动局限于同一表定义、DDL、写入映射和测试。
  - Cons：Stage 28 必须承担一次窄范围 schema 扩展；已有数据库不会被 SQLAlchemy `create_all()` 自动 ALTER，需要使用更新后的 DDL 重建或由操作者显式迁移。
- **Option B：持久化查询只使用 bank 表已有的金额、日期等字段**
  - Pros：无需修改 schema；实现路径较短。
  - Cons：删除 reference 交集这一既有判别条件，改变业务算法并扩大误匹配风险；违反 Stage 28 的零算法漂移边界。
- **Option C：继续把上传阶段预计算 candidate 作为 Tool 事实来源**
  - Pros：无需 schema 变更，也无需再次查询候选流水。
  - Cons：不能证明持久化查询、租户隔离、timeout 或查询失败语义；与真实只读 Tool 的 accepted 边界冲突。

### Decision

采用 **Option A**，并取代 ADR-28.2 中关于 T+1 持久化实现前提的部分；ADR-28.2 的三态结果、
EMPTY/FAILED 区分和工作流 fail-closed 语义保持不变。

- 在 `t_bank_transaction` 增加 nullable `VARCHAR(64)` 字段：`reference_no`、
  `merchant_order_no`、`voucher_no`。
- 同步修改 `src/bank_reconciliation_agent/services/transactions.py` 的 SQLAlchemy `Table` 与 bank
  insert 映射，以及 `src/bank_reconciliation_agent/db/schema.sql` 的 MySQL DDL。两份 schema 必须
  保持字段名、类型和 nullable 语义一致。
- 不为三个字段新增索引。`lookup_t1_context` 先按 `user_id + task_id` 限定任务内 bank rows，再调用
  共享确定性函数；Stage 28 不引入新的全表查询或生产查询优化。
- T+1 匹配规则保持不变：金额相等、bank `accounting_date` 等于 clear `trade_date + 1 day`，且三个
  reference 字段至少一个非空值相交。
- 测试必须证明三个字段能从 bank DataFrame 写入并读回、SQLAlchemy 与 `schema.sql` 对齐、上传分类
  与持久化 Tool 查询对同一 fixture 返回相同 candidate。
- 本 Stage 不引入 Alembic 或自建 migration framework。既有数据库的升级/重建要求必须在 Report
  Back 和 PR 风险中如实说明；不得声称 `create_all()` 会修改已有表。

### Consequences

- 正面：`lookup_t1_context` 可以从真实持久化数据复现上传阶段 candidate，同时保留租户隔离和原有
  防误匹配条件。
- 正面：bank/clear 两侧关联字段语义对齐，Stage 28 不需要弱化算法或信任内存 candidate。
- 负面：`t_bank_transaction` 增加三个 nullable 列，schema 改动范围大于原 Stage 28 计划。
- 负面：已有 MySQL/Compose 数据卷不会被 `create_all()` 自动升级；未显式迁移或重建时，新代码可能
  因缺列失败。
- 约束：除这三个 bank 关联字段及其写入/测试外，不修改其他表、索引、API schema 或 T+1 算法。
