# 银企智能对账 Agent

基于多智能体的多账源智能对账与审计辅助系统。项目面向银行流水、企业账簿、清算流水等多源数据，提供上传解析、规则对账、RAG 证据召回、AI 审计建议、人工复核和指标看板能力。

> 数据合规：本仓库只应使用模拟或脱敏数据，禁止提交真实客户数据、真实银行流水或银行内部文档。

## 当前阶段

当前代码处于 **V1-3 开发版**，重点是：

- by-taskId SSE 看板实时结果推送
- 量化指标仪表盘
- 银企对账与银行清算对账双场景
- RAG 证据、Fallback、Hook、Memory、Checkpoint 等 Agent 链路演进

这不是稳定部署版。2026-06-17 的本地 smoke 显示：基础页面和多数 API 可以访问，但看板实时链路仍有阻断问题，见“当前 smoke 状态”和“已知问题”。

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
- OpenAI-compatible LLM provider abstraction，默认 Fake provider
- LangGraph / checkpoint sqlite
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
scripts/          数据生成、RAG 构建、DB reset 等脚本
tests/            后端 pytest
decisions/        ADR
```

## 本地启动

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

Vite 会把 `/api` 代理到 `127.0.0.1:8000`。前端 API 客户端会统一带 `X-User-ID: demo_user`。

## 演示数据

常用样例：

- 银企对账：`mock_data/mvp1_bank.xlsx` + `mock_data/mvp1_clear.xlsx`
- 银行清算对账：`mock_data/mvp2a3_core.xlsx` + `mock_data/mvp2a3_clearing.xlsx`

银企样例的预期概要：

- 银行端 7 行，企业端 6 行
- 自动平账 2 行
- 异常 6 行，进入人工复核

## 当前 smoke 状态

最近一次本地 smoke 时间：2026-06-17。

已确认可返回 `200`：

- 前端首页
- 后端 Swagger
- `GET /api/v1/metrics/dashboard`
- `POST /api/v1/reconcile/upload`
- `GET /api/v1/reconcile/{task_id}/status`
- `GET /api/v1/reconcile/{task_id}/exceptions`
- `GET /api/v1/ledger`
- `GET /api/v1/review/pending`

当前阻断点：

- `POST /api/v1/reconcile/{task_id}/start-live` 返回 `200`
- 紧接着 `GET /api/v1/reconcile/{task_id}/events` 返回 `404 live event stream not found`

初步定位：`start_live()` 注册 emitter 后，后台任务很快发出 `task_progress` 和 `task_done`，随后立刻 `unregister(task_id)`。真实浏览器顺序是 start-live 返回后再发起 events 订阅，此时 emitter 可能已经被清理，因此看板实时链路失败。

## 已知问题

- 看板实时链路：`start-live -> events` 存在 404，当前不应宣称看板 SSE 链路已稳定。
- 旁路日志：本地运行时出现过 `rag_log` / `agent_log` 的 `OperationalError`，主流程可返回，但日志或证据链落库需要继续排查。
- dev reload 噪音：`uvicorn --reload` 运行时会频繁出现 `changes detected`，可能与运行时文件写入被 watcher 捕获有关。
- Docker Compose：暂不建议作为主入口。建议先修复核心 smoke，再补 Compose 编排和容器内冒烟测试。

## 常用命令

后端：

```bash
uv run pytest
uv run pytest tests/test_reconciliation_start_live.py tests/test_reconciliation_live_events_endpoint.py -q
uv run ruff check .
uv run python -m scripts.generate_mock_excel
uv run python -m scripts.reset_db --yes
```

真实 embedding 测试默认不跑，CI 默认使用 hash 后端。需要手工验证本地模型路径时：

```bash
uv sync --extra dev --extra embedding
export HF_HOME=/path/to/hf-cache
uv run pytest -m embedding_real -v
```

`embedding_real` 测试只读取本地 Hugging Face / sentence-transformers 缓存；模型或依赖不可用时会 skip，不会在测试中下载模型。首次下载请在测试外完成，后续复用同一个 `HF_HOME`。

前端：

```bash
cd frontend
npm run test
npm run build
npm run typecheck
```

## 手工 smoke 示例

```bash
BASE=http://127.0.0.1:8000/api/v1
HEADER='X-User-ID: demo_user'

curl -X POST "$BASE/reconcile/upload" \
  -H "$HEADER" \
  -F bank_file=@mock_data/mvp1_bank.xlsx \
  -F clear_file=@mock_data/mvp1_clear.xlsx \
  -F scenario_type=BANK_ENTERPRISE

curl "$BASE/reconcile/<task_id>/status" -H "$HEADER"
curl "$BASE/reconcile/<task_id>/exceptions" -H "$HEADER"
curl -X POST "$BASE/reconcile/<task_id>/start-live" -H "$HEADER"
curl "$BASE/reconcile/<task_id>/events" -H "$HEADER"
curl "$BASE/ledger?page=1&page_size=20" -H "$HEADER"
curl "$BASE/review/pending?page=1&page_size=10" -H "$HEADER"
curl "$BASE/metrics/dashboard" -H "$HEADER"
```

## 开发约束

- 金额计算使用 `Decimal`，不要交给 LLM 或 float。
- RAG 无命中必须转人工，不得臆造 evidence。
- 所有业务查询显式按 `user_id` 过滤。
- 前端请求统一带 `X-User-ID: demo_user`。
- `db/schema.sql` 与 service 内 `Table` 定义需要保持同步。
- 不要把真实 `.env`、真实数据、运行时数据库文件提交到仓库。

## Docker Compose 状态

当前还未把 Docker Compose 作为推荐运行方式。建议顺序：

1. 修复 `start-live -> events` 404。
2. 排查 `rag_log` / `agent_log` `OperationalError`。
3. 本地跑通 smoke 和测试。
4. 再添加后端、前端、MySQL 的 Compose 编排。
5. 在 Compose 环境里重跑 smoke。

## 协作说明

架构决策记录在 `decisions/`。开发协作约定见 `AGENTS.md`。当前文档描述的是开发态真实状态；修复已知问题后，需要同步更新 README 的 smoke 状态和 Docker Compose 章节。
