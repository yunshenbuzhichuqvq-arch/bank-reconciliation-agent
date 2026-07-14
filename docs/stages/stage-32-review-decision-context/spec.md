# Stage 32 Spec: 人工复核最小决策上下文

**Stage**: `stage-32-review-decision-context`
**Branch**: `stage-32-review-decision-context`
**Status**: accepted
**Date**: 2026-07-14

## Stage Goal

以轻量、局部、可测试的改动，使人工复核列表中的每一项至少能够回答：

1. 这是哪个任务、哪一笔对账流水？
2. 两侧原始流水号分别是什么？
3. 两侧金额和差额是多少？
4. 当前状态是什么，提交处置时是否仍能确认操作对象？

本 Stage 不建设完整左右流水详情面板，不重构人工复核流程。

## Builds On

- `decisions/ADR-003.md`：MVP-1 曾因后端契约冻结推迟复核页左右流水面板；本 Stage 仅偿还其中的
  最小身份与金额上下文缺口。
- `decisions/ADR-031-checkpoint-state-persistence-and-idempotency.md`：现有人工审批事务、Checkpoint 与
  幂等行为继续作为权威 contract。
- `system-prd.md` §4.4：人工复核应能基于双账源信息做最终判断；用户已明确把本 Stage 收敛为
  轻量化补齐，而非完整实现该章节的全部 UI。
- 当前 `ReviewService.list_pending()`、`PendingReviewItem`、`ReviewCard.vue` 和
  `ApproveDialog.vue`。

## Architecture Impact

**Architecture Impact**: Yes
**ADR Required**: Yes
**ADR**: `decisions/ADR-32.1-minimal-review-decision-context.md` (`accepted`)

原因：本 Stage 向公共 `GET /api/v1/review/pending` 响应增加字段，并冻结其 tenant-scoped join 与
Decimal-safe 金额语义。ADR/spec 已由用户确认，tasks 必须保持在该边界内。

## In Scope

### Backend contract and projection

1. 扩展 `PendingReviewItem`，增加任务、业务流水、两侧流水号和金额字段。
2. 扩展 `ReviewService.list_pending()` 的单次查询，复用现有队列、差错台账和交易表。
3. 两侧交易表必须使用 `LEFT OUTER JOIN`，保证单边异常仍返回 pending item。
4. 所有 join 必须同时包含 `user_id`、`task_id`、`flow_id`。
5. 保持现有分页、排序、总数、筛选、AI/RAG 字段和审批接口兼容行为。

### Frontend presentation

1. 更新 `PendingReviewItem` TypeScript 类型。
2. 在现有 `ReviewCard` 中显示：
   - `flow_id`（主标识）；
   - `task_id` 与低强调的 `queue_id`；
   - `bank_serial_no` 与 `clearing_serial_no`；
   - `bank_amount`、`clear_amount`、`discrepancy_amount`。
3. null 侧显示“无对应流水”，不得显示 `0.00` 或虚构字段。
4. 把 `PENDING_HUMAN` 显示为“待人工复核”，不原样暴露内部 token。
5. 删除卡片中的“历史参考 MVP 占位”区域，但不删除后端兼容字段。
6. 保持现有样式系统和弹窗结构；仅在确认摘要中重复 `flow_id` 与金额上下文。
7. 更新页面说明，去掉“当前契约不提供左右流水金额面板”的过时提示。

### Verification

1. 后端测试覆盖正常双边、单边 null、Decimal JSON、分页/排序和 tenant isolation。
2. 前端行为测试覆盖业务流水标识、金额对比、状态文案、占位移除和确认摘要。
3. 运行 Stage/PR 全量后端与前端门禁，并将真实结果写入 Stage 32 `verification.md`。

## Out of Scope

- 完整左右流水详情面板或新的 review detail endpoint。
- 展示交易日期、方向、账号、交易对象、摘要、用途、渠道、余额或全部原始字段。
- 回填或启用 `bank_transaction_id`、`clear_transaction_id`。
- 数据库表、索引、migration 或 `db/schema.sql` 变更。
- 修改 `POST /review/{queue_id}/approve`、人工备注规则、事务、Checkpoint、幂等或记忆副作用。
- 修改 Agent、prompt、RAG 检索、evidence 内容、置信度、历史案例统计或规则分支。
- 修改 Ledger、Upload、Dashboard、Workbench、Report、Metrics 或 Trace 页面。
- 新增依赖、状态管理、通用格式化框架或 UI 组件库。
- 处理 `ADR-003` 中与本 Stage 无关的任务列表、CORS 或错误码缺口。

## Inputs and Outputs

### Input

现有请求保持不变：

```http
GET /api/v1/review/pending?task_id=<optional>&page=1&page_size=10
Authorization: Bearer <token>
```

### Output contract

每个 `items[]` 在保留现有字段的基础上新增：

```json
{
  "task_id": "TASK-...",
  "flow_id": "F2003",
  "bank_serial_no": "B202606010003",
  "clearing_serial_no": "C202606010003",
  "bank_amount": "1000.00",
  "clear_amount": "980.00",
  "discrepancy_amount": "20.00"
}
```

字段约束：

- `task_id`、`flow_id`、`discrepancy_amount` 必须存在。
- `bank_serial_no`、`clearing_serial_no`、`bank_amount`、`clear_amount` 在单边流水时允许为 `null`。
- Decimal 金额经 JSON 输出为精确十进制字符串；前端以字符串展示，不通过 float/JavaScript number
  重算差额。
- null 只表示该侧无关联流水或字段确实缺失，不得替换为零值。

## Main Flow

```text
GET /review/pending
  -> JWT 解析 user_id
  -> queue INNER JOIN ledger（现有 tenant/task/flow 关联）
  -> LEFT JOIN bank transaction（tenant/task/flow）
  -> LEFT JOIN clear transaction（tenant/task/flow）
  -> PendingReviewItem Decimal-safe projection
  -> ReviewCard 显示业务标识、两侧流水号和金额
  -> 用户打开现有 ApproveDialog
  -> 弹窗重复 flow_id 与金额上下文
  -> 现有 approve contract 提交，事务与幂等逻辑不变
```

## API and Function Contracts

### `PendingReviewItem`

新增字段使用后端现有列的原始语义，不创建第二套计算：

| Response field | Source |
| --- | --- |
| `task_id` | `t_reconciliation_queue.task_id` |
| `flow_id` | `t_reconciliation_queue.flow_id` |
| `bank_serial_no` | `t_bank_transaction.bank_serial_no` |
| `clearing_serial_no` | `t_clear_transaction.clearing_serial_no` |
| `bank_amount` | `t_error_ledger.bank_amount` |
| `clear_amount` | `t_error_ledger.clear_amount` |
| `discrepancy_amount` | `t_error_ledger.discrepancy_amount` |

### `ReviewService.list_pending()`

- 仍返回一页 pending items 与原有 `total`。
- count query 不因交易表 join 产生重复计数；实现可以保持现有 count 范围，或采用等价且经测试证明的
  唯一计数方式。
- rows query 保持 `created_at, id` 的现有稳定排序。
- 无法关联某侧交易行不是 endpoint 错误；对应可空字段返回 `null`。
- 数据库异常继续走现有错误处理，不新增静默 fallback 或额外查询补偿。

### Frontend display

- 标识与金额必须在卡片首屏可见，不依赖展开 RAG 或打开其他页面。
- 金额使用现有 `tabular-nums` 风格；不得在浏览器端计算新的 `discrepancy_amount`。
- 内部状态文案从 `STATUS_META` 或等价的现有枚举映射读取，不能复制一套散落常量。
- 操作按钮、事件、loading、成功提示和列表移除行为不变。

## Data Model Impact

无数据库 schema 变化，无 migration。

本 Stage 只读取已有列并扩展 API projection。`bank_transaction_id` 与 `clear_transaction_id` 继续保持
现状，不作为关联前提。

## Cross-cutting Requirements

### Tenant isolation

- pending base filter 保持 `queue.user_id == authenticated user_id`。
- queue、ledger、bank transaction、clear transaction 的每条 join condition 都必须包含 `user_id`。
- 测试必须证明相同 `task_id + flow_id` 的其他用户流水号和金额不会泄露。

### Amount precision

- 后端 schema 使用 `Decimal`，不转 `float`。
- 前端接收并展示字符串，不进行金额运算。
- null 与 `0.00` 必须保持不同语义。

### Compatibility

- 原有响应字段不删除或改名。
- approval endpoint、路由、query 参数、分页与排序不变。
- 不要求现有客户端在请求中增加参数。

### Accessibility and clarity

- 流水号和金额使用明确文本标签，不能只靠位置或颜色表达两侧含义。
- null 文案应能被屏幕阅读器读取；不使用单独的 `—` 表达关键业务缺失状态。
- 按钮标签和键盘行为沿用现有组件，不在本 Stage 重写交互。

## Acceptance Criteria

1. pending item 响应包含 `task_id`、`flow_id`、两侧流水号、两侧金额和差额，现有字段仍存在。
2. 双边金额不一致样例能返回并展示两侧原始流水号、精确金额和差额。
3. 单边样例仍出现在列表中，缺失侧字段为 `null`，前端明确显示“无对应流水”。
4. 相同 `task_id + flow_id` 的跨用户交易行不会进入当前用户响应。
5. 分页 `total`、items 数量和现有稳定排序不因 join 改变。
6. 页面不再把 `PENDING_HUMAN` 原样显示为“AI 建议”，而显示“待人工复核”。
7. 页面不再显示“历史参考 MVP 占位”或虚假的 `0%` 历史通过率。
8. 用户无需离开卡片即可识别待复核业务流水并核对金额差异。
9. 确认弹窗重复显示同一 `flow_id` 与金额上下文，但提交 payload 和审批结果不变。
10. 无数据库 schema、依赖、其他页面、Agent/RAG 或审批事务变更。
11. focused backend/frontend tests、全量 pytest、Ruff、frontend test/typecheck/build 全部通过并如实记录。

## Risks and Open Questions

### Risks

- 交易表 join 条件遗漏 `user_id` 会导致严重租户数据泄露；这是 Blocking 风险。
- `INNER JOIN` 交易表会丢失单边异常；必须使用 `LEFT OUTER JOIN`。
- 前端把 Decimal 字符串转为 number 会重新引入金额精度风险。
- 额外 join 若破坏唯一性，会放大分页结果或 `total`；必须用现有唯一约束和测试锁定。

### Open Questions

无。用户已经明确选择轻量化改动；完整左右流水详情、历史案例与 RAG 可读性不在本 Stage 讨论。
