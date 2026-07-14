# ADR-32.1: 以现有数据投影补齐最小人工复核决策上下文

- **Status**: accepted
- **Date**: 2026-07-14
- **Stage**: `stage-32-review-decision-context`
- **Deciders**: 用户（2026-07-14 确认 ADR/spec）、Codex（提案）
- **Related**: `decisions/ADR-003.md`、`decisions/ADR-031-checkpoint-state-persistence-and-idempotency.md`、
  `system-prd.md` §4.4

## Context

当前人工复核卡片只展示内部 `queue_id`、异常类型、规则分支、`ai_suggestion`、置信度、AI 理由和
RAG chunk ID。`GET /api/v1/review/pending` 的 `PendingReviewItem` 不包含 `task_id`、`flow_id`、两侧
流水号或金额，因此用户无法识别正在处置哪一笔业务流水，也无法在点击“确认平账”或“强制挂账”前
核对最基本的金额差异。

这不是数据尚未落库：

- `t_reconciliation_queue` 已有 `task_id`、`flow_id` 和 `user_id`；
- `t_error_ledger` 已有 `bank_amount`、`clear_amount` 和 `discrepancy_amount`；
- `t_bank_transaction` 与 `t_clear_transaction` 已分别保存 `bank_serial_no` 与
  `clearing_serial_no`，并可按 `user_id + task_id + flow_id` 唯一关联。

`ADR-003` 在 MVP-1 后端契约冻结期间明确把左右流水面板推迟。该冻结条件已经结束，但用户本次只要求
轻量修复：补齐单笔身份和金额上下文、修正误导文案，不建设完整左右流水详情面板，也不重构复核流程。

## Options Considered

### Option A：只改前端，继续使用现有 `/review/pending` 响应

优点：不修改后端公共响应模型。

缺点：前端拿不到 `task_id`、`flow_id`、流水号和金额；若逐条调用其他接口拼装，会增加请求、竞态和
错误处理，且默认未按 `task_id` 筛选时甚至缺少可靠关联键，不能解决问题。

### Option B：向现有 `PendingReviewItem` 增量投影最小字段（采纳）

在现有 pending query 上增加 tenant-scoped `LEFT OUTER JOIN`，把队列、差错台账和两侧交易表中已经
存在的识别字段和金额字段加入响应。前端只在现有卡片和确认弹窗中增加紧凑展示，并修正状态文案。

优点：单次查询即可得到人工决策最低上下文；不新增表、接口、依赖或状态；现有字段全部保留，属于
向后兼容的响应扩展。

缺点：pending query 增加两次 join；公共响应模型新增字段，后端与 TypeScript 类型及测试必须同步。

### Option C：新增完整 review detail endpoint 与左右流水详情模型

优点：可以覆盖日期、方向、账号、交易对象、摘要、用途和更多差异字段，长期扩展性最好。

缺点：超出本次轻量化目标，需要新接口、详情加载状态和更大 UI 改造；会把一个局部修复演变为完整
复核工作台重构。

## Decision

采用 **Option B**。

### 1. 现有 pending endpoint 做向后兼容的字段扩展

`GET /api/v1/review/pending` 的每个 `PendingReviewItem` 增加：

- `task_id: str`
- `flow_id: str`
- `bank_serial_no: str | null`
- `clearing_serial_no: str | null`
- `bank_amount: Decimal | null`
- `clear_amount: Decimal | null`
- `discrepancy_amount: Decimal`

现有 `queue_id`、AI、RAG 和历史占位字段继续保留，避免破坏已有 caller。金额在 JSON 中必须保持
Decimal-safe 字符串语义；前端不得先转成 JavaScript `number` 再展示。

### 2. 查询只投影已有数据，不修改持久化模型

- 继续以 `t_reconciliation_queue` 与 `t_error_ledger` 的现有 tenant-scoped join 为主。
- 对 `t_bank_transaction`、`t_clear_transaction` 使用 `LEFT OUTER JOIN`，关联条件必须同时包含
  `user_id`、`task_id`、`flow_id`。
- 单边流水允许其中一侧 join 结果为 `null`；不得补 `0`、伪造流水号或丢弃该待复核项。
- 不回填当前一直为 `null` 的 `bank_transaction_id` / `clear_transaction_id`，不做 schema migration。

### 3. 前端只增加最小决策上下文

- 卡片首要标识改为 `flow_id`，同时展示 `task_id`、`bank_serial_no`、`clearing_serial_no`；
  `queue_id` 仅保留为低强调内部辅助标识。
- 增加银行端金额、企业/清算端金额、差额三项紧凑对比；缺失侧明确显示“无对应流水”，不能显示为
  `0.00`。
- 将 `PENDING_HUMAN` 作为处理状态显示为“待人工复核”，不再把内部 token 原样放在“AI 建议”下。
- 移除卡片中的“历史参考 MVP 占位”展示；后端兼容字段本 Stage 不删除。
- 确认弹窗结构和提交行为保持不变，只把处置对象摘要从单独的 `queue_id` 改为可识别的 `flow_id`
  与金额上下文。

### 4. 处置、Agent 与 evidence contract 不变

- `POST /api/v1/review/{queue_id}/approve` 请求、响应、状态映射、事务、Checkpoint 和幂等行为不变。
- 不修改 AuditAgent、RAG 检索、chunk 内容、置信度或 `ai_reason` 生成逻辑。
- RAG 来源本 Stage 继续使用现有展示，不新增详情加载或 evidence 重构。

## Consequences

### Positive

- 用户可以在处置前明确识别任务、业务流水和两侧原始流水号，并核对金额差异。
- 复用已有表和 endpoint，改动集中在 review schema/query 与两个现有前端组件。
- 单边流水、金额精度和 tenant isolation 都能通过确定性测试覆盖。

### Negative

- 页面仍不是 `system-prd.md` §4.4 描述的完整左右流水面板；日期、方向、账号、交易对象和摘要仍需从
  其他页面或原始文件核对。
- `t_bank_transaction` / `t_clear_transaction` 的现有命名继续暴露在局部 contract 中，本 Stage 不做
  Source A / Source B 通用模型重构。
- pending list query 增加 join，需要测试分页总数和排序没有被放大或改变。

### Constraints

- 不新增数据库表、索引、迁移、API endpoint 或前端依赖。
- 不修改其他页面、全局设计 token、路由或状态管理。
- 不把缺失金额解释为零，不使用 float 处理金额。
- 所有新增查询关联必须显式包含 `user_id`，跨用户数据不得进入响应。
