# 《银企对账 Agent 系统》产品 PRD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目名称 | 银企对账 Agent 系统(多账源智能对账与审计辅助) |
| 项目类型 | 个人开源项目(求职作品) |
| 业务场景 | 银企对账:企业账簿 / ERP 明细 × 银行流水(单场景) |
| 核心抽象 | 一套通用双账源对账引擎(Source A 主账源 / Source B 对账账源)+ Scenario Profile,当前只落地 `BANK_ENTERPRISE` |
| 技术栈 | FastAPI、Vue 3、MySQL 8.0、LangGraph、RAG(ChromaDB)、Redis、Docker |
| LLM | DeepSeek V4 Pro(`deepseek-v4-pro`,目前为 preview;OpenAI 兼容接口;默认可切 Fake provider) |
| 阶段规划 | 阶段一 最小闭环 → 阶段二 Agent 工程做深 → 阶段三 作品化 |
| 数据边界 | 仅使用模拟数据和脱敏数据,不使用真实客户数据或银行内部资料 |

## 2. 产品概述

本系统是一套面向**银企对账**的 AI 应用:企业账簿 / ERP 明细与银行流水核对,帮助企业财务人员在大批量流水核对中降低耗时、快速定位差异、减轻人工复核压力,处理双账源流水差异、单边缺失、跨期入账、手续费 / 税费差异、重复记账、人工复核和审计报告生成的流程。

系统底层是**一套通用 Reconciliation Engine + Scenario Profile**:引擎只认 Source A(主账源)/ Source B(对账账源),由 `scenario_type` 选择字段映射、规则库、RAG 知识库、Prompt 和报告模板。当前只落地银企对账一个场景,引擎可扩展到其他对账场景(见 §18)。

系统采用"确定性代码 + 规则引擎 + Multi-Agent + RAG + 输出校验管线 + Human-in-the-Loop"的组合架构。确定性代码负责文件解析、字段映射、金额计算和数据库事务;规则引擎基于 YAML 声明式规则将异常流水分发到处理分支;Multi-Agent(DeepSeek V4 Pro)负责模糊摘要结构化、审计判断和报告生成;RAG 采用混合检索 + Reranker + Query Rewrite 全链路提供规则依据和审计溯源;输出校验管线作为护栏负责 Schema 校验、硬约束校验和事务落库;Human-in-the-Loop 在金融风险场景保留人工确认。

## 3. 产品范围与阶段规划

围绕同一条银企对账主链路逐层加厚,每阶段都有可验收产物。当前进度标注于 2026-06。

### 3.1 阶段一:最小闭环  ✅ 基本完成

目标:完成从模拟 Excel 到差错台账查询的主链路 + 本地可演示页面,证明"规则对账 + Agent 审计 + RAG 依据 + MySQL 台账"可以跑通。

核心链路:

```text
准备模拟 Excel 数据
  → 上传 source_a_file(企业账簿)+ source_b_file(银行流水),scenario_type = BANK_ENTERPRISE
  → Pandas 读取、字段校验、数据清洗、字段映射
  → 三阶段匹配 + 基础规则对账
  → 识别异常交易(AMOUNT_MISMATCH + 单边缺失:BANK_UNARRIVED / BOOK_UNRECORDED)
  → 异常进入 Agent 审计流程
  → RAG 检索规则依据(ChromaDB Top-K + 相似度阈值)
  → AuditAgent 输出结构化审计建议(含 evidence)
  → 结果写入 MySQL 差错台账
  → API 查询任务状态和差错明细
```

包含:

- 模拟企业账簿和银行流水 Excel(覆盖正常平账、金额差错、单边缺失)。
- FastAPI 文件上传接口;Pandas 读取、字段校验和数据清洗。
- YAML 声明式规则引擎 + ExceptionRouter(核心分支)。
- **AuditAgent 真实 LLM 调用**:结构化 JSON 输出(decision / risk_level / reason / confidence / evidence)+ Schema 校验 + 有界重试 + 兜底转人工。
- Markdown 规则文档 + ChromaDB Top-K 检索。
- MySQL 任务表、流水表、队列表、差错台账表、RAG 检索记录表。
- 任务状态查询 API、差错明细查询 API。
- Vue:账单上传页、任务看板、差错台账页、人工复核页;人工复核事务更新台账。
- 单笔异常的本地 trace。

产物:API + 数据库记录 + Agent/RAG JSON + 一条完整 trace + 本地页面。

### 3.2 阶段二:Agent 工程做深  🔶 大部分完成

目标:把"Agent 能判断"做成"Agent 可约束、可追踪、可评测"。

新增:

- **ExtractionAgent 接入**:从正则匹配升级为 DeepSeek V4 Pro 调用,从模糊摘要 / 户名结构化提取线索。
- **AuditAgent LLM 化**:从 if-else 升级为 DeepSeek V4 Pro 调用,基于 RAG 证据输出结构化审计决策。三个 LLM 调用点均通过 OpenAI 兼容接口(`openai` SDK + DeepSeek base_url)。
- **LangGraph 条件路由**:PreCheckNode → ExceptionRouter → 条件分支 → AuditAgent → END;按 `exception_branch` 决定是否调用 ExtractionAgent、TraceAgent(可选)或 RAG 子流程。串行执行,是否并行依据真实 LLM 延迟数据再定。
- **增强 RAG**:Dense + BM25 双路召回 + RRF 融合 + Cross-Encoder Reranker(默认轻量,可换 BGE)+ Query Rewrite(DeepSeek 调用)。Reranker 与 Query Rewrite 可开关,关闭后主链路仍可运行。
- **3 级 Fallback**:L1 标准 → L2 历史人工确认案例 few-shot(来自差错台账)→ L3 可选追溯 / 换角度。RAG 无命中直接转人工。
- **输出校验管线**:Schema 校验(+有界重试)→ 硬约束 C1–C6 → 决策 / Fallback 路由 → 事务落库。
- **structlog 结构化日志**:所有 LLM 调用点输出 JSON 日志(`trace_id`、`agent_name`、`step`、`prompt_version`)。
- **Prompt 版本管理**:Prompt 以独立文件存放并纳入版本控制;`t_agent_execution_log.prompt_version` 可追溯;附 Prompt 版本对比脚本。
- **工具调用权限边界**:L0 只读 / L1 结构化输出 / L2 禁止直写库(见 §15)。
- **RAG 评测集(真实 Recall@5/MRR)+ Agent 决策质量评估**(统计方法,不对 LLM 非确定性做严格一致性断言)。
- 数据库新增字段:`prompt_version`、`fallback_level`、`llm_tokens`、`rag_scores_json` 等。

产物:真实 LLM Agent 输出 + 增强 RAG trace + Fallback 日志 + 评测报告 + Prompt 版本对比。

### 3.3 阶段三:作品化  🚧 进行中

目标:让作品"能跑、能看、能解释效果"。

新增:

- **Vue 工作台 + SSE**:实时展示 Agent 执行步骤、异常分支、RAG 检索详情(Dense/BM25/Reranker 分数)、决策与置信度、Fallback 层级。
- **ARQ 后台任务队列**:对账任务异步执行,上传接口即时返回 task_id。
- **Redis**:LLM 结果缓存、API 调用限流、幂等去重。
- **量化指标小面板**:核心 Agent 指标可视化。
- **Docker Compose 一键启动**(Docker 直接暴露端口,无 Nginx)。
- Markdown 审计报告。
- (可选)JWT 登录;(可选加分项)云服务器部署。

**当前状态**:工作台与指标盘可访问;`start-live → events` 实时链路返回 404,**主链路最后一步未通**;ARQ / Redis / JWT / Compose 未做。

> 进度口径:✅ 基本完成 / 🔶 大部分完成 / 🚧 进行中。未完成项不写成已达成结果。

## 4. 页面与交互设计

阶段一起建前端;鉴权用 `X-User-ID: demo_user` 模拟,阶段三可选 JWT。

### 4.1 账单上传页(阶段一)

上传主账源 Source A(企业账簿 / ERP 明细)与对账账源 Source B(银行流水)Excel。展示字段校验结果和上传后统计(Source A / Source B 总笔数、自动平账数、待 AI 审计数)。文件格式错误或必填字段缺失时拒绝上传。上传成功后生成 task_id 并跳转任务看板。

### 4.2 任务看板(阶段一)

展示对账任务列表、任务状态、自动平账率、待复核数、挂账数、异常类型分布。提供"启动 AI 审计"按钮。阶段一 / 二手动刷新;阶段三改为 SSE 实时更新。

### 4.3 Agent 流式工作台(阶段三)

通过 SSE 实时展示 Agent 执行事件:当前处理流水、异常分支路由、RAG 检索详情(Dense/BM25/Reranker 分数)、AuditAgent 决策与置信度、Fallback 层级、最终决策。阶段二使用轮询或后端日志返回。

### 4.4 人工复核页(阶段一)

左侧主账源 Source A 流水 / 右侧对账账源 Source B 流水 / 中间 AI 推荐理由与 RAG 来源。支持确认平账、强制挂账、人工备注。每次操作记录操作人、时间、动作和备注,通过事务更新台账。`PENDING_HUMAN` 超过 24 小时自动标记 `OVERDUE`,任务看板高亮提示。

### 4.5 差错台账页(阶段一)

分页查询,按任务、差错类型、处理状态、风险等级筛选。单笔详情含 AI 审计意见、RAG 来源、人工处理记录,以及 Agent 决策链路回放(本地 trace)。

### 4.6 报表审计页(阶段三)

展示总笔数 / 总金额 / 自动平账率 / 人工复核数 / 挂账金额、异常类型分布、Agent 决策分布、ReportAgent 生成的 Markdown 报告。

### 4.7 量化指标面板(阶段三)

展示自动平账率、Agent 审计采纳率、RAG Recall@5/MRR、Schema 符合率、人工复核触发率、Fallback 触发率、LLM Token 消耗与成本趋势。

## 5. 后端 API 设计

统一返回 `{code, message, data}`。所有 API 携带 `X-User-ID`(阶段一 / 二为固定演示值,阶段三可选 JWT)。

### 5.1 登录(可选,阶段三)

`POST /api/v1/auth/login`

```json
// 请求
{ "username": "demo", "password": "demo123" }
// 响应
{ "code": 200, "message": "login success",
  "data": { "access_token": "jwt-token", "token_type": "bearer", "user_id": "demo_user" } }
```

### 5.2 上传对账单(阶段一)

`POST /api/v1/reconcile/upload` (`multipart/form-data`,Header `X-User-ID`)

字段:`scenario_type`(缺省 `BANK_ENTERPRISE`)、`source_a_file`(企业账簿 / ERP 明细)、`source_b_file`(银行流水)。

```json
// 响应(阶段三改为异步,即时返回 task_id)
{
  "code": 200, "message": "upload success",
  "data": {
    "task_id": "TASK_20260526_001",
    "scenario_type": "BANK_ENTERPRISE",
    "total_source_a_rows": 5000, "total_source_b_rows": 4996,
    "auto_fixed_rows": 4860, "pending_ai_rows": 120, "pending_human_rows": 16,
    "status": "UPLOADED"
  }
}
```

### 5.3 启动对账工作流(阶段一)

`POST /api/v1/reconcile/{task_id}/start`

```json
{ "code": 200, "message": "workflow started",
  "data": { "task_id": "TASK_20260526_001", "status": "AI_RUNNING" } }
```

### 5.4 查询任务状态(阶段一)

`GET /api/v1/reconcile/{task_id}/status`

```json
{
  "code": 200, "message": "success",
  "data": {
    "task_id": "TASK_20260526_001", "scenario_type": "BANK_ENTERPRISE",
    "status": "PENDING_HUMAN",
    "auto_fixed_rows": 4860, "ai_processed_rows": 104, "ai_retrying_rows": 2,
    "fallback_l2_rows": 8, "fallback_l3_rows": 3,
    "pending_human_rows": 16, "unresolved_rows": 3
  }
}
```

### 5.5 Agent 执行事件流(阶段三,SSE)

`GET /api/v1/reconcile/{task_id}/events`

```json
{
  "event_type": "RAG_RETRIEVED", "queue_id": 1024, "agent": "AuditAgent",
  "message": "命中手续费 / 税费差异处理规则(Hybrid Search + Reranker)",
  "payload": {
    "query_rewritten": "手续费 税费 金额差异 处理规则",
    "source": "rag_knowledge/bank_enterprise/fee_tax_diff.md#手续费差异",
    "dense_score": 0.78, "bm25_score": 0.81, "reranker_score": 0.87, "final_score": 0.87
  }
}
```

校验管线状态事件:

```json
{
  "event_type": "PIPELINE_STATUS", "queue_id": 1024,
  "payload": {
    "schema": "PASSED (attempt 1)",
    "constraint": "PASSED",
    "decision": "FALLBACK_L2",
    "fallback_level": 2
  }
}
```

### 5.6 查询待复核列表(阶段一)

`GET /api/v1/review/pending?task_id=&page=&page_size=`

```json
{
  "code": 200, "message": "success",
  "data": {
    "items": [
      {
        "queue_id": 1024, "error_type": "NARRATIVE_NAME_MISMATCH",
        "exception_branch": "BE-R004", "risk_level": "MEDIUM",
        "ai_suggestion": "APPROVED_MATCH", "ai_confidence": 0.72,
        "ai_reason": "金额与入账日期一致,但企业账簿摘要与银行流水客户名称不一致,疑似同一笔,建议人工确认",
        "rag_sources": [
          { "source": "rag_knowledge/bank_enterprise/basic_matching.md#摘要与户名不一致", "reranker_score": 0.86 }
        ],
        "similar_historical_cases": 3, "historical_approve_rate": "80%"
      }
    ],
    "total": 16
  }
}
```

### 5.7 人工审批(阶段一)

`POST /api/v1/review/{queue_id}/approve`

```json
// 请求
{ "action": "APPROVED_MATCH", "handler_username": "demo", "remark": "人工核对原交易后确认可平账" }
// 响应
{ "code": 200, "message": "review submitted",
  "data": { "queue_id": 1024, "current_status": "FIXED" } }
```

审批后:MySQL 事务更新台账状态与复核记录。人工确认结果会作为后续同类异常的 Fallback few-shot 案例。

### 5.8 查询差错台账(阶段一)

`GET /api/v1/ledger?scenario_type=&task_id=&error_type=&exception_branch=&handle_status=&risk_level=&start_date=&end_date=&page=&page_size=`

### 5.9 RAG 检索调试(阶段一)

`POST /api/v1/rag/search`

```json
// 请求
{ "scenario_type": "BANK_ENTERPRISE", "query": "差了两块钱是什么情况", "top_k": 5, "enable_rewrite": true, "enable_hybrid": true }
// 响应(阶段二,含混合检索细节)
{
  "code": 200, "message": "success",
  "data": {
    "original_query": "差了两块钱是什么情况",
    "rewritten_query": "手续费差异 金额不一致 税费 处理规则",
    "items": [
      {
        "source": "rag_knowledge/bank_enterprise/fee_tax_diff.md#手续费差异",
        "dense_score": 0.78, "bm25_score": 0.81, "rrf_rank": 1,
        "reranker_score": 0.87, "final_score": 0.87,
        "content": "金额差恰好等于标准手续费 / 税费时,按手续费差异处理。"
      }
    ],
    "search_meta": { "dense_candidates": 20, "sparse_candidates": 20, "after_fusion": 10, "after_rerank": 5, "above_threshold": 3 }
  }
}
```

### 5.10 生成审计报告(阶段三)

`POST /api/v1/reports/{task_id}/generate`

```json
{
  "code": 200, "message": "report generated",
  "data": {
    "task_id": "TASK_20260526_001", "scenario_type": "BANK_ENTERPRISE",
    "report_id": 18, "format": "markdown",
    "summary": {
      "total_source_a_rows": 5000, "total_source_b_rows": 4996,
      "auto_fixed_rows": 4860, "ai_processed_rows": 104, "pending_human_rows": 16,
      "unresolved_rows": 3, "auto_fix_rate": "97.2%", "ai_audit_accuracy": "87.5%"
    }
  }
}
```

> 已删除原 `GET /api/v1/memory/{user_id}/context` 记忆查询接口(随记忆引擎一并移除)。

## 6. 数据库设计

标准建表 + 合理索引,**不使用 HASH 分区 / 物化视图 / JSON 虚拟列索引**。所有业务表带 `scenario_type`(预留多场景,默认 `BANK_ENTERPRISE`);启用 JWT 时带 `user_id` 做行级过滤。

### 6.1 对账任务表 `t_reconciliation_task`(阶段一)

```sql
CREATE TABLE t_reconciliation_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  batch_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  task_name VARCHAR(128) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
  total_source_a_rows INT NOT NULL DEFAULT 0,
  total_source_b_rows INT NOT NULL DEFAULT 0,
  auto_fixed_rows INT NOT NULL DEFAULT 0,
  pending_ai_rows INT NOT NULL DEFAULT 0,
  ai_processed_rows INT NOT NULL DEFAULT 0,          -- 阶段二
  ai_retrying_rows INT NOT NULL DEFAULT 0,
  fallback_l2_rows INT NOT NULL DEFAULT 0,           -- 阶段二
  fallback_l3_rows INT NOT NULL DEFAULT 0,           -- 阶段二
  pending_human_rows INT NOT NULL DEFAULT 0,
  unresolved_rows INT NOT NULL DEFAULT 0,
  total_llm_tokens INT NOT NULL DEFAULT 0,           -- 阶段二
  total_llm_cost DECIMAL(10,4) NOT NULL DEFAULT 0.0000,  -- 阶段二
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_task (user_id, task_id),
  INDEX idx_user_batch (user_id, batch_id),
  INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.2 主账源流水表 `t_source_a_transaction`(阶段一)

主账源 Source A(企业账簿 / ERP 明细,`source_type = ENTERPRISE_BOOK`)。字段与 `mock_data/source_a_*.xlsx` 保持一致,保留标准化字段便于匹配、台账和 Agent 上下文复用。

```sql
CREATE TABLE t_source_a_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  source_side CHAR(1) NOT NULL DEFAULT 'A',
  source_type VARCHAR(32) NOT NULL DEFAULT 'ENTERPRISE_BOOK',
  flow_id VARCHAR(64),
  voucher_no VARCHAR(64),                -- 企业账簿凭证号
  accounting_period VARCHAR(16),         -- 会计期间(跨期入账判定)
  accounting_date DATE,
  value_date DATE,
  account_no_masked VARCHAR(64),
  customer_name_masked VARCHAR(128),
  counterparty_account_no_masked VARCHAR(64),
  counterparty_name_masked VARCHAR(128),
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  transaction_direction VARCHAR(16),
  amount DECIMAL(18,2) NOT NULL,
  debit_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  credit_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  fee_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  balance_after DECIMAL(18,2),
  trade_time DATETIME NOT NULL,
  summary VARCHAR(255),
  purpose VARCHAR(128),
  posting_status VARCHAR(32),
  remark VARCHAR(255),
  match_status VARCHAR(32) DEFAULT NULL,
  matched_source_b_id BIGINT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_flow (user_id, task_id, flow_id),
  INDEX idx_user_task_time (user_id, task_id, trade_time),
  INDEX idx_match_status (task_id, match_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.3 对账账源流水表 `t_source_b_transaction`(阶段一)

对账账源 Source B(银行流水,`source_type = BANK_STATEMENT`)。字段与 `mock_data/source_b_*.xlsx` 保持一致。

```sql
CREATE TABLE t_source_b_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  source_side CHAR(1) NOT NULL DEFAULT 'B',
  source_type VARCHAR(32) NOT NULL DEFAULT 'BANK_STATEMENT',
  flow_id VARCHAR(64),
  bank_serial_no VARCHAR(64),
  account_no_masked VARCHAR(64),
  customer_name_masked VARCHAR(128),
  counterparty_account_no_masked VARCHAR(64),
  counterparty_name_masked VARCHAR(128),
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  transaction_direction VARCHAR(16),
  amount DECIMAL(18,2) NOT NULL,
  fee_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  balance_after DECIMAL(18,2),
  trade_time DATETIME NOT NULL,
  value_date DATE,
  status VARCHAR(32),
  summary VARCHAR(255),
  voucher_no VARCHAR(64),
  reference_no VARCHAR(64),
  remark VARCHAR(255),
  match_status VARCHAR(32) DEFAULT NULL,
  matched_source_a_id BIGINT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_flow (user_id, task_id, flow_id),
  INDEX idx_user_task_time (user_id, task_id, trade_time),
  INDEX idx_user_serial (user_id, bank_serial_no),
  INDEX idx_match_status (task_id, match_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.4 待核验队列表 `t_reconciliation_queue`(阶段一)

```sql
CREATE TABLE t_reconciliation_queue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  source_a_transaction_id BIGINT NULL,
  source_b_transaction_id BIGINT NULL,
  error_type VARCHAR(32) NOT NULL,
  exception_branch VARCHAR(32) DEFAULT NULL,          -- 阶段二
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_AI',
  risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW',
  retry_count INT NOT NULL DEFAULT 0,
  fallback_level INT NOT NULL DEFAULT 0,              -- 阶段二
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_task_status (user_id, task_id, status),
  INDEX idx_error_branch (error_type, exception_branch)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.5 差错台账表 `t_error_ledger`(阶段一)

```sql
CREATE TABLE t_error_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  error_type VARCHAR(32) NOT NULL,
  exception_branch VARCHAR(32) DEFAULT NULL,           -- 阶段二
  discrepancy_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  ai_cleaned_json JSON,
  ai_audit_opinion TEXT,
  ai_confidence DECIMAL(5,4) DEFAULT NULL,
  rag_scores_json JSON,                                -- 阶段二
  rag_source VARCHAR(512),
  fallback_path VARCHAR(128) DEFAULT NULL,             -- 阶段二
  handle_status VARCHAR(32) NOT NULL DEFAULT 'UNTREATED',
  handler_username VARCHAR(64),
  handle_remark VARCHAR(255),
  handled_at DATETIME,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_error (user_id, task_id, error_type),
  INDEX idx_handle_status (handle_status),
  INDEX idx_branch_status (exception_branch, handle_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.6 人工复核表 `t_human_review`(阶段一)

```sql
CREATE TABLE t_human_review (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  ai_suggestion VARCHAR(32),
  ai_confidence DECIMAL(5,4),
  ai_reason TEXT,
  ai_fallback_level INT DEFAULT 0,
  action VARCHAR(32) NOT NULL,
  handler_username VARCHAR(64) NOT NULL,
  remark VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_queue (user_id, task_id, queue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.7 Agent 执行日志表 `t_agent_execution_log`(阶段一/二)

```sql
CREATE TABLE t_agent_execution_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  queue_id BIGINT,
  agent_name VARCHAR(64) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  input_payload JSON,
  output_payload JSON,
  pipeline_results JSON,                               -- 校验管线结果(阶段二)
  rag_retrieval_id BIGINT,
  prompt_version VARCHAR(16) DEFAULT NULL,             -- 阶段二
  fallback_level INT NOT NULL DEFAULT 0,               -- 阶段二
  llm_tokens INT NOT NULL DEFAULT 0,                   -- 阶段二
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_queue (user_id, task_id, queue_id),
  INDEX idx_agent_event (agent_name, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.8 RAG 检索记录表 `t_rag_retrieval_log`(阶段一/二)

```sql
CREATE TABLE t_rag_retrieval_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  queue_id BIGINT,
  original_query TEXT NOT NULL,
  rewritten_query TEXT,                                -- 阶段二
  top_k INT NOT NULL,
  dense_candidates INT DEFAULT 20,                     -- 阶段二
  sparse_candidates INT DEFAULT 20,                    -- 阶段二
  fusion_candidates INT DEFAULT 10,                    -- 阶段二
  after_rerank INT DEFAULT 5,                          -- 阶段二
  best_dense_score DECIMAL(8,4),                       -- 阶段二
  best_reranker_score DECIMAL(8,4),                    -- 阶段二
  sources JSON,
  selected_chunk_id VARCHAR(128),                      -- 阶段二
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_queue (user_id, task_id, queue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.9 审计报告表 `t_audit_report`(阶段三)

```sql
CREATE TABLE t_audit_report (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL DEFAULT 'demo_user',
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  report_format VARCHAR(16) NOT NULL DEFAULT 'markdown',
  report_content MEDIUMTEXT NOT NULL,
  report_metrics JSON,
  created_by VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_task (user_id, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.10 用户表 `t_user`(可选,阶段三启用 JWT 时)

```sql
CREATE TABLE t_user (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'reviewer',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 已删除:三张记忆表(`t_short_term_memory` / `t_long_term_memory` / `t_summary_memory`)、规则命中统计表(`t_rule_hit_stats`),以及流水表的 HASH 分区与 Agent 日志表的 JSON 虚拟列索引。

## 7. Agent 工作流设计

### 7.1 全局状态与节点

`ReconciliationState` 与节点定义见 `overall-architecture.md` §4。主链路 2 个 Agent(ExtractionAgent + AuditAgent),TraceAgent 可选;报告走 SQL 聚合 + 模板,LLM 润色可选。

### 7.2 工作流路由

```text
PreCheckNode(按 scenario_type 选规则库 + 异常分支路由)
  → 条件分支(根据 exception_branch 决定调用 ExtractionAgent、TraceAgent 或 RAG 子流程)
  → AuditAgent
  → 输出校验管线(Schema → 硬约束 → 决策/Fallback → 事务)
  → confidence < 0.85 → 多级 Fallback → 仍低 → HumanReviewNode(Checkpoint 挂起/恢复)
```

### 7.3 Agent 输出约束

ExtractionAgent 输出:

```json
{ "standard_type": "NAME_VARIANT", "original_flow_id": "FLOW_001", "cleaned_remark": "对手户名简称与全称差异", "confidence": 0.91 }
```

AuditAgent 输出:

```json
{
  "decision": "PENDING_HUMAN",
  "risk_level": "MEDIUM",
  "confidence": 0.72,
  "reason": "金额与入账日期一致,但摘要与户名不一致,Fallback L2 后仍低于阈值",
  "evidence": [
    { "source_type": "project_rule",
      "source": "rag_knowledge/bank_enterprise/basic_matching.md#摘要与户名不一致",
      "dense_score": 0.71, "reranker_score": 0.82 }
  ],
  "fallback_applied": true, "fallback_level": 2, "next_action": "HUMAN_REVIEW"
}
```

### 7.4 错误处理

| 场景 | 处理策略 |
|------|---------|
| JSON 解析失败 | 重试 ≤ 3 次(每次调整 Prompt 角度),仍失败 → 转人工 |
| RAG 无命中 | 直接转人工,**不触发 Fallback** |
| RAG 命中但分数偏低 | 进入 Fallback L2(换角度重试),仍低 → 转人工 |
| 工具调用失败 | 记录日志 → 转人工 |
| 数据库事务失败 | 回滚 → 标记任务 FAILED → 保留输入数据 |
| Schema 校验失败 | 重试 ≤ 3 次 → 转人工 |
| 硬约束校验失败 | 直接转人工(不重试,业务规则不应被绕过) |
| DeepSeek API 不可用 | 熔断 → 降级为确定性规则 → 全部标记 PENDING_HUMAN |

### 7.5 Fallback 分级策略

| 级别 | 策略 | Prompt 变化 | 新增信息 |
|------|------|------------|---------|
| L1(默认) | 标准审计 Prompt | System Prompt + 当前异常项 + RAG 规则原文 | — |
| L2(增强) | Few-shot 注入 | 追加 2-3 个同类异常的历史人工确认案例 | 差错台账中的历史处理记录 |
| L3(可选追溯) | TraceAgent 深度查询 / 换审计视角 | 追加关联流水追溯结果或切换视角 | Tool 返回的关联流水和追溯链 |

触发条件:L1 `confidence < 0.85` 或 RAG `best_score < 0.5` → L2;L2 仍低 → L3;L3 仍低 → 转人工;RAG 无命中 → 直接转人工(不触发 Fallback);任意级别抛异常 → 记录日志直接转人工。

## 8. 输出校验管线与硬约束设计

原 11 个 Pre/Post Hook 收敛为 **4 阶段管线**(详见 `overall-architecture.md` §2.5):

```text
① Schema 校验(+有界重试 ≤ 3 次) → ② 硬约束校验(C1–C6) → ③ 决策/Fallback 路由 → ④ 事务落库
```

- 鉴权:普通 API 中间件,不进管线。
- 限流 / 结果缓存:归 LLM 客户端封装层(Redis),不进管线。
- 事务写入独立为基础设施(先校验、后事务、再非阻塞副作用);副作用(日志、token 成本)失败不影响主流程。

硬约束 C1–C6:

| 约束 | 描述 | 实现 |
|------|------|------|
| C1 | `decision` ∈ {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED} | Pydantic Literal |
| C2 | `evidence` 不能为空列表 | field_validator |
| C3 | `|diff| > 10000` 时 `risk_level` 不能为 LOW | ConstraintValidator |
| C4 | `decision = PENDING_HUMAN` 时 `reason` 必须说明依据不足原因 | ConstraintValidator |
| C5 | `decision = AUTO_FIXED` 时 `confidence` 必须 ≥ 0.85 | ConstraintValidator |
| C6 | RAG 无命中或 `best_score < 0.5` 时禁止 `AUTO_FIXED` | ConstraintValidator |

## 9. RAG 工作流设计

阶段一用 Markdown 规则 + ChromaDB Top-K 证明 RAG 依据链路成立;阶段二引入 Query Rewrite、Hybrid Search、RRF 和 Reranker。

### 9.1 增强 RAG 流程(阶段二)

```text
规则文档 Markdown
  → 文档清洗
  → 结构化切片(## 标题 + 语义边界混合策略,min_chunk=200, max_chunk=800)
  → Dense 向量化(中文 Embedding)+ BM25 稀疏索引(jieba 分词)
  → 存入 ChromaDB(同时存 dense vector 和 sparse metadata)
  → Query Rewrite(DeepSeek 把自然语言映射为规则术语)
  → 双路召回:Dense Top-20 + BM25 Top-20
  → RRF 融合,取 Top-10
  → Cross-Encoder Reranker(默认轻量模型,可换 BGE-Reranker-v2-m3)精排,取 Top-5
  → Dense Score(≥ 0.5)+ Reranker Score(≥ 0.3)双阈值过滤
  → 返回 rag_context 给 AuditAgent
```

### 9.2 Query Rewrite 设计

```text
输入: "这笔流水为什么没对上"   → 输出: "单边账 银行未到账 流水匹配失败 处理规则"
输入: "差了两块钱是什么情况"   → 输出: "手续费差异 金额不一致 税费 处理规则"
```

Prompt 要求:输出空格分隔关键词(非完整句子);口语化映射为标准业务术语;保留关键实体(金额、日期、流水号);不添加规则文档中不存在的新概念。

### 9.3 RAG 评测体系

| 阶段 | 评测集规模 | 用途 |
|------|-----------|------|
| 二 | ~50 条(核心分支 × 10) | 验证检索基本可用,发现明显缺陷 |
| 三 | 120+ 条 | 系统化输出 Recall@5/MRR/NDCG@5 |

指标:Recall@5、MRR、NDCG@5。每次调整切片策略、检索参数或 Embedding 模型后运行评测脚本(`scripts/eval_rag.py`,评测集 `data/rag_eval_set.json`),输出 Markdown 表格 + JSON 详细结果。评测脚本跑通前不把提升幅度写成实测结论。

### 9.4 兜底策略

| 场景 | Dense Score | Reranker Score | 策略 |
|------|------------|---------------|------|
| 命中且高分 | ≥ 0.7 | ≥ 0.7 | Agent 可直接引用 |
| 命中但边缘 | ≥ 0.5 | ≥ 0.3 | Agent 可引用但提高 confidence 阈值 |
| 命中但低分 | < 0.5 或 | < 0.3 | Fallback L2(换角度重试) |
| 无命中 | — | — | 直接转人工,**不触发 Fallback** |

## 10. 异常分支网络设计

系统不是简单的"对上了 / 没对上"二元判断,而是基于声明式规则引擎和异常分支集合,覆盖真实银企对账中的各类差错场景。完整分支见 `overall-architecture.md` §5。

### 10.1 核心接口

```python
class ExceptionRouter:
    async def route(
        self, scenario_type: str, source_a_item: dict, source_b_item: dict, diff: Decimal
    ) -> RouteResult:
        """
        按 YAML 规则优先级逐一匹配,返回命中的分支和处理策略。
        确定性规则可覆盖的分支直接处理,无法覆盖的才进入 Agent 链路。
        """
        for rule in self.rule_engine.rules_for(scenario_type):
            if rule.matches(source_a_item, source_b_item, diff):
                return RouteResult(
                    rule_id=rule.id, exception_branch=rule.exception_branch,
                    action=rule.action, agent_needed=rule.action == "PENDING_AI",
                    agent_type=rule.agent_type, rag_query=rule.rag_query,
                    confidence_threshold=rule.confidence_threshold or 0.85,
                )
```

### 10.2 规则版本管理

- 规则文件头部包含 `version` 字段(如 `version: "1.0.0"`)。
- `t_reconciliation_task` 记录 `rule_version`,每次任务启动时写入,确保任何对账任务可追溯到所用规则版本。

### 10.3 规则冲突检测

ExceptionRouter 按优先级逐一匹配,第一个命中即返回。`RuleEngine._load_rules()` 完成后对同优先级规则两两检查条件是否可能交集,检测到潜在冲突记录 WARNING 日志(列出冲突规则 ID 和重叠条件),运行时不阻塞匹配。

## 11. 数据来源与审计依据设计

### 11.1 数据来源原则

只用项目人工构造的模拟数据,字段结构对应企业账簿与银行流水,姓名 / 账号 / 流水号 / 金额 / 摘要均为虚构或脱敏。数据设计同时满足:安全合规、业务可信(覆盖真实差错模式)、结果可复现(每类样本有明确预期识别结果)。

### 11.2 模拟数据场景(银企对账)

| 场景 | 说明 | 预期异常类型 | 阶段 |
| --- | --- | --- | --- |
| 正常平账 | 双账源流水号、金额、日期可匹配 | — | 一 |
| 基础金额差错 | 流水可匹配但金额不一致 | AMOUNT_MISMATCH | 一 |
| 银行已到账企业未入账 | 银行(B)有、企业账簿(A)无 | BOOK_UNRECORDED | 一 |
| 企业已记账银行未到账 | 企业账簿(A)有、银行(B)无 | BANK_UNARRIVED | 一 |
| 摘要 / 客户名不一致 | 金额一致但摘要或户名不同,需语义结构化 | NARRATIVE_NAME_MISMATCH | 二 |
| 疑似重复记账 | 同主体同金额时间差 < 5min | DUPLICATE_BOOKING | 二 |
| 手续费 / 税费差异 | 金额差恰好等于标准手续费 / 税费 | FEE_TAX_DIFF | 二 |
| 跨期入账 | 入账日期跨会计期间 | CROSS_PERIOD_POSTING | 二 |

### 11.3 审计依据来源(三层)

① 公开制度依据(人行《支付结算办法》、《人民币银行结算账户管理办法》,财政部《会计基础工作规范》、《企业内部控制基本规范》、《会计档案管理办法》,仅作规则设计参考);② 项目自定义业务规则(Markdown/YAML,标注演示规则);③ Agent/RAG 运行证据(RAG 命中来源、Dense/Reranker 分数、Agent 输出 JSON、Fallback 路径、人工复核记录、差错台账)。

## 12. 报表审计设计

### 12.1 报表指标

报告包含:任务编号、对账日期、处理用户;Source A / Source B 总笔数与总金额;自动平账笔数 / 率;AI 审计笔数 / 采纳率;各 Fallback 层级触发笔数;人工复核笔数 / 率;挂账笔数 / 差错金额合计;异常类型分布(按 exception_branch);LLM Token 总消耗和估算成本。

### 12.2 ReportAgent 输入 / 输出

输入为 SQL 聚合后的 metrics 与 error_distribution;输出按模板生成 Markdown 报告(本批次概览、异常类型分布、高风险事项、人工复核建议、RAG 引用列表、检索质量摘要、后续建议)。**统计数据必须来自 SQL 聚合,ReportAgent 只负责文字组织,不做数据计算。**

## 13. 量化指标体系

只保留会真实测量的指标,逐条标注**目标 / 实测**口径;未测量项只标"目标"。

| 指标 | 采集方式 | 口径 |
|------|---------|------|
| 自动平账率 | `t_reconciliation_task` 统计 | 实测(演示数据目标 > 95%) |
| Agent 审计采纳率 | `t_human_review` 与 `ai_suggestion` 对比 | 目标 > 85%(需人工标注样本) |
| RAG Recall@5 | 评测脚本 | 实测(目标 ≥ 0.85) |
| RAG MRR | 评测脚本 | 实测(目标 ≥ 0.70) |
| RAG NDCG@5 | 评测脚本 | 实测(目标 ≥ 0.78) |
| Agent Schema 一次通过率 | 校验管线计数器 | 实测(目标 > 92%) |
| 人工复核触发率 | 状态统计 | 实测 |
| Fallback 触发率 | Agent 日志 fallback_level | 实测 |
| LLM Token 消耗 / 成本 | 日志聚合 | 实测 |

实测值以仓库内评测产物(`reports/`、`logs/`)为准。已删除 P50/P95/P99 时延分位与 SLA 目标表(属 SRE 信号,非本项目核心)。

## 14. 验收标准

### 14.1 阶段一

- 能上传两份模拟 Excel 并生成对账任务;Pandas 完成字段校验 / 清洗 / 标准化。
- 三阶段匹配识别自动平账与异常;至少覆盖 AMOUNT_MISMATCH + 单边缺失(BANK_UNARRIVED / BOOK_UNRECORDED)。
- 异常执行 RAG 检索并返回来源与相似度分数。
- AuditAgent 输出结构化 JSON(含 evidence)、通过 Schema 校验。
- 任务 / 流水 / 异常 / 审计建议写入 MySQL;任务状态与差错明细 API 可查。
- Vue 上传 / 看板 / 台账 / 复核页可用;人工复核事务更新台账。
- 能输出单笔异常的本地 trace(输入 → RAG 命中 → Agent 输出 → 落库)。
- 覆盖最小负向测试:缺字段、金额非法、空文件或重复流水中至少 3 类。

### 14.2 阶段二

- ExtractionAgent / AuditAgent 为真实 DeepSeek V4 Pro 调用(OpenAI 兼容接口)。
- LangGraph 条件路由按 exception_branch 分发;ExceptionRouter 覆盖银企对账异常分支全集。
- 3 级 Fallback 可工作(L1 标准 → L2 历史 few-shot → L3 可选追溯);RAG 无命中直接转人工。
- 增强 RAG(Dense+BM25+RRF+Reranker+Query Rewrite)可工作,Reranker / Rewrite 可开关。
- 输出校验管线 4 阶段可工作;硬约束 C1–C6 生效。
- Prompt 独立文件 + 版本;structlog 覆盖所有 LLM 调用点;附 Prompt 版本对比脚本。
- 工具调用权限边界落地(L0/L1/L2)。
- RAG 评测脚本输出 Recall@5/MRR;Agent 决策质量评估(同一输入跑 10 次统计 decision 分布)可运行。
- 数据库完成阶段二字段新增(prompt_version、fallback_level、llm_tokens、rag_scores_json 等)。

### 14.3 阶段三

- 上传异步化(ARQ),即时返回 task_id。
- SSE 展示 Agent 执行过程(步骤、RAG 详情、Fallback 层级)。
- Redis 接入 LLM 结果缓存 / 限流 / 幂等。
- 量化指标面板可用;Markdown 审计报告可生成。
- Docker Compose 一键启动(无 Nginx)。
- (可选)JWT 登录;(可选加分项)云服务器部署。

## 15. 工具调用权限与可靠性保障

### 15.1 工具调用权限边界

Agent 使用普通函数工具(不用 MCP),定义三级权限边界,从阶段二开始落地:

| 级别 | 范围 | 说明 |
|---------|------|------|
| L0 只读 | RAG 检索、差错台账查询、历史案例检索 | Agent 可自由调用,不修改任何数据 |
| L1 结构化输出 | Agent 输出 JSON 审计建议 | 必须通过 Schema + 硬约束校验才能被消费 |
| L2 数据库写入 | 台账落库、队列 / 任务统计更新 | Agent **禁止直接写入**,必须经事务保障 |

各 Agent 工具白名单:ExtractionAgent 纯 LLM 推理(禁数据库);AuditAgent 仅 RAG 检索 + 计算结果(只读);TraceAgent 仅追溯查询(只读)。校验管线 ② 校验 Agent 输出是否包含不应有的数据库操作指令,检测到越权立即标记 `PENDING_HUMAN` 并记日志。

### 15.2 可靠性保障(围绕 LLM API 不稳定)

- **优雅降级**:DeepSeek 不可用 → 降级为确定性规则,异常标记 PENDING_HUMAN;ChromaDB 不可用 → 无 RAG 模式,evidence 为空、强制 PENDING_HUMAN。降级事件记 WARNING 日志。
- **重试 + 熔断**:LLM 调用失败重试 ≤ 3 次(指数退避 1s/2s/4s);连续 5 次失败 → 熔断 OPEN,30s 后 HALF_OPEN 探测。
- **Token 预算**:单笔异常输入 4000 + 输出 1000 = 5000 token 上限;单批次任务总 token 上限可配置(默认 500,000),达上限后剩余异常标记 PENDING_HUMAN。

## 16. 风险与边界

### 16.1 数据边界

只使用模拟 / 脱敏数据;不使用真实客户数据或银行内部资料;演示数据中姓名、账号、流水号均虚构或脱敏;公开制度依据只作规则设计参考,项目自定义规则标注为演示规则。

### 16.2 AI 决策边界

AI 不做金额计算(只读 READ-ONLY 结果);AI 不直接修改账务状态(所有写入经事务);AI 不做最终金融决策(低置信 + 无依据 + 高风险均转人工);AI 只提供结构化分析、规则引用和处理建议。

### 16.3 安全与隔离边界

所有 API 携带 `X-User-ID`;启用 JWT 时业务查询按 `user_id` 行过滤;RAG 无命中不臆造 evidence。基础安全验证(越权访问、user_id 隔离、日志脱敏、Prompt injection 基础防护)作为**可选加分项**,依赖扫描与 OWASP 检查不在核心范围。

## 17. LLM 选型说明

### 17.1 为什么选择 DeepSeek V4 Pro

| 维度 | 说明 |
|------|------|
| 成本 | 极低,个人项目可承受大量调试调用(具体价格**参考,以官网为准**) |
| 中文能力 | 顶级,银企对账场景全中文 |
| 接口兼容 | OpenAI 兼容接口(`openai` SDK + 自定义 base_url),零迁移成本 |
| 可测试性 | 工程上做 provider 抽象,默认可切 Fake provider,主链路与测试不依赖真实 Key |
| 可私有化 | 提供开源权重,后续可本地部署消除 API 依赖 |

### 17.2 集成方式

```python
from openai import OpenAI

client = OpenAI(api_key="sk-xxx", base_url="https://api.deepseek.com/v1")
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "你是银企对账审计助手..."},
        {"role": "user", "content": "请判断以下异常..."},
    ],
    temperature=0.1,                          # 金融场景需要低温度
    response_format={"type": "json_object"},  # 结构化输出
)
```

### 17.3 依赖管理

阶段二新增依赖:`openai`(DeepSeek API 调用)、`structlog`(结构化日志)、`jieba`(BM25 中文分词)、`rank-bm25`(BM25 稀疏检索)。阶段三新增:`arq`(异步队列)、`redis`。

## 18. 边界与可扩展方向

以下能力在原设计中存在,本版本**有意收敛**以突出 Agent 工程信号,是清晰的扩展点而非遗漏:

- **银行内部清算对账**等第二场景:引擎 Source A / Source B 抽象已保留,可新增 Scenario Profile(`BC-` 规则、`bank_clearing/` 知识库)扩展。
- **多租户三级隔离**:当前最多按 `user_id` 行过滤,可扩展为数据 / 会话 / 记忆三级隔离。
- **三层记忆引擎**:当前以历史人工确认案例 few-shot 作轻量替代,可演进为短期 / 长期 / 摘要记忆。
- **MCP 工具层**:当前用普通函数工具,可标准化为 MCP Server。
- **云部署与运维**:可补 Docker Compose 云端部署、压测与安全审查,均为加分项,非必做。
