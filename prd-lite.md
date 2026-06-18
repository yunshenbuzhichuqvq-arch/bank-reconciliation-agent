# 银企对账 Agent · 系统 PRD(精简版)

> 本文是 `system-prd.md` 的精简版,范围收敛为**单场景银企对账 + 三阶段交付**,重心放在 Agent 工程而非全栈/运维。原文保留了完整的双场景、多租户、记忆引擎与 SLA 设计,本文不替代它。配套架构见 `architecture-lite.md`。

## 1. 文档信息

| 项 | 内容 |
| --- | --- |
| 项目名称 | 银企对账 Agent(多账源智能对账与审计辅助) |
| 项目类型 | 个人开源项目(求职作品) |
| 业务场景 | 银企对账:企业账簿 / ERP 明细 × 银行流水(单场景) |
| 核心抽象 | 通用双账源对账引擎(Source A 主账源 / Source B 对账账源)+ Scenario Profile,当前只落地 `BANK_ENTERPRISE` |
| 技术栈 | FastAPI、Vue 3、MySQL 8.0、LangGraph、RAG(ChromaDB)、Redis、Docker |
| LLM | DeepSeek V4 Pro(`deepseek-v4-pro`,preview;OpenAI 兼容接口;默认可切 Fake provider) |
| 阶段 | 阶段一 最小闭环 → 阶段二 Agent 工程做深 → 阶段三 作品化 |
| 数据边界 | 仅用模拟 / 脱敏数据,不用真实客户数据或银行内部资料 |

## 2. 产品概述

帮助财务 / 对公人员在大批量银行流水核对中降低耗时、快速定位差异、减轻人工复核压力,处理双账源流水差异、单边缺失、跨期入账、手续费 / 税费差异、重复记账、人工复核和审计报告。

架构组合:**确定性代码 + YAML 规则引擎 + Agent(LangGraph)+ RAG + 输出校验管线 + Human-in-the-Loop**。确定性代码负责解析、字段映射、金额计算和事务;规则引擎把异常分发到处理分支;Agent(DeepSeek V4 Pro)负责摘要结构化和审计判断;RAG(混合检索 + Reranker + Query Rewrite)提供规则依据和审计溯源;输出校验管线作为护栏;Human-in-the-Loop 在金融风险场景保留人工确认。

## 3. 范围与三阶段规划

围绕**同一条银企对账主链路**逐层加厚,每阶段都有可验收产物。当前进度标注于 2026-06-17。

### 阶段一 · 最小闭环  ✅ 基本完成

从模拟 Excel 到差错台账的后端主链路 + 本地可演示页面。

- 模拟企业账簿 / 银行流水 Excel(覆盖正常平账、金额差错、单边缺失)。
- FastAPI 上传 → Pandas 清洗 / 字段校验 / 映射 → 三阶段匹配 → 异常识别。
- YAML 声明式规则引擎 + ExceptionRouter(核心分支)。
- **AuditAgent 真实 LLM 调用**:结构化 JSON 输出(decision / risk_level / reason / confidence / evidence)+ Schema 校验 + 有界重试 + 兜底转人工。
- 基础 RAG:Markdown 规则 + ChromaDB Top-K + 相似度阈值。
- MySQL 任务 / 流水 / 队列 / 台账落库;任务状态与差错明细查询 API。
- Vue:上传页 / 任务看板 / 差错台账页 / 人工复核页。
- 能打出一条完整本地 trace(规则命中 → RAG 命中 → Agent 输出 → 落库)。

**产物**:API + 数据库记录 + Agent/RAG JSON + 一条完整 trace + 本地页面。

### 阶段二 · Agent 工程做深  🔶 大部分完成

把"Agent 能判断"做成"Agent 可约束、可追踪、可评测"。

- **LangGraph 状态机 + 条件路由**:显式建模出错 / 低置信 / 工具失败 / 无依据分支。
- **ExtractionAgent 接入**:摘要 / 户名结构化。
- **三级 Fallback**:L1 标准 → L2 历史人工确认案例 few-shot → L3 可选追溯 / 换角度;RAG 无命中直接转人工。
- **增强 RAG**:Dense + BM25 + RRF + Cross-Encoder Reranker(默认轻量,可换 BGE)+ Query Rewrite(可开关)。
- **输出校验管线**:Schema 校验(+重试)→ 硬约束 C1–C6 → 决策/Fallback 路由 → 事务落库。
- **Prompt 独立文件 + 版本管理**;structlog 结构化日志覆盖所有 LLM 调用点。
- **工具调用权限边界**:L0 只读 / L1 结构化输出 / L2 禁止直写库。
- **RAG 评测集(真实 Recall@5/MRR)+ Agent 决策质量评估**(统计方法,不对 LLM 非确定性做严格一致性断言)。

**产物**:真实 LLM Agent 输出 + 增强 RAG trace + Fallback 日志 + 评测报告 + Prompt 版本对比。

### 阶段三 · 作品化  🚧 进行中

让作品"能跑、能看、能解释效果"。

- **Vue 工作台 + SSE**:实时展示 Agent 执行步骤、RAG 命中、Fallback 层级。
- **ARQ 异步任务队列**:上传即返回 task_id,Agent 后台异步执行(LLM 慢,不能阻塞请求)。
- **Redis**:LLM 结果缓存、API 限流、幂等去重。
- **量化指标小面板**:核心 Agent 指标可视化。
- **Docker Compose 一键启动**(无 Nginx,Docker 直接暴露端口)。
- (可选)最简 JWT 登录;(可选加分项)云服务器部署。

**当前状态**:工作台与指标盘可访问;**`start-live → events` 实时链路返回 404,主链路最后一步未通**;ARQ / Redis / JWT / Compose 未做。

> 进度口径:✅ 基本完成 / 🔶 大部分完成 / 🚧 进行中。未完成项不写成已达成结果。

## 4. 页面与交互

阶段一起建前端;鉴权用 `X-User-ID: demo_user` 模拟,阶段三可选 JWT。

| 页面 | 阶段 | 要点 |
|---|---|---|
| 账单上传页 | 一 | 上传 Source A / Source B Excel,展示字段校验与上传统计;格式 / 必填错误拒绝上传 |
| 任务看板 | 一 | 任务列表、自动平账率、待复核数、挂账数、异常分布;阶段三改 SSE 实时刷新 |
| 人工复核页 | 一 | 左 Source A / 右 Source B / 中 AI 推荐理由与 RAG 来源;确认平账 / 强制挂账 / 备注,事务更新台账 |
| 差错台账页 | 一 | 按任务 / 差错类型 / 风险 / 状态筛选分页;单笔详情含 AI 意见、RAG 来源、人工记录、trace 回放 |
| Agent 流式工作台 | 三 | SSE 展示当前流水、异常分支、RAG 检索详情(Dense/BM25/Reranker 分数)、决策与置信度、Fallback 层级 |
| 量化指标面板 | 三 | 自动平账率、Agent 采纳率、RAG Recall@5/MRR、Schema 符合率、人工复核率、token 成本趋势 |

## 5. 后端 API

统一返回 `{code, message, data}`,均带 `X-User-ID`(阶段三可选 JWT)。

| 接口 | 方法 | 阶段 | 说明 |
|---|---|---|---|
| `/reconcile/upload` | POST | 一 | 上传 `source_a_file` / `source_b_file` + `scenario_type`;阶段三改异步即时返回 task_id |
| `/reconcile/{task_id}/start` | POST | 一 | 启动对账工作流 |
| `/reconcile/{task_id}/status` | GET | 一 | 任务统计:总笔数、自动平账、AI 处理、Fallback、待人工 |
| `/reconcile/{task_id}/exceptions` | GET | 一 | 异常明细 |
| `/reconcile/{task_id}/events` | GET | 三 | SSE 事件流(Agent 步骤、RAG 命中、Fallback 层级) |
| `/review/pending` | GET | 一 | 待复核列表(含 AI 建议、RAG 来源、历史相似案例数) |
| `/review/{queue_id}/approve` | POST | 一 | 人工审批,事务更新台账与复核记录 |
| `/ledger` | GET | 一 | 差错台账查询(任务 / 差错类型 / 风险 / 状态 / 日期) |
| `/rag/search` | POST | 一 | RAG 检索调试(返回各路分数与融合细节) |
| `/reports/{task_id}/generate` | POST | 三 | 生成 Markdown 审计报告 |

> 已删除原 `/memory/{user_id}/context` 记忆查询接口(随记忆引擎一并移除)。

### upload 响应示例

```json
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

## 6. 数据库设计

标准建表 + 合理索引,**不使用 HASH 分区 / 物化视图 / JSON 虚拟列索引**。所有业务表带 `scenario_type`(预留多场景);若启用 JWT 则带 `user_id` 做行过滤。

| 表 | 阶段 | 关键字段 |
|---|---|---|
| `t_reconciliation_task` | 一 | task_id、scenario_type、status、各类行数统计、`fallback_l2_rows`、`total_llm_tokens` |
| `t_source_a_transaction` | 一 | task_id、flow_id、amount(DECIMAL)、trade_time、summary、match_status(企业账簿) |
| `t_source_b_transaction` | 一 | task_id、flow_id、amount(DECIMAL)、trade_time、summary、match_status(银行流水) |
| `t_reconciliation_queue` | 一 | task_id、error_type、`exception_branch`、status、risk_level、retry_count、`fallback_level` |
| `t_error_ledger` | 一 | queue_id、error_type、discrepancy_amount、ai_audit_opinion、ai_confidence、`rag_scores_json`、`fallback_path`、rag_source、handle_status |
| `t_human_review` | 一 | queue_id、ai_suggestion、ai_confidence、action、handler_username、remark |
| `t_agent_execution_log` | 二 | agent_name、event_type、input/output_payload(JSON)、`prompt_version`、`fallback_level`、`llm_tokens` |
| `t_rag_retrieval_log` | 一/二 | original/rewritten_query、dense/bm25/reranker 分数、sources(JSON)、selected_chunk_id |
| `t_user` | 三(可选) | username、password_hash、role(仅启用 JWT 时) |

> 已删除:三张记忆表(`t_short_term_memory` / `t_long_term_memory` / `t_summary_memory`)、规则命中统计表(`t_rule_hit_stats`)、审计报告表降为按需。

差错台账示例 DDL:

```sql
CREATE TABLE t_error_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  error_type VARCHAR(32) NOT NULL,
  exception_branch VARCHAR(32) DEFAULT NULL,
  discrepancy_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
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
  INDEX idx_task_error (task_id, error_type),
  INDEX idx_handle_status (handle_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## 7. Agent 工作流与输出约束

全局状态、节点定义、条件路由见 `architecture-lite.md` §4。主链路 2 个 Agent(ExtractionAgent + AuditAgent),TraceAgent 可选。

AuditAgent 输出:

```json
{
  "decision": "PENDING_HUMAN",
  "risk_level": "MEDIUM",
  "confidence": 0.72,
  "reason": "金额与入账日期一致,但摘要与户名不一致,Fallback L2 后仍低于阈值",
  "evidence": [
    { "source": "rag_knowledge/bank_enterprise/basic_matching.md#摘要与户名不一致",
      "dense_score": 0.71, "reranker_score": 0.82 }
  ],
  "fallback_applied": true, "fallback_level": 2,
  "next_action": "HUMAN_REVIEW"
}
```

### 错误处理

| 场景 | 策略 |
|---|---|
| JSON 解析失败 | 重试 ≤ 3 次(每次调 Prompt 角度),仍失败 → 转人工 |
| RAG 无命中 | 直接转人工,**不触发 Fallback** |
| RAG 命中但分数低 | 进 Fallback L2,仍低 → 转人工 |
| Schema / 硬约束校验失败 | Schema 重试;硬约束直接转人工(不重试) |
| 数据库事务失败 | 回滚 → 标记 FAILED → 保留输入 |
| DeepSeek API 不可用 | 熔断 → 降级为确定性规则 → 全部标记 PENDING_HUMAN |

## 8. 输出校验管线与硬约束

原 11 个 Pre/Post Hook 收敛为 **4 阶段管线**(详见 `architecture-lite.md` §5):

```text
Schema 校验(+有界重试) → 硬约束校验(C1–C6) → 决策/Fallback 路由 → 事务落库
```

- 鉴权:普通 API 中间件,不进管线。
- 限流 / 结果缓存:归 LLM 客户端封装层(Redis),不进管线。
- 事务写入独立为基础设施;副作用(日志)非阻塞、失败不影响主流程。

硬约束 C1–C6 见架构文档。

## 9. RAG 工作流

增强流程、Query Rewrite、无命中策略、评测见 `architecture-lite.md` §6。

评测集规模按阶段递进:

| 阶段 | 规模 | 用途 |
|---|---|---|
| 二 | ~50 条(核心分支 × 10) | 验证检索基本可用,发现明显缺陷 |
| 三 | 120+ 条 | 系统化输出 Recall@5/MRR/NDCG@5 量化指标 |

评测脚本 `scripts/eval_rag.py`,评测集 `data/rag_eval_set.json`。

## 10. 数据来源与审计依据

只用人工构造的模拟数据;字段结构对应企业账簿与银行流水,姓名 / 账号 / 流水号 / 金额 / 摘要均虚构或脱敏。

银企对账样本场景:

| 场景 | 预期异常类型 | 阶段 |
|---|---|---|
| 正常平账 | — | 一 |
| 基础金额差错 | AMOUNT_MISMATCH | 一 |
| 银行已到账企业未入账 | BOOK_UNRECORDED | 一 |
| 企业已记账银行未到账 | BANK_UNARRIVED | 一 |
| 摘要 / 客户名不一致 | NARRATIVE_NAME_MISMATCH | 二 |
| 疑似重复记账 | DUPLICATE_BOOKING | 二 |
| 手续费 / 税费差异 | FEE_TAX_DIFF | 二 |
| 跨期入账 | CROSS_PERIOD_POSTING | 二 |

审计依据三层:① 公开制度依据(人行支付结算、财政部会计基础规范等,仅作参考);② 项目自定义业务规则(Markdown/YAML,标注演示规则);③ 运行证据(RAG 命中来源、各路分数、Agent 输出 JSON、Fallback 路径、人工复核记录)。

## 11. 报表

按模板生成 Markdown 报告,统计数据来自 SQL 聚合,LLM 只做文字组织(可选),不做数据计算。报告含:本批次概览、异常类型分布、高风险事项、人工复核建议、RAG 引用列表、检索质量摘要。

## 12. 量化指标体系

只保留会真实测量的指标,每条标注**目标 / 实测**口径。未测量项只标"目标",不写成系统结果。

| 指标 | 采集方式 | 类型 |
|---|---|---|
| 自动平账率 | 任务统计表 | 实测(演示数据目标 > 95%) |
| Agent 审计采纳率 | 人工复核表 vs ai_suggestion | 目标 > 85%(需人工标注样本) |
| RAG Recall@5 / MRR | 评测脚本 | 实测(目标 R@5 ≥ 0.85 / MRR ≥ 0.70) |
| Agent Schema 一次通过率 | 校验管线计数 | 实测(目标 > 92%) |
| 人工复核触发率 | 状态统计 | 实测 |
| Fallback 触发率 | Agent 日志 fallback_level | 实测 |
| LLM token 消耗 / 成本 | 日志聚合 | 实测 |

> 实测值以仓库内评测产物(`reports/`、`logs/`)为准。已删除 P50/P95/P99 时延分位与 SLA 目标表(属 SRE 信号)。

## 13. 验收标准

### 阶段一

- 能上传两份模拟 Excel 并生成对账任务;Pandas 完成字段校验 / 清洗 / 标准化。
- 三阶段匹配识别自动平账与异常;至少覆盖 AMOUNT_MISMATCH + 单边缺失。
- 异常执行 RAG 检索并返回来源与分数。
- AuditAgent 输出结构化 JSON(含 evidence)、通过 Schema 校验。
- 任务 / 流水 / 异常 / 审计建议写入 MySQL;状态与差错明细 API 可查。
- Vue 上传 / 看板 / 台账 / 复核页可用;人工复核事务更新台账。
- 能输出单笔异常的本地 trace(输入 → RAG 命中 → Agent 输出 → 落库)。

### 阶段二

- ExtractionAgent / AuditAgent 为真实 DeepSeek V4 Pro 调用(OpenAI 兼容接口)。
- LangGraph 条件路由按 exception_branch 分发。
- 三级 Fallback 可工作;RAG 无命中直接转人工。
- 增强 RAG(Dense+BM25+RRF+Reranker+Query Rewrite)可工作,Reranker / Rewrite 可开关。
- 输出校验管线 4 阶段可工作;硬约束 C1–C6 生效。
- Prompt 独立文件 + 版本;structlog 覆盖所有 LLM 调用点。
- 工具调用权限边界落地(L0/L1/L2)。
- RAG 评测脚本输出 Recall@5/MRR;Agent 决策质量评估(统计方法)可运行。

### 阶段三

- 上传异步化(ARQ),即时返回 task_id。
- SSE 展示 Agent 执行过程(步骤、RAG 详情、Fallback 层级)。
- Redis 接入 LLM 结果缓存 / 限流 / 幂等。
- 量化指标面板可用;Docker Compose 一键启动。
- (可选)JWT 登录;(可选加分项)云服务器部署。

## 14. 工具调用权限与可靠性

### 14.1 工具调用权限边界

普通函数工具(不用 MCP),三级权限:

| 级别 | 范围 | 约束 |
|---|---|---|
| L0 只读 | RAG 检索、台账查询、历史案例检索 | 自由调用,不改数据 |
| L1 结构化输出 | Agent 输出 JSON 审计建议 | 必须过 Schema + 硬约束才被消费 |
| L2 数据库写入 | 台账落库、队列 / 统计更新 | Agent **禁止直接写**,必须经事务保障 |

各 Agent 工具白名单:ExtractionAgent 纯 LLM 推理(禁数据库);AuditAgent 仅 RAG / 计算结果(只读);TraceAgent 仅追溯查询(只读)。

### 14.2 可靠性(围绕 LLM API 不稳定)

- **优雅降级**:DeepSeek 不可用 → 降级为确定性规则,异常标记 PENDING_HUMAN;ChromaDB 不可用 → 无 RAG 模式,evidence 为空、强制 PENDING_HUMAN。
- **重试 + 熔断**:LLM 调用失败重试 ≤ 3 次(指数退避);连续 5 次失败 → 熔断 OPEN,30s 后 HALF_OPEN 探测。
- **token 预算**:单笔异常输入/输出有上限,超预算无结果 → 降级标记 PENDING_HUMAN。

## 15. 风险与边界

- **数据边界**:只用模拟 / 脱敏数据,不用真实客户数据或银行内部资料;自定义规则标注为演示规则。
- **AI 决策边界**:AI 不算金额(只读 READ-ONLY 结果)、不直接改账务状态(经事务)、不做最终金融决策(低置信 / 无依据 / 高风险转人工)。
- **安全边界**:所有 API 带 `X-User-ID`;启用 JWT 时业务查询按 `user_id` 行过滤;RAG 无命中不臆造 evidence。

## 16. LLM 选型

| 维度 | DeepSeek V4 Pro |
|---|---|
| 成本 | 极低,个人项目可承受大量调试调用(具体价格**参考,以官网为准**) |
| 中文能力 | 顶级,对账场景全中文 |
| 接口 | OpenAI 兼容(`openai` SDK + `base_url=https://api.deepseek.com/v1`) |
| 可测试性 | 工程上做 provider 抽象,默认可切 Fake provider,主链路与测试不依赖真实 Key |
| 可私有化 | 提供开源权重,后续可本地部署消除 API 依赖 |

```python
from openai import OpenAI
client = OpenAI(api_key="sk-xxx", base_url="https://api.deepseek.com/v1")
resp = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[...],
    temperature=0.1,                       # 金融场景低温度
    response_format={"type": "json_object"},
)
```

阶段二新增依赖:`openai`、`structlog`、`jieba`、`rank-bm25`。

## 17. 边界与可扩展方向

以下能力在原设计中存在,本版本**有意收敛**以突出 Agent 工程信号,是清晰的扩展点而非遗漏:

- **银行内部清算对账**等第二场景:引擎 Source A / Source B 抽象已保留,可新增 Scenario Profile 扩展。
- **多租户三级隔离**:当前最多按 `user_id` 行过滤,可扩展。
- **三层记忆引擎**:当前以历史人工确认案例 few-shot 作轻量替代,可演进为短期 / 长期 / 摘要记忆。
- **MCP 工具层**:当前用普通函数工具,可标准化为 MCP Server。
- **云部署**:可作加分项补云端部署,非必做。
