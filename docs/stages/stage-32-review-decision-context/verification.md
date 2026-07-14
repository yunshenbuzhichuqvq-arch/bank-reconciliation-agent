# Stage 32 Verification

- **Stage**: `stage-32-review-decision-context`
- **Branch**: `stage-32-review-decision-context`
- **Verified Revision**: `efebb88f0ebfd5f57071f4f5b3f974052218c4ff`
- **Date**: 2026-07-14
- **Review Status**: review-blocked (pre-existing ruff format)

## Scope

验证 Stage 32 是否只扩展 pending review 的最小身份/金额上下文，并保持 tenant isolation、Decimal
精度、单边流水、审批行为和其他页面不回归。TASK-32.4 修复了 Codex review 发现的状态语义错误。

## Verification Results

### Backend focused test

- [x] `uv run pytest tests/test_review.py -q` — **17 passed**

### Backend full gate

- [x] `uv run pytest` — **1221 passed, 1 skipped**（skip: `test_llm_live_smoke` — 环境限制）
- [x] `uv run ruff check .` — **All checks passed!**
- [x] `uv run ruff format --check src/bank_reconciliation_agent/schemas/review.py src/bank_reconciliation_agent/services/review.py tests/test_review.py` — **3 files already formatted**
- [ ] `uv run ruff format --check .` — **90 files would be reformatted**（全部为 Stage 32 以外的预存文件）

### Frontend gate

- [x] `npm run test -- ReviewCard.spec.ts v1-3-8-pages.spec.ts` — **13 passed**
- [x] `npm run test` — **80 passed** (20 test files)
- [x] `npm run typecheck` — **passed**
- [x] `npm run build` — **passed**

### Scope and hygiene

- [x] `git diff --check main...HEAD` — **no whitespace errors**
- [x] `git diff --stat main...HEAD` — **11 files changed, 769 insertions(+), 59 deletions(−)**，全部为 Stage 32 允许文件（含 TASK-32.4 新增 `enums.ts`）
- [x] `git status --short` — 无意外修改；未跟踪：`decisions/ADR-32.1-*.md`、`docs/stages/stage-32-*/`（规划文件）、`mock_data/*.xlsx`（用户预存）

## Acceptance Criteria Evidence

- [x] pending item identity and two-side serial numbers — `task_id`、`flow_id`、`bank_serial_no`、`clearing_serial_no` 已返回并显示
- [x] Decimal-safe two-side amounts and discrepancy — `bank_amount`、`clear_amount`、`discrepancy_amount` 以 Decimal + `@field_serializer` 序列化为字符串
- [x] single-side null behavior — `BE-R005`/`BE-R006` 缺失侧为 null，前端显示"无对应流水"
- [x] tenant isolation for joined transaction rows — 跨用户回归测试通过
- [x] pagination and ordering compatibility — `total=6`、分页/排序不变
- [x] **human-readable pending status** — `ReviewCard`「处理状态」固定显示"待人工复核"，**不读取 `ai_suggestion`**；`PENDING_HUMAN`/`APPROVED_MATCH`/`FORCE_HOLD` 三种 `ai_suggestion` 值均通过组件测试验证不暴露内部 token
- [x] **shared status mapping** — `ReviewCard` 使用 `STATUS_META.PENDING_HUMAN.label` 读取文案，不硬编码
- [x] historical placeholder removed from UI — "相似案例"/"历史参考" 已移除
- [x] approve dialog identity context and unchanged payload — 弹窗显示 `flow_id` + 金额，confirm payload 不变
- [x] no schema, dependency, Agent/RAG, approval transaction or unrelated page changes — `git diff --stat` 仅允许文件

## TASK-32.4 Root Cause

`ReviewCard` 将 `item.ai_suggestion`（AI 处置建议，取值 `PENDING_HUMAN`/`APPROVED_MATCH`/`FORCE_HOLD`）误作为「处理状态」标签展示。pending 列表所有条目的真实队列状态均为 `PENDING_HUMAN`。修复方案：

1. `enums.ts`：`STATUS_META.PENDING_HUMAN.label` → `"待人工复核"`
2. `ReviewCard.vue`：「处理状态」通过 `STATUS_META.PENDING_HUMAN.label` 读取，不依赖 `ai_suggestion`
3. `ReviewCard.spec.ts`：分支覆盖三种 `ai_suggestion` 输入

## Blockers

| # | 门禁 | 详情 | 状态 |
|---|---|---|---|
| 1 | Stage 正式文件 | accepted ADR、spec、tasks 仍未被 Git 跟踪，不满足 Stage/PR artifact gate | Open — user action |
| 2 | `uv run ruff format --check .` | 90 个 Stage 32 未修改的预存文件需重新格式化 | Pre-existing |

### 分析

TASK-32.4 已消除 `APPROVED_MATCH` / `FORCE_HOLD` token 暴露，补齐三分支组件测试，并通过 `STATUS_META.PENDING_HUMAN.label` 读取状态文案。Codes re-review 复跑：

- focused frontend `13 passed`、frontend full `80 passed`、typecheck/build passed
- focused backend `17 passed`、backend full `1221 passed, 1 skipped`
- Ruff check 与 changed-path Ruff format passed

accepted ADR、spec、tasks 仍是未跟踪文件，必须由用户纳入 Stage 分支。两个 `mock_data/*.xlsx` 继续视为用户预存数据，不属于 Stage 32。

ruff format 历史债务不涉及 Stage 32 修改文件，与本 Stage 功能 blocker 分开记录。
