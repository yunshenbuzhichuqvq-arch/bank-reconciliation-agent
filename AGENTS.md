# AGENTS.md
本文件是 `bank-reconciliation-agent` 仓库的统一协作说明。open code 与 Codex 共享此文件，但角色不同：open code 负责规划、架构决策和代码审查；Codex 负责实现、测试和报告。
## 1. 项目背景
- 项目：`bank-reconciliation-agent`
- 项目级文档以 `main` 为准：`requirements-analysis.md`、`system-prd.md`、`overall-architecture.md`
- 项目按 stage 增量推进，每个 stage 建立在前一阶段稳定代码之上
- 开发在本地 IDE 完成；GitHub PR 只负责合并前审查、测试记录与最终合并
- `main` 只接收通过 GitHub PR 的稳定代码
## 2. 角色分工
```text
open code:     规划 + 约束 + 审查
Codex:     执行 + 测试 + 报告
用户:       建分支 + commit/push + 创建 PR + 决定 merge
GitHub PR: 合并前检查 + review 记录 + 合并入口
main:      只接收已通过 PR 的稳定代码
```
- open code：生成和维护 `ADR.md` / `spec.md` / `tasks.md`，做架构取舍、范围定义、任务拆分和验收设计，审查 Codex 的 commit、分支 diff、PR 与 `PR.md` 草稿。open code 不写实现代码，不改代码目录。
- Codex：按 `tasks.md` 顺序实现当前 task，对照 Acceptance Criteria 与 DoD 自查，运行测试和 lint，提交实现 commit，每个 task 输出 Report Back，stage 收尾汇总生成 `PR.md` 草稿。
- 用户：从最新 `main` 创建本地 stage 分支，执行需要人工确认的 commit / push，在 GitHub 创建 PR，并决定是否 merge。
## 3. 全局原则
- 不假设、不隐藏疑问；发现需求、spec、task、ADR 歧义时必须指出。
- 优先简单方案；不做 speculative design，不写单次使用的过度抽象。
- 只做当前 task 或当前 stage 明确要求的事。
- 每一行改动都必须能追溯到当前 `TASK-N.X` 或 open code 的规划职责。
- 不顺手重构、不扩大 API contract、不引入未声明依赖。
- 不虚构测试结果；没跑、失败、环境缺失都必须如实记录。
- 工作流优先于速度；无法验证的任务不能交付。
## 4. Git / PR 工作流
用户从最新 `main` 创建 stage 分支：
```bash
git checkout main
git pull origin main
git checkout -b stage-N-xxx
```
stage 开发在本地分支完成。完成后 push 到 GitHub，由用户创建 PR：
```bash
git push origin stage-N-xxx
# GitHub: base=main, compare=stage-N-xxx → review/test → 页面 merge
```
合并后本地同步与清理：
```bash
git checkout main
git pull origin main
git branch -d stage-N-xxx
git push origin --delete stage-N-xxx
rm -f spec.md tasks.md PR.md
```
禁止本地 merge 回 main：
```bash
# 禁止
git checkout main
git merge stage-N-xxx
git push origin main
```
如果 `git branch -d` 失败，先确认 GitHub PR 已 merge，再考虑 `git branch -D`。不要用本地 merge + push 推进 main。
## 5. main 冻结与文档维护
stage 期间冻结 `main`：不向 `main` 直接提交任何东西，不在 `main` 上做探索性重构、热修、文档修补，`main` 只通过 PR 前进。
main 自有文档只在 main 维护：`AGENTS.md`、`requirements-analysis.md`、`system-prd.md`、`overall-architecture.md`。stage 分支内不要随意修改这些文档，避免 PR 合并时覆盖 main 文档。必须热修 main 时，走 `fix/*` 分支 + PR；合并后让在途 stage 分支同步最新 `main` 并复跑测试。
## 6. stage 文件生命周期
```text
main 永远干净：src/ + tests/ + 项目级文档 + decisions/ + AGENTS.md
stage-N-xxx：
  ADR.md     tracked，stage 开头由 open code 生成，收尾拆进 decisions/ 后删除
  spec.md    gitignored，open code 维护，Codex 只读
  tasks.md   gitignored，open code 维护，Codex 只读
  PR.md      gitignored，Codex 收尾生成，用户复制进 GitHub PR 描述
```
`.gitignore` 必须包含：
```gitignore
/spec.md
/tasks.md
/PR.md
/docs/interview/*.md
```

`docs/interview/` 下产生的面试资产文件属于本地复盘材料，必须 gitignored，不进入 PR 或 main。若需要保留目录结构，可只提交 `docs/interview/.gitkeep`，但不得提交 `issue-log.md`、`pending-issues.md`、`project-qa-bank.md`。
`ADR.md` 不加入 `.gitignore`，因为它在 stage 中需要 tracked，但最终不能进入 main。
```bash
git check-ignore spec.md tasks.md PR.md docs/interview/issue-log.md docs/interview/pending-issues.md docs/interview/project-qa-bank.md  # 应命中
git check-ignore ADR.md                  # 应返回空
```
可以进 main：`src/`、`tests/`、`scripts/`、`rules/`、`frontend/`、依赖文件、`AGENTS.md`、项目级文档、`decisions/ADR-*.md`、`docs/` 中非 gitignored 的正式文档。
不能进 main：`ADR.md`、`spec.md`、`tasks.md`、`PR.md`、`docs/interview/*.md`、密钥、`.env`、缓存、构建产物、大文件、`__pycache__`、`node_modules`。
## 7. ADR.md 防漏三道闸
删除闸：push 前必须归档 `decisions/` 后执行：
```bash
git rm ADR.md
git commit -m "docs(adr): drop stage-N scratchpad"
git ls-files ADR.md
git diff --stat main...HEAD
```
要求：`git ls-files ADR.md` 为空，`git diff --stat main...HEAD` 不含 `ADR.md`。
head 闸：merge 前检查 PR head，避免 PR 早开但删除 commit 没进入 head：
```bash
gh pr view <n> --json headRefOid
git ls-tree <head-oid> ADR.md
```
要求：`git ls-tree <head-oid> ADR.md` 为空。
复核闸：merge 后检查 origin/main：
```bash
git ls-tree origin/main ADR.md
```
要求：为空。若漏入 main，走 `fix/*` 分支 + PR 删除，不在 main 直接删。
## 8. commit 规范
使用 Conventional Commits：`feat:` / `fix:` / `test:` / `refactor:` / `docs:` / `chore:`。
Codex 实现 commit body 必须包含：
```text
Refs: TASK-N.X
```
示例：
```bash
git add src/... tests/...
git commit -m "feat: <一句话变更>" -m "Refs: TASK-N.X"
```
ADR 相关 commit：
```text
docs(adr): stage-N architectural decisions
docs(adr): revise ADR-N.X ...
docs(adr): archive stage-N decisions
docs(adr): drop stage-N scratchpad
```
一个 task 可以有多个 commit，但每个 commit 都必须关联同一个 task。
## 9. open code 工作规则
open code 每次开工前读取：当前分支、`.gitignore` 和脚手架残留、`AGENTS.md`、`overall-architecture.md`、`system-prd.md`、`requirements-analysis.md` 当前 stage 相关章节、`decisions/` 下所有历史 ADR、当前 `src/` / `frontend/` / `tests/` 结构，以及 `docs/interview/` 已有面试资产文档。
如果当前在 `main`，open code 只做说明、规划或提醒建 stage 分支，不生成 stage 三件套。
open code 禁止事项：不写实现代码；不改 `src/`、`tests/`、`scripts/`、`rules/`、`frontend/src/`；不替 Codex 做实现层决策；不在 `spec.md` 写入无法追溯到 ADR 的非平凡设计选择；不 commit `spec.md` / `tasks.md` / `PR.md`；不在 `main` 上生成 `ADR.md` / `spec.md` / `tasks.md`；不自动 commit / push / merge；不让用户本地 merge 回 main；不写 `PR.md`，只审查 Codex 生成的草稿。
open code 产出顺序固定：`ADR.md → spec.md → tasks.md`。跳过 `ADR.md` 直接写 `spec.md` 禁止。
## 10. open code 产物模板
`ADR.md`：
```markdown
# Stage N — Architectural Decisions
## ADR-N.1: <决策标题>
**Slug**: `<short-slug-for-filename>`
**Status**: proposed | accepted | rejected | superseded
**Date**: YYYY-MM-DD
### Context
### Options Considered
- Option A: Pros / Cons
- Option B: Pros / Cons
### Decision
### Consequences
```
ADR 写外部依赖选型、模块边界、数据模型关键约束、错误/重试/幂等/Fallback、观测策略、LLM 接入边界。变量名、普通文件位置、局部实现细节不写 ADR。每条 ADR 至少两个备选方案，Consequences 必须包含负向影响。
`spec.md`：
```markdown
# Stage N Spec: <名称> (scratchpad, gitignored)
## Stage Goal
## Builds On
- main 当前状态
- ADR.md
- decisions/ADR-X.Y-xxx.md
## Scope
### In Scope
### Out of Scope
## Design
### 涉及的模块与接口
### API Contract / 函数签名
### Domain / 数据模型变更
### Cross-cutting
## Risks & Open Questions
```
`spec.md` 是 stage 级设计契约。任何非平凡设计点必须能指回 `ADR.md` 或历史 `decisions/ADR-*.md`。
`tasks.md`：
```markdown
# Stage N Tasks (scratchpad, gitignored)
> Codex 按序执行；Acceptance Criteria 全勾 + DoD 全过才算完成。
> 发现 spec 歧义 / ADR 缺对应条目，停止并报告，不自行决策。
## TASK-N.1: <标题>
**Status**: todo | in-progress | review | done | blocked
**Spec ref**: spec.md §<章节>
**ADR ref**: ADR-N.X 或 decisions/ADR-X.Y-xxx.md
**Goal**: <一句话>
**Files**: create / modify / don't touch
**Out of Scope**: ...
**Implementation Steps**: 1. ...
**Acceptance Criteria**: - [ ] ...
**Definition of Done**: `uv run pytest ...` + `uv run ruff check ...`
**Report Back**: Changed files / Tests run / Deviations / Risks
```
每个 task 的 DoD 必须能直接复制运行。无法验证的 task 不交给 Codex。
## 11. open code 工作模式
开启新 stage：确认在 `stage-N-*`，做体检，读取项目文档和历史 ADR，生成 `ADR.md`，提示用户 review + commit；用户确认后生成 `spec.md`，再拆 `tasks.md`，并说明 `spec.md` / `tasks.md` 不 commit。
调整 stage 内容：更新 `tasks.md`，必要时同步 `spec.md`；涉及设计理由变化时，先修订 `ADR.md`。
审查 Codex 实现或 PR：定位 `TASK-N.X`、`Spec ref`、`ADR ref`，对照 `ADR` / `spec` / `task` / `DoD`，检查越界修改、未声明依赖、是否破坏 main 已有能力，输出 `Blocking` / `Non-blocking` / `Approve` / `Request Changes`。通过后把 `tasks.md` 对应 task 标为 done，不 commit。
补充或修订 ADR：新决策追加 `ADR-N.X`；修订则旧条目标 `superseded`，新条目说明取代关系；用户拍板后同步受影响的 `spec.md` / `tasks.md`，并提示 commit `ADR.md` 修订。
stage 收尾：
```bash
git status
git branch --show-current
git fetch origin
git diff --stat main...HEAD
```
确认在 `stage-N-*`，工作区无未提交代码改动，脚手架未被跟踪。若 main 已变，让 stage 分支 merge `origin/main` 并复跑测试；有冲突则停止报告，不擅自改实现代码。随后确认 tasks 全 done 或 out-of-scope，ADR 无 proposed；将 accepted ADR 拆入 `decisions/ADR-<stage>.<seq>-<slug>.md`，提示 commit：`docs(adr): archive stage-N decisions`；删除 `ADR.md` 并通过删除闸；确认 Codex 已生成 `PR.md`；push 分支并创建 GitHub PR；审查 Files changed、测试、scope、`PR.md`、ADR 防漏 head 闸；合并后执行复核闸。
## 12. Codex 工作规则
Codex 每次执行前必须读取：`AGENTS.md`、`spec.md`、`tasks.md`、当前 task 引用的 `ADR.md` 或 `decisions/ADR-*.md`、当前 task 相关源码和测试；涉及问题修复、优化方向或模块完成时，还必须读取 `docs/interview/` 下对应文档。
Codex 每次只执行一个 `TASK-N.X`。执行前确认当前分支不是 `main`，定位当前 task，阅读 `Spec ref` 和 `ADR ref`，确认 `Files` 范围，写出简短执行计划。
执行中严格按 task 顺序实现，不做 Out of Scope，不引入 spec 未声明的新依赖，不顺手重构，不扩大 API contract，不改规划文件来适配自己的实现。发现 task 与代码现状冲突时，停止并报告。
执行后运行 task 指定 DoD。若 task 未指定 DoD，默认运行：
```bash
uv run pytest
uv run ruff check .
```
涉及前端时，额外运行对应前端命令。随后提交 commit，body 包含 `Refs: TASK-N.X`，并输出 Report Back。
Codex 只可修改当前 task 明确允许的 `Files.modify` / `Files.create` 文件。常见范围：`src/`、`tests/`、`scripts/`、`rules/`、`frontend/`、依赖文件、`db/schema.sql`、`docs/interview/`、stage 收尾时的 `PR.md`。
除非用户明确要求，Codex 不得修改：`AGENTS.md`、`requirements-analysis.md`、`system-prd.md`、`overall-architecture.md`、`ADR.md`、`spec.md`、`tasks.md`、`decisions/ADR-*.md`、与当前 task 无关的代码、测试、配置、格式化结果。发现规划文件有错，在 Report Back 中说明并停止，不擅自改。
## 13. Report Back 与 PR.md
Report Back 模板：
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
### Interview Docs
- Updated: yes/no
- Files: `docs/interview/...` or `N/A`
- Git status: ignored / not committed
### Commit
- `<commit hash>`: `<commit message>`
```
测试未跑、失败或环境缺失时必须写真实状态：
```markdown
### Tests Run
- [ ] `uv run pytest` — not run: <原因>
```
不要写“应该通过”。只能记录真实结果。
默认一个 stage 一个 PR，一个 task 一个或多个 commit。`PR.md` 由 Codex 在 stage 全部 task 完成后生成，用户复制到 GitHub PR 描述框。`PR.md` 是 gitignored 临时文件，不 commit。open code 只审查，不编写。
`PR.md` 模板：
```markdown
# Stage N: <一句话标题>
## 变更内容
- ...
## 对应任务
- [x] TASK-N.1 ...
## 架构决策
- decisions/ADR-N.1-xxx.md
## 测试情况
- [x] uv run pytest
- [x] uv run ruff check .
- [x] 前端 typecheck/build（如涉及前端）
## 风险点
- ...
## Reviewer 重点检查
- ...
## 不在本 PR 范围内
- ...
```
字段来源：变更内容、测试情况、风险点、偏差来自各 task Report Back；对应任务来自 `tasks.md`；架构决策列本 stage 已归档的 `decisions/ADR-*.md`；不在本 PR 范围内来自 `spec.md` 的 Out of Scope。
PR 前必须满足：所有当前 stage task 完成或明确 out-of-scope；DoD 命令真实运行并记录；无未提交改动；无不该提交文件；无 `ADR.md` / `spec.md` / `tasks.md` / `PR.md` / `docs/interview/*.md` 进入 PR。如果 open code review 返回 `Request Changes`，Codex 只修改 Blocking 项要求的内容，不顺手扩展。
## 14. 面试资产维护
项目需要长期维护三类面试资产文档，用于记录真实问题、沉淀优化方向、从项目反向抽取基础题。open code 负责规划与审查这些文档的质量；Codex 在实现和测试后按真实情况补充记录。不得编造生产经历、虚构故障、虚构测试结果或夸大项目落地情况。

三类文档固定放在：
```text
docs/interview/
  issue-log.md          # 已遇到、已分析、已解决或已规避的问题
  pending-issues.md     # 待解决问题、优化方向、新功能、技术债
  project-qa-bank.md    # 从项目代码和架构中抽取的八股题库
```

如果目录或文件不存在，允许在对应 task 或 stage 收尾时创建。`docs/interview/*.md` 必须加入 `.gitignore`，只作为本地面试资产维护，不得进入 PR 或 main。其内容必须来自真实开发过程、真实代码结构、真实设计取舍。

### 14.1 问题日志：issue-log.md
当开发、测试、审查或联调中出现 bug、失败测试、设计冲突、依赖问题、数据问题、性能问题、RAG 命中问题、Agent 工具调用问题、状态流转问题、权限问题、部署问题时，维护 `docs/interview/issue-log.md`。

每条记录使用以下结构：
```markdown
## [YYYY-MM-DD] <问题标题>

### Situation
当时在开发或测试什么模块？上下文是什么？

### Task
预期要完成什么？正确行为应该是什么？

### Action
排查了哪些方向？尝试了哪些方案？做了哪些改动？

### Result
最终结果是什么？已解决、规避、延期，还是转入待解决问题？

### Root Cause
根因是什么？

### Alternatives Considered
- 方案 A：优点 / 缺点
- 方案 B：优点 / 缺点

### Final Solution
最终采用什么方案？为什么？

### Interview Talking Point
面试时如何把这个问题讲成一个工程化解决案例？

### Related Files
- `path/to/file.py`
- `path/to/test_file.py`
```

记录规则：
- 不写“修了一个 bug”这类流水账。
- 必须写清楚问题、根因、备选方案、最终方案和结果。
- 能关联代码文件就必须写 Related Files。
- 如果问题没有完全解决，必须同步追加到 `pending-issues.md`。
- 该日志天然服务于 STAR 表达，但不得伪造生产事故或团队协作背景。

### 14.2 待解决问题：pending-issues.md
当发现优化方向、新功能、技术债、架构欠缺、评测不足、观测不足、异常处理不完整、权限边界不清、部署体验差、RAG 质量不稳定、Agent 控制策略不完善时，维护 `docs/interview/pending-issues.md`。

每条记录使用以下结构：
```markdown
## [PENDING] <问题或想法标题>

### Background
为什么这个问题或想法重要？

### Current Limitation
当前系统哪里做得不够？

### Possible Direction
可能怎么解决？

### Technical Value
这个优化能体现什么工程能力？

### Priority
High / Medium / Low

### Estimated Difficulty
Easy / Medium / Hard

### Related Modules
- module name
- `path/to/file.py`
```

记录规则：
- 先记录，再决定是否进入后续 stage。
- 不为了显得复杂而堆优化项。
- 优先记录能增强项目可信度的方向：观测、评估、失败恢复、状态持久化、工具权限、幂等、RAG 召回、Agent 循环控制、成本与延迟控制、测试覆盖、部署稳定性。
- stage 规划时，open code 应优先从该文件中挑选高价值项进入 `ADR.md` / `spec.md` / `tasks.md`。

### 14.3 项目八股题库：project-qa-bank.md
当一个主要模块被实现、重构、审查或修复后，维护 `docs/interview/project-qa-bank.md`。题目必须从当前项目代码、架构决策、测试和问题日志中抽取，不写脱离项目的纯教材题。

每道题使用以下结构：
```markdown
## Q: <问题>

### Short Answer
适合面试时先说出的简短答案。

### Project Context
这个问题在本项目中对应哪个模块、链路或设计取舍？

### Deep Dive
展开解释原理、实现方式、边界条件和取舍。

### Related Code
- `path/to/file.py`

### Possible Follow-up Questions
- 追问 1
- 追问 2
```

题库范围包括但不限于：
- Python / FastAPI / Pydantic
- SQLAlchemy Core / MySQL / SQLite / 事务 / 索引
- Decimal 金额计算
- Redis / 缓存 / 幂等 / 去重，若项目引入
- RAG chunk / embedding / ChromaDB / 检索失败处理
- Agent 状态机 / 工具调用 / fallback / 人工介入
- 观测、日志、评估、测试、异常恢复
- Docker / 部署 / 配置管理，若项目涉及
- API contract / 权限控制 / `user_id` 隔离

维护规则：
- 每个重要模块完成后，至少补充 3-5 道与该模块相关的问题。
- 每道题必须能指向项目上下文或相关代码。
- 用户要求“每天十道题”“从项目抽八股”“结合项目复习”时，优先从该文件选题；不足时再基于当前项目代码补充生成，并写回题库。

### 14.4 自动维护触发条件
open code 与 Codex 在每次任务结束前都要检查是否需要维护上述三类文档：

1. 出现真实问题、失败、冲突、排查过程：更新 `issue-log.md`。
2. 出现暂不解决的优化方向、技术债、新功能想法：更新 `pending-issues.md`。
3. 完成或审查了重要模块：更新 `project-qa-bank.md`。

不需要每次强行更新。没有真实内容时，在 Report Back 或 review 结论中写明：`Interview docs: no update needed`。如果有更新，必须写明更新了哪些文件、记录了什么内容。

## 15. 技术栈与目录
- Python >= 3.11，uv，以 `uv.lock` 为准
- FastAPI + Pydantic v2
- SQLAlchemy Core，非 ORM，使用 `Table` + `MetaData`
- 生产库 MySQL：`mysql+pymysql`
- 测试库 SQLite：`tests/conftest.py` 覆写 `MYSQL_DSN` 为临时 sqlite 文件
- 金额统一使用 `decimal.Decimal`
- RAG 使用 ChromaDB
- Lint：ruff，line-length=100
- 当前无 mypy/typecheck 配置，除非 spec 另行声明
```text
src/bank_reconciliation_agent/
  api/            FastAPI 路由层；dependencies.py 做鉴权；v1/router.py 挂载子路由
  core/           config.py，pydantic-settings，读取 .env
  db/             session.py engine 工厂 + schema.sql MySQL DDL，手工维护
  schemas/        Pydantic 模型；common.py 有 ApiResponse[T] / Page[T]
  services/       业务 + 持久化；每个 service 自带 SQLAlchemy Table，懒 create_all
  agents/         Agent 实现
  rag/            retriever.py，ChromaDB 检索
scripts/          generate_mock_excel.py、build_rule_chunks.py
rules/            业务规则 YAML
mock_data/        固定样本 Excel
tests/            pytest；conftest.py 把 DB 指向 sqlite
spec.md           open code 维护，Codex 只读，gitignored
tasks.md          open code 维护，Codex 只读，gitignored
decisions/        长期 ADR，进入 main
```
持久化模式必须沿用：每个 service 模块顶层定义 `Table`，跨库兼容写法使用 `BigInteger().with_variant(Integer, "sqlite")`、`JSON().with_variant(Text, "sqlite")`，`_ensure_initialized()` 内使用 `metadata.create_all(engine, tables=[...])`。service 为模块级单例，写操作用 `engine.begin()`，需要跨表原子时透传 `connection` 参数。
## 16. 常用命令
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
## 17. 后端红线
1. 金额计算绝不交给 LLM 或 float，一律使用 `Decimal`
2. RAG 无命中必须转人工，不得臆造 evidence
3. AuditAgent 输出必须含可溯源 evidence
4. 所有业务查询必须显式按 `user_id` 过滤，不得跨用户读写
5. 不引入未在 spec / ADR 声明的新依赖
6. 只做当前 spec In Scope；Out of Scope / don't touch 文件一律不动
7. `db/schema.sql` 与 service 内 `Table` 定义是同一 schema 的两个产物，改一处必须同步另一处
8. 发现 spec、task、ADR 有错或缺口，显式提出，不绕过
9. 不提交密钥、`.env`、缓存、构建产物、大文件
10. 不在 `main` 上写代码、提交代码或 merge 代码
## 18. 前端约定
前端代码位于 `frontend/`，与 Python 后端隔离。技术栈：Vue 3 + Vite + TypeScript + Element Plus。具体范围以 `spec.md` 和当前 task 为准。
```text
frontend/src/
  api/          axios 客户端，拆 ApiResponse 信封，注入 X-User-ID
  types/        镜像后端 schema 的 TS 类型
  constants/    status/risk/error_type 中文标签 + 色调
  styles/       tokens.css / element-overrides.css
  components/   AppShell + ui/ 基础组件
  pages/        页面
  router/       路由
  composables/  组合式逻辑
```
前端命令：
```bash
cd frontend && npm install
npm run dev
npm run typecheck
npm run build
npm run test
```
前端红线：不碰后端契约，除非 spec 明确要求；跨域只用 Vite proxy，不加 CORS；不引入 Pinia、Tailwind、图表库等未声明依赖；每个请求带 `X-User-ID: demo_user`，由 api 客户端统一注入；枚举文案统一走 `constants/`；金额显示使用等宽数字和 `tabular-nums`；遵循 `overall-frontend-design-style.md` 和设计 token；缺字段按 spec 降级，不虚构数据。
## 19. 自检清单
open code 自检：ADR 是否覆盖关键架构取舍、每条有 Slug、至少两个备选、Consequences 含负向影响、与历史 ADR 不冲突；spec 是否有清晰 Stage Goal、Builds On、In/Out of Scope、接口/签名/contract，且非平凡设计点能指回 ADR；tasks 是否有 Spec ref、ADR ref、可验证 AC、可复制 DoD、Report Back 模板；PR review 是否核对变更、测试、风险、scope、脚手架防漏、三道闸，以及 `docs/interview/` 是否按真实问题和模块变化在本地维护且未进入 PR。
Codex 自检：当前分支不是 `main`；已定位唯一 task；已读取 `Spec ref` 和 `ADR ref`；已确认 `Files` 范围；没有做 Out of Scope；没有新增未声明依赖；没有顺手重构；没有修改规划文件；每个改动都能追溯到当前 task；DoD 已真实运行；已检查是否需要更新 `docs/interview/`；`docs/interview/*.md` 已被 `.gitignore` 忽略且未进入 commit；commit body 含 `Refs: TASK-N.X`；Report Back 完整。
## 20. 沟通风格
- 直接、具体、可执行
- 少用形容词，不写空泛评价
- 发现 ADR 错误时，走修 ADR → 提示 commit → 同步 spec/tasks 的流程
- 需要用户执行命令时，明确给出命令与 commit message
- 明确区分本地开发、远程分支、GitHub PR、main 合并
- review 结论必须落到 Blocking、Non-blocking、Approve 或 Request Changes
