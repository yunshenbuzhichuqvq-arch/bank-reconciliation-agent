# 《基于多智能体（Multi-Agent）架构的银行自动化对账与报表审计系统》总体架构

## 1. 项目定位与架构目标

本项目是一个面向个人开源作品集和转行求职展示的 AI 应用系统。项目场景来自银行对公柜员工作中常见的对账、冲正、挂账、日终报表和人工复核流程，目标是把真实业务问题抽象成一个可开发、可部署、可面试讲透的系统。

系统的核心定位不是“让大模型替人算账”，而是：

> 用确定性代码完成金融账务中的精确计算和状态落库，用 Multi-Agent 处理非结构化摘要、跨日追溯、规则解释和审计报告生成，用 Human-in-the-Loop 保留金融场景中的人工复核边界，用 Hook 链和硬约束保证安全与合规底线。

架构设计需要同时服务四个目标：

1. **业务可信**：场景来自银行对账和报表审计，不是泛泛的聊天机器人。
2. **工程可落地**：先做 MVP-0 后端最小 AI 对账闭环，再逐步补本地产品闭环、线上部署和工程化能力。
3. **AI 能力明确**：突出 RAG、Agent 编排、工具调用、结构化输出和审计溯源。
4. **面试可表达**：每个技术选择都能解释“为什么这么做”，有量化指标和设计决策依据。

### 1.1 2026 Agent 求职定位与取舍

2026 年的 Agent 应用面试已经不再只看“能不能调用大模型”，而是更关注系统是否具备生产化意识：确定性边界、工具调用安全、状态持久化、人工复核、评测体系、可观测性和成本控制。因此，本项目刻意避免做成“上传文件后让 LLM 直接给结论”的玩具 Demo，而是把银行对账拆成可验证的工程链路。

但本项目仍然是个人开源求职项目，不宣称可直接替代真实银行生产系统。文档中的 Hook 链、记忆引擎、增强 RAG、MCP 和压测等能力按阶段落地：MVP-0 先证明主链路可运行，MVP 做本地可演示闭环，V1/V2 再补齐评测、可观测性和部署能力。所有量化指标在未跑通评测前均作为目标口径或演示口径，不冒充真实生产数据。

面试时最重要的不是“用了多少技术名词”，而是能拿出证据链：接口返回、数据库记录、RAG 命中结果、Agent 输出 JSON、Hook 校验日志、人工复核记录、评测报告和演示截图。

## 2. 八层总体架构

系统采用前后端分离架构，整体划分为八层。在传统六层架构基础上，新增“Hook 链与硬约束层”作为安全与质量门禁，新增“记忆引擎与上下文管理层”作为跨切割关注点，贯穿 Agent 执行全生命周期。

```text
+--------------------------------------------------------------------------------+
| 前端交互层 Vue 3 + Element Plus + ECharts                                        |
| 上传账单 | 任务看板 | Agent 流式工作台 | 人工复核 | 差错台账 | 报表审计              |
+--------------------------------------------------------------------------------+
                                      |
                                      | HTTP / SSE
                                      v
+--------------------------------------------------------------------------------+
| API 服务层 FastAPI + Pydantic + JWT + 多租户中间件                                |
| 文件上传 | 任务创建 | 状态查询 | 工作流启动 | 人工审批 | 台账查询 | 报告导出             |
+--------------------------------------------------------------------------------+
                                      |
                   +------------------+------------------+
                   |                                     |
                   v                                     v
+--------------------------------------+   +-------------------------------------+
| 确定性计算层 Pandas + Decimal + 规则引擎  |   | Multi-Agent 编排层 LangGraph       |
| Excel 清洗 | 金额比对 | 异常分支路由 | 事务写入|   | 提取 | 审计 | 追溯 | 报表 | 人工挂起 |
+--------------------------------------+   +-------------------------------------+
                   |                                     |
                   +------------------+------------------+
                                      |
                    +-----------------+-----------------+
                    |                                   |
                    v                                   v
+--------------------------------------+   +-------------------------------------+
| Hook 链与硬约束层                      |   | 记忆引擎与上下文管理层                 |
| Pre-Hook: Auth → RateLimit → Memory  |   | 短期记忆(Redis) | 长期记忆(SQLite)    |
| Post-Hook: Schema → Constraint → Log |   | 摘要压缩 | Context Window 组装         |
+--------------------------------------+   +-------------------------------------+
                    |                                   |
                    +-----------------+-----------------+
                                      |
                                      v
+--------------------------------------------------------------------------------+
| 数据与知识层 MySQL 8.0 + ChromaDB + Redis + SQLite                                |
| 任务 | 流水 | 待核验队列 | 差错台账 | 复核记录 | Agent日志 | RAG文档 | 报告          |
+--------------------------------------------------------------------------------+
                                      |
                                      v
+--------------------------------------------------------------------------------+
| 可观测性与评测层 LangFuse + structlog + RAG 评测集 + Agent Schema 符合性测试         |
+--------------------------------------------------------------------------------+
                                      |
                                      v
+--------------------------------------------------------------------------------+
| 工程化与部署层 Docker Compose + Celery/ARQ + Nginx + 环境变量 + 云服务器部署          |
+--------------------------------------------------------------------------------+
```

### 2.1 前端交互层

前端使用 Vue 3、Element Plus、Pinia 和 ECharts，目标不是做营销页面，而是做一个可以真实演示业务流程的工作台。

核心页面包括：

- 账单上传页：上传银行端流水和清算端流水。
- 任务看板：展示总笔数、自动平账数、AI 审计中、待人工复核、挂账数。
- Agent 流式工作台：通过 SSE 展示 Agent 当前处理步骤、工具调用和 RAG 命中依据。
- 人工复核页：展示双端流水、AI 推荐理由、RAG 来源和人工操作按钮。
- 差错台账页：查询已确认差错、挂账、冲正、手续费差异等记录。
- 报表审计页：查看日终统计、异常分布和审计报告。

### 2.2 API 服务层

后端使用 FastAPI 作为统一入口，负责文件上传、任务管理、工作流启动、人工审批、台账查询和报告导出。

关键能力包括：

- Pydantic 请求和响应校验。
- JWT 登录鉴权，保护线上 Demo 接口和模型调用额度。
- **多租户中间件**：所有请求强制携带 `X-User-ID`，注入到 `request.state`，后续所有 DB 查询和记忆检索均按 `user_id` 隔离。
- SSE 流式推送 Agent 执行过程。
- 统一异常处理和审计日志。
- 环境变量管理数据库、模型 Key、向量库路径等配置。

### 2.3 确定性计算层

确定性计算层处理所有必须精确、可复现、可审计的动作，并承担异常分支路由职责。

职责包括：

- Excel 字段清洗和标准化。
- 双端流水初步匹配（三阶段匹配算法）。
- 金额差异计算（`decimal.Decimal`，多币种精度上下文）。
- **异常分支路由**：基于声明式规则 YAML 的决策树，将异常分发到不同的处理分支（手续费匹配、重复入账检测、日切窗口判断、冲正关键词识别、金额模式分析），确定性规则能覆盖的分支直接处理，无法覆盖的才进入 Agent 链路。
- MySQL 事务写入。

本层的核心原则是：**凡是金额计算、状态更新、数据库写入，不交给 LLM。**

#### 2.3.1 三阶段流水匹配算法

```
阶段 1: 精确匹配（HASH JOIN）
  - 条件: bank.flow_id == clear.flow_id AND bank.amount == clear.amount
  - 结果: AUTO_FIXED，直接平账

阶段 2: 模糊匹配（Composite Index Probe）
  - 条件: bank.amount == clear.amount AND bank.trade_time.date() == clear.trade_time.date()
         AND (bank.counterparty_account LIKE '%' + clear.channel + '%')
  - 结果: 候选匹配 → 人工/Agent 确认

阶段 3: 单边残留识别（Anti-Join）
  - 条件: 阶段 1 + 阶段 2 均未匹配的流水
  - 结果: 标记为 SINGLE_SIDE_MISSING 或进入 Cutoff 检测
```

#### 2.3.2 声明式规则引擎

规则不再硬编码为 if-else，而是用 YAML 定义，程序启动时加载并动态执行：

```yaml
rules:
  - id: R001
    name: 精确匹配自动平账
    priority: 1
    conditions:
      - field: amount_diff
        operator: eq
        value: 0
      - field: flow_id
        operator: matched
    action: AUTO_FIX

  - id: R002
    name: 金额差异进入审计
    priority: 2
    conditions:
      - field: amount_diff
        operator: neq
        value: 0
      - field: flow_id
        operator: matched
    action: PENDING_AI
    error_type: AMOUNT_MISMATCH

  - id: R003
    name: 手续费分离检测
    priority: 3
    conditions:
      - field: amount_diff
        operator: in_set
        value: [0.50, 1.00, 2.00, 5.00, 10.00, 100.00]
    action: PENDING_AI
    error_type: SUSPECTED_FEE_DIFF
    agent_type: AuditAgent
    rag_query: "手续费差异处理规则"

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
    agent_type: TraceAgent
```

面试可讲点：规则与代码分离，业务人员可直接维护 YAML 文件；规则支持优先级排序，高优先级规则先匹配；同一笔异常只会命中一条规则，避免冲突。

### 2.4 Multi-Agent 编排层

Multi-Agent 编排层使用 LangGraph 实现状态机和节点路由。Agent 不是多个聊天机器人，而是带状态、工具、边界和失败兜底的业务节点。

建议节点如下：

- `PreCheckNode`：规则预处理节点，不依赖 LLM，完成基础对账和异常分类。
- `ExtractionAgent`：提取 Agent，将不规范摘要结构化为标准 JSON。
- `AuditAgent`：审计 Agent，结合规则、RAG 和工具结果做审计判断。
- `TraceAgent`：追溯 Agent，处理跨日切、冲正、退款和原流水追踪。
- `ReportAgent`：报表 Agent，生成审计摘要和报告。
- `HumanReviewNode`：人工复核节点，负责挂起流程并等待人工审批。

#### 2.4.1 并行执行与 Subgraph

同一笔异常流水上，ExtractionAgent（语义提取）和 RAG 检索（规则召回）可以并行执行，通过 LangGraph 的 `Send` API 汇聚结果给 AuditAgent：

```text
PreCheckNode
    │
    ├──> ExtractionAgent ──┐
    │                      ├──> AuditAgent
    └──> RAG Subgraph ─────┘
              │
              ├─ Query Rewrite Node
              ├─ Hybrid Search Node
              ├─ Reranker Node
              └─ Filter Node
```

RAG 检索被封装为独立的 Subgraph，内部有完整的查询改写 → 混合检索 → Rerank → 阈值过滤子流程，AuditAgent 只需调用 Subgraph 的入口，不感知内部实现。

#### 2.4.2 多级 Fallback 策略

```
AuditAgent 首次判断
  │
  ├─ confidence >= 0.85 → 直接落库，写入台账
  │
  ├─ 0.6 <= confidence < 0.85 → 二级 Fallback
  │     └─ 更换 Prompt 角度（如从"金额差异"视角切换为"手续费"视角）
  │         ├─ 二次判断 confidence >= 0.85 → 落库
  │         └─ 仍低 → 三级 Fallback
  │
  ├─ confidence < 0.6 → 三级 Fallback
  │     └─ 调用 TraceAgent 查询历史相似异常的处理记录
  │         ├─ 有参考 → 注入历史记录后 AudAgent 再次判断
  │         └─ 无参考 → PENDING_HUMAN
  │
  └─ RAG 无命中 → PENDING_HUMAN（不做 Fallback，直接转人工）
```

3 层递进 fallback，而不是简单的"低就转人工"。面试时可重点讲这个设计决策。

#### 2.4.3 Checkpoint 断点续跑

人工复核节点（HumanReviewNode）支持挂起和恢复：

- 使用 LangGraph 的 `SqliteSaver` 或 `PostgresSaver` 持久化图状态。
- 人工审批通过/拒绝后，从 Checkpoint 恢复执行，继续后续节点。
- 避免从头重跑整个任务，节省 LLM Token 和时间。
- 支持中断恢复的幂等性：同一 queue_id 重复审批不会产生重复台账记录。

#### 2.4.4 MCP 协议工具层

将 Agent 依赖的外部能力封装为 MCP（Model Context Protocol）Server，实现工具层的标准化和解耦：

```text
AuditAgent (MCP Client)
    │
    ├── MCP Server: rag-server
    │     └─ Tool: search_rules(query, top_k) → 返回规则依据
    │
    ├── MCP Server: ledger-server
    │     └─ Tool: query_ledger(task_id, error_type) → 返回历史台账
    │
    └── MCP Server: trace-server
          └─ Tool: trace_original_flow(flow_id, date_range) → 追溯原流水
```

面试可讲点：MCP 正在成为 Agent 工具层的重要协议之一。这里引入 MCP 不是为了追热点，而是为了把 RAG、台账查询和流水追溯从 Agent 编排代码中解耦出来。V1 阶段可先以轻量 MCP Server 形式演示工具标准化；如果时间不足，也可以保留为普通 service/tool 接口，不影响 MVP 主链路。

### 2.5 Hook 链与硬约束层

Hook 链是本系统区别于普通 AI Demo 的核心架构设计。它保证 Agent 在执行前和执行后都经过严格的门禁校验。

#### 2.5.1 Pre-Hook 链（Agent 执行前）

```
Pre-Hook 链（按优先级顺序执行，任意环节失败即中断）:

  ① AuthHook —— 权限校验（首节点，安全底线）
     ├─ JWT Token 有效性
     ├─ 提取 user_id 和 role
     ├─ 校验 user_id 对所请求 task_id 的归属
     └─ 校验角色是否有权限执行当前操作

  ② RateLimitHook —— 频率控制
     ├─ Redis Sliding Window：单用户每分钟最多 50 次 Agent 调用
     └─ asyncio.Semaphore：全局 LLM API 并发上限
     （注：不限频可能导致模型 Key 超额或被风控封禁）

  ③ MemoryHook —— 记忆注入
     ├─ user_id → SQLite 检索长期记忆（同类异常的历史处理方式）
     ├─ thread_id → Redis 检索短期记忆（本批次已处理的模式）
     ├─ thread_id → Redis 检索摘要（已处理 > 20 笔时的压缩版上下文）
     └─ 调用 MemoryManager.build_context() 组装完整 Context Window

  ④ ValidationHook —— 输入校验
     └─ HardConstraintValidator 校验输入数据完整性和格式

  ⑤ CacheHook —— 缓存检查
     └─ Redis 查同一 queue_id 是否已处理过 → 命中则直接返回缓存结果
```

#### 2.5.2 Post-Hook 链（Agent 执行后）

```
Post-Hook 链:

  ⑥ SchemaHook —— 输出 Schema 校验
     └─ Pydantic model_validate，失败 → 重试（最多 3 次）→ 仍失败 → 转人工

  ⑦ ConstraintHook —— 硬约束校验
     ├─ 金额差异-风险等级一致性：|diff| > 10000 不能标记为 LOW
     ├─ evidence 字段不能为空列表
     ├─ decision 字段必须在枚举值内
     └─ PENDING_HUMAN 时 reason 必须说明不足原因

  ⑧ DecisionHook —— 决策路由
     ├─ confidence >= 0.85 → 直接落库
     ├─ 0.6 <= confidence < 0.85 → 触发二级 Fallback
     ├─ confidence < 0.6 → 触发三级 Fallback
     └─ RAG 无命中 → PENDING_HUMAN

  ⑨ MemoryUpdateHook —— 记忆更新
     ├─ Redis ← 短期记忆（本任务决策记录）
     ├─ Redis ← 更新摘要（累计满 20 笔触发 LLM 压缩）
     └─ SQLite ← 长期记忆（仅保存人工确认的最终结果）

  ⑩ LogHook —— 审计日志
     ├─ MySQL ← t_agent_execution_log
     ├─ MySQL ← t_rag_retrieval_log
     ├─ structlog ← JSON 格式日志（带 trace_id, user_id, thread_id）
     └─ LangFuse ← LLM 调用 trace（token 消耗、耗时、状态）

  ⑪ TransactionHook —— 事务写入
     └─ MySQL 事务写入差错台账、更新队列状态、更新任务统计
```

#### 2.5.3 四层硬约束体系

| 层级 | 约束内容 | 实现机制 |
|------|---------|---------|
| L1 输入约束 | 金额精度、流水号格式、日期范围、必填字段 | Pydantic validator |
| L2 计算约束 | 金额差异 = Decimal(bank) - Decimal(clear)，LLM 只读不可修改 | 工具函数返回计算结果，Prompt 中标注为 READ-ONLY |
| L3 输出约束 | Schema 符合、decision 枚举、evidence 非空、风险-金额一致性 | Pydantic model_validate + 自定义 field_validator |
| L4 数据库约束 | 事务原子性、外键完整性、CHECK 约束、唯一约束防重复 | MySQL InnoDB 事务 + 表结构约束 |

面试可讲点：金融系统不允许 LLM 自由发挥。四层硬约束确保 Agent 的输出必须通过所有门禁才能落库，整个过程可审计、可复现、可回滚。

### 2.6 记忆引擎与上下文管理层

记忆引擎是本系统实现“有状态 Agent”的关键。与传统“每次调用独立无记忆”的 Demo 不同，本系统的 Agent 拥有短期记忆、长期记忆和摘要记忆三层体系，显著提升审计一致性。

#### 2.6.1 三层记忆模型

```
┌─────────────────────────────────────────────────────────┐
│              短期记忆（Short-term Memory）                  │
│  作用域：本任务内（thread_id 隔离）                         │
│  存储：Redis Sorted Set（按时间排序）                       │
│  TTL：任务结束后 24 小时                                   │
│  内容：本批次已处理异常的模式、Agent 决策记录                │
│  示例："前 10 笔跨日切单边账都确认平账了"                   │
├─────────────────────────────────────────────────────────┤
│              长期记忆（Long-term Memory）                   │
│  作用域：跨任务（user_id 隔离）                             │
│  存储：SQLite（嵌入式，检索延迟 < 5ms）                     │
│  TTL：永久                                                  │
│  内容：历史任务中同类异常的最终处理方式（仅保存人工确认结果） │
│  检索：按 error_type + 关键字段做语义相似度检索              │
│  示例："过去 5 次冲正摘要不明确的异常，人工均选择确认平账"   │
├─────────────────────────────────────────────────────────┤
│              摘要记忆（Summary Memory）                     │
│  作用域：本任务内（thread_id 隔离）                         │
│  存储：Redis String                                        │
│  更新频率：每处理 20 笔异常触发一次 LLM 摘要压缩            │
│  内容：前 N 笔决策模式的压缩文本（~300 token）              │
│  目的：防止 Context Window 随处理笔数线性膨胀               │
│  示例："本批次以金额差异为主(60%)，其次为日切单边(25%)..."  │
└─────────────────────────────────────────────────────────┘
```

#### 2.6.2 Context Window 组装策略

每次 Agent 调用前，MemoryManager 按以下结构组装注入 Context Window 的内容：

```text
┌─────────────────────────────────────────────┐
│ System Prompt（固定，约 500 token）            │  ← 角色定义、输出 Schema、硬约束规则
├─────────────────────────────────────────────┤
│ Long-term Memory（按需检索，约 800 token）      │  ← user_id 下的历史相似异常处理方式
├─────────────────────────────────────────────┤
│ Short-term Memory（本会话累积，约 600 token）   │  ← 本任务已处理的模式，保证决策一致性
├─────────────────────────────────────────────┤
│ Summary Buffer（摘要压缩，约 300 token）        │  ← 历史笔数的统计摘要（仅当处理 > 20 笔时）
├─────────────────────────────────────────────┤
│ RAG Context（本次检索，约 1000 token）          │  ← 混合检索 + Rerank 后的规则片段
├─────────────────────────────────────────────┤
│ Current Item（当前流水，约 400 token）          │  ← 银行端 + 清算端流水结构化 JSON
├─────────────────────────────────────────────┤
│ Tool Results（工具返回，约 500 token）          │  ← Decimal 金额计算结果、TraceAgent 追溯结果
└─────────────────────────────────────────────┘
                                        │
                          总计约 3500-4100 token
                                        │
                    远低于主流 LLM 上下文上限（128K+），
                    但包含了完整决策所需的全部信息。
```

#### 2.6.3 记忆存储架构

| 存储 | 用途 | 数据结构 | 延迟 | 持久化 |
|------|------|---------|------|--------|
| Redis | 短期记忆 + 速率限制 + 分布式锁 + 缓存 | Sorted Set + Hash + String | < 1ms | 可选 RDB/AOF |
| SQLite | 长期记忆（跨会话永久存储） | 结构化表 | < 5ms | 永久文件 |

为什么长期记忆用 SQLite 而不是 MySQL？
- 长期记忆是读多写少场景，SQLite 完全胜任
- 嵌入式无网络延迟，Agent 检索记忆无需跨进程调用
- 记忆存储与业务存储分离，降低主库负载
- 离线可用：即使 MySQL 连接中断，Agent 的记忆检索不受影响

### 2.7 数据与知识层

#### 2.7.1 MySQL 8.0（业务数据）

MySQL 存储结构化业务数据。所有业务表均包含 `user_id` 字段实现多租户隔离。

- 对账任务（含批次维度：`batch_id → task_id → queue_item_id` 三级关系）
- 银行端流水（HASH 分区按 task_id）
- 清算端流水（HASH 分区按 task_id）
- 待核验队列
- 差错台账
- 人工复核记录
- Agent 执行日志（output_payload JSON 列建虚拟列索引）
- RAG 检索记录
- 审计报告（含物化视图做报表统计预聚合）

关键设计：

- **用户隔离**：每张表包含 `user_id` 列，所有查询强制带 `WHERE user_id = ?`。
- **分区表**：流水表按 `task_id` 做 HASH 分区，大任务查询不扫全表。
- **JSON 虚拟列索引**：Agent 日志表的 `output_payload` 对高频查询字段（`decision`、`risk_level`）建虚拟列索引，避免 JSON 全表扫描。
- **物化视图**：报表统计走预聚合的物化视图或定时刷新的汇总表，而非实时聚合。

#### 2.7.2 ChromaDB（向量知识库）

存储规则和合规知识的向量化索引，支持混合检索（Dense + Sparse）。

#### 2.7.3 Redis（内存缓存与短期记忆）

- 短期记忆存储（Sorted Set）
- 摘要缓存（String）
- 速率限制（Sliding Window）
- 缓存（Agent 调用结果缓存，防重复处理）
- 分布式锁（防止同一 queue_id 并发处理）

#### 2.7.4 SQLite（长期记忆）

- 长期记忆表（`t_long_term_memory`）：按 user_id + error_type 组织
- 嵌入在 Agent 进程中，无网络延迟

### 2.8 可观测性与评测层

可观测性从 V2 提前到 MVP 阶段实施。这是大模型应用区别于传统软件的核心工程问题。

- **LangFuse 集成**：每次 LLM 调用的 token 消耗、耗时、成功/失败状态自动上报，生成可视化 Trace。
- **结构化日志**：使用 `structlog` 输出 JSON 格式日志，每条日志携带 `trace_id`、`user_id`、`thread_id`、`agent_name`、`step`。
- **RAG 检索质量监控**：记录每次检索的 query、top-k 结果、相似度分数、最终被使用的 chunk，离线分析未命中 query 的特征。
- **成本追踪**：每个 Agent 调用的 token 消耗和按模型定价折算的成本。
- **RAG 评测集**：手写 50-100 条 `(query, expected_rule_ids)`，每次调整切片策略或检索参数后跑一遍，输出 Recall@5、MRR、NDCG@5。
- **Agent Schema 符合性测试**：用 Pytest + Pydantic `model_validate`，对每种异常类型构造 mock 输入，验证 Agent 输出一定符合 Schema，统计通过率。

这部分的产物必须可展示：`logs/*.jsonl` 中能看到 trace_id 和 hook 结果，`reports/rag_eval.md` 能看到检索评测结果，测试输出能证明 Agent JSON 没有绕过 Schema。没有这些证据时，相关指标只作为目标，不写成“已经达到”。

### 2.9 工程化与部署层

工程化层服务于项目从本地 Demo 走向可展示作品。

MVP-0 阶段：
- 本地 FastAPI。
- Pandas 清洗和基础规则对账。
- 简化 AuditAgent + RAG 检索。
- 本地 ChromaDB + SQLite。
- MySQL 数据落库。
- 模拟 Excel 数据。

MVP 阶段：
- 本地 FastAPI + Vue 3。
- Docker MySQL + Redis。
- 本地 ChromaDB + SQLite。
- 模拟 Excel 数据。
- LangGraph 基础工作流（含 Checkpoint）。
- Hook 链基础实现（Auth + Schema + Constraint + Log）。
- 人工复核基础流程。
- 记忆引擎（短期 + 长期）。
- RAG 混合检索 + Reranker。
- LangFuse + structlog 可观测性。

V1 阶段：
- Docker Compose 一键启动（含 Nginx 反向代理）。
- Celery/ARQ 后台任务队列（对账任务异步执行）。
- JWT 鉴权 + 多租户中间件。
- SSE 流式推送 Agent 执行过程。
- 云服务器部署。
- README、演示数据和部署说明。
- MCP 协议工具层。
- RAG 评测集 + Agent Schema 符合性测试。
- 量化指标仪表板（自动平账率、Agent 审计准确率、RAG Recall@5 等）。

V2 阶段：
- RAG 评测体系完善（含 A/B 测试框架）。
- Agent 执行日志离线分析。
- Prompt 版本管理和效果对比。
- 失败样本分析。
- PDF 报告导出。
- 压力测试与性能调优。

## 3. 核心设计原则

### 3.1 规则优先，AI 补充

能用确定性规则解决的问题，不交给大模型。系统采用“YAML 声明式规则引擎 + 异常分支决策树”双层机制，规则可覆盖的分支直接处理，无法覆盖的才进入 Agent + RAG 链路。

面试可讲点：这体现的是 AI 应用开发中的边界意识——不是让 AI 替代所有逻辑，而是让 AI 补足传统规则难处理的语义理解和归因解释。

### 3.2 金额计算绝不交给 LLM

金融账务中的金额计算必须可复现、可验证、可审计。系统统一使用 Python `decimal.Decimal` 和 MySQL 事务保证精确性，不同币种使用 `decimal.localcontext` 控制精度（如 JPY 0 位小数、CNY 2 位小数）。

Agent 只能读取工具返回的计算结果，Prompt 中标注为 READ-ONLY：

```json
{
  "bank_amount": "1000.00",
  "clear_amount": "990.00",
  "diff": "10.00",
  "_note": "READ-ONLY: computed by deterministic layer"
}
```

### 3.3 RAG 无据不判定

涉及跨日切、冲正、挂账、手续费争议等业务判断时，Agent 不能凭借预训练知识直接给结论。它必须先从 RAG 知识库检索到规则依据。

如果没有命中规则或命中分数低于阈值，系统强制进入 `PENDING_HUMAN`，不触发 Fallback。

### 3.4 硬约束门禁

Agent 输出不直接落库，必须通过 Post-Hook 链的 Schema 校验、Constraint 校验和 Transaction 校验。任何一环保失败即触发重试或转人工。详见 2.5 节。

### 3.5 多租户与用户隔离

银行是典型的多操作员环境。系统实现三级隔离：

- **数据隔离**：所有 MySQL 表包含 `user_id` 列，API 中间件强制注入 WHERE 条件。
- **会话隔离**：LangGraph 通过 `config.thread_id` 隔离不同对账任务的状态。
- **记忆隔离**：短期记忆按 `thread_id` 隔离，长期记忆按 `user_id` 分区检索。

操作员 A 的流水、任务、Agent 记忆完全与操作员 B 隔离，中间件层面保证不会出现跨用户数据泄露。

### 3.6 Human-in-the-Loop 兜底

金融场景中 AI 推荐不能等同于最终处理结果。只要出现低置信度、无规则依据、高风险金额、工具调用失败等情况，流程必须进入人工复核。

人工复核需要记录：

- 操作人。
- 操作时间。
- 操作动作（确认平账 / 强制挂账）。
- 人工备注。
- AI 推荐理由。
- RAG 来源。

人工确认的最终结果会写入长期记忆（SQLite），影响后续同类异常的 Agent 判断。

### 3.7 全链路可追踪

系统需要记录每一次 Agent 决策过程，包括输入、工具调用、RAG 命中片段、输出 JSON、Hook 链校验结果、路由结果和错误信息。

这样做有两个目的：

1. 方便开发阶段调试 Agent 行为。
2. 面试时能解释 AI 判断不是黑盒，而是有日志、有依据、有兜底。

## 4. Multi-Agent 协作架构

### 4.1 全局状态结构

LangGraph 中各节点共享 `ReconciliationState`：

```python
from typing import Any, Dict, List, Optional, TypedDict

class ReconciliationState(TypedDict):
    task_id: str
    user_id: str                # 用户隔离标识
    thread_id: str              # 会话隔离标识
    current_queue_id: Optional[int]
    bank_item: Dict[str, Any]
    clear_item: Dict[str, Any]
    error_type: Optional[str]
    exception_branch: Optional[str]  # 异常分支路由结果
    math_result: Dict[str, str]
    extraction_result: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    long_term_memory: List[Dict[str, Any]]   # 长期记忆
    short_term_memory: List[Dict[str, Any]]  # 短期记忆
    summary_buffer: Optional[str]            # 摘要记忆
    audit_decision: Dict[str, Any]
    retry_count: int
    fallback_level: int        # 当前 Fallback 层级（0/1/2）
    next_action: str
    error_message: Optional[str]
    agent_logs: List[Dict[str, Any]]
```

### 4.2 节点职责

| 节点 | 类型 | 职责 | 阶段 |
| --- | --- | --- | --- |
| `AuthCheckNode` | Hook | JWT 校验、user_id 归属校验、角色权限校验 | MVP |
| `PreCheckNode` | 确定性代码 | YAML 规则引擎、三阶段匹配、异常分支路由 | MVP-0 |
| `ExtractionAgent` | LLM Agent | 模糊摘要结构化，输出 JSON | MVP |
| `AuditAgent` | LLM Agent | 结合计算结果和 RAG 依据输出结构化审计建议 | MVP-0 |
| `TraceAgent` | LLM + Tool | 查询 T+1 流水、追溯冲正和退款链路 | V2 |
| `HumanReviewNode` | 状态节点 | 挂起流程，等待人工审批（支持 Checkpoint 恢复） | MVP |
| `ReportAgent` | LLM + Tool | 生成审计摘要和报告（数据来自 SQL 聚合） | V1/V2 |

### 4.3 路由规则

MVP-0 路由：

```text
START
  -> 上传并解析双端 Excel
  -> PreCheckNode 完成字段校验、数据清洗、三阶段匹配和异常分支路由
  -> 确定性规则可覆盖的异常 → 直接写入台账
  -> 确定性规则无法覆盖 → RAG 检索
  -> AuditAgent 输出结构化审计建议
  -> Post-Hook 链校验
  -> 写入 MySQL 差错台账和任务统计
  -> END
```

MVP 及后续路由：

```text
START
  -> AuthCheckNode（权限校验）
  -> PreCheckNode（规则引擎 + 异常分支路由）
  -> 分支 1：FEE_DIFF / EXACT_MATCH → 直接写入台账
  -> 分支 2：FUZZY_REVERSAL → ExtractionAgent ∥ RAG Subgraph → AuditAgent
  -> 分支 3：CUTOFF_SINGLE_SIDE → RAG Subgraph → TraceAgent → AuditAgent
  -> 分支 4：SUSPECTED_DUPLICATE → TraceAgent → AuditAgent
  -> 分支 5：UNKNOWN_ANOMALY → RAG Subgraph → AuditAgent (高阈值)
  -> Post-Hook 链校验
  -> confidence >= 0.85 → 写入台账
  -> confidence < 0.85 → 多级 Fallback
  -> Fallback 耗尽 → HumanReviewNode（Checkpoint 挂起）
  -> 人工审批完成 → 恢复执行 → 更新记忆 → END
```

### 4.4 失败处理

- JSON 解析失败：最多重试 3 次，每次更换 Prompt 角度。仍失败则转人工。
- RAG 未命中：直接转人工，不触发 Fallback（没有依据就不能判断）。
- 工具调用失败：记录日志并转人工。
- 数据库事务失败：回滚并标记任务失败，保留输入数据以便恢复。
- Agent 输出不符合 Schema：Post-Hook SchemaHook 拒绝落库并触发重试。
- 硬约束校验失败：拒绝落库并转人工（硬约束失败不重试，因为业务规则不应被绕过）。
- 速率限制触发：返回 429，前端提示用户稍后重试。

## 5. 异常分支网络设计

异常分支是本系统业务复杂度的核心体现。系统不是简单的“对上了/没对上”，而是通过 12 个异常分支覆盖真实银行对账中的各类差错场景。

### 5.1 异常分支总览

```text
金额不一致（diff ≠ 0）
  │
  ├─ R001: 差异 ∈ {0.50, 1.00, 2.00, 5.00, 10.00, 100.00}
  │     └─ 分支: SUSPECTED_FEE_DIFF → AuditAgent + 手续费规则 RAG
  │
  ├─ R002: 差异 = 原金额 × N（整数倍）
  │     └─ 分支: SUSPECTED_DUPLICATE → TraceAgent 查原流水
  │
  ├─ R003: 流水号匹配但金额不一致
  │     └─ 分支: AMOUNT_MISMATCH → AuditAgent
  │
  └─ R004: 流水号不匹配
        ├─ R004a: 交易时间在日切窗口 (22:00-24:00)
        │     └─ 分支: CUTOFF_SINGLE_SIDE → T+1 追溯
        ├─ R004b: 摘要含冲正/撤销/退款/抹账关键词
        │     └─ 分支: FUZZY_REVERSAL → ExtractionAgent → AuditAgent
        ├─ R004c: 金额 + 日期 + 对方户名相似
        │     └─ 分支: SOFT_MATCH_CANDIDATE → AuditAgent 辅助确认
        └─ R004d: 完全无匹配
              └─ 分支: SINGLE_SIDE_MISSING → PENDING_HUMAN

单边存在（一端有流水，另一端无）
  │
  ├─ R005: 有流水端的交易时间在日切窗口
  │     └─ 分支: CUTOFF_SINGLE_SIDE → TraceAgent T+1 追溯
  │
  └─ R006: 非日切窗口
        └─ 分支: SINGLE_SIDE_MISSING → 直接写入台账，标记挂账

重复检测
  │
  ├─ R007: 同客户 + 同金额 + 时间差 < 5min
  │     └─ 分支: SUSPECTED_DUPLICATE → TraceAgent
  │
  └─ R008: 同客户 + 同金额 + 不同渠道
        └─ 分支: CROSS_CHANNEL_DUPLICATE → AuditAgent
```

### 5.2 路由架构

系统采用“确定性规则树 → Agent → Fallback”的混合路由：

- **确定性规则树**（Rule Engine）先执行：基于 YAML 规则和条件分支，能确定的直接处理。
- **Agent + RAG**：规则无法覆盖的进入 Agent 链路。
- **多级 Fallback**：Agent 低置信度时逐级递进，最终兜底到人工复核。

## 6. RAG 合规知识库与业务规则中心

RAG 是本项目的核心模块，不只是给 Agent 补充上下文。它承担“规则依据、业务解释、审计溯源”三类职责。

### 6.1 数据来源与证据流

本项目的数据和审计依据采用分层设计：

```text
人工构造模拟 Excel
  -> Pandas 清洗和规则对账
  -> 异常交易上下文
  -> RAG 混合检索（Dense + Sparse → Rerank → Filter）
  -> AuditAgent 生成结构化审计建议
  -> MySQL 保存差错台账、RAG 来源和审计结果
```

数据来源只使用人工构造的模拟数据。银行端流水和清算端流水的字段结构参考对账业务需要设计，但客户姓名、账号、流水号、金额和摘要均为虚构或脱敏样式。

审计依据由三层组成：

- **公开制度依据**：中国人民银行公开支付结算制度、银行结算账户管理制度，以及财政部公开会计基础工作、企业内部控制和会计档案管理规范。
- **项目自定义业务规则**：面向演示场景编写的 Markdown 规则，包括基础对账、跨日切、冲正退款、手续费差异、人工复核和报表口径。
- **运行证据**：RAG 命中的规则来源、相似度分数、Reranker 得分、AuditAgent 输出 JSON、人工复核记录和差错台账记录。

### 6.2 RAG 解决的问题

1. **防止幻觉**：Agent 没有检索到规则时不能自动判定。
2. **规则可维护**：业务规则写成 Markdown/PDF 文档，而不是全部塞进 Prompt。
3. **审计可追溯**：每个关键判断保存引用来源。
4. **对齐 JD 技能**：覆盖文档处理、切片、Embedding、向量检索、BM25 稀疏检索、Rerank、评测。

### 6.3 知识库内容

MVP-0 阶段使用项目自定义规则文档：

- 基础对账规则。
- 跨日切单边账处理规则。
- 冲正和退款识别规则。
- 人工复核触发规则。

MVP 阶段补充：

- 手续费差异处理规则。
- 报表审计口径说明。

V1/V2 阶段可加入公开规则和 PDF/Word 文档解析，但不使用任何银行内部资料或客户数据。

### 6.4 增强 RAG 流程

```text
规则文档 Markdown/PDF
  -> 文档清洗
  -> 结构化切片（按 ## 标题 + 语义边界混合策略）
  -> Dense 向量化（中文 Embedding 模型） + Sparse 索引（BM25）
  -> 存入 ChromaDB（同时存储 dense vector 和 sparse metadata）
  -> 用户/Agent 输入查询
  -> Query Rewrite（LLM 把自然语言映射为规则术语）
  -> 双路召回：Dense Top-20 + Sparse Top-20
  -> RRF（Reciprocal Rank Fusion）融合排序，取 Top-10
  -> Cross-Encoder Reranker（BGE-Reranker-v2-m3）精排，取 Top-5
  -> 相似度阈值过滤 + Reranker 分数阈值过滤
  -> 返回 rag_context 给 AuditAgent
  -> 保存 rag_source、检索分数、Reranker 分数和最终使用的 chunk
```

### 6.5 检索策略演进

| 阶段 | 检索策略 | 关键能力 |
|------|---------|---------|
| MVP-0 | Top-K Dense + 简单阈值 | 先跑通基础链路 |
| MVP | Hybrid Search (Dense + BM25) + RRF + Reranker + Query Rewrite | 提升召回率和精度 |
| V1 | + RAG 评测集 (50+ query) + Recall@5/MRR/NDCG | 量化检索质量 |
| V2 | + A/B 对比 + Reranker 模型对比 + 失败样本分析 | 持续优化 |

### 6.6 查询改写（Query Rewrite）

对账场景中，用户/Agent 输入的查询可能是：

> "这笔流水为什么没对上"

而规则文档里写的是：

> "单边账跨日切处理规则：日切敏感窗口内产生的单边账，应优先追溯下一清算日流水"

中间加一层 LLM 做查询改写，把自然语言映射到规则术语：

```
Input:  "这笔流水为什么没对上"
Output: "单边账 跨日切窗口 流水匹配失败 处理规则"
```

面试可讲点：查询改写是本 RAG 系统的核心优化之一。对账术语和自然语言之间存在语义 Gap，直接做向量检索容易漏召回。V1 阶段通过同一评测集对比“纯 Dense 检索”和“Query Rewrite + Hybrid + Reranker”，用 Recall@5/MRR/NDCG 说明改造是否有效；在评测脚本跑通前，不把提升幅度写成实测结论。

### 6.7 为什么选择 Cross-Encoder Reranker？

面试必问题。Bi-Encoder（Embedding 模型）的优势是速度快、可预计算，但缺点是 query 和 document 独立编码，丢失了交互信息。Cross-Encoder 把 query 和 document 拼接后一起过模型，做全文交互打分，精度显著更高，但速度慢（每对都需完整推理）。

本系统的策略是“粗排 + 精排”：先用 Bi-Encoder 做双路召回（快，召回 20 条候选），再用 Cross-Encoder Reranker 对 Top-10 做精排（慢但准），最终取 Top-5。

选择 BGE-Reranker-v2-m3 而非 Cohere Rerank API 的原因：
- 中文场景效果更好（BGE 系列在中文 benchmark 上表现优于 Cohere）
- 本地部署无 API 调用成本
- 离线可用，不依赖外部服务

### 6.8 无命中策略

如果 RAG 没有命中可用规则（Dense 分数 < 0.5 且 Reranker 分数 < 0.3），`AuditAgent` 必须输出：

```json
{
  "decision": "PENDING_HUMAN",
  "reason": "未检索到足够的业务规则或合规依据，转人工复核",
  "rag_source": [],
  "fallback_applied": false
}
```

注意：RAG 无命中时**不触发 Fallback**，直接转人工。因为没有规则依据就没有推理基础。

## 7. 多租户与用户隔离架构

### 7.1 三级隔离模型

```text
user_id: "zhangsan"（操作员张三）
  ├─ thread_id: "thread_001"（今天上午的对账任务）
  │   ├─ task_id: "TASK_20260526_001"
  │   ├─ short-term memory（Redis，key 含 thread_id）
  │   └─ summary buffer（Redis，key 含 thread_id）
  ├─ thread_id: "thread_002"（今天下午的对账任务）
  │   ├─ task_id: "TASK_20260526_002"
  │   ├─ short-term memory（Redis）
  │   └─ summary buffer（Redis）
  └─ long-term memory（SQLite，按 user_id 分区检索）

user_id: "lisi"（操作员李四）
  └─ ...（完全隔离，张三看不到李四的任何数据）
```

### 7.2 隔离实现

| 隔离级别 | 隔离键 | 作用域 | 实现机制 |
|---------|-------|--------|---------|
| 数据隔离 | `user_id` | MySQL 行级 | 所有表加 `user_id` 列 + API 中间件强制注入 WHERE |
| 会话隔离 | `thread_id` | 单次对账任务 | LangGraph `config.thread_id` + Redis Key 前缀 |
| 记忆隔离 | `user_id` | 长期记忆检索 | SQLite WHERE user_id + Redis Key 前缀 |

### 7.3 API 中间件

```python
# middleware/tenant.py
from fastapi import Request, HTTPException

class TenantMiddleware:
    async def __call__(self, request: Request, call_next):
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            raise HTTPException(status_code=401, detail="Missing X-User-ID")

        request.state.user_id = user_id
        structlog.contextvars.bind_contextvars(user_id=user_id)

        response = await call_next(request)
        return response
```

后续所有数据库查询、记忆检索、缓存操作都从 `request.state.user_id` 取值，保证不会出现跨用户数据泄露。

## 8. 数据流与状态流转

### 8.1 完整 Agent 执行生命周期

下面是一次完整的 AuditAgent 调用生命周期，展示了 Pre/Post Hook 链、记忆引擎、异常分支路由和硬约束校验如何协作：

```text
─────────────────────────────────────────────────────────────
                    PRE-PROCESSING HOOKS
─────────────────────────────────────────────────────────────
 ① AuthHook
    JWT → user_id → 角色 → task_id 权限 → 通过/403

 ② RateLimitHook
    Redis Sliding Window → user_id 频率检查 → 通过/429

 ③ MemoryHook
    user_id → SQLite 检索长期记忆（同类异常的历史处理方式）
    thread_id → Redis 检索短期记忆（本批次已处理的模式）
    thread_id → Redis 检索摘要（如已处理 > 20 笔）
    调用 MemoryManager.build_context() 组装 Context Window

 ④ ValidationHook
    输入数据完整性、金额精度、必填字段校验

 ⑤ CacheHook
    Redis 查 queue_id 是否已处理 → 命中返回缓存结果
─────────────────────────────────────────────────────────────
                    EXCEPTION ROUTING
─────────────────────────────────────────────────────────────
 ⑥ ExceptionRouter.route(bank_item, clear_item, diff)
    分支 1: 手续费匹配 → 自动处理，跳过 Agent
    分支 2: 重复入账 → TraceAgent
    分支 3: 日切窗口 → RAG + AuditAgent
    分支 4: 冲正关键词 → ExtractionAgent ∥ RAG → AuditAgent
    分支 5: 无规则匹配 → RAG (高阈值) + AuditAgent
─────────────────────────────────────────────────────────────
                    RAG PIPELINE (Subgraph)
─────────────────────────────────────────────────────────────
 ⑦ Query Rewrite → Dense召回 + BM25召回 → RRF融合 → Reranker → 过滤
─────────────────────────────────────────────────────────────
                    AGENT EXECUTION
─────────────────────────────────────────────────────────────
 ⑧ Agent 执行（Context Window = System + Memory + Summary + RAG + Item + Tools）
    LangGraph Checkpoint 保存状态
    输出结构化 JSON
─────────────────────────────────────────────────────────────
                    POST-PROCESSING HOOKS
─────────────────────────────────────────────────────────────
 ⑨ SchemaHook
    Pydantic model_validate → 失败重试 3 次 → 仍失败转人工

 ⑩ ConstraintHook
    硬约束校验：金额-风险一致性、evidence 非空、decision 枚举合法

 ⑪ DecisionHook
    confidence >= 0.85 → 直接落库
    0.6 <= confidence < 0.85 → 二级 Fallback（换 Prompt 角度）
    confidence < 0.6 → 三级 Fallback（TraceAgent 查历史）
    RAG 无命中 → PENDING_HUMAN（不触发 Fallback）

 ⑫ MemoryUpdateHook
    Redis ← 短期记忆
    Redis ← 更新摘要（累计满 20 笔触发压缩）
    SQLite ← 长期记忆（仅人工确认结果）

 ⑬ LogHook
    MySQL ← t_agent_execution_log
    MySQL ← t_rag_retrieval_log
    structlog ← JSON 日志
    LangFuse ← LLM trace

 ⑭ TransactionHook
    MySQL 事务写入台账 + 更新队列 + 更新任务统计
─────────────────────────────────────────────────────────────
```

### 8.2 状态定义

| 状态 | 含义 |
| --- | --- |
| `UPLOADED` | 文件已上传，等待处理 |
| `PRECHECKING` | 预处理中（字段清洗、规则引擎、异常分支路由） |
| `PENDING_AI` | 待 AI 审计 |
| `AI_RUNNING` | AI 审计中 |
| `AI_RETRYING` | AI 审计重试中（Schema/Constraint 失败） |
| `FALLBACK_L2` | 二级 Fallback 中 |
| `FALLBACK_L3` | 三级 Fallback 中 |
| `PENDING_HUMAN` | 待人工复核（Checkpoint 挂起） |
| `FIXED` | 已平账 |
| `UNRESOLVED` | 挂账或未解决 |
| `FAILED` | 系统处理失败（事务回滚） |
| `REPORTED` | 已生成报告 |

## 9. 量化指标体系

系统在关键节点埋点采集指标，支撑面试时的量化表达。以下为核心指标：

| 指标 | 含义 | 采集方式 | 目标口径 |
|------|------|---------|-----------|
| 自动平账率 | 规则引擎直接匹配的比例 | 任务统计表 | 演示数据目标 > 96% |
| Agent 审计准确率 | AuditAgent 建议被人工采纳的比例 | 人工复核表统计 | 人工标注样本目标 > 85% |
| RAG Recall@5 | 规则召回率 | 评测脚本自动计算 | 评测集目标 > 0.85 |
| RAG MRR | 平均倒数排名 | 评测脚本自动计算 | 评测集目标 > 0.70 |
| 单笔平均处理时延 | PreCheck 到台账落库耗时 | structlog 统计 | 本地演示目标 < 3s |
| Agent Schema 符合率 | JSON 输出一次通过 Pydantic 校验的比例 | 重试计数器 | 测试集目标 > 92% |
| 人工复核触发率 | 所有异常中最终转人工的比例 | 状态统计 | 演示数据目标 < 2% |
| Fallback 触发率 | 触发二级及以上 Fallback 的比例 | Agent 日志 | 演示数据目标 < 10% |
| LLM Token 消耗/任务 | 每批次对账的 Token 总消耗 | LangFuse | — |

面试时重点展示指标的采集方法和样本集，而不是只背数字。真正加分的是能打开评测报告，说明哪些 query 没命中、为什么没命中、下一步怎么改切片或改 Query Rewrite。

## 10. 数据与安全边界

本项目是个人开源学习项目，必须明确安全边界：

- 只使用模拟数据和脱敏数据。
- 模拟数据由项目人工构造，用于覆盖正常平账、金额差错、单边缺失、跨日切、冲正退款、手续费差异、重复入账和漏记账等场景。
- 不使用任何真实客户数据。
- 不使用任何银行内部资料。
- 公开制度依据只作为项目规则设计参考，不等同于真实银行内部审计制度。
- 项目自定义规则必须标注为演示规则。
- 不宣称系统可直接用于真实生产银行系统。
- AI 只做辅助分析和建议，不做最终金融决策。
- 金额计算、状态落库、人工审批由确定性代码和数据库事务保障。

## 11. MVP-0 / MVP / V1 / V2 架构演进

### 11.1 MVP-0：后端最小 AI 对账闭环

实现目标：

- 准备两份模拟 Excel。
- 通过 FastAPI 上传银行端流水和清算端流水。
- 使用 Pandas 完成字段校验、数据清洗和基础对账。
- 识别基础金额差错和单边缺失。
- RAG 能检索 Markdown 规则并返回来源（基础 Top-K + 相似度阈值）。
- AuditAgent 能输出结构化 JSON 审计建议（含 evidence 字段）。
- 结果写入 MySQL 差错台账。
- 通过 API 查询任务状态和差错明细。

### 11.2 MVP：本地产品闭环

实现目标：

- 通过 Vue 页面上传两份模拟 Excel。
- 任务看板展示对账统计。
- 完成跨日切样例处理。
- 完成模糊冲正样例处理。
- LangGraph 串联 PreCheckNode、ExtractionAgent、AuditAgent 和 HumanReviewNode。
- LangGraph Checkpoint 支持人工复核断点续跑。
- Agent 并行执行（ExtractionAgent ∥ RAG Subgraph）。
- RAG 混合检索（Dense + BM25 + RRF）+ Reranker + Query Rewrite。
- Hook 链基础实现（AuthHook、SchemaHook、ConstraintHook、LogHook）。
- 记忆引擎（Redis 短期记忆 + Redis 摘要 + SQLite 长期记忆）。
- 多租户中间件（X-User-ID 注入）。
- YAML 声明式规则引擎 + 异常分支路由。
- AI 无法判断时进入人工复核（多级 Fallback）。
- LangFuse + structlog 可观测性。
- 前端能查看任务、台账和复核项。

### 11.3 V1：在线作品

实现目标：

- Docker Compose 一键启动（含 Nginx）。
- Celery/ARQ 后台任务队列（对账异步执行，上传即时返回 task_id）。
- JWT 登录鉴权。
- SSE 展示 Agent 执行过程（含 Pre/Post Hook 状态、RAG 检索详情）。
- 支持手续费/批量业务差异。
- 支持 Markdown 审计报告。
- MCP 协议工具层（RAG Server、Ledger Server、Trace Server）。
- RAG 评测集（50+ query）+ 评测脚本（Recall@5/MRR/NDCG）。
- Agent Schema 符合性测试。
- 量化指标仪表板。
- README 含启动说明、演示数据和量化指标。
- 部署到云服务器。

### 11.4 V2：简历最终版

实现目标：

- 增强 TraceAgent（T+1 追溯、原流水匹配）和 ReportAgent（多维度分析）。
- 支持重复入账、漏记账和异常归因。
- RAG A/B 对比框架 + 失败样本分析。
- Agent 执行日志离线分析 + Prompt 版本管理。
- PDF 报告导出（含图表）。
- 压力测试与性能调优。

## 12. 面试可讲点

这个架构可以重点讲以下 12 件事：

1. **业务理解**：项目不是抽象 AI Demo，而是从银行对账、冲正、挂账和报表审计中抽象出来的 12 类异常场景。
2. **AI 边界**：金额计算、状态落库、审批结果不交给 LLM。四层硬约束保证门禁。
3. **异常分支**：不是简单的"对上了/没对上"，而是 12 个异常分支 + 规则树 + Agent + 多级 Fallback 的混合路由系统。
4. **RAG 价值**：混合检索 + Reranker + Query Rewrite 全链路优化，配有离线评测集和 Recall@5/MRR 量化指标。Agent 的审计判断必须有规则来源，没有依据就转人工。
5. **记忆引擎**：三层记忆（短期/长期/摘要），有状态 Agent 保证审计一致性，Redis + SQLite 双存储。
6. **Hook 链**：Pre-Hook 链（Auth → RateLimit → Memory → Validation → Cache）和 Post-Hook 链（Schema → Constraint → Decision → Memory → Log → Transaction），安全与质量门禁。
7. **多租户隔离**：user_id + thread_id 双重隔离，API 中间件强制注入，银行多操作员环境的安全底线。
8. **MCP 协议**：工具层标准化解耦，Agent 通过 MCP 协议调用 RAG、台账查询和流水追溯服务。
9. **可观测性**：LangFuse 全链路 Trace + structlog 结构化日志 + RAG 质量监控 + Token 成本追踪。
10. **后端能力**：FastAPI、Pydantic、MySQL 事务、SSE、JWT、Docker、Celery/ARQ 后台任务队列，全在系统里有具体用途。
11. **量化指标**：自动平账率、Agent 审计准确率、RAG Recall@5/MRR、Schema 符合率，每项技术选择都有数据支撑。
12. **学习路径**：MVP-0 → MVP → V1 → V2 四个版本的递进，体现了从核心链路验证到全功能产品的工程规划能力。
