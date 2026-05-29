# 《基于多智能体（Multi-Agent）架构的银行自动化对账与报表审计系统》系统 PRD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目名称 | 基于多智能体（Multi-Agent）架构的银行自动化对账与报表审计系统 |
| 项目类型 | 个人开源求职项目 |
| 目标岗位 | AI Agent 开发工程师 / AI 应用开发工程师 / Python 后端开发工程师 |
| 技术栈 | FastAPI、Vue 3、MySQL 8.0、LangGraph、RAG、ChromaDB、Redis、SQLite、Docker、LangFuse |
| 项目阶段 | MVP-0 后端最小闭环 -> MVP-1 本地产品闭环 -> MVP-2 Agent 工程化闭环 -> V1 在线作品 -> V2 简历最终版 |
| 数据边界 | 仅使用模拟数据和脱敏数据，不使用真实客户数据或银行内部资料 |

## 2. 产品概述

本系统面向银行对账和报表审计场景，模拟银行运营人员在日终对账中处理双端流水差异、跨日切单边账、冲正退款、手续费差异、人工复核和审计报告生成的流程。

系统采用“确定性代码 + 规则引擎 + Multi-Agent + RAG + 记忆引擎 + Hook 链 + Human-in-the-Loop”的组合方式：

- **确定性代码**负责 Excel 清洗、金额计算、规则引擎和数据库事务。
- **规则引擎**基于声明式 YAML 规则，将异常流水分发到 12 个处理分支。
- **Multi-Agent**负责模糊摘要结构化、业务追溯、审计判断和报告生成。
- **RAG**采用混合检索 + Reranker + Query Rewrite 全链路，提供规则依据和审计溯源。
- **记忆引擎**提供三层记忆（短期/长期/摘要），使 Agent 具备跨调用和跨会话的决策一致性。
- **Hook 链**作为 Pre/Post Processing 门禁，负责权限校验、速率限制、记忆注入、硬约束校验和审计日志。
- **Human-in-the-Loop**负责在金融风险场景中保留人工确认。

产品目标不是替代真实银行系统，而是作为个人学习和求职展示项目，证明候选人能把银行业务问题抽象成可开发的软件系统，并在每个技术选择背后有清晰的设计决策和量化指标。

### 2.1 2026 Agent 求职表达原则

本项目的求职表达重点不是“堆满 Agent 热词”，而是证明以下能力：

- 能把金融对账问题拆成确定性规则、Agent 判断、人工复核和审计留痕四类边界。
- 能说明每个 Agent 节点为什么存在，什么时候不该让 LLM 参与。
- 能给 RAG、Hook、Memory、Fallback、可观测性分别提供可运行证据。
- 能用评测集、日志、测试和数据库记录证明系统不是一次性 Demo。

因此，PRD 中的复杂能力按阶段落地。MVP-0 只验证主链路；MVP-1 做本地演示所需的最小产品闭环；MVP-2 再补 Agent 工作流、Hook、Memory 和增强 RAG；V1/V2 补评测、部署、MCP、A/B 和压力测试。所有未实际跑出的指标均作为目标口径，不在简历和面试中表述为真实生产数据。

## 3. 产品范围与阶段规划

本项目采用 MVP-0 -> MVP-1 -> MVP-2 -> V1 -> V2 的递进式版本规划。五个版本不是互相独立的功能清单，而是围绕同一条主链路逐层加厚。

MVP-0 是后续阶段的前置子集，用于降低开发风险，先验证核心业务链路和 AI 审计链路是否成立。MVP-1 把后端能力变成本地可演示产品；MVP-2 再补 Agent 工程化深度；V2 是最终出现在简历上的完整版本。

每个阶段都必须有可验收产物。MVP-0 的产物是 API、数据库记录、RAG/Agent JSON 和最小 trace；MVP-1 的产物是本地页面、人工复核流、YAML 规则和复核记录；MVP-2 的产物是 LangGraph 工作流、Hook/Memory 日志、Fallback 和增强 RAG trace；V1 的产物是部署地址、SSE 演示、评测报告和指标仪表板；V2 的产物是失败样本分析、A/B 对比、安全验证和压力测试报告。

### 3.1 MVP-0：后端最小 AI 对账闭环

目标：先完成从模拟 Excel 到差错台账查询的后端主链路，证明“规则对账 + Agent 审计 + RAG 依据 + MySQL 台账”可以跑通。

核心链路：

```text
准备模拟 Excel 数据
  -> 上传银行端流水 + 清算端流水
  -> Pandas 读取、字段校验、数据清洗
  -> 基础规则对账
  -> 识别异常交易（AMOUNT_MISMATCH + SINGLE_SIDE_MISSING）
  -> 异常进入 Agent 审计流程
  -> RAG 检索规则依据（ChromaDB Top-K + 相似度阈值）
  -> AuditAgent 输出结构化审计建议（含 evidence 字段）
  -> 结果写入 MySQL 差错台账
  -> 通过 API 查询任务状态和差错明细
```

包含：

- 模拟银行端流水和清算端流水 Excel（覆盖正常平账、金额差错、单边缺失 3 类场景）。
- FastAPI 文件上传接口。
- Pandas 读取、字段校验和数据清洗。
- 基础规则对账和异常识别（if-else 规则，MVP-1 阶段升级为 YAML 引擎）。
- 简化 AuditAgent（单次调用，无多级 Fallback）。
- Markdown 规则文档 + ChromaDB Top-K 检索。
- AuditAgent 结构化 JSON 输出（含 evidence 字段）。
- MySQL 任务表、流水表和差错台账表。
- RAG 检索记录表。
- 任务状态查询 API。
- 差错明细查询 API。

不包含：

- Vue 前端页面。
- 登录鉴权。
- SSE 流式事件。
- 人工复核页面。
- 报告生成。
- 多 Agent 完整编排。
- Hook 链。
- 记忆引擎。
- YAML 规则引擎。
- 混合检索 / Reranker / Query Rewrite。
- Docker Compose 一键部署。

### 3.2 MVP-1：本地可演示产品闭环

目标：在 MVP-0 后端主链路基础上，补齐本地页面、人工复核和声明式规则，让项目从“API 能跑”变成“本地可以完整演示的业务产品”。MVP-1 阶段追求产品闭环完整，不追求完整 Agent 工程化能力。

新增：

- Vue 账单上传页。
- 任务看板（含统计指标）。
- 差错台账页。
- 人工复核基础页。
- **YAML 声明式规则引擎第一版**：替换 MVP-0 的硬编码 if-else。
- **ExceptionRouter 第一版**：先覆盖金额差错、单边缺失、跨日切单边、模糊冲正、疑似重复入账 5 个核心分支。
- 跨日切单边账样例。
- 模糊冲正样例。
- 疑似重复入账样例。
- Agent 执行日志入库。
- 本地 JSON trace 文件，用于回放单笔异常的规则命中、RAG 命中和 Agent 输出。
- 人工复核结果写回差错台账。
- 人工复核操作记录表。
- 多租户中间件第一版：仍使用 `X-User-ID: demo_user`，但所有查询必须显式按 `user_id` 过滤。

MVP-1 暂不包含：

- LangGraph 完整工作流。
- Agent 并行执行。
- Hook 链。
- 记忆引擎。
- LangGraph Checkpoint。
- 多级 Fallback。
- Hybrid Search / Reranker / Query Rewrite。
- LangFuse。
- JWT 鉴权。
- SSE 流式工作台。
- 后台任务队列。
- MCP 协议工具层。

### 3.3 MVP-2：Agent 工程化闭环

目标：在 MVP-1 的本地产品闭环基础上，把简单 Agent 调用升级为可追踪、可约束、可复核的 Agent 工作流。MVP-2 阶段追求 Agent 架构深度，但仍保持本地运行，不承担线上部署和完整评测体系。

新增：

- LangGraph 基础工作流（PreCheckNode → ExceptionRouter → ExtractionAgent ∥ RAG Subgraph → AuditAgent → HumanReviewNode）。
- **Agent 并行执行**：ExtractionAgent 与 RAG Subgraph 并行，通过 Send API 汇聚。
- **ExceptionRouter 完整版**：扩展到 12 个异常分支。
- **RAG Subgraph**：封装 Query Rewrite → Hybrid Search → Reranker → Filter 子流程。
- **Hook 链基础实现**：
  - Pre-Hooks: AuthHook、RateLimitHook、MemoryHook、ValidationHook
  - Post-Hooks: SchemaHook、ConstraintHook、DecisionHook、MemoryUpdateHook、LogHook
- **记忆引擎最小版**：
  - Redis 短期记忆（Sorted Set，thread_id 隔离）
  - Redis 摘要记忆（累计满 20 笔触发 LLM 压缩）
  - SQLite 长期记忆（user_id 隔离，仅存储人工确认结果）
- **LangGraph Checkpoint**：HumanReviewNode 断点续跑。
- **多级 Fallback**：AuditAgent 三级递进策略。
- **增强 RAG**：Dense + BM25 + RRF，Reranker 和 Query Rewrite 可开关。
- **可观测性保底**：structlog 结构化日志 + 本地 JSON trace；LangFuse 作为可选集成。
- 数据库改造：补齐 Agent 日志、记忆、Fallback、RAG 混合检索细节和 JSON 虚拟列索引。
- **Prompt 版本管理**：所有 LLM 调用点（ExtractionAgent、AuditAgent、Query Rewrite、Summary Compression）的 Prompt 以独立文件存放，纳入版本控制。`t_agent_execution_log` 记录 `prompt_version`，确保每次 Agent 决策可追溯到具体 Prompt 版本。
- **端到端集成测试**：基于已知 mock Excel 的固定对账结果，验证从上传到台账落库的全链路正确性；覆盖正常平账、金额差错、单边缺失三类场景的预期输出。
- **Agent 决策回归测试**：给定固定 RAG 输入和异常项，验证 Agent 输出决策的一致性（同一输入不应出现相反的决策）。

MVP-2 的简化策略：

- AuthHook 可先用 `X-User-ID` + 固定演示用户模拟，V1 再接 JWT。
- MemoryHook 只注入最近 N 条同类处理记录，不做复杂长期记忆排序。
- Reranker 和 Query Rewrite 必须可关闭，保证主链路在本地资源不足时仍可运行。
- LangFuse 如果本地配置不可用，structlog JSON 日志必须保底记录完整 trace。

MVP-2 暂不包含：

- 云服务器部署。
- JWT 鉴权。
- SSE 流式工作台。
- Markdown/PDF 审计报告。
- MCP 协议工具层。
- 后台任务队列。
- 大规模 RAG 评测集。
- 在线量化指标仪表板。

### 3.4 V1：在线作品版

目标：形成可放到 GitHub 和服务器上演示的作品，补齐量化指标和评测体系，让项目从“能跑”升级为“能解释效果和失败原因”。

新增：

- Docker Compose 一键启动（含 Nginx 反向代理）。
- **Celery/ARQ 后台任务队列**：对账任务异步执行，上传接口即时返回 task_id。
- JWT 登录鉴权。
- SSE 展示 Agent 执行过程（含 Pre/Post Hook 状态、RAG 检索详情、Fallback 层级）。
- 手续费/批量业务差异样例。
- Markdown 审计报告。
- MCP 协议工具层可选演示：RAG Server、Ledger Server、Trace Server 以 MCP 形式提供；若时间不足，保留为 V2 增强。
- **RAG 评测集**：手写 50 条 (query, expected_rule_ids)，评测脚本输出 Recall@5/MRR/NDCG。
- **Agent Schema 符合性测试**：Pytest + Pydantic，统计通过率。
- **量化指标仪表板**：前端展示核心指标。
- README、演示数据和部署说明。
- 云服务器部署。

### 3.5 V2：简历最终版

目标：补充 AI 应用工程化能力，形成最终写入简历并支撑面试深挖的版本。V2 不再继续堆功能，而是围绕“效果、稳定性、成本和失败分析”做深度优化。

新增：

- TraceAgent 和 ReportAgent 增强。
- 重复入账、漏记账、异常归因。
- RAG A/B 对比框架（不同切片策略、不同 Embedding 模型对比）。
- Prompt 版本记录和效果对比。
- Agent 执行日志离线分析。
- PDF 报告导出（含图表）。
- 失败样本分析。
- 压力测试与性能调优。
- **安全审查**：依赖扫描（`pip-audit` / `npm audit`）、静态代码分析（Bandit / Semgrep）、OWASP Top 10 检查（SQL 注入、XSS、路径遍历、敏感信息泄露）。输出安全审查报告，标注风险等级和修复建议。

## 4. 页面与交互设计

MVP-0 阶段不要求建设前端页面，主要通过 Swagger、Postman 或 curl 调用 API 演示主链路。前端页面从 MVP-1 阶段开始建设，V1 再补齐登录、SSE 和在线演示体验。

### 4.1 登录页

阶段：V1。

功能：

- 用户输入账号和密码。
- 后端返回 JWT。
- 前端保存 Token 并在后续请求中携带。

MVP-1/MVP-2 阶段可在请求 Header 中直接传入 `X-User-ID: demo_user` 模拟用户身份。

### 4.2 账单上传页

阶段：MVP-1。

说明：MVP-0 只提供上传 API，不建设上传页面。

功能：

- 上传银行端流水 Excel。
- 上传清算端流水 Excel。
- 展示字段校验结果。
- 展示上传后统计：银行端总笔数、清算端总笔数、自动平账数、待 AI 审计数。

关键交互：

- 文件格式错误时提示用户。
- 必填字段缺失时拒绝上传。
- 上传成功后跳转任务看板（V1：即时返回 task_id，异步处理）。

### 4.3 任务看板

阶段：MVP-1。

功能：

- 展示对账任务列表。
- 展示任务状态、自动平账率、待复核数、挂账数。
- 展示异常类型分布（饼图 / 柱状图）。
- 提供“启动 AI 审计”按钮。
- MVP-1/MVP-2 阶段支持手动刷新；V1 改为 SSE 实时更新。

### 4.4 Agent 流式工作台

阶段：V1。

功能：

- 通过 SSE 实时展示 Agent 执行事件。
- 展示当前处理流水。
- 展示 Pre-Hook 状态（权限校验 ✓、速率限制 ✓、记忆注入 ✓）。
- 展示异常分支路由结果。
- 展示工具调用，例如金额计算、T+1 查询、RAG 检索。
- 展示 RAG 命中规则和相似度分数（含 Dense Score + Reranker Score）。
- 展示 AuditAgent 决策和置信度。
- 展示 Fallback 层级和 Post-Hook 校验状态。
- 展示最终决策结果。

MVP-1/MVP-2 阶段可以先使用普通轮询或后端日志返回；V1 改为 SSE。

### 4.5 人工复核页

阶段：MVP-1。

说明：MVP-0 中 AI 无法自动判断的结果先写入差错台账和任务状态，不建设人工复核页面。

功能：

- 左侧展示银行端流水。
- 右侧展示清算端流水。
- 中间展示 AI 推荐操作、推荐理由、RAG 来源（含原始规则片段）。
- MVP-1 展示 AI 审计置信度；MVP-2 进一步展示 Fallback 路径。
- MVP-2 展示同类异常的历史处理记录（来自长期记忆检索）。
- 支持确认平账、强制挂账、人工备注。

关键要求：

- 每次操作必须记录操作人、时间、动作和备注。
- 人工确认后通过事务更新相关表。
- MVP-1 记录人工复核结果；MVP-2 将人工确认结果写入长期记忆（SQLite），影响后续 Agent 判断。

**复核超时与升级机制：**

人工复核并非无限等待。当待复核项长时间未处理时，系统需要自动升级通知或变更状态：

- 超时定义：任务进入 `PENDING_HUMAN` 状态后，若 24 小时内未被处理，视为超时。
- 超时升级：超时后自动将该项标记为 `OVERDUE`，并在任务看板中以醒目方式提示。
- MVP-1 实现：任务看板按创建时间排序，超时项高亮显示；不实现自动通知。
- MVP-2 实现：可通过 Hook 链中的 DecisionHook 检测超时并写入 Agent 执行日志。
- V1 实现：支持配置超时时长，超时后通过 SSE 推送提醒。

### 4.6 差错台账页

阶段：MVP-1。

说明：MVP-0 只提供差错明细查询 API，不建设台账页面。

功能：

- 分页查询差错台账。
- 按任务、差错类型、处理状态、日期、风险等级筛选。
- 查看单笔详情（含 AI 审计意见、RAG 来源、人工处理记录）。
- 查看 Agent 决策链路回放（MVP-2 起支持本地 trace，V1 起支持 SSE 回放）。

### 4.7 报表审计页

阶段：V1。

功能：

- 展示总笔数、总金额、自动平账率、人工复核数、挂账金额。
- 展示异常类型分布图。
- 展示 Agent 决策分布（自动平账 / AI 审计处理 / Fallback / 人工复核）。
- 展示 ReportAgent 生成的 Markdown 审计报告。
- V2 支持 PDF 导出。

### 4.8 RAG 知识库管理页

阶段：V2。

功能：

- 查看规则文档列表。
- 查看文档切片策略和切片列表。
- 输入查询语句测试检索结果（含 Dense Score + BM25 Score + Reranker Score）。
- 查看混合检索的双路得分和 RRF 融合过程。
- 查看相似度分数和来源。

### 4.9 量化指标仪表板（V1 新增）

阶段：V1。

功能：

- 展示自动平账率、Agent 审计准确率、RAG Recall@5/MRR。
- 展示 Agent Schema 符合率、人工复核触发率。
- 展示单笔平均处理时延（P50/P95/P99）。
- 展示 LLM Token 消耗趋势和成本估算。

## 5. 后端 API 设计

### 5.1 鉴权说明

所有 API 均需携带 `X-User-ID` Header（MVP-0/MVP-1/MVP-2 阶段为固定演示值，V1 阶段改为 JWT）。

### 5.2 登录接口

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
    "token_type": "bearer",
    "user_id": "demo_user"
  }
}
```

### 5.3 上传对账单

阶段：MVP-0。

`POST /api/v1/reconcile/upload`

类型：`multipart/form-data`

Header：`X-User-ID: demo_user`

字段：

- `bank_file`
- `clear_file`

响应（V1 改为异步，即时返回 task_id）：

```json
{
  "code": 200,
  "message": "upload success",
  "data": {
    "task_id": "TASK_20260526_001",
    "total_bank_rows": 5000,
    "total_clear_rows": 4996,
    "auto_fixed_rows": 4860,
    "pending_ai_rows": 120,
    "pending_human_rows": 16,
    "status": "UPLOADED"
  }
}
```

### 5.4 启动对账工作流

阶段：MVP-0。

`POST /api/v1/reconcile/{task_id}/start`

Header：`X-User-ID: demo_user`

响应：

```json
{
  "code": 200,
  "message": "workflow started",
  "data": {
    "task_id": "TASK_20260526_001",
    "status": "AI_RUNNING"
  }
}
```

### 5.5 查询任务状态

阶段：MVP-0。

`GET /api/v1/reconcile/{task_id}/status`

Header：`X-User-ID: demo_user`

响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "task_id": "TASK_20260526_001",
    "status": "PENDING_HUMAN",
    "auto_fixed_rows": 4860,
    "ai_processed_rows": 104,
    "ai_retrying_rows": 2,
    "fallback_l2_rows": 8,
    "fallback_l3_rows": 3,
    "pending_human_rows": 16,
    "unresolved_rows": 3
  }
}
```

### 5.6 Agent 执行事件流

阶段：V1。

`GET /api/v1/reconcile/{task_id}/events`

协议：SSE。

事件示例：

```json
{
  "event_type": "RAG_RETRIEVED",
  "queue_id": 1024,
  "agent": "AuditAgent",
  "message": "命中跨日切处理规则（Hybrid Search + Reranker）",
  "payload": {
    "query_rewritten": "单边账 跨日切窗口 流水匹配失败 处理规则",
    "source": "rules/cutoff.md#跨日切单边账",
    "dense_score": 0.78,
    "bm25_score": 0.81,
    "reranker_score": 0.87,
    "final_score": 0.87
  }
}
```

Hook 状态事件：

```json
{
  "event_type": "HOOK_STATUS",
  "queue_id": 1024,
  "payload": {
    "pre_hooks": {
      "auth": "PASSED",
      "rate_limit": "PASSED (12/50)",
      "memory_injection": "PASSED (2 long-term + 8 short-term)",
      "validation": "PASSED",
      "cache": "MISS"
    },
    "post_hooks": {
      "schema": "PASSED (attempt 1)",
      "constraint": "PASSED",
      "fallback_level": 0
    }
  }
}
```

### 5.7 查询待复核列表

阶段：MVP-1。

`GET /api/v1/review/pending`

Header：`X-User-ID: demo_user`

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
        "exception_branch": "R004b",
        "risk_level": "MEDIUM",
        "ai_suggestion": "APPROVED_MATCH",
        "ai_confidence": 0.72,
        "ai_reason": "摘要疑似冲正原交易，但缺少明确原流水号，建议人工确认",
        "rag_sources": [
          {
            "source": "rules/reversal.md#冲正识别规则",
            "reranker_score": 0.86
          }
        ],
        "similar_historical_cases": 3,
        "historical_approve_rate": "80%"
      }
    ],
    "total": 16
  }
}
```

### 5.8 人工审批

阶段：MVP-1。

`POST /api/v1/review/{queue_id}/approve`

Header：`X-User-ID: demo_user`

请求：

```json
{
  "action": "APPROVED_MATCH",
  "handler_username": "demo",
  "remark": "人工核对原交易后确认可平账"
}
```

审批后的自动化操作：

- MySQL 事务更新台账状态。
- MVP-1 记录人工复核操作并更新台账状态。
- MVP-2 进一步更新 Redis 短期记忆、SQLite 长期记忆，并在累计满 20 笔时触发 Redis 摘要更新。

响应：

```json
{
  "code": 200,
  "message": "review submitted",
  "data": {
    "queue_id": 1024,
    "current_status": "FIXED",
    "memory_updated": {
      "short_term": true,
      "long_term": true
    }
  }
}
```

### 5.9 查询差错台账

阶段：MVP-0。

`GET /api/v1/ledger`

Header：`X-User-ID: demo_user`

查询参数：

- `task_id`
- `error_type`
- `exception_branch`
- `handle_status`
- `risk_level`
- `start_date`
- `end_date`
- `page`
- `page_size`

### 5.10 生成审计报告

阶段：V1。

`POST /api/v1/reports/{task_id}/generate`

Header：`X-User-ID: demo_user`

响应：

```json
{
  "code": 200,
  "message": "report generated",
  "data": {
    "task_id": "TASK_20260526_001",
    "report_id": 18,
    "format": "markdown",
    "summary": {
      "total_bank_rows": 5000,
      "total_clear_rows": 4996,
      "auto_fixed_rows": 4860,
      "ai_processed_rows": 104,
      "pending_human_rows": 16,
      "unresolved_rows": 3,
      "auto_fix_rate": "97.2%",
      "ai_audit_accuracy": "87.5%"
    }
  }
}
```

### 5.11 RAG 检索调试

阶段：MVP-0。

`POST /api/v1/rag/search`

请求：

```json
{
  "query": "23:55 发生的单边账如何处理",
  "top_k": 5,
  "enable_rewrite": true,
  "enable_hybrid": true
}
```

响应（MVP-2 版本，含混合检索细节）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "original_query": "23:55 发生的单边账如何处理",
    "rewritten_query": "单边账 跨日切窗口 日切时间 流水匹配失败 处理规则",
    "items": [
      {
        "source": "rules/cutoff.md#跨日切单边账",
        "dense_score": 0.78,
        "bm25_score": 0.81,
        "rrf_rank": 1,
        "reranker_score": 0.87,
        "final_score": 0.87,
        "content": "日切敏感窗口内产生的单边账，应优先追溯下一清算日流水。"
      }
    ],
    "search_meta": {
      "dense_candidates": 20,
      "sparse_candidates": 20,
      "after_fusion": 10,
      "after_rerank": 5,
      "above_threshold": 3
    }
  }
}
```

### 5.12 记忆查询（MVP-2 新增，调试用）

阶段：MVP-2。

`GET /api/v1/memory/{user_id}/context`

查询参数：

- `thread_id`
- `error_type`

响应：

```json
{
  "code": 200,
  "data": {
    "short_term_memory": {
      "recent_decisions": 12,
      "summary": "本批次以金额差异为主(60%)，其次为日切单边(25%)，冲正退款(10%)，手续费(5%)。前 12 笔中 10 笔自动平账，1 笔 Fallback L2，1 笔转人工。"
    },
    "long_term_memory": {
      "similar_cases": 5,
      "historical_pattern": "过去 5 次 AMOUNT_MISMATCH 类型异常中，人工确认平账 4 次，挂账 1 次。",
      "avg_confidence": 0.88
    }
  }
}
```

## 6. 数据库设计

所有业务表均包含 `user_id` 列用于多租户隔离。所有 SQL 查询在中间件层强制注入 `WHERE user_id = ?` 条件。

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

阶段：MVP-0。MVP-1 阶段补充 `batch_id` 和本地任务展示字段；MVP-2 阶段补充 Agent/Fallback 统计字段。

```sql
CREATE TABLE t_reconciliation_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  batch_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  task_name VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
  total_bank_rows INT NOT NULL DEFAULT 0,
  total_clear_rows INT NOT NULL DEFAULT 0,
  auto_fixed_rows INT NOT NULL DEFAULT 0,
  pending_ai_rows INT NOT NULL DEFAULT 0,
  ai_retrying_rows INT NOT NULL DEFAULT 0,
  fallback_l2_rows INT NOT NULL DEFAULT 0,
  fallback_l3_rows INT NOT NULL DEFAULT 0,
  pending_human_rows INT NOT NULL DEFAULT 0,
  unresolved_rows INT NOT NULL DEFAULT 0,
  total_llm_tokens INT NOT NULL DEFAULT 0,
  total_llm_cost DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_task (user_id, task_id),
  INDEX idx_user_batch (user_id, batch_id),
  INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.3 银行端流水表 `t_bank_transaction`

阶段：MVP-0。字段与 `mock_data/bank_transactions.xlsx` 保持一致，同时保留 `amount`、`trade_time`、`account_no_masked`、`customer_name_masked` 等标准化字段，便于后续基础匹配、差错台账和 Agent 上下文复用。MVP-1 阶段按 `task_id` 做 HASH 分区。

```sql
CREATE TABLE t_bank_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  flow_id VARCHAR(64),
  bank_serial_no VARCHAR(64),
  accounting_date DATE,
  accounting_time TIME,
  value_date DATE,
  self_account_no_masked VARCHAR(64),
  self_account_name_masked VARCHAR(128),
  self_bank_name VARCHAR(128),
  account_no_masked VARCHAR(64),
  customer_name_masked VARCHAR(128),
  counterparty_account_no_masked VARCHAR(64),
  counterparty_name_masked VARCHAR(128),
  counterparty_bank_name VARCHAR(128),
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  transaction_type VARCHAR(32),
  transaction_direction VARCHAR(16),
  amount DECIMAL(18,2) NOT NULL,
  debit_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  credit_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  fee_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  balance_after DECIMAL(18,2),
  trade_time DATETIME NOT NULL,
  channel VARCHAR(32),
  summary VARCHAR(255),
  purpose VARCHAR(128),
  posting_status VARCHAR(32),
  branch_no VARCHAR(32),
  teller_id VARCHAR(64),
  transaction_code VARCHAR(32),
  source_system VARCHAR(64),
  remark VARCHAR(255),
  match_status VARCHAR(32) DEFAULT NULL,
  matched_clear_id BIGINT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_flow (user_id, task_id, flow_id),
  INDEX idx_user_task_time (user_id, task_id, trade_time),
  INDEX idx_user_serial (user_id, bank_serial_no),
  INDEX idx_match_status (task_id, match_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY HASH (CRC32(task_id)) PARTITIONS 8;
```

### 6.4 清算端流水表 `t_clear_transaction`

阶段：MVP-0。字段与 `mock_data/clear_transactions.xlsx` 保持一致，同时保留标准化 `amount`、`trade_time`、`summary` 字段。MVP-1 阶段按 `task_id` 做 HASH 分区。

```sql
CREATE TABLE t_clear_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  flow_id VARCHAR(64),
  clearing_serial_no VARCHAR(64),
  merchant_id VARCHAR(64),
  merchant_name VARCHAR(128),
  store_name VARCHAR(128),
  terminal_id VARCHAR(64),
  channel VARCHAR(32),
  transaction_type VARCHAR(32),
  trade_date DATE,
  settlement_date DATE,
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  amount DECIMAL(18,2) NOT NULL,
  transaction_amount DECIMAL(18,2) NOT NULL,
  fee_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  net_amount DECIMAL(18,2) NOT NULL,
  trade_time DATETIME NOT NULL,
  status VARCHAR(32),
  summary VARCHAR(255),
  batch_no VARCHAR(64),
  voucher_no VARCHAR(64),
  reference_no VARCHAR(64),
  merchant_order_no VARCHAR(64),
  payer_account_no_masked VARCHAR(64),
  payer_name_masked VARCHAR(128),
  payee_account_no_masked VARCHAR(64),
  payee_name_masked VARCHAR(128),
  order_description VARCHAR(255),
  remark VARCHAR(255),
  match_status VARCHAR(32) DEFAULT NULL,
  matched_bank_id BIGINT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_flow (user_id, task_id, flow_id),
  INDEX idx_user_task_time (user_id, task_id, trade_time),
  INDEX idx_user_clearing_serial (user_id, clearing_serial_no),
  INDEX idx_user_merchant_order (user_id, merchant_order_no),
  INDEX idx_match_status (task_id, match_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY HASH (CRC32(task_id)) PARTITIONS 8;
```

### 6.5 待核验队列表 `t_reconciliation_queue`

阶段：MVP-0。MVP-1 阶段新增 `exception_branch`；MVP-2 阶段新增 `fallback_level`。

```sql
CREATE TABLE t_reconciliation_queue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  bank_transaction_id BIGINT NULL,
  clear_transaction_id BIGINT NULL,
  error_type VARCHAR(32) NOT NULL,
  exception_branch VARCHAR(32) DEFAULT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_AI',
  risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW',
  retry_count INT NOT NULL DEFAULT 0,
  fallback_level INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_task_status (user_id, task_id, status),
  INDEX idx_error_branch (error_type, exception_branch)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.6 差错台账表 `t_error_ledger`

阶段：MVP-0。MVP-1 阶段新增 `exception_branch` 和 `ai_confidence`；MVP-2 阶段新增 `rag_scores_json`、`fallback_path`。

```sql
CREATE TABLE t_error_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  error_type VARCHAR(32) NOT NULL,
  exception_branch VARCHAR(32) DEFAULT NULL,
  discrepancy_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  ai_cleaned_json JSON,
  ai_audit_opinion TEXT,
  ai_confidence DECIMAL(5,4) DEFAULT NULL,
  rag_scores_json JSON,
  rag_source VARCHAR(512),
  fallback_path VARCHAR(128) DEFAULT NULL,
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

### 6.7 人工复核表 `t_human_review`

阶段：MVP-1。

```sql
CREATE TABLE t_human_review (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
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

### 6.8 Agent 执行日志表 `t_agent_execution_log`

阶段：MVP-1。MVP-2 版本新增 JSON 虚拟列索引。

```sql
CREATE TABLE t_agent_execution_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  queue_id BIGINT,
  agent_name VARCHAR(64) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  input_payload JSON,
  output_payload JSON,
  pre_hook_results JSON,
  post_hook_results JSON,
  rag_retrieval_id BIGINT,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_queue (user_id, task_id, queue_id),
  INDEX idx_agent_event (agent_name, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- MVP-2: 对 output_payload 中的高频查询字段建虚拟列索引
ALTER TABLE t_agent_execution_log
  ADD COLUMN v_decision VARCHAR(32)
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(output_payload, '$.decision'))) VIRTUAL,
  ADD INDEX idx_v_decision (v_decision);

ALTER TABLE t_agent_execution_log
  ADD COLUMN v_risk_level VARCHAR(16)
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(output_payload, '$.risk_level'))) VIRTUAL,
  ADD INDEX idx_v_risk_level (v_risk_level);
```

### 6.9 RAG 检索记录表 `t_rag_retrieval_log`

阶段：MVP-0。MVP-2 阶段新增混合检索细节字段。

```sql
CREATE TABLE t_rag_retrieval_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  queue_id BIGINT,
  original_query TEXT NOT NULL,
  rewritten_query TEXT,
  top_k INT NOT NULL,
  dense_candidates INT DEFAULT 20,
  sparse_candidates INT DEFAULT 20,
  fusion_candidates INT DEFAULT 10,
  after_rerank INT DEFAULT 5,
  best_dense_score DECIMAL(8,4),
  best_reranker_score DECIMAL(8,4),
  sources JSON,
  selected_chunk_id VARCHAR(128),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_queue (user_id, task_id, queue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.10 审计报告表 `t_audit_report`

阶段：V1。

```sql
CREATE TABLE t_audit_report (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  report_format VARCHAR(16) NOT NULL DEFAULT 'markdown',
  report_content MEDIUMTEXT NOT NULL,
  report_metrics JSON,
  created_by VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_task (user_id, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.11 规则命中和效果统计表 `t_rule_hit_stats`（V2 新增）

阶段：V2。

用于记录每条 YAML 规则的命中次数和处理准确率，支撑规则优化。

```sql
CREATE TABLE t_rule_hit_stats (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rule_id VARCHAR(16) NOT NULL,
  rule_name VARCHAR(128) NOT NULL,
  hit_count INT NOT NULL DEFAULT 0,
  auto_resolved_count INT NOT NULL DEFAULT 0,
  agent_processed_count INT NOT NULL DEFAULT 0,
  human_review_count INT NOT NULL DEFAULT 0,
  avg_processing_time_ms INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_rule_id (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## 7. 记忆引擎与上下文管理设计

阶段：MVP-2。

记忆引擎是 Agent 从“无状态调用”升级为“有状态决策”的核心模块。MVP-1 只记录人工复核历史，不注入 Agent 上下文；MVP-2 再引入短期、长期和摘要三层记忆。详见 `overall-architecture.md` 2.6 节。

### 7.1 三层记忆模型

| 记忆层 | 作用域 | 存储 | 数据结构 | TTL | 更新触发 |
|--------|-------|------|---------|-----|---------|
| 短期记忆 | 本任务（thread_id） | Redis | Sorted Set（按时间排序） | 任务结束 + 24h | 每次 Agent 决策后 |
| 长期记忆 | 跨任务（user_id） | SQLite | 结构化表 | 永久 | 人工确认后 |
| 摘要记忆 | 本任务（thread_id） | Redis | String | 任务结束 + 24h | 每 20 笔触发 LLM 压缩 |

### 7.2 Context Window 组装

```text
┌─────────────────────────────────────────────┐
│ System Prompt（约 500 token）                  │
├─────────────────────────────────────────────┤
│ Long-term Memory（约 800 token，SQLite 检索）   │
├─────────────────────────────────────────────┤
│ Short-term Memory（约 600 token，Redis 读取）   │
├─────────────────────────────────────────────┤
│ Summary Buffer（约 300 token，仅当 > 20 笔时）  │
├─────────────────────────────────────────────┤
│ RAG Context（约 1000 token，混合检索 + Rerank） │
├─────────────────────────────────────────────┤
│ Current Item（约 400 token）                   │
├─────────────────────────────────────────────┤
│ Tool Results（约 500 token）                   │
└─────────────────────────────────────────────┘
```

### 7.3 记忆管理器接口

```python
class MemoryManager:
    def __init__(self, redis_client, sqlite_path):
        self.short_term = RedisShortTermMemory(redis_client)
        self.summary = RedisSummaryMemory(redis_client)
        self.long_term = SQLiteLongTermMemory(sqlite_path)

    async def build_context(
        self,
        user_id: str,
        thread_id: str,
        error_type: str,
        current_item: dict,
        rag_context: list,
        tool_results: dict,
    ) -> str:
        """组装完整的 Context Window 文本"""
        ...

    async def update_after_decision(
        self,
        user_id: str,
        thread_id: str,
        error_type: str,
        decision: dict,
        is_human_confirmed: bool = False,
    ):
        """Agent 决策/人工确认后更新记忆"""
        ...
```

### 7.4 摘要压缩质量验证

摘要记忆每 20 笔触发 LLM 压缩时，存在关键信息丢失的风险（如遗漏某笔 HIGH 风险交易的处理结果）。压缩质量需要可验证。

- 压缩前保存：触发压缩时，将待压缩的 20 条原始记录写入临时快照（JSON）。
- 压缩后校验：对压缩后的摘要文本做关键字段回检——
  - 所有 `risk_level = HIGH` 的条目是否在摘要中被提及。
  - 所有 `decision = PENDING_HUMAN` 的条目是否保留。
  - 摘要中包含的 flow_id 数量是否 >= 原始条数的 80%（允许低风险条目被合并概括）。
- 校验失败：丢弃本次压缩结果，保留原始记录，记录 WARNING 日志。
- MVP-2：实现快照保存和高风险条目回检；校验失败时降级为不压缩（保留全量记录）。
- V1：增加压缩前后语义相似度评分（Embedding cosine similarity），低于阈值则告警。

## 8. Hook 链与硬约束设计

阶段：MVP-2。

Hook 链是保证 Agent 安全、质量和可追溯性的门禁系统。MVP-1 先通过普通 service 校验和本地 trace 保证主链路可演示；MVP-2 再把权限、校验、约束、日志和事务写入沉淀为统一 Hook 链。详见 `overall-architecture.md` 2.5 节。

### 8.1 Pre-Hook 链

| 序号 | Hook | 职责 | 失败策略 |
|------|------|------|---------|
| ① | AuthHook | JWT 校验、user_id 与 task_id 归属校验、角色权限校验 | 返回 403 |
| ② | RateLimitHook | Redis Sliding Window 单用户频率控制 | 返回 429 |
| ③ | MemoryHook | 调用 MemoryManager.build_context() 组装上下文 | 降级（跳过记忆，仅用 System Prompt） |
| ④ | ValidationHook | 输入数据完整性、金额精度、必填字段校验 | 返回 400 |
| ⑤ | CacheHook | 检查同一 queue_id 是否已处理 | 命中返回缓存结果 |

### 8.2 Post-Hook 链

| 序号 | Hook | 职责 | 失败策略 |
|------|------|------|---------|
| ⑥ | SchemaHook | Pydantic model_validate 校验 JSON 输出 | 重试（最多 3 次）→ 转人工 |
| ⑦ | ConstraintHook | 硬约束校验（金额-风险一致性、evidence 非空、枚举合法） | 转人工（不重试） |
| ⑧ | DecisionHook | 按置信度路由（直接落库 / 二级 Fallback / 三级 Fallback / 转人工） | 路由到对应分支 |
| ⑨ | MemoryUpdateHook | Redis ← 短期记忆 + SQLite ← 长期记忆（仅人工确认） | 非阻塞日志 |
| ⑩ | LogHook | MySQL + structlog + LangFuse 写入 | 非阻塞日志 |
| ⑪ | TransactionHook | MySQL 事务写入台账 + 队列更新 + 任务统计更新 | 回滚 + 标记 FAILED |

### 8.2.1 Hook 熔断机制

当 Hook 依赖的外部服务（如 Redis、ChromaDB）不可用时，如果每个请求仍然尝试连接、等待超时、再降级，会导致整体延迟飙升。熔断机制确保失败快速传播，保护系统资源。

- 每个依赖外部服务的 Hook 维护一个熔断状态机：**CLOSED（正常） → OPEN（熔断） → HALF_OPEN（探测）**。
- 连续失败 N 次（默认 5 次）后进入 OPEN 状态，直接跳过该 Hook 并记录日志，不再尝试连接外部服务。
- OPEN 状态持续一段时间后（默认 30s），自动进入 HALF_OPEN，允许下一次请求尝试连接。
  - 尝试成功：恢复 CLOSED 状态。
  - 尝试失败：回到 OPEN 状态，等待下一个探测窗口。
- 熔断事件必须记录在 Agent 执行日志中，包含：Hook 名称、触发时间、失败原因、当前状态。
- MVP-2 实现 MemoryHook（Redis）和 RAG Subgraph（ChromaDB）的熔断器。
- V1 扩展至所有 Pre/Post Hook。

### 8.3 硬约束规则

| 约束 | 描述 | 实现 |
|------|------|------|
| C1 | `decision` 必须在枚举值 {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED} 内 | Pydantic Literal |
| C2 | `evidence` 不能为空列表 | Pydantic field_validator |
| C3 | `|diff| > 10000` 时 `risk_level` 不能为 LOW | 自定义 ConstraintValidator |
| C4 | `decision = PENDING_HUMAN` 时 `reason` 必须说明依据不足的具体原因 | 自定义 ConstraintValidator |
| C5 | `decision = AUTO_FIXED` 时 `confidence` 必须 >= 0.85 | 自定义 ConstraintValidator |
| C6 | RAG 无命中（best_score < 0.5）时禁止 `decision = AUTO_FIXED` | 自定义 ConstraintValidator |

## 9. Agent 工作流设计

### 9.1 全局状态

```python
from typing import Any, Dict, List, Optional, TypedDict

class ReconciliationState(TypedDict):
    task_id: str
    user_id: str
    thread_id: str
    current_queue_id: Optional[int]
    bank_item: Dict[str, Any]
    clear_item: Dict[str, Any]
    error_type: Optional[str]
    exception_branch: Optional[str]
    math_result: Dict[str, str]
    extraction_result: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    long_term_memory: List[Dict[str, Any]]
    short_term_memory: List[Dict[str, Any]]
    summary_buffer: Optional[str]
    audit_decision: Dict[str, Any]
    confidence: Optional[float]
    retry_count: int
    fallback_level: int
    next_action: str
    error_message: Optional[str]
    agent_logs: List[Dict[str, Any]]
```

### 9.2 节点定义

| 节点 | 类型 | 职责 | 阶段 |
| --- | --- | --- | --- |
| `AuthCheckNode` | Hook | JWT 校验、user_id 归属校验、角色权限校验 | MVP-2 |
| `PreCheckNode` | 确定性代码 | 基础匹配、字段校验、规则引擎、异常分支路由 | MVP-0/MVP-1 |
| `ExtractionAgent` | LLM Agent | 模糊摘要结构化 | MVP-2 |
| `AuditAgent` | LLM Agent | 基于 RAG、记忆和工具结果做结构化审计建议 | MVP-0 |
| `TraceAgent` | LLM + Tool | 跨日切、冲正、退款链路追溯 | V2 |
| `HumanReviewNode` | 状态节点 | MVP-1 提供人工复核记录；MVP-2 支持 Checkpoint 挂起/恢复 | MVP-1/MVP-2 |
| `ReportAgent` | LLM + Tool | 生成审计摘要和报告（数据来自 SQL 聚合） | V1/V2 |

### 9.3 并行执行

```text
PreCheckNode (ExceptionRouter)
    │
    ├── extraction_needed?
    │     └──> ExtractionAgent ──────────┐
    │                                    ├──> AuditAgent
    └── rag_needed?                      │
          └──> RAG Subgraph ─────────────┘
                    │
                    ├─ Query Rewrite Node
                    ├─ Dense Retrieval Node ──┐
                    ├─ BM25 Retrieval Node ───┤ (并行)
                    ├─ RRF Fusion Node ───────┘
                    ├─ Reranker Node
                    └─ Filter Node
```

### 9.4 状态流转

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

MVP-1 状态流转：

```text
START
  -> 上传并解析双端 Excel
  -> YAML RuleEngine + ExceptionRouter 匹配 5 个核心分支
  -> 规则可处理项写入台账
  -> 规则无法确认项写入人工复核队列
  -> 人工复核页提交处理动作
  -> 事务更新差错台账、复核记录和任务统计
  -> 本地 JSON trace 记录规则命中、RAG 命中、Agent 输出和人工动作
  -> END
```

MVP-2 及后续状态流转：

```text
START
  -> AuthCheckNode（权限校验）
  -> PreCheckNode（规则引擎 + 异常分支路由）
  -> [ExceptionRouter 分发到 12 类分支]
  -> [并行] ExtractionAgent + RAG Subgraph（如需要）
  -> AuditAgent 生成审计判断
  -> Post-Hook 链校验
  -> confidence >= 0.85 → 写入台账
  -> confidence < 0.85 → Fallback L2（换 Prompt 角度重试）
  -> confidence 仍 < 0.85 → Fallback L3（查长期记忆和人工历史；V2 由 TraceAgent 增强）
  -> confidence 仍 < 0.85 或 RAG 无命中 → HumanReviewNode（Checkpoint 挂起）
  -> 人工审批完成 → 恢复执行 → MemoryUpdateHook → END
```

### 9.5 Agent 输出约束

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
  "risk_level": "MEDIUM",
  "confidence": 0.72,
  "reason": "疑似冲正交易，摘要关键词匹配但未检索到明确原流水号，Fallback L2 后仍低于阈值",
  "evidence": [
    {
      "source_type": "project_rule",
      "source": "rules/reversal.md#冲正识别规则",
      "dense_score": 0.71,
      "reranker_score": 0.82
    }
  ],
  "fallback_applied": true,
  "fallback_level": 2,
  "next_action": "HUMAN_REVIEW"
}
```

### 9.6 错误处理

| 场景 | 处理策略 |
|------|---------|
| JSON 解析失败 | 重试 3 次（每次调整 Prompt 温度），仍失败 → 转人工 |
| RAG 无命中 | 直接转人工，**不触发 Fallback**（无依据不可判断） |
| RAG 命中但分数偏低 | 进入 Fallback L2（换角度重试），仍低 → 转人工 |
| 工具调用失败 | 记录日志 → 转人工 |
| 数据库事务失败 | 回滚 → 标记任务 FAILED → 保留输入数据 |
| Schema 校验失败 | 重试 3 次 → 转人工 |
| 硬约束校验失败 | 直接转人工（不重试，业务规则不应被绕过） |
| 速率限制触发 | 返回 429 → 前端提示用户稍后重试 |

### 9.6.1 Fallback 分级策略

多级 Fallback 不是简单的“重试”，每一级有不同的 Prompt 策略和信息增量，确保逐级为 Agent 提供更多判断依据。

| 级别 | 策略 | Prompt 变化 | 新增信息 |
|------|------|------------|---------|
| L1（默认） | 标准审计 Prompt | 系统 Prompt + 当前异常项 + RAG 规则原文 | — |
| L2（增强） | Few-shot 注入 | 在 Prompt 中追加 2-3 个同类异常的历史人工确认案例 | 短期记忆中的同类处理记录 |
| L3（追溯） | TraceAgent 深度查询 | 追加跨日切流水查询、原交易追溯、冲正链路校验结果 | Tool 返回的关联流水和追溯链 |

Fallback 触发条件：

- L1 输出 `confidence < 0.85` 或 RAG `best_score < 0.5` → 进入 L2。
- L2 输出 `confidence < 0.85` → 进入 L3。
- L3 输出 `confidence < 0.85` 或 RAG 无命中 → 转人工复核。
- 任意级别抛出异常 → 记录日志，直接转人工（不跨级重试）。

MVP-2 实现 L1 + L2；L3 待 V1 TraceAgent 完成后接入。

## 10. 异常分支网络设计

系统不是简单的“对上了/没对上”二元判断，而是通过声明式规则引擎和异常分支覆盖真实银行对账中的各类差错场景。MVP-1 先覆盖 5 个核心分支，确保本地产品闭环可演示；MVP-2 再扩展到完整 12 个分支并接入 Agent 工作流。

### 10.1 YAML 规则示例

```yaml
rules:
  # ── 金额差异类 ──
  - id: R001
    name: 手续费分离检测
    priority: 1
    conditions:
      - field: amount_diff
        operator: in_set
        value: [0.50, 1.00, 2.00, 5.00, 10.00, 100.00]
      - field: flow_id
        operator: matched
    action: PENDING_AI
    error_type: SUSPECTED_FEE_DIFF
    exception_branch: FEE_DIFF
    agent_type: AuditAgent
    rag_query: "手续费差异处理规则"

  - id: R002
    name: 疑似重复入账
    priority: 2
    conditions:
      - field: amount_ratio
        operator: is_integer_multiple
      - field: customer_name
        operator: same
    action: PENDING_AI
    error_type: SUSPECTED_DUPLICATE
    exception_branch: DUPLICATE
    agent_type: TraceAgent

  - id: R003
    name: 流水号匹配但金额不一致
    priority: 3
    conditions:
      - field: amount_diff
        operator: neq
        value: 0
      - field: flow_id
        operator: matched
    action: PENDING_AI
    error_type: AMOUNT_MISMATCH
    exception_branch: AMOUNT_MISMATCH
    agent_type: AuditAgent

  # ── 单边缺失类 ──
  - id: R004
    name: 日切窗口单边检测
    priority: 4
    conditions:
      - field: trade_time
        operator: in_range
        value: ["22:00", "24:00"]
      - field: match_status
        operator: eq
        value: SINGLE_SIDE
    action: PENDING_AI
    error_type: CUTOFF_SINGLE_SIDE
    exception_branch: CUTOFF
    agent_type: TraceAgent

  - id: R005
    name: 非日切单边缺失
    priority: 5
    conditions:
      - field: match_status
        operator: eq
        value: SINGLE_SIDE
      - field: trade_time
        operator: not_in_range
        value: ["22:00", "24:00"]
    action: PENDING_HUMAN
    error_type: SINGLE_SIDE_MISSING
    exception_branch: SINGLE_SIDE

  # ── 语义类 ──
  - id: R006
    name: 冲正退款关键词检测
    priority: 6
    conditions:
      - field: summary
        operator: contains_any
        value: ["冲正", "撤销", "退款", "抹账", "冲销", "作废"]
    action: PENDING_AI
    error_type: FUZZY_REVERSAL
    exception_branch: REVERSAL
    agent_type: ExtractionAgent
    need_rag: true
    rag_query: "冲正退款识别规则"

  # ── 模糊匹配类 ──
  - id: R007
    name: 金额日期对方户名相似
    priority: 7
    conditions:
      - field: amount_diff
        operator: eq
        value: 0
      - field: trade_date
        operator: same_day
      - field: counterparty_similarity
        operator: gte
        value: 0.7
    action: PENDING_AI
    error_type: SOFT_MATCH_CANDIDATE
    exception_branch: SOFT_MATCH
    agent_type: AuditAgent

  # ── 兜底 ──
  - id: R999
    name: 未知异常（兜底）
    priority: 99
    conditions: []
    action: PENDING_AI
    error_type: UNKNOWN_ANOMALY
    exception_branch: UNKNOWN
    agent_type: AuditAgent
    confidence_threshold: 0.85
    rag_query: "基础对账规则"
```

### 10.2 ExceptionRouter

```python
class ExceptionRouter:
    async def route(
        self, bank_item: dict, clear_item: dict, diff: Decimal
    ) -> RouteResult:
        """
        按 YAML 规则优先级逐一匹配，返回命中的分支和处理策略。
        确定性规则可覆盖的分支直接处理，无法覆盖的才进入 Agent 链路。
        """
        for rule in self.rule_engine.rules_sorted_by_priority:
            if rule.matches(bank_item, clear_item, diff):
                return RouteResult(
                    rule_id=rule.id,
                    exception_branch=rule.exception_branch,
                    action=rule.action,
                    agent_needed=rule.action == "PENDING_AI",
                    agent_type=rule.agent_type,
                    rag_query=rule.rag_query,
                    confidence_threshold=rule.confidence_threshold or 0.85,
                )
```

### 10.3 规则引擎核心接口

```python
class RuleEngine:
    def __init__(self, rules_yaml_path: str):
        self.rules = self._load_rules(rules_yaml_path)

    def _load_rules(self, path: str) -> list[Rule]:
        """程序启动时加载 YAML 规则文件，解析为 Rule 对象列表"""

    def match(self, bank_item, clear_item, diff) -> Optional[Rule]:
        """按优先级逐一匹配，返回第一个命中的规则"""

    def get_stats(self) -> dict:
        """返回各规则的命中统计（来自 t_rule_hit_stats）"""
```

### 10.4 规则版本管理

YAML 规则文件会随业务场景扩展而迭代。规则变更需要有版本标识和变更历史，确保任何一次对账任务都可以追溯到所使用的规则版本。

- 规则文件头部包含 `version` 字段（如 `version: "1.0.0"`）。
- `t_reconciliation_task` 表记录 `rule_version`，每次任务启动时写入。
- `t_rule_hit_stats` 表按 `rule_id + rule_version` 维度统计命中率，支撑规则优化。
- 规则变更时需在文件头部 `changelog` 字段中记录变更摘要。
- MVP-1：规则文件头部加 `version` 字段 + `t_reconciliation_task.rule_version`。
- MVP-2：`t_rule_hit_stats` 按版本统计。
- V2：规则 A/B 对比框架借用版本字段进行效果对比。

### 10.5 规则冲突检测

ExceptionRouter 按优先级逐一匹配，第一个命中即返回。当两个规则同优先级且条件存在重叠时，匹配结果取决于 YAML 文件中的声明顺序，行为不稳定。

- 加载时检测：`RuleEngine._load_rules()` 完成后，对同 priority 的规则两两检查条件是否可能存在交集。
- 检测到潜在冲突时：记录 WARNING 级别日志，列出冲突规则 ID 和重叠条件。
- 运行时不阻塞：冲突检测仅作为告警，不影响匹配执行（以免误报阻断流程）。
- MVP-1：实现同优先级规则的条件重叠检测和日志告警。
- MVP-2：支持在规则文件中显式声明 `override: true` 标记有意覆盖的场景。

## 11. RAG 工作流设计

MVP-0 使用 Markdown 规则文档 + ChromaDB Top-K 检索证明 RAG 依据链路成立；MVP-2 再引入 Query Rewrite、Hybrid Search、RRF 和 Reranker。V1 阶段补齐系统性 RAG 评测集和指标报告。

### 11.1 增强 RAG 流程

```text
规则文档 Markdown/PDF
  -> 文档清洗
  -> 结构化切片（按 ## 标题 + 语义边界混合策略，min_chunk=200, max_chunk=800）
  -> Dense 向量化（BGE-large-zh-v1.5）+ BM25 稀疏索引（jieba 分词）
  -> 存入 ChromaDB（同时存储 dense vector 和 sparse metadata）
  -> 用户/Agent 输入自然语言查询
  -> Query Rewrite（LLM 把自然语言映射为规则术语）
  -> 双路召回：Dense Top-20 + BM25 Top-20（并行执行）
  -> RRF（Reciprocal Rank Fusion）融合排序，取 Top-10
  -> Cross-Encoder Reranker（BGE-Reranker-v2-m3）精排，取 Top-5
  -> Dense Score 阈值过滤（>= 0.5）+ Reranker Score 阈值过滤（>= 0.3）
  -> 返回 rag_context 给 AuditAgent
  -> 保存 rag_source、检索分数、Reranker 分数和最终使用的 chunk
```

### 11.2 Query Rewrite 设计

```text
输入: "这笔流水为什么没对上"
输出: "单边账 跨日切窗口 流水匹配失败 处理规则"

输入: "这个退款要怎么处理"
输出: "冲正交易 退款 反向抹账 原流水追溯 识别规则"

输入: "差了两块钱是什么情况"
输出: "手续费差异 金额不一致 渠道费 批量业务规则"
```

Prompt 设计：

```text
你是一个银行对账领域的查询改写助手。将用户输入的自然语言查询改写为规则检索关键词。

要求：
1. 输出由空格分隔的关键词，不要输出完整句子。
2. 将口语化表达映射为标准业务术语：
   - "没对上" → "流水匹配失败 单边账"
   - "退款" → "冲正交易 退款 反向抹账"
   - "少钱/多钱" → "金额差异 金额不一致"
   - "跨天" → "跨日切 T+1"
3. 保留原查询中的关键实体（如金额、日期、流水号）。
4. 不要添加规则文档中不存在的新概念。
```

### 11.3 RAG 评测体系

阶段：MVP-2 准备评测集骨架（每分支 3 条，共 36 条），V1 扩充至完整评测集并系统化运行。

评测集规模按阶段递进：

| 阶段 | 评测集规模 | 覆盖范围 | 用途 |
|------|-----------|---------|------|
| MVP-2 | 36 条（12 分支 × 3 条） | 所有异常分支 | 验证 RAG 检索基本可用，发现明显缺陷 |
| V1 | 120-180 条（12 分支 × 10-15 条） | 所有分支 + 边界 case | 评测脚本输出 Recall@5/MRR/NDCG@5，支撑简历量化指标 |
| V2 | 200+ 条 | 含对抗样本和长尾分支 | A/B 对比、Reranker/Embedding 模型选型 |

评测指标与运行方式：

- 指标：Recall@5、MRR、NDCG@5。
- 运行方式：每次调整切片策略、检索参数或 Embedding 模型后，运行评测脚本。
- 输出：Markdown 表格 + JSON 详细结果（含每个 query 的命中详情）。

```text
评测脚本: scripts/eval_rag.py
评测集: data/rag_eval_set.json

输出示例 (V1 目标):
  Recall@5:  >= 0.85
  MRR:       >= 0.70
  NDCG@5:    >= 0.78
```

### 11.4 兜底策略

| 场景 | Dense Score | Reranker Score | 策略 |
|------|------------|---------------|------|
| 命中且高分 | >= 0.7 | >= 0.7 | Agent 可直接引用 |
| 命中但边缘 | >= 0.5 | >= 0.3 | Agent 可引用但提高 confidence 阈值 |
| 命中但低分 | < 0.5 或 | < 0.3 | Fallback L2（换角度重试） |
| 无命中 | — | — | 直接转人工，**不触发 Fallback** |

## 12. 数据来源与审计依据设计

### 12.1 数据来源原则

本项目不使用真实银行流水、真实客户信息或银行内部制度。所有演示数据均为项目人工构造的模拟数据，字段结构和异常模式来自银行对账业务抽象。

数据设计需要同时满足三点：

- **安全合规**：姓名、账号、流水号、金额、摘要均为虚构或脱敏样式。
- **业务可信**：样本覆盖真实对账中常见的差错模式。
- **结果可复现**：每类样本都有明确的预期识别结果，方便测试和演示。

### 12.2 模拟数据类型

MVP-0 阶段至少准备两类 Excel：

- 银行端流水：模拟银行核心、网银或柜面系统中的入账/出账流水。
- 清算端流水：模拟清算平台、第三方支付渠道或批量业务系统中的清算流水。

样本场景按阶段扩展：

| 场景 | 说明 | 预期异常分支 | 阶段 |
| --- | --- | --- | --- |
| 正常平账 | 双端流水号、金额、日期可匹配 | — | MVP-0 |
| 基础金额差错 | 流水可匹配但金额不一致 | AMOUNT_MISMATCH | MVP-0 |
| 单边缺失 | 一端存在流水，另一端缺失 | SINGLE_SIDE_MISSING | MVP-0 |
| 跨日切单边 | 日切窗口内当天单边，T+1 出现补记 | CUTOFF_SINGLE_SIDE | MVP-1 |
| 冲正/退款/反向抹账 | 摘要不规范，需要语义结构化 | FUZZY_REVERSAL | MVP-1 |
| 疑似重复入账 | 同客户同金额时间差 < 5min | SUSPECTED_DUPLICATE | MVP-1 |
| 手续费差异 | 金额差恰好等于标准手续费 | SUSPECTED_FEE_DIFF | V1 |
| 批量业务部分失败 | 金额差为单笔金额的整数倍 | SUSPECTED_DUPLICATE | V1 |
| 跨渠道疑似重复 | 同客户同金额不同渠道 | CROSS_CHANNEL_DUPLICATE | V2 |
| 漏记账 | 一端有流水另一端完全无记录 | SINGLE_SIDE_MISSING | V2 |
| 多币种差异 | 不同币种精度差异导致的尾差 | AMOUNT_MISMATCH | V2 |

### 12.3 审计依据来源

审计依据由三层组成。

第一层是公开制度依据：

- 中国人民银行《支付结算办法》
- 中国人民银行《人民币银行结算账户管理办法》
- 财政部《会计基础工作规范》
- 财政部等五部委《企业内部控制基本规范》
- 财政部、国家档案局《会计档案管理办法》

第二层是项目自定义业务规则（Markdown/YAML 格式，标注为演示规则）。

第三层是 Agent/RAG 运行证据，包括 RAG 命中的规则来源、Dense/Reranker 分数、Agent 输出 JSON、Fallback 路径、人工复核记录和差错台账记录。

## 13. 报表审计设计

### 13.1 报表指标

报告需要包含：

- 任务编号、对账日期、处理用户。
- 银行端总笔数 / 清算端总笔数 / 总金额。
- 自动平账笔数 / 自动平账率。
- AI 审计笔数 / Agent 审计准确率。
- 各 Fallback 层级触发笔数。
- 人工复核笔数 / 人工复核触发率。
- 挂账笔数 / 差错金额合计。
- 异常类型分布（按 exception_branch 维度）。
- 单笔平均处理时延（P50/P95/P99）。
- LLM Token 总消耗和估算成本。

### 13.2 ReportAgent 输入

```json
{
  "task_id": "TASK_20260526_001",
  "metrics": {
    "total_bank_rows": 5000,
    "total_clear_rows": 4996,
    "auto_fixed_rows": 4860,
    "auto_fix_rate": "97.2%",
    "ai_processed_rows": 104,
    "ai_audit_accuracy": "87.5%",
    "fallback_l2_rows": 8,
    "fallback_l3_rows": 3,
    "pending_human_rows": 16,
    "human_review_rate": "1.2%",
    "unresolved_rows": 3,
    "avg_processing_time_ms": 2300,
    "total_llm_tokens": 485000,
    "estimated_cost_cny": 2.43
  },
  "error_distribution": {
    "AMOUNT_MISMATCH": 40,
    "CUTOFF_SINGLE_SIDE": 32,
    "FUZZY_REVERSAL": 28,
    "SUSPECTED_FEE_DIFF": 20,
    "SUSPECTED_DUPLICATE": 12,
    "SOFT_MATCH_CANDIDATE": 4
  }
}
```

### 13.3 ReportAgent 输出

输出 Markdown 报告，包含：

- 本批次对账概览。
- 主要异常类型和异常分支分布。
- 高风险事项（risk_level=HIGH 的条目）。
- 人工复核建议。
- RAG 规则引用列表。
- RAG 检索质量摘要（平均 Reranker Score 等）。
- 后续处理建议。

统计数据必须来自 SQL 聚合（含物化视图），ReportAgent 只负责文字组织和解释，不做数据计算。

## 14. 量化指标体系

| 指标 | 含义 | 采集方式 | 目标口径 |
|------|------|---------|-----------|
| 自动平账率 | 规则引擎直接匹配的比例 | `t_reconciliation_task` 统计 | 演示数据目标 > 96% |
| Agent 审计准确率 | AuditAgent 建议被人工采纳的比例 | `t_human_review` 与 `ai_suggestion` 对比 | 人工标注样本目标 > 85% |
| RAG Recall@5 | 规则召回率 | 评测脚本自动计算 | 评测集目标 > 0.85 |
| RAG MRR | 平均倒数排名 | 评测脚本自动计算 | 评测集目标 > 0.70 |
| RAG NDCG@5 | 归一化折损累积增益 | 评测脚本自动计算 | 评测集目标 > 0.78 |
| 单笔平均处理时延 | PreCheck 到台账落库的总耗时 | structlog 日志统计 | 本地演示目标 < 3s |
| Agent Schema 符合率 | JSON 输出一次通过 Pydantic 校验的比例 | Post-Hook SchemaHook 计数器 | 测试集目标 > 92% |
| 人工复核触发率 | 所有异常中最终转人工的比例 | 状态统计 | 演示数据目标 < 2% |
| Fallback 触发率 | 触发二级及以上 Fallback 的比例 | Agent 日志 fallback_level 字段 | 演示数据目标 < 10% |
| Token 消耗/千笔 | 每千笔异常的平均 LLM Token 消耗（含重试和 Fallback） | LangFuse 聚合 | — |

指标展示原则：如果某个指标还没有评测脚本或日志采集支撑，只能在 README 中标注为“目标值”或“待评测”，不能写成已达到的系统结果。

## 15. 验收标准

### 15.1 MVP-0 验收标准

- 能准备并使用两份模拟 Excel：银行端流水和清算端流水。
- 能通过 FastAPI 上传两份 Excel，并生成对账任务。
- 能使用 Pandas 完成字段校验、数据清洗和标准化。
- 能通过基础规则识别自动平账交易和异常交易。
- 能至少识别基础金额差错和单边缺失两类异常。
- 能对异常交易执行 RAG 检索，并返回规则来源和相似度分数。
- AuditAgent 能输出结构化 JSON 审计建议（含 evidence 字段）。
- 能将任务、流水、异常和审计建议写入 MySQL。
- 能通过 API 查询任务状态，包括总笔数、自动平账数、异常数和处理状态。
- 能通过 API 查询差错明细，包括异常类型、差异金额、AI 审计建议和 RAG 来源。
- 能说明模拟数据来源、字段含义、覆盖场景和预期识别结果。
- AuditAgent 输出必须包含 evidence 字段，能追溯到项目规则或公开依据摘要。
- 能提供端到端演示脚本或命令序列，输出 task_id、任务统计、差错台账和 Agent evidence。
- 能覆盖最小负向测试：缺字段、金额非法、空文件或重复流水中的至少 3 类。
- 能通过 AuditAgent JSON Schema 校验测试。
- 能提供 5 条以内的 RAG smoke eval，证明核心查询能命中预期规则。
- 能输出单笔异常的本地 trace 样例，记录输入、RAG 命中、Agent 输出和落库结果。

### 15.2 MVP-1 验收标准

- 能通过 Vue 页面上传两份模拟 Excel。
- 能在任务看板查看对账任务和核心统计。
- 能在差错台账页筛选、分页并查看单笔异常详情。
- 能在人工复核页确认平账、强制挂账并填写人工备注。
- 能通过事务更新差错台账、复核记录和任务统计。
- YAML 声明式规则引擎可替换 MVP-0 的硬编码 if-else。
- ExceptionRouter 第一版能覆盖金额差错、单边缺失、跨日切单边、模糊冲正、疑似重复入账 5 个核心分支。
- 能处理跨日切单边账、模糊冲正、疑似重复入账样例。
- 前端仍使用手动刷新或轮询，不要求 SSE。
- 能记录 Agent 执行日志和本地 JSON trace。
- 多租户中间件第一版可工作，所有业务查询按 `user_id` 过滤。

### 15.3 MVP-2 验收标准

- 能通过 LangGraph 串联 AuthCheckNode、PreCheckNode、ExceptionRouter、ExtractionAgent、RAG Subgraph、AuditAgent 和 HumanReviewNode。
- Agent 并行执行（ExtractionAgent ∥ RAG Subgraph）。
- Hook 链 Pre/Post Processing 完整运行，至少包含 AuthHook、ValidationHook、SchemaHook、ConstraintHook、DecisionHook 和 LogHook。
- AuthHook 首节点权限校验。
- 记忆引擎最小版（Redis 短期 + SQLite 长期 + 摘要压缩）可工作。
- YAML 声明式规则引擎 + ExceptionRouter 扩展到 12 分支路由。
- RAG 混合检索（Dense + BM25 + RRF）可工作。
- Reranker 和 Query Rewrite 可开关，关闭后主链路仍能运行。
- AI 无法判断时进入多级 Fallback → HumanReviewNode → 人工复核流程。
- HumanReviewNode 支持 Checkpoint 挂起和恢复。
- structlog 结构化日志和本地 JSON trace 能记录 Hook、Fallback、RAG 和 Agent 输出。
- LangFuse 可作为可选集成，不作为 MVP-2 阻塞项。

### 15.4 V1 验收标准

- Docker Compose 可启动前端、后端、MySQL、Redis 和 ChromaDB。
- Celery/ARQ 后台异步对账任务。
- 支持 JWT 登录。
- Agent 执行过程通过 SSE 展示（含 Pre/Post Hook 状态、Fallback 层级）。
- 支持手续费/批量业务差异样例。
- 支持 Markdown 审计报告。
- RAG 评测集可用，输出 Recall@5/MRR/NDCG 数据。
- Agent Schema 符合性测试可运行。
- 量化指标仪表板可用。
- README 包含本地启动、部署说明和演示账号。
- 项目可部署到云服务器。
- MCP 协议工具层可作为加分项独立运行，不作为 V1 必须验收项。

### 15.5 V2 验收标准

- 支持重复入账和漏记账样例。
- RAG A/B 对比框架可运行。
- Agent 执行日志离线分析可用。
- 支持 Prompt 版本记录和效果对比。
- 支持 PDF 报告导出（含图表）。
- 能输出失败样本分析报告。
- 压力测试通过（单任务 50000 笔流水），并记录 P50/P95/P99、内存峰值和数据库写入耗时。
- 能输出失败样本分类：RAG 未命中、规则冲突、Agent JSON 失败、证据不足、人工推翻。
- 能完成基础安全验证：越权访问、user_id 隔离、日志脱敏、Prompt injection 基础防护。

## 16. 面试证据链

为了避免项目看起来只是文档设计，每个核心能力都需要对应一个可展示证据。

| 能力 | 证据形式 | 阶段 |
|------|---------|------|
| 规则对账 | 上传接口响应、任务统计、差错台账 SQL 查询结果 | MVP-0 |
| Agent 审计 | AuditAgent JSON 输出、evidence 字段、RAG 来源 | MVP-0 |
| MVP-0 演示闭环 | 端到端脚本输出、负向测试、RAG smoke eval、本地 trace 样例 | MVP-0 |
| RAG 检索 | 检索调试接口返回、命中 chunk、相似度分数 | MVP-0/MVP-2 |
| 本地产品闭环 | 上传页、任务看板、差错台账页、人工复核页截图 | MVP-1 |
| 人工复核 | 复核页面截图、人工审批记录、台账状态变化 | MVP-1 |
| YAML 规则引擎 | 规则文件、命中日志、ExceptionRouter 分支统计 | MVP-1/MVP-2 |
| Hook 链 | structlog 日志中的 pre_hook/post_hook 结果 | MVP-2 |
| 记忆引擎 | 同类异常历史记录查询、MemoryUpdate 日志 | MVP-2 |
| 可观测性 | LangFuse Trace 或本地 JSON trace 文件 | MVP-2/V1 |
| RAG 评测 | `reports/rag_eval.md` 和 `data/rag_eval_set.json` | V1 |
| Schema 测试 | Pytest 输出和失败样本 | V1 |
| 部署能力 | Docker Compose 启动截图、部署地址、README | V1 |
| 失败分析与压测 | 失败样本表、原因分类、压测报告、安全验证记录 | V2 |

## 17. 风险与边界

### 17.1 数据边界

- 只使用模拟数据和脱敏数据。
- 不使用真实客户数据。
- 不使用银行内部资料。
- 演示数据中的姓名、账号、流水号均为虚构或脱敏。
- 公开制度依据只作为项目规则设计参考，不直接等同于真实银行内部审计制度。
- 项目自定义规则必须明确标注为演示规则，不冒充银行内部制度。

### 17.2 AI 决策边界

- AI 不做金额计算（只读取工具返回的 READ-ONLY 结果）。
- AI 不直接修改账务状态（所有写入经 TransactionHook 和事务保障）。
- AI 不做最终金融决策（低置信度 + 无依据 + 高风险均转人工）。
- AI 只提供结构化分析、规则引用和处理建议。

### 17.3 安全与隔离边界

- 所有 API 请求必须携带 X-User-ID。
- 所有数据库查询由中间件强制注入 WHERE user_id 条件。
- 记忆检索（Redis + SQLite）按 user_id 隔离。
- LangGraph 会话状态按 thread_id 隔离。
- AuthHook 是 Pre-Hook 链的首节点，任何权限校验失败均不启动 Agent。

### 17.4 项目边界

本项目用于学习、开源展示和求职面试，不宣称可直接用于真实生产银行系统。真实生产系统还需要权限隔离、审计合规、灾备、压测、安全评估和更严格的数据治理。

## 18. 面试讲解线索

面试时可以按下面顺序讲：

1. **项目来源**：自己有银行柜员经历，知道对账、冲正、挂账和报表审计是实际存在的问题。
2. **业务抽象**：把银行对账拆成 12 个异常分支，覆盖金额差错、日切单边、冲正退款、手续费、重复漏记等场景。
3. **技术边界与硬约束**：金额计算由 Decimal 完成，AI 只读不写，四层硬约束保证门禁。
4. **Agent 设计**：用 LangGraph 把权限校验、预处理、提取、审计、追溯、人工复核和报表生成串成工作流，含并行执行和多级 Fallback。
5. **RAG 增强**：混合检索 + Reranker + Query Rewrite 全链路，配评测集和 Recall@5/MRR/NDCG 指标；如果还未跑评测，就明确说这是 V1 的验收目标。
6. **记忆引擎**：三层记忆（Redis 短期 + SQLite 长期 + LLM 摘要压缩），Agent 从无状态调用升级为有状态决策；实际效果通过人工确认样本和同类异常一致性来评估。
7. **Hook 链**：5 Pre-Hooks + 6 Post-Hooks，权限校验首节点 + 硬约束门禁 + 审计日志，满足银行安全合规要求。
8. **多租户隔离**：user_id + thread_id 双重隔离，API 中间件强制注入，银行多操作员环境的安全底线。
9. **MCP 协议**：工具层标准化解耦，Agent 通过标准协议调用外部能力。
10. **后端能力**：FastAPI、Pydantic、MySQL 事务 + 分区 + JSON 索引、SSE、JWT、Docker、Celery/ARQ 都在系统里有具体用途。
11. **数据和依据来源**：数据全部模拟，依据来自公开制度、项目自定义规则和 RAG 证据流，不使用真实客户数据或银行内部资料。
12. **分阶段实现**：MVP-0 验证后端最小 AI 对账闭环，MVP-1 做成本地可演示产品，MVP-2 补齐 Agent 工程化能力（含 LangGraph、Hook、Memory 和增强 RAG），V1 上线展示（含部署和评测体系），V2 做深度优化（含 A/B 对比、失败分析、安全验证和压测）。
13. **量化指标**：每个技术选择都对应采集口径和证据文件；未实测的数字只作为目标，不冒充生产结果。
