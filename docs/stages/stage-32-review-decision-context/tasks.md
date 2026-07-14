# Stage 32 Tasks: 人工复核最小决策上下文

- **Stage**: `stage-32-review-decision-context`
- **Branch**: `stage-32-review-decision-context`
- **Spec**: `docs/stages/stage-32-review-decision-context/spec.md`
- **ADR**: `decisions/ADR-32.1-minimal-review-decision-context.md`
- **Status**: review-blocked
- **Date**: 2026-07-14

## Execution Rules

- opencode 每次只执行一个 task；开始前阅读 `AGENTS.md`、accepted spec、accepted ADR 和当前 task。
- 规划文件由用户先单独提交；opencode 不修改或混入提交：ADR、spec、tasks、verification。
- 每个实现 task 先增加能证明当前 contract 缺口的失败测试，再做最小实现并运行指定门禁。
- `Files to Modify` 是当前 task 的完整允许边界；需要扩大时停止并报告，由 Codex 修订 task。
- 不新增 endpoint、数据库 schema、依赖、状态管理或完整左右流水详情模型。
- 金额保持 Decimal-safe 字符串语义；不得使用 float 或 JavaScript `number` 重算。
- 所有新增 join 必须显式包含 `user_id`；单边流水不得因 join 被过滤。
- Task 完成后检查 `git diff`，创建只引用当前 task 的 Conventional Commit；不得 push 或 merge。
- opencode 不自行修改 task 状态。Codex review 通过后再由 Codex更新本文件。
- 未运行、失败或受环境阻塞的验证必须如实 Report Back，不得标记 task 完成。

## Dependency Order

```text
TASK-32.1 Backend pending-review projection
  -> TASK-32.2 Frontend review context presentation
    -> TASK-32.3 Stage/PR verification
```

---

## TASK-32.1 — 扩展 tenant-safe pending review 响应

**Status**: done
**Spec Ref**: `Backend contract and projection`、`Output contract`、
`ReviewService.list_pending()`、`Tenant isolation`、`Amount precision`
**ADR Ref**: `ADR-32.1` Decision 1、2、4

### Goal

向现有 `GET /api/v1/review/pending` 的每个 item 增量返回任务、业务流水、两侧流水号和金额字段，
同时保持分页、排序、单边流水、tenant isolation 与现有审批 contract 不变。

### Files to Modify

- Modify: `src/bank_reconciliation_agent/schemas/review.py`
- Modify: `src/bank_reconciliation_agent/services/review.py`
- Modify: `tests/test_review.py`

### Do Not Touch

- `src/bank_reconciliation_agent/api/`
- `src/bank_reconciliation_agent/services/reconciliation.py`
- `src/bank_reconciliation_agent/services/queue.py`
- `src/bank_reconciliation_agent/services/ledger.py`
- `src/bank_reconciliation_agent/services/transactions.py`
- `src/bank_reconciliation_agent/services/review_graph.py`
- 其他 backend tests、frontend、数据库 schema、依赖、Agent、RAG、规则和规划文件

### Out of Scope

- 新增 endpoint、detail model、逐 item 二次查询或 N+1 查询。
- 修改 `POST /review/{queue_id}/approve`、状态映射、事务、Checkpoint、幂等或记忆副作用。
- 回填 `bank_transaction_id` / `clear_transaction_id`，修改已有表、索引或 migration。
- 计算新的差额、改写 AI/RAG 字段、删除历史占位兼容字段。
- 为方便测试修改 fixture 生成器、业务规则、预期异常数量或排序。

### Acceptance Criteria

- `PendingReviewItem` 新增并返回 `task_id`、`flow_id`、`bank_serial_no`、
  `clearing_serial_no`、`bank_amount`、`clear_amount`、`discrepancy_amount`。
- 金额 schema 使用 `Decimal`；JSON 保持精确十进制字符串，禁止转换为 float。
- rows query 对两侧交易表使用 `LEFT OUTER JOIN`；每条 join 同时包含 `user_id`、`task_id`、
  `flow_id`。
- 现有 queue-ledger tenant-scoped join、pending filter、`task_id` filter 和
  `created_at, id` 排序保持不变。
- count query 的 `total` 与 items 分页不被新增 join 放大；现有 6 条样例和两页分页断言继续成立。
- 双边 `BE-R002 / AMOUNT_MISMATCH` 样例返回两侧流水号、两侧金额和差额，并与持久化值一致。
- 至少一个单边样例仍返回，缺失侧的流水号和金额为 `null`，存在侧数据正确；不能以 `0` 替代 null。
- 增加跨用户回归测试：即使另一用户存在相同 `task_id + flow_id`，其流水号或金额也不会进入当前
  用户响应。
- 原有 `queue_id`、AI、RAG、历史兼容字段和审批测试不回归。
- 不修改允许列表以外的文件，不新增依赖或数据库变更。

### Verification Commands

```bash
uv run pytest tests/test_review.py -q
uv run ruff check \
  src/bank_reconciliation_agent/schemas/review.py \
  src/bank_reconciliation_agent/services/review.py \
  tests/test_review.py
uv run ruff format --check \
  src/bank_reconciliation_agent/schemas/review.py \
  src/bank_reconciliation_agent/services/review.py \
  tests/test_review.py
```

### Report Back Requirements

- Changed Files
- Response Contract Summary：新增字段、类型与 JSON 金额语义
- Query Summary：join 类型及完整 tenant keys
- Single-side Behavior：null 侧与存在侧的测试证据
- Pagination/Ordering Compatibility
- Tenant Isolation Evidence
- Tests Run：逐条命令、退出码和真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-32.1`

---

## TASK-32.2 — 在现有复核卡片与确认弹窗展示最小上下文

**Status**: review-blocked
**Spec Ref**: `Frontend presentation`、`Frontend display`、
`Accessibility and clarity`、Acceptance Criteria 6–9
**ADR Ref**: `ADR-32.1` Decision 3、4

### Goal

在不重构页面、不改变交互和提交 payload 的前提下，让用户在现有卡片及确认弹窗中识别业务流水、
核对两侧流水号和金额，并看到正确的“待人工复核”状态文案。

### Files to Modify

- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/ReviewPage.vue`
- Modify: `frontend/src/components/review/ReviewCard.vue`
- Modify: `frontend/src/components/review/ApproveDialog.vue`
- Create: `frontend/tests/ReviewCard.spec.ts`
- Create: `frontend/tests/ApproveDialog.spec.ts`
- Modify only if the existing page smoke requires fixture alignment:
  `frontend/tests/v1-3-8-pages.spec.ts`

### Do Not Touch

- `frontend/src/api/review.ts`
- `frontend/src/constants/enums.ts`
- 其他 pages、components、tests、router、styles、composables 和 package files
- 全部 backend、数据库、Agent、RAG、规则和规划文件

### Out of Scope

- 完整左右流水详情、折叠面板、详情抽屉、新路由或新 API 调用。
- 展示日期、方向、账号、交易对象、摘要、渠道、用途、余额或全部原始字段。
- 修改按钮动作、确认 payload、处理人/备注校验、loading、成功提示或列表移除行为。
- 重做页面视觉、全局 token、响应式系统或无关组件。
- 优化 RAG 来源、历史案例统计、AI reason 或 risk badge。
- 新增格式化库、复制新的状态常量或把金额转成 JavaScript `number`。

### Acceptance Criteria

- TypeScript `PendingReviewItem` 与 accepted backend response contract 一致，金额字段为
  `string | null` / `string`，不声明为 number。
- 卡片主标识显示 `flow_id`；`task_id` 和 `queue_id` 仍可见但低于业务流水标识层级。
- 卡片显示 `bank_serial_no`、`clearing_serial_no`、`bank_amount`、`clear_amount` 和
  `discrepancy_amount`，金额使用现有 `tabular-nums` 风格。
- 任一侧金额或流水号为 null 时，该侧明确显示“无对应流水”，不能显示为 `0.00`、空白或单独的 `—`。
- `PENDING_HUMAN` 通过现有 `STATUS_META` 或等价现有映射显示为“待人工复核”；卡片不再出现
  “AI 建议 PENDING_HUMAN”。
- “历史参考 MVP 占位”、相似案例 `0` 和历史通过率 `0%` 不再渲染；RAG 来源区域保持现有行为。
- `ReviewPage` 说明更新为符合当前 contract 的文案，不再声称缺少金额面板。
- `ApproveDialog` 保持结构、处理人/备注、事件与 payload 不变；摘要重复显示同一 `flow_id` 和三项
  金额上下文，不再只依赖 `queue_id` 识别处置对象。
- 新增组件行为测试覆盖正常双边、单边 null、状态映射、历史占位移除和弹窗确认 payload。
- 现有页面 smoke、前端 typecheck 和 build 不回归；不修改允许列表以外的文件。

### Verification Commands

```bash
cd frontend
npm run test -- ReviewCard.spec.ts ApproveDialog.spec.ts v1-3-8-pages.spec.ts
npm run typecheck
npm run build
```

### Report Back Requirements

- Changed Files
- Information Hierarchy Summary：`flow_id`、task/queue、两侧流水号和金额的位置
- Null-side Display Summary
- Status Copy Summary：证明不再原样显示 `PENDING_HUMAN`
- Dialog Compatibility：事件与 payload 未改变
- Tests Run：逐条命令、退出码和真实结果
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-32.2`

---

## TASK-32.3 — 运行 Stage/PR 全量验证并记录结果

**Status**: done (`review-blocked`)
**Spec Ref**: `Verification`、全部 `Acceptance Criteria`、全部横切要求
**ADR Ref**: `ADR-32.1` 全部 Decision 与 Constraints

### Goal

在 TASK-32.1 和 TASK-32.2 均通过 Codex review 后，从当前 Stage 分支运行完整后端、前端、格式和
scope 门禁，并把真实结果写入 Stage 32 `verification.md`。本 task 不修复实现；若门禁失败，停止并
Report Back，由 Codex review 决定是否新增一个有界修复 task。

### Files to Modify

- Modify: `docs/stages/stage-32-review-decision-context/verification.md`

### Do Not Touch

- 全部 backend、frontend、tests、数据库、依赖、Agent、RAG、规则和其他文档
- ADR、spec、tasks
- 用户现有未跟踪 `mock_data/*.xlsx`

### Out of Scope

- 在验证 task 中顺手修复测试、格式、实现或文案问题。
- 扩大 Stage 范围、降低断言、跳过失败门禁或把未运行命令标记为通过。
- commit/push/PR/merge 或修改 `main`。

### Acceptance Criteria

- 真实运行全部 Verification Commands，并记录命令、退出码、通过/失败/未运行原因和关键数量。
- focused backend test 证明 pending response、单边 null、Decimal 和 tenant isolation。
- full pytest、Ruff check 与 Ruff format gate 如实记录；任何失败不得写成 passed。
- frontend full test、typecheck 和 build 如实记录。
- `git diff --check main...HEAD` 与 `git diff --stat main...HEAD` 证明无空白错误且范围只包含 Stage 32。
- `git status --short` 单独列出用户已有未跟踪 `mock_data/*.xlsx`，不得把它们归入 Stage 32 交付物。
- verification 明确记录 verified revision；工作区不干净时说明哪些是预期规划文件、Stage 变更或用户
  原有文件。
- 若全部门禁通过，记录 `Review Status: ready-for-codex-review`；否则记录
  `Review Status: blocked` 和 closed blocker list。

### Verification Commands

```bash
uv run pytest tests/test_review.py -q
uv run pytest
uv run ruff check .
uv run ruff format --check .

cd frontend
npm run test
npm run typecheck
npm run build

cd ..
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
git rev-parse HEAD
```

### Report Back Requirements

- Verified Revision and Working Tree State
- Backend Focused/Full Test Results
- Ruff Check/Format Results
- Frontend Test/Typecheck/Build Results
- Diff Scope and Untracked-file Separation
- Acceptance Criteria Checklist
- Blockers：没有则写 `None`
- Deviations From Spec
- Risks/Follow-up
- Commit：仅提交 verification 更新，body 包含 `Refs: TASK-32.3`

---

## TASK-32.4 — 修正复核卡片状态语义并重新验证

**Status**: review-blocked
**Spec Ref**: `Frontend presentation`、`Frontend display`、Acceptance Criteria 6、11
**ADR Ref**: `ADR-32.1` Decision 3、4

### Goal

修复 Codex review 发现的状态语义错误：pending 列表中的卡片必须显示当前处理状态“待人工复核”，
不能把 `ai_suggestion`（例如 `APPROVED_MATCH`、`FORCE_HOLD`）误标为“处理状态”并原样暴露。
修复后重新运行 Stage/PR 门禁，并更新 verification 的真实结果。

### Files to Modify

- Modify: `frontend/src/constants/enums.ts`
- Modify: `frontend/src/components/review/ReviewCard.vue`
- Modify: `frontend/tests/ReviewCard.spec.ts`
- Modify: `docs/stages/stage-32-review-decision-context/verification.md`

### Do Not Touch

- 其他 frontend 文件和测试
- 全部 backend、数据库、依赖、Agent、RAG、规则、ADR、spec 和其他文档
- 用户现有未跟踪 `mock_data/*.xlsx`

### Out of Scope

- 修改后端 pending response contract 或新增状态字段。
- 删除、重命名或改变 `ai_suggestion` 的 API 语义。
- 恢复“AI 建议”区域、重做卡片布局或修改处置按钮与 payload。
- 顺手修复 Stage 32 以外的 Ruff format 历史债务。

### Acceptance Criteria

- `ReviewCard` 的“处理状态”不再读取 `item.ai_suggestion`，而是从现有 `STATUS_META` 显示 pending
  item 的状态文案“待人工复核”。
- `STATUS_META.PENDING_HUMAN` 的共享文案与 accepted ADR/spec 一致为“待人工复核”。
- 分别使用 `ai_suggestion=PENDING_HUMAN`、`APPROVED_MATCH`、`FORCE_HOLD` 的组件测试均证明：
  卡片显示“待人工复核”，且不显示三个内部 token。
- 现有 flow/task/queue、流水号、金额、null 侧、AI 理由、RAG 来源和按钮事件测试不回归。
- focused frontend tests、frontend full gate、backend full gate、Ruff、diff/hygiene 检查均真实运行并记录。
- `verification.md` 的 verified revision、Review Status、diff 文件数和 blocker list 与修复后的实际状态一致；
  预存的 repo-wide Ruff format 失败必须继续如实与 Stage 32 changed-path 结果分开记录。

### Verification Commands

```bash
cd frontend
npm run test -- ReviewCard.spec.ts v1-3-8-pages.spec.ts
npm run test
npm run typecheck
npm run build

cd ..
uv run pytest tests/test_review.py -q
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ruff format --check \
  src/bank_reconciliation_agent/schemas/review.py \
  src/bank_reconciliation_agent/services/review.py \
  tests/test_review.py
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
git rev-parse HEAD
```

### Report Back Requirements

- Changed Files
- Root Cause：说明 `ai_suggestion` 与 pending 处理状态为何不是同一语义
- Branch Coverage：`PENDING_HUMAN`、`APPROVED_MATCH`、`FORCE_HOLD` 三种输入的断言
- Tests Run：逐条命令、退出码和真实结果
- Verification Update：verified revision、Review Status 和 blocker list
- Deviations From Spec
- Risks/Follow-up
- Commit：Conventional Commit，body 包含 `Refs: TASK-32.4`
