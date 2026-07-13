# 银企智能对账 Agent

基于多智能体的多账源智能对账与审计辅助系统。项目面向银行流水、企业账簿、清算流水等多源数据，提供上传解析、规则对账、RAG 证据召回、AI 审计建议、人工复核和指标看板能力。

> 数据合规：本仓库只应使用模拟或脱敏数据，禁止提交真实客户数据、真实银行流水或银行内部文档。

## 当前阶段

当前代码处于 **Stage 27 可复现交付** 开发版，JWT 鉴权、ARQ/Redis 异步队列、五服务 Docker Compose、外部黑盒 smoke 和 GitHub CI 均已落地。默认使用 Fake LLM provider + hash embedding，不调用 DeepSeek、不下载真实模型。

## 能力概览

- 上传两份 Excel，生成对账任务。
- 清洗、校验并按规则识别自动平账和异常流水。
- 支持银企对账和银行清算对账场景。
- 异常进入 AI 审计链路，输出审计意见、风险等级、Fallback 路径和 RAG 证据。
- 差错台账支持按任务、差错类型、风险、处理状态查询。
- 人工复核支持确认平账、强制挂账，并写回复核结果。
- 指标仪表盘聚合线上任务、异常、复核和离线评测快照。
- 前端提供上传页、任务看板、工作台、差错台账、人工复核和指标页。

## 技术栈

后端：

- Python >= 3.11
- uv
- FastAPI + Pydantic v2
- SQLAlchemy Core
- MySQL (`mysql+pymysql`)
- SQLite 测试库
- ChromaDB
- Redis（LLM 缓存、限流、幂等去重）
- ARQ 异步任务队列
- JWT Bearer 鉴权（`POST /api/v1/auth/login`）
- OpenAI-compatible LLM provider abstraction，默认 Fake provider
- LangGraph / checkpoint sqlite（HumanReview 子图）
- ruff + pytest

前端：

- Vue 3
- Vite
- TypeScript
- Vue Router
- Element Plus
- ECharts
- Vitest
- `@vue/test-utils` + `happy-dom`

## 目录结构

```text
src/bank_reconciliation_agent/
  api/            FastAPI 路由层
  core/           配置
  db/             engine 工厂和 MySQL DDL
  schemas/        Pydantic schema
  services/       业务服务和持久化
  agents/         Agent 实现
  rag/            RAG 检索
frontend/
  src/api/        前端 API 客户端
  src/pages/      页面
  src/components/ 组件
  src/router/     路由
mock_data/        本地演示 Excel
rules/            YAML 规则和规则资料
scripts/          数据生成、RAG 构建、smoke demo 等脚本
tests/            后端 pytest
decisions/        ADR
```

## 一键启动（五服务 Compose，零外部凭证）

本 Stage 提供一条命令启动整个演示拓扑（无需预装 MySQL/Redis/uv/Node）：

```bash
cp .env.example .env
docker compose up --build -d --wait
```

五服务拓扑：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| `mysql` | Compose 内 `3306` | MySQL 8.4，database `AI_agent` |
| `redis` | Compose 内 `6379` | Redis 7.4，DB 0 |
| `backend` | host `8000` | Uvicorn，JWT auth，Fake LLM + hash embedding |
| `worker` | 无 host 端口 | ARQ worker，消费 Redis 异步对账任务 |
| `frontend` | host `4173` | Vite preview，`/api` proxy 到 backend |

backend 与 worker 复用同一 Python 镜像并共享 `uploads_data` 卷；MySQL/Redis 使用具名数据卷，不暴露 host 端口。默认不需要 DeepSeek key 或真实 embedding 下载。

健康检查：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"Bank Reconciliation Agent","db":"ok"}
```

前端：`http://127.0.0.1:4173/`

清理：

```bash
docker compose down --volumes --remove-orphans
```

> demo 密码和 JWT secret 仅为本地 non-production 默认值，已通过 `${NAME:-demo-value}` 提供；真实环境请用环境变量覆盖。

## 本地开发启动

### 1. 后端

```bash
uv sync --extra dev

cp .env.example .env
# 编辑 .env 中的 MYSQL_DSN，不要提交真实口令

# 首次或本地库 schema 漂移时可重建 dev DB
uv run python -m scripts.reset_db --yes

uv run uvicorn bank_reconciliation_agent.main:app --reload
```

后端默认地址：

- API: `http://127.0.0.1:8000/api/v1`
- Swagger: `http://127.0.0.1:8000/docs`

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：`http://127.0.0.1:5173/`

Vite 会把 `/api` 代理到 `127.0.0.1:8000`。当前 API 鉴权使用 JWT Bearer Token（`POST /api/v1/auth/login`），前端通过 `Authorization: Bearer <token>` 访问业务 API。

## 演示数据

常用样例：

- 银企对账：`mock_data/mvp1_bank.xlsx` + `mock_data/mvp1_clear.xlsx`
- 银行清算对账：`mock_data/mvp2a3_core.xlsx` + `mock_data/mvp2a3_clearing.xlsx`

银企样例的预期概要：

- 银行端 7 行，企业端 6 行
- 自动平账 2 行
- 异常 6 行，进入人工复核

## 外部黑盒 Smoke

容器外执行 `scripts/smoke_demo.py` 可验证 JWT、ARQ 异步队列、SSE 实时事件、人工复核和审计报告。脚本连续运行两次以证明 `force=true` 重走 worker，并输出 v1.0 JSON summary。

```bash
uv sync --extra dev
uv run python -m scripts.smoke_demo --summary-json artifacts/smoke-run-1.json
uv run python -m scripts.smoke_demo --summary-json artifacts/smoke-run-2.json
```

两条路径：
- **ARQ path**：`BANK_ENTERPRISE`，`force=true` → Redis/ARQ worker → 异常 → 人工复核 → 报告
- **SSE path**：`BANK_CLEARING`，`start-live → events → TASK_DONE` → 状态 → 报告
- **Replay API**：`GET /api/v1/traces/{task_id}/flows/{flow_id}?trace_id=` 按 JWT user→task→flow→trace 顺序验证 ownership，默认返回最新执行，支持历史 run 选择。前端页面 `/traces/:taskId/:flowId` 从差错台账详情进入。

summary JSON 输出包含 `schema_version: "1.0"`、9 个稳定步骤名、`boundary: {llm_provider: "fake", embedding_backend: "hash"}` 和两条 path 的 task IDs。成功返回 0，失败仍尽力写 summary 并返回非零。

## 手动 JWT 调用示例

```bash
BASE=http://127.0.0.1:8000/api/v1

# 获取 token
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_user","password":"demo12345"}' | jq -r '.data.access_token')

# 上传文件
curl -X POST "$BASE/reconcile/upload-async" \
  -H "Authorization: Bearer $TOKEN" \
  -F bank_file=@mock_data/mvp1_bank.xlsx \
  -F clear_file=@mock_data/mvp1_clear.xlsx \
  -F scenario_type=BANK_ENTERPRISE -F force=true

# 查询状态
curl "$BASE/reconcile/<task_id>/status" -H "Authorization: Bearer $TOKEN"

# 异常列表
curl "$BASE/reconcile/<task_id>/exceptions" -H "Authorization: Bearer $TOKEN"

# 待复核
curl "$BASE/review/pending?task_id=<task_id>" -H "Authorization: Bearer $TOKEN"

# 审批
curl -X POST "$BASE/review/<queue_id>/approve" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"APPROVED_MATCH","handler_username":"demo_user","remark":"人工确认"}'

# 查看报告
curl "$BASE/reconcile/<task_id>/report" -H "Authorization: Bearer $TOKEN"
```

## 常用命令

后端：

```bash
uv run pytest
uv run ruff check .
uv run python -m scripts.generate_mock_excel
uv run python -m scripts.reset_db --yes
```

前端：

```bash
cd frontend
npm run test
npm run build
npm run typecheck
```

## Hosted CI

GitHub Actions workflow（`.github/workflows/ci.yml`）在 PR 上运行四个 check：

- `backend-quality`：`uv sync --frozen` → `uv run pytest` + `uv run ruff check .`
- `frontend-quality`：`npm ci` → `npm run test` + `npm run typecheck` + `npm run build`
- `deterministic-eval`：fresh 生成 dense baseline、hybrid_rerank comparison、Agent schema conformance，CI layer gate 阻断
- `delivery-smoke`：`docker compose up --build -d --wait` → smoke 两次 → always 清理

全部使用 `LLM_PROVIDER=fake` + `EMBEDDING_BACKEND=hash`，不调用 DeepSeek、不读仓库 secrets。真实 provider/embedding/cost 缺失表现为 `environment_gap`，不阻断默认 PR。

## 开发约束

- 金额计算使用 `Decimal`，不要交给 LLM 或 float。
- RAG 无命中必须转人工，不得臆造 evidence。
- 所有业务查询显式按 `user_id` 过滤。
- 当前鉴权为 JWT Bearer Token；`X-User-ID` 仅为历史设计，不再作为当前 API 调用契约。
- `db/schema.sql` 与 service 内 `Table` 定义需要保持同步。`CREATE TABLE IF NOT EXISTS t_trace_span` 已在 `schema.sql` 中提供，fresh database 可通过执行该 DDL 创建表。`_ensure_initialized()` 只延续 local/test 行为，不得依赖它隐藏生产 schema 变更；existing MySQL/Compose 数据卷必须显式重放更新后的 `schema.sql`。
- 不要把真实 `.env`、真实数据、运行时数据库文件提交到仓库。

## 已知限制

- SSE 实时事件是进程内 emitter（单 backend 实例，`AgentStreamEvent.schema_version="1.2"`），不具备断线回放或水平扩展能力。浏览器断开后可通过持久化 Replay API 恢复完整 Timeline，但 SSE 自身不支持 `Last-Event-ID` 或跨实例广播。
- Execution Trace 按 flow 完成后批量写入 `t_trace_span`（append-only），flow 完成前发生进程崩溃则当前 Trace 不可恢复（crash gap）。当前无 retention/delete 机制，进入生产前需补充数据治理决策。
- `vite preview` 仅适合本地演示；生产部署需另立 ADR 决定静态资源服务器和反向代理。
- 镜像使用版本 tag (`mysql:8.4`, `redis:7.4-alpine`) 而非 digest，不能宣称字节级跨架构复现。
- 默认路径为 Fake/hash，不调用真实模型；真实 DeepSeek 和 embedding 仅允许显式 opt-in。

## 协作说明

架构决策记录在 `decisions/`。开发协作约定见 `AGENTS.md`。当前文档描述的是开发态真实状态。
