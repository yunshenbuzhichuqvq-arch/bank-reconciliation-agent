# 《基于多智能体（Multi-Agent）架构的银行自动化对账与报表审计系统》系统 PRD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目名称 | 基于多智能体（Multi-Agent）架构的银行自动化对账与报表审计系统 |
| 项目类型 | 个人开源求职项目 |
| 目标岗位 | AI Agent 开发工程师 / AI 应用开发工程师 / Python 后端开发工程师 |
| 技术栈 | FastAPI、Vue 3、MySQL 8.0、LangGraph、RAG、ChromaDB、Docker |
| 项目阶段 | MVP-0 后端最小闭环 -> MVP 本地产品闭环 -> V1 在线作品 -> V2 简历最终版 |
| 数据边界 | 仅使用模拟数据和脱敏数据，不使用真实客户数据或银行内部资料 |

## 2. 产品概述

本系统面向银行对账和报表审计场景，模拟银行运营人员在日终对账中处理双端流水差异、跨日切单边账、冲正退款、手续费差异、人工复核和审计报告生成的流程。

系统采用“确定性代码 + Multi-Agent + RAG + Human-in-the-Loop”的组合方式：

- 确定性代码负责 Excel 清洗、金额计算、规则初筛和数据库事务。
- Multi-Agent 负责模糊摘要结构化、业务追溯、审计判断和报告生成。
- RAG 负责提供规则依据和审计溯源。
- Human-in-the-Loop 负责在金融风险场景中保留人工确认。

产品目标不是替代真实银行系统，而是作为个人学习和求职展示项目，证明候选人能把银行业务问题抽象成可开发的软件系统。

## 3. 产品范围与阶段规划

本项目采用 MVP-0 -> MVP -> V1 -> V2 的递进式版本规划。四个版本不是互相独立的功能清单，而是围绕同一条“Excel 上传 -> 规则对账 -> Agent 审计 -> RAG 依据 -> MySQL 台账 -> API 查询”的主链路逐层加厚。

MVP-0 是 MVP 的前置子集，不作为最终产品版本。它用于降低开发风险，先验证核心业务链路和 AI 审计链路是否成立。V2 是最终出现在简历上的完整版本。

### 3.1 MVP-0：后端最小 AI 对账闭环

目标：先完成从模拟 Excel 到差错台账查询的后端主链路，证明“规则对账 + Agent 审计 + RAG 依据 + MySQL 台账”可以跑通。

核心链路：

```text
准备模拟 Excel 数据
  -> 上传银行端流水 + 清算端流水
  -> Pandas 读取、字段校验、数据清洗
  -> 基础规则对账
  -> 识别异常交易
  -> 异常进入 Agent 审计流程
  -> RAG 检索规则依据
  -> AuditAgent 输出结构化审计建议
  -> 结果写入 MySQL 差错台账
  -> 通过 API 查询任务状态和差错明细
```

包含：

- 模拟银行端流水和清算端流水 Excel。
- FastAPI 文件上传接口。
- Pandas 读取、字段校验和数据清洗。
- 基础规则对账和异常识别。
- 简化 AuditAgent。
- Markdown 规则文档 + ChromaDB Top-K 检索。
- AuditAgent 结构化 JSON 输出。
- MySQL 任务表、流水表和差错台账表。
- 任务状态查询 API。
- 差错明细查询 API。

不包含：

- Vue 前端页面。
- 登录鉴权。
- SSE 流式事件。
- 人工复核页面。
- 报告生成。
- 多 Agent 完整编排。
- Docker Compose 一键部署。

### 3.2 MVP：本地可演示产品闭环

目标：在 MVP-0 后端主链路基础上，补齐本地可演示的产品界面和基础人工复核流程。

新增：

- Vue 账单上传页。
- 任务看板。
- 差错台账页。
- 人工复核基础页。
- LangGraph 基础工作流。
- ExtractionAgent、AuditAgent 和 HumanReviewNode。
- 跨日切单边账样例。
- 模糊冲正样例。
- Agent 执行日志入库。

暂不包含：

- 云服务器部署。
- 完整权限系统。
- SSE 流式工作台。
- Markdown/PDF 审计报告。
- RAG Rerank。
- 复杂监控。

### 3.3 V1：在线作品版

目标：形成可放到 GitHub 和服务器上演示的作品。

新增：

- Docker Compose 一键启动。
- JWT 登录鉴权。
- SSE 展示 Agent 执行过程。
- 手续费/批量业务差异样例。
- Markdown 审计报告。
- README、演示数据和部署说明。
- 云服务器部署。

### 3.4 V2：简历最终版

目标：补充 AI 应用工程化能力，形成最终写入简历并支撑面试深挖的版本。

新增：

- TraceAgent 和 ReportAgent 增强。
- 重复入账、漏记账、异常归因。
- RAG Rerank。
- RAG 检索评测。
- Prompt 版本记录。
- Agent 执行日志分析。
- PDF 报告导出。
- 基础可观测性指标。
- 失败样本分析。

## 4. 页面与交互设计

MVP-0 阶段不要求建设前端页面，主要通过 Swagger、Postman 或 curl 调用 API 演示主链路。前端页面从 MVP 阶段开始建设，V1 再补齐登录、SSE 和在线演示体验。

### 4.1 登录页

阶段：V1。

功能：

- 用户输入账号和密码。
- 后端返回 JWT。
- 前端保存 Token 并在后续请求中携带。

MVP 阶段可使用固定演示用户或暂不接入登录。

### 4.2 账单上传页

阶段：MVP。

说明：MVP-0 只提供上传 API，不建设上传页面。

功能：

- 上传银行端流水 Excel。
- 上传清算端流水 Excel。
- 展示字段校验结果。
- 展示上传后统计：银行端总笔数、清算端总笔数、自动平账数、待 AI 审计数。

关键交互：

- 文件格式错误时提示用户。
- 必填字段缺失时拒绝上传。
- 上传成功后跳转任务看板。

### 4.3 任务看板

阶段：MVP。

功能：

- 展示对账任务列表。
- 展示任务状态。
- 展示自动平账率、待复核数、挂账数、异常类型分布。
- 提供“启动 AI 审计”按钮。

### 4.4 Agent 流式工作台

阶段：V1。

功能：

- 通过 SSE 实时展示 Agent 执行事件。
- 展示当前处理流水。
- 展示工具调用，例如金额计算、T+1 查询、RAG 检索。
- 展示 RAG 命中规则和决策结果。

MVP 阶段可以先使用普通轮询或后端日志返回；V1 改为 SSE。

### 4.5 人工复核页

阶段：MVP。

说明：MVP-0 中 AI 无法自动判断的结果先写入差错台账和任务状态，不建设人工复核页面。

功能：

- 左侧展示银行端流水。
- 右侧展示清算端流水。
- 中间展示 AI 推荐操作、推荐理由、RAG 来源。
- 支持确认平账、强制挂账、人工备注。

关键要求：

- 每次操作必须记录操作人、时间、动作和备注。
- 人工确认后通过事务更新相关表。

### 4.6 差错台账页

阶段：MVP。

说明：MVP-0 只提供差错明细查询 API，不建设台账页面。

功能：

- 分页查询差错台账。
- 按任务、差错类型、处理状态、日期筛选。
- 查看单笔详情。
- 查看 AI 审计意见和人工处理记录。

### 4.7 报表审计页

阶段：V1。

功能：

- 展示总笔数、总金额、自动平账率、人工复核数、挂账金额。
- 展示异常类型分布图。
- 展示 ReportAgent 生成的 Markdown 审计报告。
- V2 支持 PDF 导出。

### 4.8 RAG 知识库管理页

阶段：V2。

功能：

- 查看规则文档列表。
- 查看文档切片。
- 输入查询语句测试检索结果。
- 查看相似度分数和来源。

## 5. 后端 API 设计

MVP-0 只要求支撑后端主链路，核心接口包括上传对账单、启动对账流程、查询任务状态和查询差错台账。登录、SSE、人工审批和报告生成属于后续阶段能力。

### 5.1 登录接口

阶段：V1。

`POST /api/v1/auth/login`

请求：

```json
{
  "username": "demo",
  "password": "demo123"
}
```

响应：

```json
{
  "code": 200,
  "message": "login success",
  "data": {
    "access_token": "jwt-token",
    "token_type": "bearer"
  }
}
```

### 5.2 上传对账单

阶段：MVP-0。

`POST /api/v1/reconcile/upload`

类型：`multipart/form-data`

字段：

- `bank_file`
- `clear_file`

响应：

```json
{
  "code": 200,
  "message": "upload success",
  "data": {
    "task_id": "TASK_20260521_001",
    "total_bank_rows": 5000,
    "total_clear_rows": 4996,
    "auto_fixed_rows": 4860,
    "pending_ai_rows": 120,
    "pending_human_rows": 16
  }
}
```

### 5.3 启动对账工作流

阶段：MVP-0。

`POST /api/v1/reconcile/{task_id}/start`

响应：

```json
{
  "code": 200,
  "message": "workflow started",
  "data": {
    "task_id": "TASK_20260521_001",
    "status": "AI_RUNNING"
  }
}
```

### 5.4 查询任务状态

阶段：MVP-0。

`GET /api/v1/reconcile/{task_id}/status`

响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "task_id": "TASK_20260521_001",
    "status": "PENDING_HUMAN",
    "auto_fixed_rows": 4860,
    "ai_processed_rows": 104,
    "pending_human_rows": 16,
    "unresolved_rows": 3
  }
}
```

### 5.5 Agent 执行事件流

阶段：V1。

`GET /api/v1/reconcile/{task_id}/events`

协议：SSE。

事件示例：

```json
{
  "event_type": "RAG_RETRIEVED",
  "queue_id": 1024,
  "agent": "AuditAgent",
  "message": "命中跨日切处理规则",
  "payload": {
    "source": "rules/cutoff.md#跨日切单边账",
    "score": 0.82
  }
}
```

### 5.6 查询待复核列表

阶段：MVP。

`GET /api/v1/review/pending`

查询参数：

- `task_id`
- `page`
- `page_size`

响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "queue_id": 1024,
        "error_type": "FUZZY_REVERSAL",
        "risk_level": "MEDIUM",
        "ai_suggestion": "APPROVED_MATCH",
        "ai_reason": "摘要疑似冲正原交易，但缺少明确原流水号，建议人工确认"
      }
    ],
    "total": 16
  }
}
```

### 5.7 人工审批

阶段：MVP。

`POST /api/v1/review/{queue_id}/approve`

请求：

```json
{
  "action": "APPROVED_MATCH",
  "handler_username": "demo",
  "remark": "人工核对原交易后确认可平账"
}
```

响应：

```json
{
  "code": 200,
  "message": "review submitted",
  "data": {
    "queue_id": 1024,
    "current_status": "FIXED"
  }
}
```

### 5.8 查询差错台账

阶段：MVP-0。

`GET /api/v1/ledger`

查询参数：

- `task_id`
- `error_type`
- `handle_status`
- `start_date`
- `end_date`
- `page`
- `page_size`

### 5.9 生成审计报告

阶段：V1。

`POST /api/v1/reports/{task_id}/generate`

响应：

```json
{
  "code": 200,
  "message": "report generated",
  "data": {
    "task_id": "TASK_20260521_001",
    "report_id": 18,
    "format": "markdown"
  }
}
```

### 5.10 RAG 检索调试

阶段：MVP-0。

`POST /api/v1/rag/search`

请求：

```json
{
  "query": "23:55 发生的单边账如何处理",
  "top_k": 3
}
```

响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "source": "rules/cutoff.md#跨日切单边账",
        "score": 0.82,
        "content": "日切敏感窗口内产生的单边账，应优先追溯下一清算日流水。"
      }
    ]
  }
}
```

## 6. 数据库设计

MVP-0 优先实现对账任务、双端流水、待核验队列、差错台账和 RAG 检索记录。用户、人工复核、Agent 完整日志和审计报告表可随 MVP/V1 阶段逐步补齐。

### 6.1 用户表 `t_user`

阶段：V1。

```sql
CREATE TABLE t_user (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'reviewer',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.2 对账任务表 `t_reconciliation_task`

阶段：MVP-0。

```sql
CREATE TABLE t_reconciliation_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL UNIQUE,
  task_name VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
  total_bank_rows INT NOT NULL DEFAULT 0,
  total_clear_rows INT NOT NULL DEFAULT 0,
  auto_fixed_rows INT NOT NULL DEFAULT 0,
  pending_ai_rows INT NOT NULL DEFAULT 0,
  pending_human_rows INT NOT NULL DEFAULT 0,
  unresolved_rows INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.3 银行端流水表 `t_bank_transaction`

阶段：MVP-0。

```sql
CREATE TABLE t_bank_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  flow_id VARCHAR(64),
  account_no_masked VARCHAR(64),
  customer_name_masked VARCHAR(64),
  amount DECIMAL(18,2) NOT NULL,
  trade_time DATETIME NOT NULL,
  summary VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_flow (task_id, flow_id),
  INDEX idx_task_time (task_id, trade_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.4 清算端流水表 `t_clear_transaction`

阶段：MVP-0。

```sql
CREATE TABLE t_clear_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  flow_id VARCHAR(64),
  channel VARCHAR(32),
  amount DECIMAL(18,2) NOT NULL,
  trade_time DATETIME NOT NULL,
  summary VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_flow (task_id, flow_id),
  INDEX idx_task_time (task_id, trade_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.5 待核验队列表 `t_reconciliation_queue`

阶段：MVP-0。

```sql
CREATE TABLE t_reconciliation_queue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  bank_transaction_id BIGINT NULL,
  clear_transaction_id BIGINT NULL,
  error_type VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_AI',
  risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW',
  retry_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_task_status (task_id, status),
  INDEX idx_error_type (error_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.6 差错台账表 `t_error_ledger`

阶段：MVP-0。

```sql
CREATE TABLE t_error_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  error_type VARCHAR(32) NOT NULL,
  discrepancy_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  ai_cleaned_json JSON,
  ai_audit_opinion TEXT,
  rag_source VARCHAR(512),
  handle_status VARCHAR(32) NOT NULL DEFAULT 'UNTREATED',
  handler_username VARCHAR(64),
  handle_remark VARCHAR(255),
  handled_at DATETIME,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_error (task_id, error_type),
  INDEX idx_handle_status (handle_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.7 人工复核表 `t_human_review`

阶段：MVP。

```sql
CREATE TABLE t_human_review (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  ai_suggestion VARCHAR(32),
  ai_reason TEXT,
  action VARCHAR(32) NOT NULL,
  handler_username VARCHAR(64) NOT NULL,
  remark VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_queue (task_id, queue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.8 Agent 执行日志表 `t_agent_execution_log`

阶段：MVP。

```sql
CREATE TABLE t_agent_execution_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  queue_id BIGINT,
  agent_name VARCHAR(64) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  input_payload JSON,
  output_payload JSON,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_queue (task_id, queue_id),
  INDEX idx_agent_event (agent_name, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.9 RAG 检索记录表 `t_rag_retrieval_log`

阶段：MVP-0。

```sql
CREATE TABLE t_rag_retrieval_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  queue_id BIGINT,
  query_text TEXT NOT NULL,
  top_k INT NOT NULL,
  best_score DECIMAL(8,4),
  sources JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_queue (task_id, queue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.10 审计报告表 `t_audit_report`

阶段：V1。

```sql
CREATE TABLE t_audit_report (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  report_format VARCHAR(16) NOT NULL DEFAULT 'markdown',
  report_content MEDIUMTEXT NOT NULL,
  created_by VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_id (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## 7. Agent 工作流设计

MVP-0 不追求完整 Multi-Agent 编排，只保留简化 Agent 审计链路：规则对账识别异常后，调用 RAG 检索规则依据，再由 AuditAgent 输出结构化审计建议。MVP 阶段再引入 LangGraph 基础工作流和多节点协作。

### 7.1 全局状态

```python
from typing import Any, Dict, List, Optional, TypedDict

class ReconciliationState(TypedDict):
    task_id: str
    current_queue_id: Optional[int]
    bank_item: Dict[str, Any]
    clear_item: Dict[str, Any]
    error_type: Optional[str]
    math_result: Dict[str, str]
    extraction_result: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    audit_decision: Dict[str, Any]
    retry_count: int
    next_action: str
    error_message: Optional[str]
    agent_logs: List[Dict[str, Any]]
```

### 7.2 节点定义

| 节点 | 职责 | 阶段 |
| --- | --- | --- |
| `PreCheckNode` | 规则预处理、金额比对、异常初筛 | MVP-0 |
| `AuditAgent` | 基于 RAG 和工具结果做结构化审计建议 | MVP-0 |
| `ExtractionAgent` | 模糊摘要结构化 | MVP |
| `HumanReviewNode` | 挂起流程等待人工审批 | MVP |
| `TraceAgent` | 跨日切、冲正、退款链路追溯 | V2 |
| `ReportAgent` | 生成审计摘要和报告 | V1/V2 |

### 7.3 状态流转

MVP-0 状态流转：

```text
START
  -> 上传并解析双端 Excel
  -> PreCheckNode 完成字段校验、数据清洗、基础对账和异常识别
  -> 对异常交易执行 RAG 检索
  -> AuditAgent 输出结构化审计建议
  -> 写入差错台账和任务统计
  -> END
```

MVP 及后续状态流转：

```text
START
  -> PreCheckNode
  -> 如果是基础金额差错，写入差错台账
  -> 如果是模糊摘要，进入 ExtractionAgent
  -> 如果需要规则依据，进入 RAG 检索
  -> AuditAgent 生成审计判断
  -> 可自动处理，更新台账和队列状态
  -> 不可自动处理，进入 HumanReviewNode
  -> 所有队列处理完成，进入 ReportAgent 或 END
```

### 7.4 Agent 输出约束

ExtractionAgent 输出：

```json
{
  "standard_type": "REVERSAL",
  "original_flow_id": "FLOW_001",
  "cleaned_remark": "冲正原交易 FLOW_001",
  "confidence": 0.91
}
```

AuditAgent 输出：

```json
{
  "decision": "PENDING_HUMAN",
  "reason": "疑似冲正交易，但未检索到足够规则依据，转人工复核",
  "risk_level": "MEDIUM",
  "rag_source": [
    "rules/reversal.md#冲正交易识别"
  ],
  "next_action": "HUMAN_REVIEW"
}
```

### 7.5 错误处理

- JSON 解析失败：重试 3 次，仍失败则转人工。
- RAG 无命中：转人工。
- 工具调用失败：记录日志并转人工。
- 数据库事务失败：回滚并标记任务失败。
- Agent 输出字段缺失：拒绝落库并重试。

## 8. 数据来源与审计依据设计

### 8.1 数据来源原则

本项目不使用真实银行流水、真实客户信息或银行内部制度。所有演示数据均为项目人工构造的模拟数据，字段结构和异常模式来自银行对账业务抽象。

数据设计需要同时满足三点：

- **安全合规**：姓名、账号、流水号、金额、摘要均为虚构或脱敏样式。
- **业务可信**：样本覆盖真实对账中常见的差错模式。
- **结果可复现**：每类样本都有明确的预期识别结果，方便测试和演示。

### 8.2 模拟数据类型

MVP-0 阶段至少准备两类 Excel：

- 银行端流水：模拟银行核心、网银或柜面系统中的入账/出账流水。
- 清算端流水：模拟清算平台、第三方支付渠道或批量业务系统中的清算流水。

样本场景按阶段扩展：

| 场景 | 说明 | 阶段 |
| --- | --- | --- |
| 正常平账 | 双端流水号、金额、日期可匹配 | MVP-0 |
| 基础金额差错 | 流水可匹配但金额不一致 | MVP-0 |
| 单边缺失 | 一端存在流水，另一端缺失 | MVP-0 |
| 跨日切单边 | 日切窗口内当天单边，T+1 出现补记 | MVP |
| 冲正/退款/反向抹账 | 摘要不规范，需要语义结构化 | MVP |
| 手续费/批量业务差异 | 金额差异来自手续费或批量业务部分失败 | V1 |
| 重复入账/漏记账 | 相近时间、同客户、同金额的疑似重复或遗漏 | V2 |

建议在后续代码工程中单独维护 `mock_data/README.md`，说明数据为虚构、字段含义、覆盖场景和每类样本的预期结果。

### 8.3 审计依据来源

审计依据由三层组成。

第一层是公开制度依据，用于说明项目遵循“规则、凭证、内控、留痕”的金融和会计基本原则。可参考：

- 中国人民银行《支付结算办法》：支付结算行为和资金收付背景依据。
- 中国人民银行《人民币银行结算账户管理办法》：银行结算账户与账户收付管理背景依据。
- 财政部《会计基础工作规范》：原始凭证、会计资料、审核和更正等基础依据。
- 财政部等五部委《企业内部控制基本规范》：内部控制、风险防范、授权审批和信息记录依据。
- 财政部、国家档案局《会计档案管理办法》：会计资料真实、完整、可用、安全和留存依据。

第二层是项目自定义业务规则，用于把公开原则和对账业务抽象成系统可执行、可检索的规则文档。这些规则不是银行内部制度，而是演示用业务规则。

第三层是 Agent/RAG 运行证据，包括 RAG 命中的规则来源、相似度分数、Agent 输出 JSON、人工复核记录和差错台账记录。

### 8.4 项目规则文件设计

规则文档以 Markdown 维护，进入 ChromaDB 前按标题或规则编号切片。

MVP-0：

- `rules/reconciliation_basic.md`：基础对账规则，例如金额、流水号、日期匹配逻辑。
- `rules/cutoff.md`：跨日切单边账处理原则。
- `rules/reversal.md`：冲正、退款、反向抹账摘要识别原则。
- `rules/review_policy.md`：无依据、低置信度、高风险金额进入人工复核或待处理状态。

MVP：

- `rules/human_review.md`：人工复核动作、备注和留痕要求。

V1：

- `rules/fee.md`：手续费、渠道费和批量业务差异规则。
- `rules/report_policy.md`：审计报告统计口径和异常分类口径。

V2：

- `rules/duplicate_missing.md`：重复入账、漏记账和疑似重复清算识别规则。
- `rules/rag_eval_policy.md`：RAG 检索评测和失败样本分析规则。

### 8.5 Agent 审计输出依据

AuditAgent 不允许仅凭模型知识输出“可以平账”。每条审计建议必须包含证据字段。

示例：

```json
{
  "decision": "PENDING_HUMAN",
  "risk_level": "MEDIUM",
  "reason": "疑似冲正交易，但未匹配到明确原流水号",
  "evidence": [
    {
      "source_type": "project_rule",
      "source": "rules/reversal.md#冲正识别规则",
      "score": 0.86
    }
  ],
  "next_action": "HUMAN_REVIEW"
}
```

如果 RAG 未命中规则、命中分数低于阈值、工具调用失败或结构化输出不完整，系统不得自动平账，必须进入人工复核或待处理状态。

## 9. RAG 工作流设计

### 9.1 RAG 目标

RAG 负责让 Agent 的关键审计判断有依据，尤其用于：

- 跨日切单边账。
- 冲正和退款。
- 手续费差异。
- 人工复核触发。
- 报表审计口径。

### 9.2 文档来源

MVP-0：

- `rules/reconciliation_basic.md`
- `rules/cutoff.md`
- `rules/reversal.md`
- `rules/review_policy.md`

MVP：

- `rules/human_review.md`

V1：

- `rules/fee.md`
- `rules/report_policy.md`

V2：

- `rules/duplicate_missing.md`
- `rules/rag_eval_policy.md`
- 公开制度依据摘要。
- PDF / Word 文档解析结果。

### 9.3 处理流程

1. 读取规则文档。
2. 按 Markdown 标题切片。
3. 使用中文 Embedding 模型向量化。
4. 写入 ChromaDB。
5. 根据当前异常上下文构造查询。
6. 检索 Top-K。
7. 过滤低分结果。
8. 返回给 AuditAgent。
9. 将检索记录写入 MySQL。

### 9.4 兜底策略

RAG 命中且分数达标：

- Agent 可以引用规则做判断。

RAG 命中但分数偏低：

- Agent 必须转人工，并说明依据不足。

RAG 无命中：

- Agent 不允许自动判定，必须转人工。

## 10. 报表审计设计

### 10.1 报表指标

报告需要包含：

- 任务编号。
- 对账日期。
- 银行端总笔数。
- 清算端总笔数。
- 自动平账笔数。
- AI 审计笔数。
- 人工复核笔数。
- 挂账笔数。
- 差错金额合计。
- 异常类型分布。

### 10.2 ReportAgent 输入

```json
{
  "task_id": "TASK_20260521_001",
  "summary": {
    "total_bank_rows": 5000,
    "total_clear_rows": 4996,
    "auto_fixed_rows": 4860,
    "pending_human_rows": 16,
    "unresolved_rows": 3
  },
  "error_distribution": {
    "AMOUNT_MISMATCH": 40,
    "CUTOFF_SINGLE_SIDE": 32,
    "FUZZY_REVERSAL": 28,
    "FEE_DIFF": 20
  }
}
```

### 10.3 ReportAgent 输出

输出 Markdown 报告，包含：

- 本批次对账概览。
- 主要异常类型。
- 高风险事项。
- 人工复核建议。
- RAG 规则引用。
- 后续处理建议。

统计数据必须来自 SQL 聚合，ReportAgent 只负责文字组织和解释。

## 11. 验收标准

### 11.1 MVP-0 验收标准

- 能准备并使用两份模拟 Excel：银行端流水和清算端流水。
- 能通过 FastAPI 上传两份 Excel，并生成对账任务。
- 能使用 Pandas 完成字段校验、数据清洗和标准化。
- 能通过基础规则识别自动平账交易和异常交易。
- 能至少识别基础金额差错和单边缺失两类异常。
- 能对异常交易执行 RAG 检索，并返回规则来源和相似度分数。
- AuditAgent 能输出结构化 JSON 审计建议。
- 能将任务、流水、异常和审计建议写入 MySQL。
- 能通过 API 查询任务状态，包括总笔数、自动平账数、异常数和处理状态。
- 能通过 API 查询差错明细，包括异常类型、差异金额、AI 审计建议和 RAG 来源。
- 能说明模拟数据来源、字段含义、覆盖场景和预期识别结果。
- AuditAgent 输出必须包含 evidence 字段，能追溯到项目规则或公开依据摘要。

### 11.2 MVP 验收标准

- 能通过 Vue 页面上传两份模拟 Excel。
- 能在任务看板查看对账任务和核心统计。
- 能处理一个跨日切单边账样例。
- 能处理一个模糊冲正样例。
- 能通过 LangGraph 串联 PreCheckNode、ExtractionAgent、AuditAgent 和 HumanReviewNode。
- AI 无法判断时能进入人工复核流程。
- 前端能查看任务、复核项和差错台账。
- 能记录基础 Agent 执行日志。

### 11.3 V1 验收标准

- Docker Compose 可启动前端、后端、MySQL 和 ChromaDB。
- 支持 JWT 登录。
- Agent 执行过程通过 SSE 展示。
- 支持手续费/批量业务差异样例。
- 支持 Markdown 审计报告。
- README 包含本地启动、部署说明和演示账号。
- 项目可部署到云服务器。

### 11.4 V2 验收标准

- 支持重复入账和漏记账样例。
- RAG 有检索评测记录。
- Agent 执行日志可查询。
- 支持 Prompt 版本记录。
- 支持 PDF 报告导出。
- 能输出失败样本分析。

## 12. 风险与边界

### 12.1 数据边界

- 只使用模拟数据和脱敏数据。
- 不使用真实客户数据。
- 不使用银行内部资料。
- 演示数据中的姓名、账号、流水号均为虚构或脱敏。
- 公开制度依据只作为项目规则设计参考，不直接等同于真实银行内部审计制度。
- 项目自定义规则必须明确标注为演示规则，不冒充银行内部制度。

### 12.2 AI 决策边界

- AI 不做金额计算。
- AI 不直接修改账务状态。
- AI 不做最终金融决策。
- AI 只提供结构化分析、规则引用和处理建议。

### 12.3 项目边界

本项目用于学习、开源展示和求职面试，不宣称可直接用于真实生产银行系统。真实生产系统还需要权限隔离、审计合规、灾备、压测、安全评估和更严格的数据治理。

## 13. 面试讲解线索

面试时可以按下面顺序讲：

1. **项目来源**：自己有银行柜员经历，知道对账、冲正、挂账和报表审计是实际存在的问题。
2. **业务抽象**：把银行对账拆成基础差错、跨日切、冲正退款、手续费、重复漏记、报表审计六类场景。
3. **技术边界**：金额计算和数据库状态更新由确定性代码完成，AI 只处理语义和解释。
4. **Agent 设计**：用 LangGraph 把预处理、提取、审计、追溯、人工复核和报表生成串成工作流。
5. **RAG 价值**：Agent 的审计判断必须引用规则来源，没有依据就转人工。
6. **数据和依据来源**：数据全部模拟，依据来自公开制度、项目自定义规则和 RAG 证据流，不使用真实客户数据或银行内部资料。
7. **后端能力**：FastAPI、Pydantic、MySQL 事务、SSE、JWT、Docker 都在系统里有具体用途。
8. **分阶段实现**：MVP-0 先验证后端最小 AI 对账闭环，MVP 做成本地可演示产品，V1 上线展示，V2 再做评测、日志、报告和可观测性，作为最终简历版本。
