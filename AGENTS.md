# AGENTS.md
`bank-reconciliation-agent` 仓库统一协作说明。项目按 stage 增量开发：用户负责决策和合并，Codex 负责规划与审查，opencode 负责实现与测试。

## 1. 规则优先级
发生冲突时按以下顺序处理：
1. 用户对当前任务的明确决定。
2. 本文件中的安全、数据隔离和金额精度红线。
3. 项目级需求与架构文档。
4. 已接受的 `decisions/ADR-*.md`。
5. 当前 stage 的 `spec.md`。
6. 当前 task 的 `tasks.md`。
7. 现有代码和测试。
下层规则只能细化上层规则。发现冲突或缺口时停止并报告，不得猜测或修改测试绕过。

## 2. 角色与权限
- 用户：确认 stage 目标、范围和验收标准；创建分支；审批重要决策；负责 push、PR 和 merge。
- Codex：维护 spec、tasks 和必要的 ADR；负责架构、拆分和审查；不写实现代码，不执行 commit/push/PR/merge。
- opencode：每次执行一个 task；实现、测试、Report Back；可创建本地 task commit；不得 push、merge 或修改规划文件。

## 3. 全局原则
- 只实现当前 stage 和 task 明确要求的内容。
- 优先简单方案，不做 speculative design 和过度抽象。
- 不顺手重构，不扩大 API contract，不修改无关文件。
- 不引入 spec 或 ADR 未声明的新依赖。
- 每项实质性变更必须追溯到当前 task 或批准的 Blocking 项。
- 测试未运行、失败或环境缺失时必须如实记录。
- 无法验证的任务不能标记完成。

## 4. Stage 文件
每个 stage 的正式文件提交到 Git：
```text
docs/stages/stage-N-xxx/
  spec.md          # 目标、范围、接口、验收标准
  tasks.md         # 任务、状态、验证命令
  verification.md  # stage 全量验证结果
```
长期架构决策保存在 `decisions/ADR-NNN-<slug>.md`。
不要使用 stage 结束后删除的根目录 `spec.md`、`tasks.md`、`ADR.md`。PR 描述直接维护在 GitHub。

## 5. Git 与 PR
创建 stage 分支：
```bash
git switch main
git pull --ff-only origin main
git switch -c stage-N-xxx
```
- 不在 `main` 上开发或提交；`main` 只通过 GitHub PR 更新。
- 禁止将 stage 分支本地 merge 回 `main`。
- 热修使用 `fix/*` 分支并通过 PR 合并。
- `main` 更新后，允许在 stage 分支合并 `origin/main`，解决冲突后复跑全量验证。
stage 完成后由用户执行：
```bash
git push -u origin stage-N-xxx
# GitHub: base=main, compare=stage-N-xxx
```
PR 合并后：
```bash
git switch main
git pull --ff-only origin main
git branch -d stage-N-xxx
git push origin --delete stage-N-xxx
```

## 6. Commit 规范
使用 Conventional Commits：`feat:` / `fix:` / `test:` / `refactor:` / `docs:` / `chore:`。
opencode commit 必须引用 task：
```bash
git commit -m "feat: import bank transactions" -m "Refs: TASK-1.2"
```
一个 task 可以有多个 commit，但每个 commit 必须引用同一 task；无关变更不得混入。

## 7. Codex 规划流程
新 stage 开始时：
1. 确认当前分支不是 `main`。
2. 阅读项目文档、相关历史 ADR、源码和测试结构。
3. 判断是否需要 ADR。
4. 编写 stage `spec.md`。
5. 用户确认后拆分 `tasks.md`。
以下情况需要 ADR：
- 引入或替换依赖、数据库、队列或基础设施。
- 改变模块边界、依赖方向、公共 API 或数据模型。
- 涉及权限、幂等、重试、失败恢复或观测策略。
- 改变 LLM、RAG 或 Agent 的职责边界。
- 存在多个具有长期影响的可行方案。
无架构影响时在 spec 写：
```text
Architecture Impact: None
ADR Required: No
```
不得为了满足格式虚构备选方案。

## 8. Spec 与 Task 要求
`spec.md` 至少包含：Stage Goal、Builds On、In/Out of Scope、输入输出、主要流程、API/函数 contract、数据模型影响、横切要求、Acceptance Criteria、Risks/Open Questions、ADR 引用。
用户主要确认：目标是否正确、范围是否清楚、错误行为是否合理、验收条件是否可测试。
每个 task 必须包含：Status、Spec Ref、ADR Ref、Goal、Files to Modify、Do Not Touch、Out of Scope、Acceptance Criteria、Verification Commands、Report Back Requirements。
一个 task 只完成一件事，应能独立测试和审查。具体局部实现由 opencode 决定，Codex 不规定无必要的实现细节。

## 9. opencode 执行流程
执行前：
1. 确认当前分支不是 `main`。
2. 阅读 `AGENTS.md`、当前 spec、tasks、相关 ADR、源码和测试。
3. 确认唯一 task、允许修改的文件和验收标准。
4. 输出简短执行计划。
执行中：
- 严格限制在当前 task 范围内。
- 不修改 spec、tasks、ADR 或项目级文档适配实现。
- 发现规划与代码冲突时停止并报告。
- Blocking 修复若需扩大文件范围，必须先由 Codex 修订 task。
执行后：
- 运行 task 指定验证命令并检查 `git diff`。
- 创建本地 task commit并输出 Report Back。

## 10. Report Back 与 Review
Report Back 必须包含：Changed Files、Implementation Summary、Tests Run、Deviations From Spec、Risks/Follow-up、Commit。
测试状态必须真实，例如：
```markdown
- [x] `uv run pytest tests/test_xxx.py -q` — passed
- [ ] `uv run pytest` — not run: task gate only
```
Codex review 检查：
- 是否满足 spec、task 和 ADR，是否遗漏 Acceptance Criteria。
- 是否越界修改、引入未声明依赖或破坏已有能力。
- 测试是否验证业务行为，而不是复制实现。
- 是否存在权限、隔离、金额精度、并发或错误处理风险。
输出固定为：
```text
Blocking
Non-blocking
Verdict: Approve | Request Changes
```
只有 Blocking 项阻止 task 或 PR 通过。

## 11. 验证门禁
Task Gate：
```bash
uv run pytest tests/test_xxx.py -q
uv run ruff check <changed-paths>
uv run ruff format --check <changed-paths>
```
Stage / PR Gate：
```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
涉及前端时追加：
```bash
cd frontend
npm run typecheck
npm run test
npm run build
```
结果写入 `verification.md`。CI 与本地结果不一致时按失败处理并调查原因。

## 12. PR 前检查
- 所有 task 为 `done` 或明确标记 `out-of-scope`。
- stage 全量验证已真实运行并记录。
- `git status` 无意外未提交改动。
- `git diff --stat main...HEAD` 与 stage 范围一致。
- 无密钥、`.env`、缓存、构建产物或大文件进入提交。
- 新增或修订 ADR 已提交到 `decisions/`。
- spec、tasks 和 verification 已随 stage 保留。

## 13. 技术栈与目录
- Python >= 3.11，依赖以 `uv.lock` 为准。
- FastAPI + Pydantic v2；SQLAlchemy Core，不使用 ORM。
- 生产 MySQL `mysql+pymysql`，测试 SQLite。
- 金额统一使用 `decimal.Decimal`；RAG 使用 ChromaDB。
- Ruff line length 为 100；当前不强制 mypy，除非 spec 声明。
```text
src/bank_reconciliation_agent/
  api/ core/ db/ schemas/ services/ agents/ rag/
scripts/      开发和数据脚本
rules/        业务规则 YAML
tests/        pytest
frontend/     Vue 3 + Vite + TypeScript + Element Plus
decisions/    长期 ADR
docs/stages/  stage 规格、任务和验证记录
```

## 14. 持久化与后端红线
持久化约定：
- service 模块顶层定义 SQLAlchemy `Table`；跨库类型沿用 `with_variant`。
- 写操作使用 `engine.begin()`；跨表原子操作透传同一 `connection`。
- 修改表结构必须同步 `db/schema.sql` 和 service 内 `Table`。
- `_ensure_initialized()` 仅用于现有本地开发和测试模式，不得隐藏生产 schema 变更。
红线：
1. 金额计算不得使用 float 或交给 LLM，一律使用 `Decimal`。
2. 所有业务查询和写入必须显式按 `user_id` 隔离。
3. RAG 无命中不得臆造 evidence，应返回无证据状态或转人工。
4. AuditAgent 输出必须包含可溯源 evidence。
5. 不引入未在 spec 或 ADR 声明的新依赖。
6. Out of Scope 和 Do Not Touch 文件不得修改。
7. 发现 spec、task 或 ADR 错误时必须报告，不得绕过。
8. 不提交密钥、`.env`、缓存、构建产物和大文件。

## 15. 前端约定
前端目录沿用 `api/`、`types/`、`constants/`、`styles/`、`components/`、`pages/`、`router/`、`composables/`。
- 不修改后端 contract，除非 spec 明确要求。
- 不引入 Pinia、Tailwind、图表库等未声明依赖。
- 本地使用 Vite proxy；生产跨域策略由部署 spec 决定。
- `X-User-ID: demo_user` 仅限本地演示，由 API 客户端统一注入。
- 枚举文案统一放 `constants/`；金额显示使用 `tabular-nums`。
- 缺字段时按 spec 降级，不虚构数据。

## 16. 常用命令
```bash
uv sync --extra dev
uv run pytest
uv run pytest tests/test_xxx.py -q
uv run ruff check .
uv run ruff format --check .
uv run uvicorn bank_reconciliation_agent.main:app --reload
cd frontend && npm run dev
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
```

## 17. 可选本地资料与沟通
个人面试资料或开发笔记可放在 gitignored 的 `docs/interview/` 或 `AGENTS.local.md`，不得成为 task、PR 或 stage 完成条件，也不得包含虚构经历或测试结果。
沟通要求：直接、具体、可执行；明确区分本地工作区、远程分支、GitHub PR 和 `main`；需要用户执行命令时给出完整命令；不隐藏阻塞问题。
