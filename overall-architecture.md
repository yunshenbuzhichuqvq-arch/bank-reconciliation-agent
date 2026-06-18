# 《银企对账 Agent 系统》总体架构

## 1. 项目定位与架构目标

本项目是一个面向**银企对账**场景的 AI 应用系统。它把企业财务与银行对公业务中常见的大批量流水核对、差异定位、归因解释、人工复核和台账报告流程,抽象成一个可开发、可部署、可验证的 Agent 系统。

系统解决企业财务人员在大批量流水核对中耗时长、差异定位困难、人工复核压力大的问题:用户上传企业账簿 / ERP 明细与银行流水,系统完成字段标准化、金额计算、流水匹配、差异分类、RAG 规则检索、Agent 审计建议、人工复核和差错台账生成。典型异常包括:企业已记账但银行未到账、银行已到账但企业未入账、金额不一致、手续费 / 税费差异、摘要或客户名称不一致、重复记账、跨期入账。

系统的核心定位不是"让大模型替人算账",而是:

> 用确定性代码完成账务核对中的精确计算和状态落库,用 Agent 处理非结构化摘要、规则解释和审计报告生成,用 Human-in-the-Loop 保留金融场景中的人工复核边界,用 Agent 输出校验管线保证安全与合规底线。

### 1.1 通用对账引擎 + 场景化配置

系统底层是**一套通用 Reconciliation Engine + Scenario Profile**,当前只落地银企对账一个场景。

- **通用对账引擎(Reconciliation Engine)**:只认 `Source A`(主账源)和 `Source B`(对账账源)两个抽象账源,不认具体业务名词。引擎提供可复用的底层能力:文件解析、字段清洗、字段映射、Decimal 金额计算、三阶段匹配算法、异常分支路由、RAG 检索、ExtractionAgent / AuditAgent、HumanReviewNode、差错台账、审计报告、输出校验管线、结构化日志和评测体系。
- **场景化配置(Scenario Profile)**:由 `scenario_type` 选定,决定字段映射模板、`source_type` 语义、RAG 知识库路径、Prompt、异常类型集合、规则库、报告模板和阈值。

当前落地的唯一场景:

| scenario_type | Source A(source_type) | Source B(source_type) | 说明 |
|---|---|---|---|
| `BANK_ENTERPRISE` | 企业账簿 / ERP 明细 = `ENTERPRISE_BOOK` | 银行流水 = `BANK_STATEMENT` | 企业账簿 / ERP 明细与银行流水对账 |

引擎与具体业务解耦,**可扩展到其他对账场景(如银行内部清算对账)**:只需新增一份 Scenario Profile(字段模板 + 规则库 + Prompt + 知识库 + 报告模板),不改动引擎主链路。多场景隔离不在当前范围。

### 1.2 架构目标

架构设计同时服务四个目标:

1. **确定性 / LLM 边界清晰**:金额计算、状态落库绝不交给 LLM;LLM 只读确定性层产出的 READ-ONLY 结果。
2. **Agent 可约束、可追踪**:每次决策有 Schema、有硬约束、有 RAG 依据、有兜底、有结构化日志。
3. **AI 能力明确**:突出 RAG、Agent 编排、工具调用、结构化输出和审计溯源。
4. **设计可表达**:每个技术选择都能解释"为什么这么做",并有可真实测量的指标。

## 2. 总体架构

系统采用前后端分离架构。相比"全栈 + 运维"式的厚重分层,这里收敛为下面 7 个部分,重心放在 Agent 工程。RAG 是 Agent 编排层在审计时调用的子流程,不单列一层。

```text
┌────────────────────────────────────────────────────────────┐
│ 前端交互层  Vue 3 + Element Plus + ECharts                   │
│ 上传账单 | 任务看板 | Agent 流式工作台(SSE) | 人工复核 | 差错台账 | 指标 │
└────────────────────────────────────────────────────────────┘
                         │ HTTP / SSE
                         ▼
┌────────────────────────────────────────────────────────────┐
│ API 服务层  FastAPI + Pydantic(鉴权为普通中间件,JWT 可选)    │
│ 文件上传 | 任务创建 | 状态查询 | 工作流启动 | 人工审批 | 台账查询 | 报告导出 │
└────────────────────────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
┌────────────────────────┐  ┌────────────────────────────────┐
│ 确定性计算层             │  │ Multi-Agent 编排层  LangGraph    │
│ Pandas 清洗 | 三阶段匹配 │  │ ExtractionAgent | AuditAgent    │
│ YAML 规则 | Decimal 计算 │  │ 状态机 + 条件路由 + 三级 Fallback │
│ 异常分支路由 | 事务写入   │  │ (审计时调用 RAG 子流程)          │
└────────────────────────┘  └────────────────────────────────┘
            │                         │
            └────────────┬────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ Agent 输出校验管线(护栏)                                     │
│ Schema 校验(+有界重试) → 硬约束校验 → 决策/Fallback 路由 → 事务落库 │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 数据与知识层  MySQL 8.0(事务) + ChromaDB + Redis(缓存/限流/幂等) │
│ 任务 | 流水 | 待核验队列 | 差错台账 | 复核记录 | Agent日志 | RAG文档 | 报告 │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 可观测性与评测层  structlog + 可回放 trace + token 成本 + Prompt 版本 + RAG 评测 │
└────────────────────────────────────────────────────────────┘
```

### 2.1 前端交互层

前端使用 Vue 3、Element Plus 和 ECharts,目标不是做营销页面,而是做一个可以真实演示业务流程的工作台。

核心页面:

- 账单上传页:上传主账源 Source A(企业账簿 / ERP 明细)与对账账源 Source B(银行流水)。
- 任务看板:展示总笔数、自动平账数、AI 审计中、待人工复核、挂账数。
- Agent 流式工作台:通过 SSE 展示 Agent 当前处理步骤、工具调用和 RAG 命中依据。
- 人工复核页:展示双账源流水、AI 推荐理由、RAG 来源和人工操作按钮。
- 差错台账页:查询已确认差错、挂账、冲正、手续费差异等记录。
- 量化指标面板:展示自动平账率、Agent 采纳率、RAG 评测指标、token 成本趋势。

### 2.2 API 服务层

后端使用 FastAPI 作为统一入口,负责文件上传、任务管理、工作流启动、人工审批、台账查询和报告导出。

关键能力:

- Pydantic 请求和响应校验。
- 鉴权为**普通中间件**:阶段一 / 二用 `X-User-ID: demo_user` 模拟身份,阶段三可选 JWT 登录。若启用 JWT,所有业务查询按其带出的 `user_id` 做行级过滤。
- SSE 流式推送 Agent 执行过程。
- 统一异常处理和审计日志。
- 环境变量管理数据库、模型 Key、向量库路径等配置。

> 完整的多租户三级隔离不在当前范围,见 §11 可扩展方向。

### 2.3 确定性计算层

确定性计算层处理所有必须精确、可复现、可审计的动作,并承担异常分支路由职责。

职责:

- 文件解析与 Excel 字段清洗、标准化、字段映射。
- 双账源(Source A / Source B)流水匹配(三阶段匹配算法)。
- 金额差异计算(`decimal.Decimal`,多币种精度上下文)。
- **异常分支路由**:基于声明式规则 YAML 的决策树,把异常分发到对应处理分支(银行未到账、企业未入账、金额不一致、手续费 / 税费差异、重复记账、跨期入账);确定性规则能覆盖的直接处理,无法覆盖的才进入 Agent 链路。
- MySQL 事务写入。

本层核心原则:**凡是金额计算、状态更新、数据库写入,不交给 LLM。**

#### 2.3.1 三阶段流水匹配算法

```text
阶段 1: 精确匹配(HASH JOIN)
  - 条件: source_a.flow_id == source_b.flow_id AND source_a.amount == source_b.amount
  - 结果: AUTO_FIXED,直接平账

阶段 2: 模糊匹配(Composite Index Probe)
  - 条件: source_a.amount == source_b.amount AND source_a.trade_time.date() == source_b.trade_time.date()
         AND (source_a.counterparty_account LIKE '%' + source_b.counterparty_key + '%')
  - 结果: 候选匹配 → 人工 / Agent 确认

阶段 3: 单边残留识别(Anti-Join)
  - 条件: 阶段 1 + 阶段 2 均未匹配的流水
  - 结果: 标记为单边残留(SINGLE_SIDE)→ 路由到对应分支
          (企业已记账银行未到账 / 银行已到账企业未入账 / 跨期入账)
```

#### 2.3.2 声明式规则引擎

规则不硬编码为 if-else,而是用 YAML 定义,程序启动时加载并动态执行。规则 ID 带场景前缀(`BE-` 银企),便于未来扩展多场景时隔离。

```yaml
# scenario_type: BANK_ENTERPRISE(银企对账规则库节选)
rules:
  - id: BE-R001
    name: 精确匹配自动平账
    priority: 1
    conditions:
      - { field: amount_diff, operator: eq, value: 0 }
      - { field: flow_id, operator: matched }
    action: AUTO_FIX

  - id: BE-R002
    name: 金额差异进入审计
    priority: 2
    conditions:
      - { field: amount_diff, operator: neq, value: 0 }
      - { field: flow_id, operator: matched }
    action: PENDING_AI
    error_type: AMOUNT_MISMATCH
    agent_type: AuditAgent

  - id: BE-R003
    name: 手续费 / 税费差异检测
    priority: 3
    conditions:
      - { field: amount_diff, operator: in_set, value: [0.50, 1.00, 2.00, 5.00, 10.00, 100.00] }
    action: PENDING_AI
    error_type: FEE_TAX_DIFF
    agent_type: AuditAgent
    rag_query: "手续费 税费 差异处理规则"

  - id: BE-R004
    name: 银行已到账企业未入账单边检测
    priority: 4
    conditions:
      - { field: match_status, operator: eq, value: SINGLE_SIDE }
      - { field: present_side, operator: eq, value: B }
    action: PENDING_AI
    error_type: BOOK_UNRECORDED
    agent_type: AuditAgent
```

**设计决策**:规则与代码分离,业务人员可直接维护 YAML 文件;规则支持优先级排序,高优先级先匹配;同一笔异常只会命中一条规则,避免冲突。这体现的是 AI 应用开发中的边界意识——不是让 AI 替代所有逻辑,而是让 AI 补足传统规则难处理的语义理解和归因解释。

### 2.4 Multi-Agent 编排层

Multi-Agent 编排层使用 LangGraph 实现状态机和节点路由。Agent 不是多个聊天机器人,而是带状态、工具、边界和失败兜底的业务节点。**主链路只有 2 个 Agent**(ExtractionAgent + AuditAgent),TraceAgent 作为可选增强。

- `PreCheckNode`:规则预处理节点,不依赖 LLM,完成基础对账和异常分类。
- `ExtractionAgent`:提取 Agent,将不规范摘要 / 户名结构化为标准 JSON。
- `AuditAgent`:审计 Agent,结合规则、RAG 和工具结果做审计判断。
- `HumanReviewNode`:人工复核节点,挂起流程并等待人工审批。
- `TraceAgent`(**可选**):追溯 Agent,处理跨期入账、后续到账与原始凭证追溯,作为 Fallback L3 的增强。

> 报告生成不设独立 Agent:统计走 SQL 聚合 + Markdown 模板,LLM 只做文字润色(可选)。

#### 2.4.1 条件路由(显式建模非 happy-path)

```text
START
  → PreCheckNode(三阶段匹配 + YAML 规则 + 异常分支路由)
  → 确定性规则可覆盖 → 直接写台账
  → 规则无法覆盖,按 exception_branch 路由:
       AMOUNT_MISMATCH / FEE_TAX_DIFF        → RAG → AuditAgent
       BANK_UNARRIVED / BOOK_UNRECORDED      → RAG → AuditAgent(必要时 TraceAgent)
       NARRATIVE_NAME_MISMATCH               → ExtractionAgent → RAG → AuditAgent
       DUPLICATE_BOOKING / CROSS_PERIOD      → (可选 TraceAgent)→ AuditAgent
  → Agent 输出校验管线
  → confidence ≥ 0.85 → 落库;否则进入多级 Fallback
  → Fallback 耗尽 / RAG 无命中 → HumanReviewNode(挂起)
  → 人工审批 → 恢复执行 → END
```

价值在于显式建模了出错、低置信、工具失败、无依据等**非 happy-path 分支**,而不是只跑通"对上了"的乐观路径。

ExtractionAgent(语义提取)和 RAG 检索(规则召回)在同一笔异常上原则上可以并行,通过 LangGraph 的 `Send` API 汇聚结果给 AuditAgent;是否并行依据真实 LLM 延迟数据决定,若 RAG 在本地显著快于 LLM 则保持串行,避免不必要的并行复杂度。

#### 2.4.2 多级 Fallback 策略

3 级递进 Fallback,而不是简单的"低置信就转人工"——这是本系统的关键设计决策之一。原"三层记忆引擎"被收敛为这里 L2 的历史 few-shot:Agent 决策不再依赖独立的记忆子系统,而是在 Fallback 时按需检索历史人工确认案例。

```text
AuditAgent L1(标准):System Prompt + RAG 规则原文 + 当前异常项
  confidence ≥ 0.85 → 落库
  否则 → L2(few-shot 增强):
        注入 2-3 个同类异常的历史人工确认案例(来自差错台账)
        confidence ≥ 0.85 → 落库
        否则 → L3(可选追溯 / 换 Prompt 角度):
              TraceAgent 追溯关联流水,或切换审计视角再判
              confidence ≥ 0.85 → 落库
              否则 → PENDING_HUMAN

RAG 无命中 → 直接 PENDING_HUMAN,不触发 Fallback(没有依据就没有推理基础)
```

#### 2.4.3 Checkpoint 断点续跑

人工复核节点(HumanReviewNode)支持挂起和恢复:

- 使用 LangGraph 的 `SqliteSaver` 持久化图状态(无需额外数据库)。
- 人工审批通过 / 拒绝后,从 Checkpoint 恢复执行,继续后续节点。
- 避免从头重跑整个任务,节省 LLM Token 和时间。
- 支持中断恢复的幂等性:同一 queue_id 重复审批不会产生重复台账记录。

### 2.5 Agent 输出校验管线(护栏)

这是原"Hook 链与硬约束层"的重定位。它不再承担鉴权 / 限流 / 缓存 / 记忆注入,只做一件事:**保证 Agent 的输出在落库前通过门禁**。鉴权下沉为普通 API 中间件;限流和结果缓存归入 LLM 客户端封装层;记忆相关环节随记忆引擎一并移除。

#### 2.5.1 四阶段管线

```text
① Schema 校验
   Pydantic model_validate;失败 → 有界重试(≤ 3 次,每次调整 Prompt 角度)→ 仍失败转人工

② 硬约束校验
   C1–C6 业务约束;失败直接转人工(不重试,业务规则不应被绕过)

③ 决策 / Fallback 路由
   confidence ≥ 0.85           → 直接落库
   0.6 ≤ confidence < 0.85     → 进入 Fallback L2
   confidence < 0.6            → 进入 Fallback L3
   RAG 无命中                  → PENDING_HUMAN(不触发 Fallback)

④ 事务落库
   MySQL 事务写台账 + 队列更新 + 任务统计;
   副作用(structlog 日志、token 成本记录)非阻塞、失败不影响主流程
```

#### 2.5.2 四层硬约束体系

| 层级 | 约束内容 | 实现机制 |
|------|---------|---------|
| L1 输入约束 | 金额精度、流水号格式、日期范围、必填字段 | Pydantic validator |
| L2 计算约束 | 金额差异 = Decimal(source_a) − Decimal(source_b),LLM 只读不可修改 | 工具函数返回计算结果,Prompt 标注 READ-ONLY |
| L3 输出约束 | Schema 符合、decision 枚举、evidence 非空、风险-金额一致性 | Pydantic model_validate + field_validator |
| L4 数据库约束 | 事务原子性、外键完整性、CHECK 约束、唯一约束防重复 | MySQL InnoDB 事务 + 表结构约束 |

具体约束项 C1–C6:

| 约束 | 内容 |
|---|---|
| C1 | `decision` ∈ {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED} |
| C2 | `evidence` 不能为空列表 |
| C3 | `|diff| > 10000` 时 `risk_level` 不能为 LOW |
| C4 | `decision = PENDING_HUMAN` 时 `reason` 必须说明依据不足的具体原因 |
| C5 | `decision = AUTO_FIXED` 时 `confidence` 必须 ≥ 0.85 |
| C6 | RAG 无命中或 `best_score < 0.5` 时禁止 `decision = AUTO_FIXED` |

**设计决策**:金融系统不允许 LLM 自由发挥。事务写入从校验管线中独立出来作为基础设施保障(先校验、后事务、再非阻塞副作用),保证 Agent 输出必须通过所有门禁才能落库,整个过程可审计、可复现、可回滚。

### 2.6 数据与知识层

降到标准工程水平:**不使用 HASH 分区、物化视图、JSON 虚拟列索引**等高级特性,改为标准建表 + 合理索引。

| 存储 | 用途 | 说明 |
|------|------|------|
| MySQL 8.0 | 任务 / 流水 / 队列 / 差错台账 / 复核记录 / Agent 日志 / RAG 日志 / 报告 | 标准建表 + 合理索引;关键写入走 InnoDB 事务 |
| ChromaDB | 规则知识库向量索引 | 同时存储 Dense vector 与 Sparse metadata,支持混合检索 |
| Redis | **仅** LLM 结果缓存、API 调用限流、幂等去重 | 不再用于记忆引擎;阶段三引入 |
| SQLite | 测试库 + LangGraph Checkpoint 持久化 | 不再承担长期记忆 |

MySQL 主要业务表:对账任务、主账源流水 `t_source_a_transaction`、对账账源流水 `t_source_b_transaction`、待核验队列、差错台账、人工复核记录、Agent 执行日志、RAG 检索记录、审计报告。所有查询按需带 `user_id`(启用 JWT 时)和 `scenario_type`(预留多场景)。完整 DDL 见 PRD §6。

### 2.7 可观测性与评测层

大模型应用区别于传统软件的核心工程问题。本层产物必须可展示:

- **结构化日志**:`structlog` 输出 JSON,每条携带 `trace_id`、`agent_name`、`step`、`prompt_version`。
- **可回放 trace**:`logs/*.jsonl` 能回放单笔异常的规则命中、RAG 命中、Agent 输出和落库结果。
- **token 成本统计**:每次 LLM 调用的 token 消耗与按模型定价折算的成本。
- **Prompt 版本管理**:Prompt 以独立文件纳入版本控制,`t_agent_execution_log.prompt_version` 让每次决策可追溯到具体版本。
- **RAG 评测集**:手写 `(query, expected_rule_ids)`,每次调整切片策略或检索参数后跑评测脚本,输出 Recall@5、MRR、NDCG@5。
- **Agent Schema 符合性测试**:用 Pytest + Pydantic `model_validate`,对每种异常类型构造 mock 输入,验证 Agent 输出符合 Schema,统计通过率。
- **LangFuse**:可选,作为 trace 可视化增强,不作为必需依赖。

没有上述证据时,相关指标只作为目标,不写成"已经达到"。

### 2.8 工程化与部署

- 本地:FastAPI(`uvicorn --reload`)+ Vue(Vite)+ 本地 MySQL / ChromaDB。
- 阶段三:ARQ 异步任务队列(上传即返回 task_id,Agent 后台异步执行)、Redis(缓存 / 限流 / 幂等)、SSE 实时推送、量化指标面板、**Docker Compose 一键启动**(Docker 直接暴露端口,无 Nginx)。
- (可选加分项)云服务器部署。

## 3. 核心设计原则

### 3.1 规则优先,AI 补充

能用确定性规则解决的问题,不交给大模型。系统采用"YAML 声明式规则引擎 + 异常分支决策树"双层机制,规则可覆盖的分支直接处理,无法覆盖的才进入 Agent + RAG 链路。

**设计决策**:这体现的是 AI 应用开发中的边界意识——不是让 AI 替代所有逻辑,而是让 AI 补足传统规则难处理的语义理解和归因解释。

### 3.2 金额计算绝不交给 LLM

金融账务中的金额计算必须可复现、可验证、可审计。系统统一使用 Python `decimal.Decimal` 和 MySQL 事务保证精确性,不同币种使用 `decimal.localcontext` 控制精度(如 JPY 0 位小数、CNY 2 位小数)。

Agent 只能读取工具返回的计算结果,Prompt 中标注为 READ-ONLY:

```json
{
  "source_a_amount": "1000.00",
  "source_b_amount": "990.00",
  "diff": "10.00",
  "_note": "READ-ONLY: computed by deterministic layer"
}
```

### 3.3 RAG 无据不判定

涉及银行未到账 / 企业未入账、跨期入账、手续费 / 税费差异等业务判断时,Agent 不能凭借预训练知识直接给结论,必须先从 RAG 知识库检索到规则依据。如果没有命中规则或命中分数低于阈值,系统强制进入 `PENDING_HUMAN`,不触发 Fallback。

### 3.4 护栏门禁

Agent 输出不直接落库,必须通过校验管线的 Schema 校验、硬约束校验和事务落库。任何一环失败即触发重试或转人工。详见 §2.5。

### 3.5 Human-in-the-Loop 兜底

金融场景中 AI 推荐不能等同于最终处理结果。只要出现低置信度、无规则依据、高风险金额、工具调用失败等情况,流程必须进入人工复核。

人工复核需要记录:操作人、操作时间、操作动作(确认平账 / 强制挂账)、人工备注、AI 推荐理由、RAG 来源。人工确认的最终结果会作为后续同类异常的 Fallback few-shot 案例,影响后续 Agent 判断。

### 3.6 全链路可追踪

系统记录每一次 Agent 决策过程,包括 `scenario_type`、`source_side`、输入、工具调用、RAG 命中片段、输出 JSON、校验管线结果、路由结果和错误信息。目的:① 方便开发阶段调试 Agent 行为;② AI 判断可追踪——不是黑盒,有日志、有依据、有兜底。

## 4. Multi-Agent 协作架构

### 4.1 全局状态结构

LangGraph 中各节点共享 `ReconciliationState`。相比原设计,去掉了多租户(`thread_id`)和三层记忆字段,新增 `historical_cases` 承载 Fallback few-shot:

```python
from typing import Any, Dict, List, Optional, TypedDict

class ReconciliationState(TypedDict):
    task_id: str
    user_id: str                    # 启用 JWT 时用于行过滤,默认 demo_user
    scenario_type: str              # 默认 BANK_ENTERPRISE,预留多场景扩展
    current_queue_id: Optional[int]
    source_a_item: Dict[str, Any]   # 主账源:企业账簿 / ERP
    source_b_item: Dict[str, Any]   # 对账账源:银行流水
    error_type: Optional[str]
    exception_branch: Optional[str] # 异常分支路由结果
    math_result: Dict[str, str]     # Decimal 计算结果(READ-ONLY)
    extraction_result: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    historical_cases: List[Dict[str, Any]]  # Fallback L2 注入的历史人工确认案例(few-shot)
    audit_decision: Dict[str, Any]
    confidence: Optional[float]
    retry_count: int
    fallback_level: int             # 当前 Fallback 层级(0/1/2)
    next_action: str
    error_message: Optional[str]
    agent_logs: List[Dict[str, Any]]
```

### 4.2 节点职责

| 节点 | 类型 | 职责 | 阶段 |
| --- | --- | --- | --- |
| `PreCheckNode` | 确定性代码 | YAML 规则引擎、三阶段匹配、异常分支路由 | 一 |
| `ExtractionAgent` | LLM Agent(DeepSeek V4 Pro) | 模糊摘要 / 户名结构化,输出 JSON | 二 |
| `AuditAgent` | LLM Agent(DeepSeek V4 Pro) | 结合计算结果和 RAG 依据输出结构化审计建议 | 一(确定性)→ 二(LLM) |
| `HumanReviewNode` | 状态节点 | 挂起流程,等待人工审批(支持 Checkpoint 恢复) | 一(基础)→ 二(Checkpoint) |
| `TraceAgent` | LLM(**可选**) | 跨期入账、后续到账与原始凭证追溯,Fallback L3 增强 | 可选 |

### 4.3 路由规则

```text
START
  → 上传并解析 source_a_file / source_b_file
  → PreCheckNode 完成字段校验、数据清洗、三阶段匹配和异常分支路由
  → 确定性规则可覆盖的异常 → 直接写入台账
  → 确定性规则无法覆盖,按 exception_branch:
       EXACT_MATCH                     → 直接写入台账
       AMOUNT_MISMATCH / FEE_TAX_DIFF  → RAG → AuditAgent
       BANK_UNARRIVED / BOOK_UNRECORDED→ RAG → AuditAgent(必要时 TraceAgent 追溯)
       NARRATIVE_NAME_MISMATCH         → ExtractionAgent → RAG → AuditAgent
       DUPLICATE_BOOKING               → (可选 TraceAgent)→ AuditAgent
       CROSS_PERIOD_POSTING            → RAG →(可选 TraceAgent)→ AuditAgent
  → Agent 输出校验管线
  → confidence ≥ 0.85 → 写入台账
  → confidence < 0.85 → 多级 Fallback
  → Fallback 耗尽 → HumanReviewNode(Checkpoint 挂起)
  → 人工审批完成 → 恢复执行 → END
```

### 4.4 失败处理

- JSON 解析失败:最多重试 3 次,每次更换 Prompt 角度。仍失败则转人工。
- RAG 未命中:直接转人工,不触发 Fallback(没有依据就不能判断)。
- 工具调用失败:记录日志并转人工。
- 数据库事务失败:回滚并标记任务失败,保留输入数据以便恢复。
- Agent 输出不符合 Schema:校验管线 ① 拒绝落库并触发重试。
- 硬约束校验失败:拒绝落库并转人工(硬约束失败不重试,因为业务规则不应被绕过)。
- DeepSeek API 不可用:熔断 → 降级为确定性规则 → 全部标记 PENDING_HUMAN。

## 5. 异常分支网络设计

异常分支是本系统业务复杂度的核心体现。系统不是简单的"对上了 / 没对上",而是覆盖真实银企对账中的各类差错场景,共用"确定性规则树 → Agent → Fallback"路由机制。

### 5.1 银企对账异常分支(Source A = 企业账簿 / ERP,Source B = 银行流水)

```text
匹配上但有差异
  │
  ├─ BE-R001: 金额一致、流水 / 对手可匹配 → EXACT_MATCH → 自动平账
  ├─ BE-R002: 流水可关联但金额不一致 → AMOUNT_MISMATCH → AuditAgent
  ├─ BE-R003: 差异 ∈ 手续费 / 税费特征集 → FEE_TAX_DIFF → AuditAgent + 手续费 / 税费规则 RAG
  └─ BE-R004: 金额一致但摘要 / 客户名称不一致 → NARRATIVE_NAME_MISMATCH → ExtractionAgent → AuditAgent

单边存在(一端有、另一端无)
  │
  ├─ BE-R005: 企业账簿(A)有、银行(B)无 → BANK_UNARRIVED(企业已记账、银行未到账)
  │           → AuditAgent(必要时 TraceAgent 查后续到账)
  ├─ BE-R006: 银行(B)有、企业账簿(A)无 → BOOK_UNRECORDED(银行已到账、企业未入账)→ AuditAgent
  └─ BE-R007: 入账日期跨会计期间(A/B 期间不一致)→ CROSS_PERIOD_POSTING → (可选 TraceAgent)+ AuditAgent

重复检测
  │
  └─ BE-R008: 同主体 + 同金额 + 同对手,疑似一端多记 → DUPLICATE_BOOKING → (可选 TraceAgent)→ AuditAgent
```

### 5.2 路由架构

系统采用"确定性规则树 → Agent → Fallback"的混合路由:

- **确定性规则树**(Rule Engine)先执行:基于 YAML 规则和条件分支,能确定的直接处理。
- **Agent + RAG**:规则无法覆盖的进入 Agent 链路,RAG 检索知识库提供依据。
- **多级 Fallback**:Agent 低置信度时逐级递进,最终兜底到人工复核。

> 引擎的分支定义与规则 ID 已按 `scenario_type` 命名(`BE-`),**可扩展到其他场景**(如清算对账的 `BC-` 分支),当前不实现。

## 6. RAG 合规知识库与业务规则中心

RAG 是本项目的核心模块,不只是给 Agent 补充上下文。它承担"规则依据、业务解释、审计溯源"三类职责。

### 6.1 数据来源与证据流

```text
人工构造模拟数据(source_a 企业账簿 / source_b 银行流水)
  → Pandas 清洗、字段映射和规则对账
  → 异常交易上下文
  → RAG 混合检索(Dense + Sparse → Rerank → Filter)
  → AuditAgent 生成结构化审计建议
  → MySQL 保存差错台账、RAG 来源和审计结果
```

数据来源只使用人工构造的模拟数据,客户姓名、账号、流水号、金额和摘要均为虚构或脱敏样式。审计依据由三层组成:

- **公开制度依据**:人民银行公开支付结算制度、银行结算账户管理制度,以及财政部公开会计基础工作、企业内部控制和会计档案管理规范。
- **项目自定义业务规则**:面向演示场景编写的 Markdown 规则(基础匹配、企业未记账、银行未到账、手续费 / 税费差异、重复记账、跨期入账、人工复核)。
- **运行证据**:RAG 命中的规则来源、相似度分数、Reranker 得分、AuditAgent 输出 JSON、人工复核记录和差错台账记录。

### 6.2 RAG 解决的问题

1. **防止幻觉**:Agent 没有检索到规则时不能自动判定。
2. **规则可维护**:业务规则写成 Markdown 文档,而不是全部塞进 Prompt。
3. **审计可追溯**:每个关键判断保存引用来源。
4. **对齐 Agent 工程技能**:覆盖文档处理、切片、Embedding、向量检索、BM25 稀疏检索、Rerank、评测。

### 6.3 知识库内容

当前只建银企对账一个库;**可按 scenario_type 扩展为多库隔离**(如新增 `bank_clearing/`),当前不实现。

```text
rag_knowledge/
  bank_enterprise/   # 银企对账规则库
    basic_matching.md          基础匹配规则
    enterprise_unbooked.md     企业未记账规则
    bank_unarrived.md          银行未到账规则
    fee_tax_diff.md            手续费 / 税费差异规则
    duplicate_booking.md       重复记账规则
    cross_period.md            跨期入账规则
    human_review.md            人工复核规则
```

### 6.4 增强 RAG 流程

```text
规则文档 Markdown
  → 文档清洗
  → 结构化切片(按 ## 标题 + 语义边界混合策略)
  → Dense 向量化(中文 Embedding) + Sparse 索引(BM25,jieba 分词)
  → 存入 ChromaDB(同时存储 dense vector 和 sparse metadata)
  → Query Rewrite(LLM 把自然语言映射为规则术语,可开关)
  → 双路召回:Dense Top-20 + BM25 Top-20
  → RRF(Reciprocal Rank Fusion)融合排序,取 Top-10
  → Cross-Encoder Reranker(默认轻量模型,可换 BGE-Reranker-v2-m3)精排,取 Top-5
  → Dense / Reranker 双阈值过滤
  → 返回 rag_context 给 AuditAgent
  → 保存 rag_source、检索分数、Reranker 分数和最终使用的 chunk
```

### 6.5 查询改写(Query Rewrite)

对账术语和自然语言之间存在语义 Gap("这笔流水为什么没对上" vs 规则文档里的"单边账处理规则"),直接做向量检索容易漏召回。中间加一层 LLM 做查询改写:

```text
Input:  "这笔流水为什么没对上"
Output: "单边账 银行未到账 流水匹配失败 处理规则"
```

**设计决策**:查询改写是否有效用同一评测集对比"纯 Dense 检索"和"Query Rewrite + Hybrid + Reranker",用 Recall@5/MRR/NDCG 量化;评测脚本跑通前,不把提升幅度写成实测结论。

### 6.6 为什么选择 Cross-Encoder Reranker

Bi-Encoder(Embedding 模型)速度快、可预计算,但 query 和 document 独立编码、丢失交互信息;Cross-Encoder 把 query 和 document 拼接后一起过模型、做全文交互打分,精度显著更高但速度慢。系统采用"粗排 + 精排":先用 Bi-Encoder 双路召回 20 条候选,再用 Cross-Encoder Reranker 对 Top-10 精排取 Top-5。

Reranker 默认使用**本地轻量模型**(无 API 调用成本、离线可用);需要更高中文精度时可切换到 BGE-Reranker-v2-m3。

### 6.7 无命中策略

如果 RAG 没有命中可用规则(Dense 分数 < 0.5 且 Reranker 分数 < 0.3),`AuditAgent` 必须输出:

```json
{
  "decision": "PENDING_HUMAN",
  "reason": "未检索到足够的业务规则或合规依据,转人工复核",
  "rag_source": [],
  "fallback_applied": false
}
```

注意:RAG 无命中时**不触发 Fallback**,直接转人工。因为没有规则依据就没有推理基础。

## 7. 数据流与状态流转

### 7.1 完整 Agent 执行生命周期

下面是一次完整的 AuditAgent 调用生命周期,展示异常分支路由、RAG 子流程和输出校验管线如何协作:

```text
─────────────────────────────────────────────────────────────
                    输入与鉴权(普通中间件)
─────────────────────────────────────────────────────────────
 鉴权中间件:X-User-ID(阶段三可选 JWT)→ user_id 行过滤
 LLM 客户端封装:限流 + 结果缓存(Redis)
─────────────────────────────────────────────────────────────
                    异常路由 EXCEPTION ROUTING
─────────────────────────────────────────────────────────────
 ExceptionRouter.route(source_a_item, source_b_item, diff)
    金额不一致 → RAG + AuditAgent
    手续费 / 税费差异 → 规则命中后 RAG + AuditAgent
    银行未到账 / 企业未入账 → RAG + AuditAgent(必要时 TraceAgent)
    摘要 / 户名不一致 → ExtractionAgent → RAG → AuditAgent
    重复记账 / 跨期入账 → (可选 TraceAgent)→ AuditAgent
─────────────────────────────────────────────────────────────
                    RAG 子流程
─────────────────────────────────────────────────────────────
 Query Rewrite → Dense 召回 + BM25 召回 → RRF 融合 → Reranker → 阈值过滤
─────────────────────────────────────────────────────────────
                    AGENT 执行
─────────────────────────────────────────────────────────────
 Context = System Prompt + RAG Context + Current Item + Tool Results
          (+ Fallback L2 时注入历史人工确认案例)
 LangGraph Checkpoint 保存状态
 输出结构化 JSON
─────────────────────────────────────────────────────────────
                    输出校验管线
─────────────────────────────────────────────────────────────
 ① Schema 校验:model_validate → 失败重试 ≤ 3 次 → 仍失败转人工
 ② 硬约束校验:C1–C6(金额-风险一致性、evidence 非空、decision 枚举合法 …)
 ③ 决策 / Fallback 路由:落库 / L2 / L3 / 转人工
 ④ 事务落库:MySQL 事务写台账 + 队列 + 任务统计
            副作用(structlog 日志、token 成本)非阻塞
─────────────────────────────────────────────────────────────
```

### 7.2 状态定义

| 状态 | 含义 |
| --- | --- |
| `UPLOADED` | 文件已上传,等待处理 |
| `PRECHECKING` | 预处理中(字段清洗、规则引擎、异常分支路由) |
| `PENDING_AI` | 待 AI 审计 |
| `AI_RUNNING` | AI 审计中 |
| `AI_RETRYING` | AI 审计重试中(Schema / Constraint 失败) |
| `FALLBACK_L2` | 二级 Fallback 中 |
| `FALLBACK_L3` | 三级 Fallback 中 |
| `PENDING_HUMAN` | 待人工复核(Checkpoint 挂起) |
| `FIXED` | 已平账 |
| `UNRESOLVED` | 挂账或未解决 |
| `FAILED` | 系统处理失败(事务回滚) |
| `REPORTED` | 已生成报告 |

## 8. 量化指标体系

系统在关键节点埋点采集指标。只保留会真实测量的指标,逐条标注**目标 / 实测**口径;未测量项只标目标,不写成系统结果。

| 指标 | 含义 | 采集方式 | 口径 |
|------|------|---------|------|
| 自动平账率 | 规则引擎直接匹配的比例 | 任务统计表 | 实测(演示数据目标 > 95%) |
| Agent 审计采纳率 | AuditAgent 建议被人工采纳的比例 | 人工复核表统计 | 目标 > 85%(需人工标注样本) |
| RAG Recall@5 | 规则召回率 | 评测脚本 | 实测(目标 ≥ 0.85) |
| RAG MRR | 平均倒数排名 | 评测脚本 | 实测(目标 ≥ 0.70) |
| Agent Schema 一次通过率 | JSON 输出一次通过 Pydantic 校验的比例 | 校验管线计数 | 实测(目标 > 92%) |
| 人工复核触发率 | 所有异常中最终转人工的比例 | 状态统计 | 实测 |
| Fallback 触发率 | 触发二级及以上 Fallback 的比例 | Agent 日志 fallback_level | 实测 |
| LLM Token 消耗 / 成本 | 每批次对账的 token 总消耗与折算成本 | 日志聚合 | 实测 |

评估重点:能打开评测报告说明哪些 query 没命中、为什么没命中、下一步怎么优化切片或 Query Rewrite。已删除 P50/P95/P99 时延分位与 SLA 目标表(属 SRE 信号,非本项目核心)。

## 9. 数据与安全边界

本项目是个人开源学习项目,明确安全边界:

- 只使用模拟数据和脱敏数据,数据由项目人工构造,覆盖银企对账各类异常(企业已记账银行未到账、银行已到账企业未入账、金额不一致、手续费 / 税费差异、摘要 / 客户名不一致、重复记账、跨期入账)。
- 不使用任何真实客户数据或银行内部资料。
- 公开制度依据只作为项目规则设计参考,不等同于真实银行内部审计制度;项目自定义规则标注为演示规则。
- 不宣称系统可直接用于真实生产银行系统。
- AI 只做辅助分析和建议,不做最终金融决策;金额计算、状态落库、人工审批由确定性代码和数据库事务保障。

## 10. 阶段演进与当前进度

六阶段(MVP-0 ~ V2)收敛为三阶段。当前进度如实标注(2026-06)。

### 阶段一 · 最小闭环  ✅ 基本完成

- 准备 source_a / source_b 两份模拟 Excel(`scenario_type = BANK_ENTERPRISE`)。
- FastAPI 上传 → Pandas 字段校验 / 清洗 / 映射 → 三阶段匹配 → 异常识别。
- YAML 声明式规则引擎 + ExceptionRouter(核心分支)。
- AuditAgent 真实 LLM 调用:结构化 JSON 输出 + Schema 校验 + 有界重试 + 兜底转人工。
- 基础 RAG:Markdown 规则 + ChromaDB Top-K + 相似度阈值。
- MySQL 任务 / 流水 / 队列 / 台账落库;Vue 上传 / 看板 / 台账 / 复核页。
- 能打出一条完整本地 trace。

### 阶段二 · Agent 工程做深  🔶 大部分完成

- LangGraph 状态机 + 条件路由(显式建模非 happy-path 分支)。
- ExtractionAgent 接入;三级 Fallback(L1 标准 → L2 历史 few-shot → L3 可选追溯)。
- 增强 RAG:Dense + BM25 + RRF + Cross-Encoder Reranker(默认轻量,可换 BGE)+ Query Rewrite(可开关)。
- Agent 输出校验管线 4 阶段 + 硬约束 C1–C6。
- Prompt 独立文件 + 版本管理;structlog 覆盖所有 LLM 调用点。
- 工具调用权限边界(L0 只读 / L1 结构化输出 / L2 禁止直写库)。
- RAG 评测集(真实 Recall@5/MRR)+ Agent 决策质量评估(统计方法)。

### 阶段三 · 作品化  🚧 进行中

- Vue 工作台 + SSE 展示 Agent 执行;ARQ 异步队列;Redis(缓存 / 限流 / 幂等)。
- 量化指标小面板;Docker Compose 一键启动(无 Nginx)。
- (可选)JWT 登录;(可选加分项)云服务器部署。
- **当前状态**:工作台 / 指标盘已通;`start-live → events` 实时链路返回 404,**主链路最后一步未通**;ARQ / Redis / JWT / Compose 未做。

## 11. 边界与可扩展方向

以下能力在原设计中存在,本版本**有意收敛**以突出 Agent 工程信号,是清晰的扩展点而非遗漏:

- **多账源场景**:引擎 Source A / Source B 抽象已保留,可新增 Scenario Profile 扩展到银行内部清算对账等场景(`BC-` 规则、`bank_clearing/` 知识库)。
- **多租户三级隔离**:当前最多按 JWT 带出的 `user_id` 做行过滤,可扩展为数据 / 会话 / 记忆三级隔离。
- **有状态记忆引擎**:当前以"历史人工确认案例 few-shot"作轻量替代,可演进为短期 / 长期 / 摘要三层记忆。
- **工具层标准化**:当前用普通函数工具,可标准化为 MCP Server。
- **云部署与运维**:可补 Docker Compose 云端部署、压测与安全审查,均为加分项,非必做。
