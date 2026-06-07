Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"
- "Refactor X" -> "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

--- project-doc ---

# AGENTS.md

给 Codex 的常驻上下文。开工前必读；与当前 stage 的 `spec.md` + `tasks.md`（单文件，含各 `TASK-N.X` 小节；均为 gitignored 脚手架）配合使用，spec/tasks 优先。

## 一句话简介

基于多智能体的多账源智能对账与审计辅助系统。当前阶段 **MVP-2a-1：三 Agent LLM 化 + 3 级 Fallback**（LLMProvider 抽象，Fake 默认 / DeepSeek 可选；银企对账主链路；增强 RAG 留 2a-2，清算副链路留 2a-3）。

## 技术栈

- Python ≥ 3.11，包管理 **uv**（`uv.lock` 为准）。
- FastAPI + Pydantic v2，SQLAlchemy Core（**非 ORM**，用 `Table` + `MetaData`）。
- 生产库 MySQL（`mysql+pymysql`）；**测试库 SQLite**（`tests/conftest.py` 覆写 `MYSQL_DSN` 为临时 sqlite 文件）。
- 金额一律 `decimal.Decimal`；RAG 用 ChromaDB。
- Lint：ruff（line-length=100）。无 mypy/typecheck 配置。

## 目录结构与职责

```
src/bank_reconciliation_agent/
  api/            FastAPI 路由层。dependencies.py 做鉴权；v1/router.py 挂载子路由
  core/           config.py（pydantic-settings，读 .env）
  db/             session.py（engine 工厂）+ schema.sql（MySQL DDL，手工维护）
  schemas/        Pydantic 模型：common.py 有 ApiResponse[T]/Page[T] 信封
  services/       业务 + 持久化。每个 service 自带 SQLAlchemy Table，懒 create_all
  agents/         audit_agent.py（MVP-1 仍为确定性，无 LLM）
  rag/            retriever.py（ChromaDB 检索）
scripts/          generate_mock_excel.py、build_rule_chunks.py
rules/            业务规则（MVP-1 新增 YAML 规则库）
mock_data/        固定样本 Excel
tests/            pytest；conftest.py 把 DB 指向 sqlite
spec.md tasks.md decisions/   ← Planner 维护，Codex 只读（spec.md/tasks.md 为 gitignored 脚手架；ADR 归档在 decisions/）
```

持久化模式（务必沿用）：每个 service 模块顶层定义 `Table`，跨库兼容写法
`BigInteger().with_variant(Integer, "sqlite")`、`JSON().with_variant(Text, "sqlite")`，
`_ensure_initialized()` 内 `metadata.create_all(engine, tables=[...])`；
service 为模块级单例；写操作用 `engine.begin()`，需要跨表原子时透传 `connection` 参数。

## 命令（可直接复制运行）

```bash
uv sync --extra dev                                   # 安装依赖（含 dev）
uv run pytest                                         # 全部测试
uv run pytest tests/test_xxx.py -q                    # 单文件
uv run ruff check .                                   # lint
uv run ruff format .                                  # 格式化
uv run python -m scripts.generate_mock_excel          # 重新生成 mock Excel
uv run python -m scripts.reset_db --yes               # 重建本地 dev MySQL（会 drop 当前库所有表）
uv run uvicorn bank_reconciliation_agent.main:app --reload   # 本地起服务
```

DoD 默认以 `uv run pytest` + `uv run ruff check .` 跑绿为准。

## 红线（违反即打回）

1. **金额计算绝不交给 LLM/float**，一律 `Decimal`。
2. **RAG 无命中 → 转人工**，不臆造 evidence；AuditAgent 输出必须含可溯源 evidence。
3. **MVP-1 起所有业务查询显式按 `user_id` 过滤**，不得跨用户读写。
4. **不引入未在 spec 注明的新依赖**；本 stage（2a-1）spec 注明的新依赖仅 `openai`、`structlog`（见 ADR-005/008）。
5. 2a-1 **不碰**：LangGraph（留 2b）、Hook 链、记忆引擎、Agent 并行、SSE、后台队列、Redis、JWT、Hybrid/Reranker/Query-Rewrite（留 2a-2）、MCP。真实 LLM 经 Provider 抽象**已纳入**本 stage。
6. **只做当前 spec In Scope 的事**；spec 的 `Out of Scope` / `不要碰` 文件一律不动。
7. `db/schema.sql` 与 service 里的 `Table` 定义是同一 schema 的两个产物，**改一处必同步另一处**。
8. 发现 spec 本身有错/缺口，在 PR 的 Report Back 里**显式提出**，不擅自扩张或绕过。

## 前端（MVP-1 第二批，spec 优先）

代码全在 `frontend/`，与 Python 后端隔离。栈：Vue3 + Vite + TypeScript + Element Plus（混合：EP 重组件主题化 + 自定义轻组件）。决策见 [ADR-003](decisions/ADR-003.md)，任务见 specs/TASK-200~204。

```
frontend/src/
  api/        axios 客户端（拆 ApiResponse 信封 + 注入 X-User-ID）+ 各域方法
  types/      镜像后端 schema 的 TS 类型
  constants/  status/risk/error_type 中文标签 + 色调（全站唯一来源）
  styles/     tokens.css（设计 token）/ element-overrides.css（EP 主题化）
  components/ AppShell + ui/ 基础组件        pages/ 四个页面        router/ composables/
```

```bash
cd frontend && npm install
npm run dev        # Vite dev（/api 代理到 127.0.0.1:8000）
npm run typecheck  # vue-tsc --noEmit
npm run build      # typecheck + vite build
npm run test       # vitest（TASK-200 api 客户端单测）
```

前端红线：
1. **不碰 `src/`（后端）与后端契约**；跨域只用 Vite proxy，不加 CORS。
2. **只用 TASK-200 允许的依赖**（vue/vue-router/element-plus/icons/axios + vite/ts/vue-tsc/vitest）；不引 Pinia/Tailwind/图表库。
3. **每个请求带 `X-User-ID: demo_user`**（api 客户端统一注入）。
4. **枚举文案统一走 `constants/`**，页面不硬编码中文；金额用等宽 + tabular-nums。
5. **遵循设计 token 与 `overall-frontend-design-style.md`**，避免冷灰企业 SaaS 与 AI 套路视觉。
6. **冻结契约内自洽**：缺字段（如复核页双边金额）按 spec 降级，**不虚构数据**。

## 提交规范

- Conventional Commits：`feat: / fix: / docs: / chore: / test: / refactor:`，描述可中文。
- commit body 关联任务：`Refs: TASK-XXX`。
- 一个 PR 对应一个 TASK；PR 描述用 spec 末尾的 Report Back 模板，如实暴露与 spec 的偏差。
