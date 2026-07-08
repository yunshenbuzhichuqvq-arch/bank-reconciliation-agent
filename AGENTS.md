# AGENTS.md
`bank-reconciliation-agent` 仓库统一协作说明。Codex 与 opencode 共享本文件，但角色严格分离：Codex 负责规划、架构决策、任务拆分、审查；opencode 负责实现、测试、报告。
## 1. 项目与协作边界
- 项目级文档以 `main` 为准：`requirements-analysis.md`、`system-prd.md`、`overall-architecture.md`、`AGENTS.md`。
- 项目按 stage 增量推进；每个 stage 基于前一阶段稳定代码。
- 本地 IDE 开发；GitHub PR 只作为合并前审查、测试记录和最终合并入口。
- `main` 只接收通过 GitHub PR 的稳定代码；禁止本地 merge 回 main。
- 角色：用户建分支、commit/push、创建 PR、决定 merge；GitHub PR 负责合并前检查；main 只保存稳定结果。
## 2. 角色分工
- Codex：维护 `ADR.md` / `spec.md` / `tasks.md`；做架构取舍、范围定义、验收设计；审查 opencode commit、diff、PR、`PR.md` 草稿。禁止写实现代码、改代码目录、自动 commit/push/merge。
- opencode：按 `tasks.md` 顺序实现单个 task；对照 Acceptance Criteria 与 DoD 自查；运行测试和 lint；提交实现 commit；每个 task 输出 Report Back；stage 收尾生成 `PR.md` 草稿。
- 用户：从最新 `main` 创建 stage 分支；执行人工确认的 commit/push；在 GitHub 创建 PR；决定是否 merge。
## 3. 全局原则
- 不假设、不隐藏疑问；发现需求、spec、task、ADR 歧义必须指出。
- 优先简单方案；不做 speculative design；不写单次使用的过度抽象。
- 只做当前 task 或当前 stage 明确要求的事。
- 每一行改动必须能追溯到当前 `TASK-N.X` 或 Codex 的规划职责。
- 不顺手重构、不扩大 API contract、不引入未声明依赖。
- 不虚构测试结果；没跑、失败、环境缺失都必须如实记录。
- 工作流优先于速度；无法验证的任务不能交付。
## 4. Git / PR 工作流
```bash
git checkout main
git pull origin main
git checkout -b stage-N-xxx
```
完成 stage 后：
```bash
git push origin stage-N-xxx
# GitHub: base=main, compare=stage-N-xxx → review/test → 页面 merge
```
合并后同步与清理：
```bash
git checkout main
git pull origin main
git branch -d stage-N-xxx
git push origin --delete stage-N-xxx
rm -f spec.md tasks.md PR.md
```
禁止：
```bash
git checkout main
git merge stage-N-xxx
git push origin main
```
如果 `git branch -d` 失败，先确认 GitHub PR 已 merge，再考虑 `git branch -D`。
## 5. main 冻结与 stage 文件生命周期
- stage 期间冻结 `main`：不直接提交、不探索性重构、不热修、不修文档；main 只通过 PR 前进。
- main 自有文档只在 main 维护：`AGENTS.md`、`requirements-analysis.md`、`system-prd.md`、`overall-architecture.md`。
- 必须热修 main 时，走 `fix/*` 分支 + PR；合并后让在途 stage 分支同步最新 `main` 并复跑测试。
```text
main: src/ + tests/ + 项目级文档 + decisions/ + AGENTS.md
stage-N-xxx:
  ADR.md    tracked；Codex 生成；收尾拆入 decisions/ 后删除
  spec.md   gitignored；Codex 维护；opencode 只读
  tasks.md  gitignored；Codex 维护；opencode 只读
  PR.md     gitignored；opencode 收尾生成；用户复制到 GitHub PR
```
`.gitignore` 必须包含：
```gitignore
/spec.md
/tasks.md
/PR.md
/docs/interview/*.md
```
可以进 main：`src/`、`tests/`、`scripts/`、`rules/`、`frontend/`、依赖文件、项目级文档、`decisions/ADR-*.md`、非 gitignored 的正式 `docs/`。不能进 main：`ADR.md`、`spec.md`、`tasks.md`、`PR.md`、`docs/interview/*.md`、密钥、`.env`、缓存、构建产物、大文件、`__pycache__`、`node_modules`。
## 6. ADR.md 防漏三道闸
删除闸：归档 `decisions/` 后执行：
```bash
git rm ADR.md
git commit -m "docs(adr): drop stage-N scratchpad"
git ls-files ADR.md
git diff --stat main...HEAD
```
要求：`git ls-files ADR.md` 为空，diff 不含 `ADR.md`。
head 闸：merge 前检查 PR head：
```bash
gh pr view <n> --json headRefOid
git ls-tree <head-oid> ADR.md
```
要求为空。
复核闸：merge 后检查：
```bash
git ls-tree origin/main ADR.md
```
要求为空；若漏入 main，走 `fix/*` 分支 + PR 删除。
## 7. commit 规范
- 使用 Conventional Commits：`feat:` / `fix:` / `test:` / `refactor:` / `docs:` / `chore:`。
- opencode 实现 commit body 必须包含 `Refs: TASK-N.X`。
```bash
git add src/... tests/...
git commit -m "feat: <一句话变更>" -m "Refs: TASK-N.X"
```
- ADR commit：`docs(adr): stage-N architectural decisions`、`docs(adr): revise ADR-N.X ...`、`docs(adr): archive stage-N decisions`、`docs(adr): drop stage-N scratchpad`。
- 一个 task 可以有多个 commit，但每个 commit 都必须关联同一个 task。
## 8. Codex 工作规则
Codex 开工前读取：当前分支、`.gitignore`、脚手架残留、项目级文档、当前 stage 相关章节、`decisions/` 历史 ADR、当前 `src/` / `frontend/` / `tests/` 结构、`docs/interview/` 已有面试资产。
如果在 `main`，Codex 只做说明、规划或提醒建 stage 分支，不生成 stage 三件套。Codex 产出顺序固定：`ADR.md → spec.md → tasks.md`，禁止跳过 ADR 直接写 spec。
Codex 禁止：写实现代码；改 `src/`、`tests/`、`scripts/`、`rules/`、`frontend/src/`；替 opencode 做实现层决策；把无法追溯到 ADR 的非平凡设计写入 spec；commit `spec.md` / `tasks.md` / `PR.md`；在 main 生成 stage 文件；自动 commit/push/merge；让用户本地 merge 回 main；编写 `PR.md`。
## 9. Codex 产物要求
`ADR.md` 记录外部依赖选型、模块边界、数据模型关键约束、错误/重试/幂等/fallback、观测策略、LLM 接入边界。变量名、普通文件位置、局部实现细节不写 ADR。每条 ADR 至少两个备选方案，Consequences 必须包含负向影响。
`ADR.md` 模板：
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
`spec.md` 是 stage 级设计契约，必须包含 Stage Goal、Builds On、In/Out of Scope、模块/接口、API contract/函数签名、Domain/数据模型、Cross-cutting、Risks/Open Questions。任何非平凡设计点必须能指回 `ADR.md` 或历史 `decisions/ADR-*.md`。
`tasks.md` 每个 task 必须包含：Status、Spec ref、ADR ref、Goal、Files create/modify/don't touch、Out of Scope、Implementation Steps、Acceptance Criteria、Definition of Done、Report Back。DoD 必须能直接复制运行；无法验证的 task 不交给 opencode。
## 10. Codex 工作模式
- 新 stage：确认在 `stage-N-*`，做体检，读取项目文档和历史 ADR，生成 `ADR.md`，提示用户 review + commit；用户确认后生成 `spec.md`，再拆 `tasks.md`，并说明 `spec.md` / `tasks.md` 不 commit。
- 调整 stage：更新 `tasks.md`，必要时同步 `spec.md`；涉及设计理由变化时先修订 `ADR.md`。
- 审查实现/PR：定位 `TASK-N.X`、`Spec ref`、`ADR ref`，对照 ADR/spec/task/DoD 检查越界修改、未声明依赖、是否破坏 main 已有能力；输出 `Blocking` / `Non-blocking` / `Approve` / `Request Changes`。通过后把 task 标为 done，不 commit。
- 修订 ADR：新决策追加 `ADR-N.X`；修订则旧条目标 `superseded`，新条目说明取代关系；用户拍板后同步 spec/tasks，并提示 commit。
- stage 收尾：检查 `git status`、当前分支、`git fetch origin`、`git diff --stat main...HEAD`；确认工作区无未提交代码改动、脚手架未被跟踪、tasks 全 done 或 out-of-scope、ADR 无 proposed；若 main 已变，让 stage merge `origin/main` 并复跑测试；有冲突则停止报告；归档 accepted ADR 到 `decisions/ADR-<stage>.<seq>-<slug>.md`；删除 `ADR.md` 并过三道闸；确认 opencode 已生成 `PR.md`；push、建 PR、审查 Files changed、测试、scope、PR.md、ADR 防漏。
## 11. opencode 工作规则
opencode 执行前必须读取：`AGENTS.md`、`spec.md`、`tasks.md`、当前 task 引用的 ADR、当前 task 相关源码和测试；涉及问题修复、优化方向或模块完成时，还要读取 `docs/interview/` 对应文档。
opencode 每次只执行一个 `TASK-N.X`。执行前确认当前分支不是 `main`，定位唯一 task，阅读 `Spec ref` 和 `ADR ref`，确认 `Files` 范围，写简短执行计划。
执行中严格按 task 顺序实现，不做 Out of Scope，不引入 spec 未声明依赖，不顺手重构，不扩大 API contract，不改规划文件适配自己的实现。发现 task 与代码现状冲突时，停止并报告。
执行后运行 task 指定 DoD；若未指定，默认：
```bash
uv run pytest
uv run ruff check .
```
涉及前端时额外运行对应前端命令。随后提交 commit，body 包含 `Refs: TASK-N.X`，并输出 Report Back。
opencode 只可修改当前 task 明确允许的文件。常见允许范围：`src/`、`tests/`、`scripts/`、`rules/`、`frontend/`、依赖文件、`db/schema.sql`、`docs/interview/`、stage 收尾时的 `PR.md`。
除非用户明确要求，opencode 不得修改：项目级文档、`ADR.md`、`spec.md`、`tasks.md`、`decisions/ADR-*.md`、与当前 task 无关的代码/测试/配置/格式化结果。发现规划文件有错，在 Report Back 中说明并停止。
## 12. Report Back 与 PR.md
Report Back 必须包含：Changed Files、Implementation Summary、Tests Run、Deviations From Spec、Risks/Follow-up、Interview Docs、Commit。测试未跑、失败或环境缺失时写真实状态，例如：
```markdown
- [ ] `uv run pytest` — not run: <原因>
```
不得写“应该通过”。
默认一个 stage 一个 PR，一个 task 一个或多个 commit。`PR.md` 由 opencode 在所有 task 完成后生成，用户复制到 GitHub PR 描述框；`PR.md` gitignored，不 commit；Codex 只审查。
`PR.md` 必须包含：变更内容、对应任务、架构决策、测试情况、风险点、Reviewer 重点检查、不在本 PR 范围内。字段来源：Report Back、`tasks.md`、归档 ADR、`spec.md` Out of Scope。
PR 前必须满足：所有 task 完成或明确 out-of-scope；DoD 真实运行并记录；无未提交改动；无不该提交文件；无 `ADR.md` / `spec.md` / `tasks.md` / `PR.md` / `docs/interview/*.md` 进入 PR。若 Codex 返回 `Request Changes`，opencode 只修改 Blocking 项。
## 13. 面试资产维护
三类本地面试资产固定放在 `docs/interview/`，必须 gitignored，不进入 PR/main；内容必须来自真实开发过程、真实代码结构、真实设计取舍，不得编造生产经历、故障、测试结果或项目落地情况。
```text
docs/interview/
  issue-log.md        # 已遇到、分析、解决或规避的问题
  pending-issues.md   # 待解决问题、优化方向、新功能、技术债
  project-qa-bank.md  # 从项目代码和架构抽取的八股题库
```
触发规则：真实问题/失败/冲突/排查 → 更新 `issue-log.md`；暂不解决的优化/技术债/新功能 → 更新 `pending-issues.md`；完成或审查重要模块 → 更新 `project-qa-bank.md`。没有真实内容时写 `Interview docs: no update needed`。
`issue-log.md` 每条必须写清 Situation、Task、Action、Result、Root Cause、Alternatives Considered、Final Solution、Interview Talking Point、Related Files。若未完全解决，同步追加到 `pending-issues.md`。
`pending-issues.md` 每条必须写 Background、Current Limitation、Possible Direction、Technical Value、Priority、Estimated Difficulty、Related Modules。优先记录观测、评估、失败恢复、状态持久化、工具权限、幂等、RAG 召回、Agent 循环控制、成本与延迟、测试覆盖、部署稳定性等高价值项。Codex 规划 stage 时优先从该文件挑选高价值项进入 ADR/spec/tasks。
`project-qa-bank.md` 每题必须写 Short Answer、Project Context、Deep Dive、Related Code、Possible Follow-up Questions。题目必须来自当前项目代码、架构决策、测试和问题日志；每个重要模块完成后至少补充 3-5 道。
## 14. 技术栈与目录
- Python >= 3.11，uv，以 `uv.lock` 为准；FastAPI + Pydantic v2；SQLAlchemy Core，非 ORM；生产 MySQL `mysql+pymysql`；测试 SQLite；金额统一 `decimal.Decimal`；RAG 使用 ChromaDB；Lint 使用 ruff，line-length=100；当前无 mypy/typecheck，除非 spec 声明。
```text
src/bank_reconciliation_agent/
  api/       FastAPI 路由；dependencies.py 鉴权；v1/router.py 挂载子路由
  core/      config.py，pydantic-settings，读取 .env
  db/        session.py engine 工厂 + schema.sql MySQL DDL
  schemas/   Pydantic 模型；common.py: ApiResponse[T] / Page[T]
  services/  业务 + 持久化；每个 service 自带 Table，懒 create_all
  agents/    Agent 实现
  rag/       retriever.py，ChromaDB 检索
scripts/     generate_mock_excel.py、build_rule_chunks.py
rules/       业务规则 YAML
mock_data/   固定样本 Excel
tests/       pytest；conftest.py 将 DB 指向 sqlite
frontend/    Vue 3 + Vite + TypeScript + Element Plus
decisions/   长期 ADR，进入 main
```
持久化模式必须沿用：service 模块顶层定义 `Table`；跨库兼容使用 `BigInteger().with_variant(Integer, "sqlite")`、`JSON().with_variant(Text, "sqlite")`；`_ensure_initialized()` 内 `metadata.create_all(engine, tables=[...])`；service 为模块级单例；写操作用 `engine.begin()`；跨表原子时透传 `connection`。
## 15. 常用命令
```bash
uv sync --extra dev
uv run pytest
uv run pytest tests/test_xxx.py -q
uv run ruff check .
uv run ruff format .
uv run python -m scripts.generate_mock_excel
uv run python -m scripts.reset_db --yes
uv run uvicorn bank_reconciliation_agent.main:app --reload
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npm run test
```
DoD 默认以 `uv run pytest` + `uv run ruff check .` 通过为准；涉及前端时加前端 typecheck/build/test。
## 16. 后端红线
1. 金额计算绝不交给 LLM 或 float，一律使用 `Decimal`。
2. RAG 无命中必须转人工，不得臆造 evidence。
3. AuditAgent 输出必须含可溯源 evidence。
4. 所有业务查询必须显式按 `user_id` 过滤，不得跨用户读写。
5. 不引入未在 spec/ADR 声明的新依赖。
6. 只做当前 spec In Scope；Out of Scope / don't touch 文件一律不动。
7. `db/schema.sql` 与 service 内 `Table` 定义是同一 schema 的两个产物，改一处必须同步另一处。
8. 发现 spec、task、ADR 有错或缺口，显式提出，不绕过。
9. 不提交密钥、`.env`、缓存、构建产物、大文件。
10. 不在 `main` 上写代码、提交代码或 merge 代码。
## 17. 前端约定
前端位于 `frontend/`，与 Python 后端隔离。范围以 `spec.md` 和当前 task 为准。
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
前端红线：不碰后端契约，除非 spec 要求；跨域只用 Vite proxy，不加 CORS；不引入 Pinia、Tailwind、图表库等未声明依赖；每个请求带 `X-User-ID: demo_user`，由 api 客户端统一注入；枚举文案统一走 `constants/`；金额显示使用等宽数字和 `tabular-nums`；遵循 `overall-frontend-design-style.md` 和设计 token；缺字段按 spec 降级，不虚构数据。
## 18. 自检清单
Codex 自检：ADR 是否覆盖关键取舍、每条有 Slug、至少两个备选、Consequences 含负向影响、与历史 ADR 不冲突；spec 是否有 Stage Goal、Builds On、In/Out of Scope、接口/签名/contract，且非平凡设计点能指回 ADR；tasks 是否有 Spec ref、ADR ref、可验证 AC、可复制 DoD、Report Back；PR review 是否核对变更、测试、风险、scope、脚手架防漏、三道闸、`docs/interview/` 是否真实维护且未进 PR。
opencode 自检：当前分支不是 `main`；已定位唯一 task；已读取 Spec ref 和 ADR ref；已确认 Files 范围；未做 Out of Scope；未新增未声明依赖；未顺手重构；未修改规划文件；每个改动可追溯到当前 task；DoD 已真实运行；已检查是否需要更新 `docs/interview/`；`docs/interview/*.md` 被 `.gitignore` 忽略且未进 commit；commit body 含 `Refs: TASK-N.X`；Report Back 完整。
## 19. 沟通风格
- 直接、具体、可执行；少用形容词，不写空泛评价。
- 发现 ADR 错误时，走修 ADR → 提示 commit → 同步 spec/tasks。
- 需要用户执行命令时，明确给出命令与 commit message。
- 明确区分本地开发、远程分支、GitHub PR、main 合并。
- review 结论必须落到 `Blocking`、`Non-blocking`、`Approve` 或 `Request Changes`。
