# Stage 32 Verification

- **Stage**: `stage-32-review-decision-context`
- **Branch**: `stage-32-review-decision-context`
- **Verified Revision**: `19da3d29995d9f13163f99e7b10ec53a367ef18f`
- **Date**: 2026-07-14
- **Review Status**: blocked

## Scope

验证 Stage 32 是否只扩展 pending review 的最小身份/金额上下文，并保持 tenant isolation、Decimal
精度、单边流水、审批行为和其他页面不回归。

## Verification Results

### Backend focused test

- [x] `uv run pytest tests/test_review.py -q` — **17 passed**

### Backend full gate

- [x] `uv run pytest` — **1221 passed, 1 skipped** (skip: `test_llm_live_smoke` — 环境限制，非 Stage 32 引入)
- [x] `uv run ruff check .` — **All checks passed!**
- [ ] `uv run ruff format --check .` — **failed: 90 files would be reformatted**（全部为预存文件，Stage 32 修改的 3 个 Python 文件已符合格式）

### Frontend gate

- [x] `cd frontend && npm run test` — **78 passed** (20 test files)
- [x] `cd frontend && npm run typecheck` — **passed** (exit 0)
- [x] `cd frontend && npm run build` — **passed** (built in 2.93s)

### Scope and hygiene

- [x] `git diff --check main...HEAD` — **no whitespace errors**
- [x] `git diff --stat main...HEAD` — **9 files changed, 687 insertions(+), 58 deletions(-)**，全部为 Stage 32 允许文件
- [x] `git status --short` — 无未预期已修改文件；未跟踪文件：`decisions/ADR-32.1-*.md`、`docs/stages/stage-32-*/`（规划文件）、`mock_data/*.xlsx`（用户预存数据）
- [x] `git rev-parse HEAD` — `19da3d29995d9f13163f99e7b10ec53a367ef18f`

## Acceptance Criteria Evidence

- [x] pending item identity and two-side serial numbers — `task_id`、`flow_id`、`bank_serial_no`、`clearing_serial_no` 已返回并显示
- [x] Decimal-safe two-side amounts and discrepancy — `bank_amount`、`clear_amount`、`discrepancy_amount` 以 Decimal 字段 + `@field_serializer` 序列化为字符串
- [x] single-side null behavior — `BE-R005` (BANK_UNARRIVED) bank 侧为 null，`BE-R006` (BOOK_UNRECORDED) clear 侧为 null；前端显示"无对应流水"
- [x] tenant isolation for joined transaction rows — `test_pending_review_tenant_isolation_no_cross_user_leakage` 通过；`other_user` 数据不泄露
- [x] pagination and ordering compatibility — `total=6`、每页 2 条、`created_at, id` 排序不变
- [x] human-readable pending status — `PENDING_HUMAN` 通过 `STATUS_META` 显示为"待复核"，不再原样暴露
- [x] historical placeholder removed from UI — "相似案例"/"历史参考"/"历史通过率" 不再渲染
- [x] approve dialog identity context and unchanged payload — 弹窗摘要显示 `flow_id` 和金额；confirm payload 结构不变
- [x] no schema, dependency, Agent/RAG, approval transaction or unrelated page changes — `git diff --stat` 仅 9 个允许文件

## Blockers

| # | 门禁 | 详情 | 状态 |
|---|---|---|---|
| 1 | `uv run ruff format --check .` | 90 个预存文件需重新格式化 | Pre-existing |

### 分析

全部 90 个需格式化的文件均不属于 Stage 32 修改范围（`scripts/`、`tests/` 等历史文件）。Stage 32 涉及的 3 个 Python 文件（`schemas/review.py`、`services/review.py`、`tests/test_review.py`）格式已通过。其他 7 个门禁（focused/full pytest、ruff check、前端 test/typecheck/build、git diff scope）全部通过。

建议由 Codex review 决定是否单独新增格式修复 task，还是将预存格式问题记入已知债务。Stage 32 实现本身不引入格式回归。
