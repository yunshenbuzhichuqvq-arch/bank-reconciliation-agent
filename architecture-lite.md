# 银企对账 Agent · 总体架构(精简版)

> 本文是 `overall-architecture.md` 的精简版,聚焦 **Agent 工程**:状态机编排、结构化输出可靠性、多级 Fallback、混合 RAG、确定性代码与 LLM 的边界。原文保留了完整的全栈与双场景设计,本文不替代它,只把重心收敛到求职作品真正想展示的信号上。
>
> LLM 全程使用 **DeepSeek V4 Pro**(model: `deepseek-v4-pro`,目前为 preview),通过 OpenAI 兼容接口接入。

## 1. 定位与设计目标

本项目是一个**银企对账**(企业账簿 / ERP 明细 × 银行流水)场景的 AI 应用。它把大批量流水核对、差异定位、归因解释、人工复核和差错台账生成抽象成一个可开发、可验证的 Agent 系统。

典型异常包括:企业已记账但银行未到账、银行已到账但企业未入账、金额不一致、手续费 / 税费差异、摘要或客户名称不一致、重复记账、跨期入账。

系统的核心定位不是"让大模型替人算账",而是:

> 用**确定性代码**完成账务核对中的精确计算和状态落库,用 **Agent**处理非结构化摘要、规则解释和审计建议,用 **Human-in-the-Loop** 保留金融场景的人工复核边界,用**输出校验管线**保证 Agent 输出的安全底线。

**通用引擎 + 单场景**:底层是一套只认 `Source A`(主账源)/ `Source B`(对账账源)的通用对账引擎,当前只落地 `BANK_ENTERPRISE` 一个 `scenario_type`(Source A = 企业账簿,Source B = 银行流水)。引擎与具体业务名词解耦,**可扩展到其他对账场景(如银行内部清算对账)**,只需新增一份 Scenario Profile(字段模板 + 规则库 + 知识库 + Prompt),不改主链路。

### 设计目标

1. **确定性 / LLM 边界清晰**:金额计算、状态落库绝不交给 LLM;LLM 只读确定性层产出的 READ-ONLY 结果。
2. **Agent 可约束、可追踪**:每次决策有 Schema、有硬约束、有 RAG 依据、有兜底、有结构化日志。
3. **每个技术选择能解释"为什么这么做"**,并有可真实测量的指标。

## 2. 系统分层

去掉了原八层里的多租户中间件、独立记忆引擎层、Nginx 等重资产,收敛为下面这张图。RAG 是 Agent 编排层在审计时调用的子流程,不单列一层。

```text
┌────────────────────────────────────────────────────────────┐
│ 前端工作台  Vue 3 + ECharts                                  │
│ 上传 | 任务看板 | Agent 流式工作台(SSE) | 人工复核 | 台账 | 指标 │
└────────────────────────────────────────────────────────────┘
                         │ HTTP / SSE
                         ▼
┌────────────────────────────────────────────────────────────┐
│ API 层  FastAPI + Pydantic(鉴权为普通中间件,JWT 可选)        │
│ 上传 | 启动 | 状态 | 复核 | 台账 | 报告 | SSE 事件             │
└────────────────────────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
┌────────────────────────┐  ┌────────────────────────────────┐
│ 确定性计算层             │  │ Agent 编排层  LangGraph         │
│ Pandas 清洗 | 三阶段匹配 │  │ ExtractionAgent | AuditAgent    │
│ YAML 规则 | Decimal 计算 │  │ 状态机 + 条件路由 + 三级 Fallback │
└────────────────────────┘  └────────────────────────────────┘
            │                         │  (审计时调用 RAG 子流程)
            └────────────┬────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│ Agent 输出校验管线(护栏)                                     │
│ Schema 校验(+有界重试) → 硬约束校验 → 决策/Fallback 路由 → 事务落库 │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 数据与知识层  MySQL(事务) + ChromaDB + Redis(缓存/限流/幂等)   │
│ 任务 | 流水 | 队列 | 差错台账 | 复核记录 | Agent 日志 | RAG 文档 │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 可观测性  structlog 结构化日志 + 可回放 trace + token 成本 + Prompt 版本 │
└────────────────────────────────────────────────────────────┘
```

## 3. 确定性计算层

确定性计算层处理所有必须精确、可复现、可审计的动作:文件解析、字段清洗与映射、流水匹配、金额差异计算、异常分支路由、MySQL 事务写入。

**核心原则:凡是金额计算、状态更新、数据库写入,不交给 LLM。**

### 3.1 三阶段流水匹配

```text
阶段 1  精确匹配:flow_id 相等 AND amount 相等 → AUTO_FIXED 直接平账
阶段 2  模糊匹配:amount 相等 AND 同日 AND 对手账号近似 → 候选匹配,转 Agent/人工确认
阶段 3  单边残留:阶段 1/2 均未匹配 → SINGLE_SIDE,路由到对应异常分支
                 (银行未到账 / 企业未入账 / 跨期入账)
```

### 3.2 YAML 声明式规则引擎

规则不硬编码为 if-else,而是用 YAML 定义、启动时加载、按优先级匹配,业务人员可直接维护。单场景规则 ID 用 `BE-` 前缀。

```yaml
rules:
  - id: BE-R002
    name: 金额差异进入审计
    priority: 2
    conditions:
      - { field: amount_diff, operator: neq, value: 0 }
      - { field: flow_id, operator: matched }
    action: PENDING_AI
    error_type: AMOUNT_MISMATCH
    agent_type: AuditAgent
```

**设计决策**:规则与代码分离、可优先级排序、同一笔异常只命中一条规则。确定性规则能覆盖的分支直接处理,无法覆盖的才进入 Agent 链路——这体现的是 AI 应用的边界意识:不是让 AI 替代所有逻辑,而是补足规则难处理的语义理解和归因。

## 4. Agent 编排层(LangGraph)

Agent 不是多个聊天机器人,而是带状态、工具、边界和失败兜底的业务节点。**主链路只有 2 个 Agent**:

| 节点 | 类型 | 职责 |
| --- | --- | --- |
| `PreCheckNode` | 确定性代码 | 三阶段匹配、YAML 规则、异常分支路由 |
| `ExtractionAgent` | LLM | 把不规范摘要 / 户名结构化为标准 JSON |
| `AuditAgent` | LLM | 结合 RAG 依据和计算结果,输出结构化审计决策 |
| `HumanReviewNode` | 状态节点 | 挂起流程,等待人工审批(LangGraph SqliteSaver 持久化,支持断点恢复) |
| `TraceAgent` | LLM(**可选**) | 跨期 / 跨日切、冲正退款链路追溯,作为 Fallback L3 的增强 |

> 报告生成不设独立 Agent:统计走 SQL 聚合 + Markdown 模板,LLM 只做文字润色(可选)。

### 4.1 全局状态(精简)

去掉了原 state 里的多租户(`user_id`/`thread_id`)和三层记忆字段,新增 `historical_cases` 承载 Fallback few-shot。

```python
from typing import Any, Dict, List, Optional, TypedDict

class ReconciliationState(TypedDict):
    task_id: str
    scenario_type: str                    # 默认 BANK_ENTERPRISE,预留多场景扩展
    current_queue_id: Optional[int]
    source_a_item: Dict[str, Any]         # 主账源:企业账簿
    source_b_item: Dict[str, Any]         # 对账账源:银行流水
    error_type: Optional[str]
    exception_branch: Optional[str]
    math_result: Dict[str, str]           # Decimal 计算结果(READ-ONLY)
    extraction_result: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    historical_cases: List[Dict[str, Any]]  # Fallback L2 注入的历史人工确认案例(few-shot)
    audit_decision: Dict[str, Any]
    confidence: Optional[float]
    retry_count: int
    fallback_level: int
    next_action: str
    error_message: Optional[str]
    agent_logs: List[Dict[str, Any]]
```

### 4.2 条件路由(显式建模非 happy-path)

```text
START
  → PreCheckNode(三阶段匹配 + YAML 规则 + 异常分支路由)
  → 确定性规则可覆盖 → 直接写台账
  → 规则无法覆盖,按 exception_branch 路由:
       AMOUNT_MISMATCH / FEE_TAX_DIFF        → RAG → AuditAgent
       BANK_UNARRIVED / BOOK_UNRECORDED      → RAG → AuditAgent(必要时 TraceAgent)
       NARRATIVE_NAME_MISMATCH               → ExtractionAgent → RAG → AuditAgent
       DUPLICATE_BOOKING / CROSS_PERIOD      → (可选 TraceAgent) → AuditAgent
  → 输出校验管线
  → confidence ≥ 0.85 → 落库;否则进入多级 Fallback
  → Fallback 耗尽 / RAG 无命中 → HumanReviewNode(挂起)
  → 人工审批 → 恢复执行 → END
```

价值在于显式建模了出错、低置信、工具失败、无依据等**非 happy-path 分支**,而不是只跑通"对上了"的乐观路径。

### 4.3 三级 Fallback

3 级递进,而不是简单的"低置信就转人工"——这是关键设计决策之一。原"三层记忆"被收敛为这里的 L2 历史 few-shot。

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

## 5. Agent 输出校验管线(护栏)

这是原"Hook 链与硬约束层"的重定位。它不再承担鉴权 / 限流 / 缓存 / 记忆,只做一件事:**保证 Agent 的输出在落库前通过门禁**。鉴权下沉为普通 API 中间件;限流和结果缓存归入 LLM 客户端封装层。

管线只有 4 个阶段:

```text
① Schema 校验   Pydantic model_validate;失败 → 有界重试(≤ 3 次)→ 仍失败转人工
② 硬约束校验    C1–C6 业务约束;失败直接转人工(不重试,业务规则不应被绕过)
③ 决策/Fallback 路由   按 confidence 与 RAG 命中情况,落库 / 进 Fallback / 转人工
④ 事务落库      MySQL 事务写台账 + 队列 + 任务统计;副作用(日志)非阻塞、失败不影响主流程
```

### 硬约束(C1–C6)

| 约束 | 内容 | 实现 |
|---|---|---|
| C1 | `decision` ∈ {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED} | Pydantic Literal |
| C2 | `evidence` 不能为空列表 | field_validator |
| C3 | `|diff| > 10000` 时 `risk_level` 不能为 LOW | ConstraintValidator |
| C4 | `decision = PENDING_HUMAN` 时 `reason` 必须说明依据不足的原因 | ConstraintValidator |
| C5 | `decision = AUTO_FIXED` 时 `confidence` 必须 ≥ 0.85 | ConstraintValidator |
| C6 | RAG 无命中或 `best_score < 0.5` 时禁止 `AUTO_FIXED` | ConstraintValidator |

**设计决策**:金融系统不允许 LLM 自由发挥。事务写入从校验管线中独立出来作为基础设施保障(先校验、后事务、再非阻塞副作用),保证整个过程可审计、可复现、可回滚。

## 6. RAG 检索

RAG 不只是给 Agent 补上下文,它承担"规则依据、业务解释、审计溯源"三类职责,是本项目的核心模块之一。知识库当前只建银企对账一个库(`rag_knowledge/bank_enterprise/`),**可按 scenario_type 扩展为多库隔离**。

### 6.1 增强检索流程

```text
规则文档(Markdown)
  → 结构化切片(## 标题 + 语义边界混合策略)
  → Dense 向量化(中文 Embedding) + BM25 稀疏索引(jieba 分词)
  → 存入 ChromaDB
  → Query Rewrite(LLM 把自然语言映射为规则术语,可开关)
  → 双路召回:Dense Top-20 + BM25 Top-20
  → RRF(Reciprocal Rank Fusion)融合,取 Top-10
  → Cross-Encoder Reranker(默认轻量模型,可换 BGE-Reranker-v2-m3)精排,取 Top-5
  → Dense / Reranker 双阈值过滤
  → 返回 rag_context,并保存来源、各路分数、最终使用的 chunk
```

**为什么用 Cross-Encoder 精排**:Bi-Encoder 召回快但 query/doc 独立编码、丢交互信息;Cross-Encoder 拼接后全文交互打分、精度更高但慢。所以"粗排(双路召回 20 条)+ 精排(Reranker 取 5 条)"兼顾速度与精度。Reranker 默认用本地轻量模型(无 API 成本、离线可用),需要更高精度时可切到 BGE。

**为什么加 Query Rewrite**:对账术语和自然语言之间存在语义 Gap("这笔为什么没对上" vs 规则文档里的"单边账跨日切处理规则"),直接向量检索易漏召回。是否有效用评测集量化,不口头下结论。

### 6.2 无命中策略

Dense 分数 < 0.5 且 Reranker 分数 < 0.3 视为无命中,`AuditAgent` 强制输出 `PENDING_HUMAN`、`evidence` 为空、不触发 Fallback。

### 6.3 评测

手写 `(query, expected_rule_ids)` 评测集,每次调整切片或检索参数后跑 `scripts/eval_rag.py`,输出 **Recall@5 / MRR /（NDCG@5）**。指标值以评测产物为准,脚本跑通前不把提升幅度写成实测结论。

## 7. 数据与知识层

降到标准水平:**去掉 HASH 分区、物化视图、JSON 虚拟列索引**等高级特性,改为标准建表 + 合理索引。

| 存储 | 用途 |
|---|---|
| MySQL 8.0 | 任务 / 流水 / 队列 / 差错台账 / 复核记录 / Agent 日志 / RAG 日志;关键写入走 InnoDB 事务 |
| ChromaDB | 规则知识库向量索引(Dense + Sparse metadata) |
| Redis | **仅** LLM 结果缓存、API 调用限流、幂等去重(不再用于记忆引擎) |
| SQLite | 测试库;LangGraph Checkpoint 持久化 |

若启用 JWT,所有业务查询按其带出的 `user_id` 做行级过滤;**可进一步扩展为多租户隔离**,当前不实现。

## 8. 可观测性

大模型应用区别于传统软件的核心工程问题。产物必须可展示:

- **结构化日志**:structlog 输出 JSON,每条带 `trace_id`、`agent_name`、`step`、`prompt_version`。
- **可回放 trace**:`logs/*.jsonl` 能回放单笔异常的规则命中、RAG 命中、Agent 输出和落库结果。
- **token 成本统计**:每次 LLM 调用的 token 消耗与按模型定价折算的成本。
- **Prompt 版本管理**:Prompt 以独立文件纳入版本控制,`t_agent_execution_log.prompt_version` 让每次决策可追溯到具体版本。
- **LangFuse**:可选,作为 trace 可视化增强,不作为必需依赖。

## 9. 核心设计原则

1. **规则优先,AI 补充**:能用确定性规则解决的不交给大模型。
2. **金额计算绝不交给 LLM**:统一用 `decimal.Decimal` + MySQL 事务;Agent 只读 READ-ONLY 计算结果。
3. **RAG 无据不判定**:检索不到规则依据,强制转人工,不靠预训练知识硬答。
4. **护栏门禁**:Agent 输出必须过 Schema + 硬约束才能落库。
5. **Human-in-the-Loop 兜底**:低置信、无依据、高风险一律转人工;人工确认结果回流为后续 few-shot。
6. **全链路可追踪**:每次决策记录输入、工具调用、RAG 命中、输出 JSON、校验结果和路由结果。

## 10. LLM 选型(摘要)

选 **DeepSeek V4 Pro**:成本低(可承受大量调试调用)、中文能力强(对账场景全中文)、OpenAI 兼容接口零迁移、可私有化。价格**参考,以官网为准**。

工程上对 LLM 做了 **provider 抽象**:默认可切换到 Fake provider,使主链路与测试不依赖真实 API Key——这本身是可测试性设计。

## 11. 数据与安全边界

- 只使用人工构造的模拟 / 脱敏数据;姓名、账号、流水号、金额、摘要均为虚构。
- 不使用任何真实客户数据或银行内部资料。
- 公开制度依据只作规则设计参考,项目自定义规则标注为演示规则。
- AI 只做辅助分析与建议,不做最终金融决策;金额计算、状态落库、人工审批由确定性代码和事务保障。

## 12. 阶段演进与当前进度

六阶段(MVP-0 ~ V2)收敛为三阶段。当前进度如实标注(2026-06-17)。

| 阶段 | 内容 | 进度 |
|---|---|---|
| **一 · 最小闭环** | 单场景银企对账;Pandas 清洗 + 三阶段匹配 + YAML 规则;AuditAgent 真实 LLM 调用 + 结构化输出 + 校验 + 重试 + 兜底;基础 RAG;能打出一条完整 trace | ✅ 基本完成 |
| **二 · Agent 工程做深** | LangGraph 状态机 + 条件路由;三级 Fallback;Prompt 独立文件 + 版本管理;RAG 评测集(真实 Recall@5/MRR)+ Agent 决策质量评测;工具调用权限边界;ExtractionAgent 接入 | 🔶 大部分完成 |
| **三 · 作品化** | Vue 工作台 + SSE 展示 Agent 执行;ARQ 异步队列;Redis(缓存/限流/幂等);量化指标小面板;Docker Compose 一键起;(可选)JWT、云部署 | 🚧 进行中:工作台 / 指标盘已通;**SSE 实时链路阻断(主链路最后一步未通)**;ARQ / Redis / JWT / Compose 未做 |

## 13. 边界与可扩展方向

以下能力在原设计中存在,本版本**有意收敛**以突出 Agent 工程信号。它们是清晰的扩展点,不是遗漏:

- **多账源场景**:引擎层 Source A / Source B 抽象已保留,可新增 Scenario Profile 扩展到银行内部清算对账等场景。
- **多租户隔离**:当前最多按 JWT 带出的 `user_id` 做行过滤,可扩展为完整的数据 / 会话 / 记忆三级隔离。
- **有状态记忆**:当前以"历史人工确认案例 few-shot"作轻量替代,可演进为短期 / 长期 / 摘要三层记忆引擎。
- **工具层标准化**:当前用普通函数工具,可标准化为 MCP Server。
- **云部署**:可作为加分项补 Docker Compose 云端部署,非必做。
