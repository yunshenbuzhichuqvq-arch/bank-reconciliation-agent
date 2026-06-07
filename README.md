# 银企智能对账 Agent（Bank Reconciliation Agent）

基于多智能体的多账源智能对账与审计辅助系统。

当前阶段 **MVP-1：本地可演示的银企对账产品闭环**——在 MVP-0 后端主链路之上补齐本地页面、人工复核和声明式规则，让项目从「API 能跑」变成「本地可以完整演示的业务产品」。本阶段不接入真实 LLM，Agent 仍为**确定性规则 + RAG 证据 + 人工复核**。

> **数据合规**：本仓库只使用模拟或脱敏数据，**严禁**包含真实客户数据、真实银行流水或银行内部文档。

## MVP-1 闭环能力

1. 上传银行流水 + 企业账簿两张 Excel。
2. 确定性 Python 清洗、校验行数据（金额一律 `Decimal`）。
3. **YAML 声明式规则引擎**对账（替换 MVP-0 的硬编码 if-else）。
4. **ExceptionRouter** 路由 5 类银企对账异常分支（见下表）。
5. **AuditAgent**（确定性，无 LLM）结合 **RAG 证据**给出审计意见，异常统一转人工。
6. 前端四页：账单上传页 / 任务看板 / 差错台账页 / 人工复核页。
7. 人工复核结果写回差错台账 + 操作记录入库。
8. Agent 执行日志入库 + 本地 JSON trace，用于回放单笔异常的规则命中、RAG 命中与 Agent 输出。
9. 多租户：所有业务查询显式按 `user_id` 过滤（MVP-1 仍用固定演示身份 `X-User-ID: demo_user`）。

ExceptionRouter 五分支（详见 [decisions/ADR-001.md](decisions/ADR-001.md)）：

| 分支 ID | error_type | 语义 |
|--------|-----------|------|
| BE-R002 | `AMOUNT_MISMATCH` | 流水可匹配但金额不一致 |
| BE-R004 | `NARRATIVE_NAME_MISMATCH` | 金额一致但摘要/客户名不一致（含模糊冲正关键词的确定性识别） |
| BE-R005 | `BANK_UNARRIVED` | 企业账簿有、银行无 |
| BE-R006 | `BOOK_UNRECORDED` | 银行有、企业账簿无 |
| BE-R008 | `DUPLICATE_BOOKING` | 同主体 + 同金额 + 同对手，疑似一端多记 |

（另有 BE-R001 `EXACT_MATCH` → 自动平账，非异常分支。）

## 技术栈

- **后端**：Python ≥ 3.11，包管理 **uv**；FastAPI + Pydantic v2；SQLAlchemy **Core**（非 ORM）；生产库 MySQL（`mysql+pymysql`），测试库 SQLite；金额一律 `Decimal`；RAG 用 ChromaDB；Lint 用 ruff。
- **前端**：Vue 3 + Vite + TypeScript + Element Plus（重组件主题化 + 自定义轻组件）。详见 [decisions/ADR-003.md](decisions/ADR-003.md)。

## 目录结构

```
src/bank_reconciliation_agent/   后端
  api/        FastAPI 路由层（dependencies.py 鉴权，v1/router.py 挂载子路由）
  core/       config.py（pydantic-settings，读 .env）
  db/         session.py（engine 工厂）+ schema.sql（MySQL DDL，手工维护）
  schemas/    Pydantic 模型（common.py 有 ApiResponse[T]/Page[T] 信封）
  services/   业务 + 持久化（每个 service 自带 SQLAlchemy Table）
  agents/     audit_agent.py（MVP-1 确定性，无 LLM）
  rag/        retriever.py（ChromaDB 检索）
frontend/src/                    前端
  api/ types/ constants/ styles/ components/ pages/ router/ composables/
rules/        YAML 规则库 + RAG 规则文档
mock_data/    模拟 Excel 样本
scripts/      generate_mock_excel / build_rule_chunks / reset_db
tests/        pytest（测试库指向 SQLite）
decisions/    架构决策记录（ADR）
AGENTS.md     Codex 常驻上下文（开发协作约定）
```

## 本地运行

### 1. 后端

```bash
# 安装依赖（含 dev）
uv sync --extra dev

# 配置数据库 DSN（不要提交真实口令）
cp .env.example .env
# 编辑 .env：MYSQL_DSN=mysql+pymysql://root:<password>@127.0.0.1:3306/AI_agent

# 建表：首次按 schema.sql 建库
mysql -uroot -p AI_agent < src/bank_reconciliation_agent/db/schema.sql
# 或：本地 dev 库 schema 漂移时，按 service Table 定义一键重建
uv run python -m scripts.reset_db --yes

# 启动 API（默认 http://127.0.0.1:8000）
uv run uvicorn bank_reconciliation_agent.main:app --reload
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev     # Vite 开发服务器，默认 http://localhost:5173，/api 代理到 127.0.0.1:8000
```

浏览器打开 `http://localhost:5173` 即可走完整 UI 闭环。

## 端到端 Demo（银企对账）

演示数据固定在 `mock_data/mvp1_bank.xlsx` 与 `mock_data/mvp1_clear.xlsx`（可用 `uv run python -m scripts.generate_mock_excel` 重新生成）。

该样本上传后的**权威预期结果**：

- `total_bank_rows`: 7，`total_clear_rows`: 6
- `auto_fixed_rows`: 2（F2001/F2002 精确匹配自动平账）
- `pending_ai_rows`: 0，`pending_human_rows`: 6（异常统一转人工）
- 6 笔异常：F2003 金额不一致、F2004 摘要/客户名不一致、F2005 银行未到账、F2006 企业未入账、F2007/F2008 疑似重复记账

### 方式 A：浏览器走完整闭环

1. **账单上传页**：上传两张 `mvp1_*.xlsx`，得到任务。
2. **任务看板**：查看统计指标，点「启动 AI 审计」。
3. **人工复核页**：对 6 笔异常逐笔「确认平账」或「强制挂账」。
4. **差错台账页**：按任务/差错类型/处理状态/风险等级筛选，查看单笔 AI 审计意见与 RAG 来源。

### 方式 B：curl（所有请求需带 `X-User-ID: demo_user`）

```bash
# 1. 上传，拿到 task_id
curl -X POST http://127.0.0.1:8000/api/v1/reconcile/upload \
  -H 'X-User-ID: demo_user' \
  -F bank_file=@mock_data/mvp1_bank.xlsx \
  -F clear_file=@mock_data/mvp1_clear.xlsx

# 2. 启动 AI 审计
curl -X POST http://127.0.0.1:8000/api/v1/reconcile/<task_id>/start \
  -H 'X-User-ID: demo_user'

# 3. 查询任务状态与统计
curl http://127.0.0.1:8000/api/v1/reconcile/<task_id>/status \
  -H 'X-User-ID: demo_user'

# 4. 查询异常列表（6 笔，含 AI 审计意见与 RAG 证据）
curl http://127.0.0.1:8000/api/v1/reconcile/<task_id>/exceptions \
  -H 'X-User-ID: demo_user'

# 5. 人工复核：待复核列表 → 逐笔确认
curl http://127.0.0.1:8000/api/v1/review/pending \
  -H 'X-User-ID: demo_user'
curl -X POST http://127.0.0.1:8000/api/v1/review/<queue_id>/approve \
  -H 'X-User-ID: demo_user' -H 'Content-Type: application/json' -d '{}'

# 6. 差错台账
curl 'http://127.0.0.1:8000/api/v1/ledger?task_id=<task_id>' \
  -H 'X-User-ID: demo_user'
```

## 自动化校验

```bash
# 后端
uv run pytest
uv run ruff check .

# 前端
cd frontend
npm run test       # vitest
npm run build      # typecheck + vite build
```

## 开发协作

本项目采用双 agent 协作：Planner（规划/审查/架构决策）+ Codex（按 spec 实现）。常驻约定见 [AGENTS.md](AGENTS.md)，架构决策见 [decisions/](decisions/)。
