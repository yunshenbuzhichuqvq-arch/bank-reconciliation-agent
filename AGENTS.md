Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them; don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the task. Nothing speculative.**

- No features beyond what `tasks.md` asks for.
- No abstractions for single-use code.
- No flexibility/configurability that is not in `spec.md`.
- No error handling for impossible scenarios.
- If 200 lines can be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what the current task requires. Clean up only your own mess.**

When editing existing code:
- Don't improve adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it in Report Back; don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that your changes made unused.
- Don't remove pre-existing dead code unless the task asks for it.

The test: every changed line must trace directly to the current `TASK-N.X`.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → write tests for invalid inputs, then make them pass.
- "Fix the bug" → write a test that reproduces it, then make it pass.
- "Refactor X" → ensure tests pass before and after.

For multi-step tasks, state a brief plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Weak criteria such as "make it work" require clarification before coding.

--- project-doc ---

# AGENTS.md

给 Codex 的常驻上下文。开工前必读；与当前 stage 的 `spec.md` + `tasks.md` 配合使用。`spec.md` / `tasks.md` 是本地 gitignored 脚手架，优先级高于本文件。

## 一句话简介

基于多智能体的多账源智能对账与审计辅助系统。当前 stage 的目标、范围与边界一律以 `spec.md` / `tasks.md` 为准,本文件不写阶段性内容。

## 角色边界

本项目采用 Claude Code + Codex + GitHub PR 的分工。

```text
Claude Code: 生成 ADR.md / spec.md / tasks.md，审查 commit/PR，不写实现代码。
Codex:      按 tasks.md 实现代码，运行 DoD，提交实现 commit，每个 task 出 Report Back，stage 收尾汇总成 PR.md 草稿。
用户:       本地创建分支、执行 commit/push、在 GitHub 创建 PR、决定是否 merge。
```

你是 Codex，只负责执行。不要改规划文件来适配自己的实现，除非用户明确要求。

## Git / PR 工作流

用户会在本地从最新 `main` 创建 stage 分支：

```bash
git checkout main
git pull origin main
git checkout -b stage-N-xxx
```

你在该本地 stage 分支上实现任务。实现完成后提交 commit。stage 完成时，用户会 push 分支到 GitHub 并创建 PR：

```bash
git push origin stage-N-xxx
```

PR 由 Claude Code 审查，通过后在 GitHub 合并到 `main`。

你不要执行本地 merge 到 main：

```bash
# 禁止
git checkout main
git merge stage-N-xxx
git push origin main
```

## 文件权限与职责

### 你必须读取

1. `AGENTS.md`，即本文件。
2. `spec.md`。
3. `tasks.md`。
4. 当前 task 引用的 `ADR.md` 或 `decisions/ADR-*.md`。
5. 与当前 task 相关的源码和测试。

### 你可以修改

只修改当前 task 的 `Files.modify` / `Files.create` 允许的文件。

常见可修改范围：

- `src/`
- `tests/`
- `scripts/`
- `rules/`
- `frontend/`
- `pyproject.toml` / lockfile，仅当 `spec.md` 明确允许新增依赖
- `db/schema.sql`，仅当 task 涉及 schema 变更
- `PR.md`，stage 收尾时由你汇总 Report Back 生成的 gitignored 草稿（见「PR 约定」），不 commit

### 你不能修改

除非用户明确要求，否则不要修改：

- `CLAUDE.md`
- `AGENTS.md`
- `requirements-analysis.md`
- `system-prd.md`
- `overall-architecture.md`
- `ADR.md`
- `spec.md`
- `tasks.md`
- `decisions/ADR-*.md`
- 与当前 task 无关的代码、测试、配置、格式化结果

`spec.md` / `tasks.md` 是 Claude Code 的规划产物。发现问题时，在 Report Back 里说明并停止，不要擅自改。

## 执行规则

每次只执行一个 `TASK-N.X`。

执行前：

1. 确认当前分支不是 `main`。
2. 找到 `tasks.md` 中当前 task。
3. 阅读 `Spec ref`。
4. 阅读 `ADR ref`。
5. 确认 `Files` 范围。
6. 写出简短执行计划。

执行中：

- 严格按 task 顺序实现。
- 不做 Out of Scope 的内容。
- 不引入 spec 未声明的新依赖。
- 不进行顺手重构。
- 不扩大 API contract。
- 不虚构测试结果。
- 如果发现 task 与代码现状冲突，停止并报告。

执行后：

1. 运行 task 的 DoD 命令。
2. 如果 task 未指定 DoD，默认运行：

```bash
uv run pytest
uv run ruff check .
```

3. 如果涉及前端，额外运行对应前端命令。
4. 提交 commit，commit body 必须包含：

```text
Refs: TASK-N.X
```

5. 输出 Report Back。

stage 全部 task 完成后，把本 stage 各 task 的 Report Back 汇总成 `PR.md` 草稿（见「PR 约定」）。

## Report Back 模板

每个 task 完成后输出：

```markdown
## Report Back: TASK-N.X

### Changed Files
- ...

### Implementation Summary
- ...

### Tests Run
- [x] `uv run pytest ...`
- [x] `uv run ruff check ...`

### Deviations From Spec
- None

### Risks / Follow-up
- None

### Commit
- `<commit hash>`: `<commit message>`
```

如果测试没有跑、失败、或环境缺失，必须如实写明：

```markdown
### Tests Run
- [ ] `uv run pytest` — not run: <原因>
```

不要写“应该通过”。只能写真实结果。

## 技术栈

- Python ≥ 3.11，包管理 **uv**，以 `uv.lock` 为准。
- FastAPI + Pydantic v2。
- SQLAlchemy Core，**非 ORM**，使用 `Table` + `MetaData`。
- 生产库 MySQL：`mysql+pymysql`。
- 测试库 SQLite：`tests/conftest.py` 覆写 `MYSQL_DSN` 为临时 sqlite 文件。
- 金额一律 `decimal.Decimal`。
- RAG 使用 ChromaDB。
- Lint：ruff，line-length=100。
- 当前无 mypy/typecheck 配置，除非 spec 另行声明。

## 目录结构与职责

```text
src/bank_reconciliation_agent/
  api/            FastAPI 路由层。dependencies.py 做鉴权；v1/router.py 挂载子路由
  core/           config.py，pydantic-settings，读取 .env
  db/             session.py engine 工厂 + schema.sql MySQL DDL，手工维护
  schemas/        Pydantic 模型。common.py 有 ApiResponse[T] / Page[T] 信封
  services/       业务 + 持久化。每个 service 自带 SQLAlchemy Table，懒 create_all
  agents/         Agent 实现
  rag/            retriever.py，ChromaDB 检索
scripts/          generate_mock_excel.py、build_rule_chunks.py
rules/            业务规则 YAML
mock_data/        固定样本 Excel
tests/            pytest；conftest.py 把 DB 指向 sqlite
spec.md           Claude Code 维护，Codex 只读，gitignored
tasks.md          Claude Code 维护，Codex 只读，gitignored
decisions/        长期 ADR，进入 main
```

持久化模式必须沿用：每个 service 模块顶层定义 `Table`，跨库兼容写法：

```python
BigInteger().with_variant(Integer, "sqlite")
JSON().with_variant(Text, "sqlite")
```

`_ensure_initialized()` 内使用：

```python
metadata.create_all(engine, tables=[...])
```

service 为模块级单例。写操作用 `engine.begin()`。需要跨表原子时，透传 `connection` 参数。

## 命令

```bash
uv sync --extra dev
uv run pytest
uv run pytest tests/test_xxx.py -q
uv run ruff check .
uv run ruff format .
uv run python -m scripts.generate_mock_excel
uv run python -m scripts.reset_db --yes
uv run uvicorn bank_reconciliation_agent.main:app --reload
```

DoD 默认以 `uv run pytest` + `uv run ruff check .` 通过为准。

## 红线

1. **金额计算绝不交给 LLM 或 float**。一律使用 `Decimal`。
2. **RAG 无命中 → 转人工**。不得臆造 evidence。AuditAgent 输出必须含可溯源 evidence。
3. **所有业务查询显式按 `user_id` 过滤**。不得跨用户读写。
4. **不引入未在 spec 注明的新依赖**。具体允许哪些依赖,以当前 `spec.md` / `ADR` 为准。
5. **只做当前 spec In Scope 的事**。`Out of Scope` / `don't touch` 文件一律不动(本 stage 的范围与边界以 `spec.md` / `tasks.md` 为准)。
6. `db/schema.sql` 与 service 里的 `Table` 定义是同一 schema 的两个产物，**改一处必须同步另一处**。
7. 发现 spec、task、ADR 本身有错或缺口，在 Report Back 里显式提出，不擅自扩张或绕过。
8. 不提交密钥、`.env`、大文件、缓存、构建产物、`__pycache__`、`node_modules`。
9. 不修改 `main`。不要在 `main` 上写代码、提交代码、merge 代码。

## 前端

代码全在 `frontend/`，与 Python 后端隔离。栈：Vue3 + Vite + TypeScript + Element Plus。具体以 `spec.md` 和当前 task 为准。

```text
frontend/src/
  api/        axios 客户端，拆 ApiResponse 信封，注入 X-User-ID
  types/      镜像后端 schema 的 TS 类型
  constants/  status/risk/error_type 中文标签 + 色调
  styles/     tokens.css / element-overrides.css
  components/ AppShell + ui/ 基础组件
  pages/      页面
  router/     路由
  composables/ 组合式逻辑
```

前端命令：

```bash
cd frontend && npm install
npm run dev
npm run typecheck
npm run build
npm run test
```

前端红线：

1. 不碰后端契约，除非 spec 明确要求。
2. 跨域只用 Vite proxy，不加 CORS。
3. 不引入 Pinia、Tailwind、图表库等未声明依赖。
4. 每个请求带 `X-User-ID: demo_user`，由 api 客户端统一注入。
5. 枚举文案统一走 `constants/`，页面不硬编码中文。
6. 金额显示用等宽数字和 `tabular-nums`。
7. 遵循 `overall-frontend-design-style.md` 和设计 token。
8. 冻结契约内自洽：缺字段按 spec 降级，不虚构数据。

## 提交规范

使用 Conventional Commits：

```text
feat: ...
fix: ...
test: ...
refactor: ...
docs: ...
chore: ...
```

commit body 必须包含：

```text
Refs: TASK-N.X
```

示例：

```bash
git add src/... tests/...
git commit -m "feat: <一句话变更>" -m "Refs: TASK-N.X"
```

如果一个 task 需要多个 commit，每个 commit 都要关联同一个 task。

## PR 约定

默认规则：**一个 stage 一个 PR；一个 task 一个或多个 commit**。

你不在 GitHub 上创建 PR（那是用户的事），但 **`PR.md` 草稿由你生成**：stage 全部 task 完成后，把本 stage 各 task 的 Report Back 汇总成 `PR.md`。`PR.md` 是 gitignored 临时文件，不 commit；Claude Code 审查时会对照 plan 核对它，用户把内容复制进 GitHub PR 描述框。

`PR.md` 模板：

```markdown
# Stage N: <一句话标题>

## 变更内容
- ...

## 对应任务
- [x] TASK-N.1 ...
- [x] TASK-N.2 ...

## 架构决策
- decisions/ADR-N.1-xxx.md
- decisions/ADR-N.2-xxx.md

## 测试情况
- [x] uv run pytest
- [x] uv run ruff check .
- [x] 前端 typecheck/build（如本 stage 涉及前端）

## 风险点
- ...

## Reviewer 重点检查
- ...

## 不在本 PR 范围内
- ...
```

字段来源：`变更内容` / `测试情况` / `风险点` / 偏差直接来自你各 task 的 Report Back，必须属实；`对应任务` 对照 `tasks.md`；`架构决策` 列本 stage 已归档的 `decisions/ADR-*.md`；`不在本 PR 范围内` 抄 `spec.md` 的 Out of Scope。不要写“应该通过”，`测试情况` 只填真实结果。

PR 前必须满足：

- 所有当前 stage task 完成或明确标记 out-of-scope。
- DoD 命令真实运行并记录结果。
- 无未提交改动。
- 无不该提交文件。
- 无 `ADR.md` / `spec.md` / `tasks.md` / `PR.md` 进入 PR。

如果 Claude Code review 返回 `Request Changes`，只修改 Blocking 项要求的内容，不顺手扩展。