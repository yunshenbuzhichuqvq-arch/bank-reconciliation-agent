# 《基于多智能体（Multi-Agent）的多账源智能对账与审计辅助系统》系统 PRD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目名称 | 基于多智能体（Multi-Agent）的多账源智能对账与审计辅助系统 |
| 项目类型 | 个人开源项目 |
| 业务场景 | 主场景：银企对账（企业账簿 / ERP 明细 × 银行流水）；副场景：银行内部清算对账（银行核心 × 清算端 / 支付通道） |
| 核心抽象 | 一套通用双账源对账引擎（Source A 主账源 / Source B 对账账源）+ 按 `scenario_type` 选择的场景化配置（Scenario Profile） |
| 技术栈 | FastAPI、Vue 3、MySQL 8.0、LangGraph、RAG、ChromaDB、SQLite、Docker、LangFuse |
| LLM | DeepSeek V4 Pro（经济、安全、中文能力强） |
| 项目阶段 | MVP-0 后端最小闭环 -> MVP-1 本地产品闭环 -> MVP-2a Agent 智能化闭环 -> MVP-2b Agent 工程化闭环 -> V1 在线作品 -> V2 深度优化版 |
| 数据边界 | 仅使用模拟数据和脱敏数据，不使用真实客户数据或银行内部资料 |

## 2. 产品概述

本系统是一套面向**多账源对账与审计辅助**的 AI 应用。它以**银企对账**为主场景（企业账簿 / ERP 明细与银行流水核对），保留**银行内部清算对账**为副场景（银行核心流水与清算端 / 支付通道流水核对），帮助企业财务人员或银行对公人员在大批量流水核对中降低耗时、快速定位差异、减轻人工复核压力，处理双账源流水差异、单边缺失、跨期 / 跨日切、冲正退款、手续费 / 税费差异、重复记账 / 清算、人工复核和审计报告生成的流程。

系统不是两套独立系统，而是**一套通用 Reconciliation Engine + 不同 Scenario Profile**：引擎只认 Source A（主账源）/ Source B（对账账源），由 `scenario_type` 选择字段映射、规则库、RAG 知识库、Prompt 和报告模板。

系统采用“确定性代码 + 规则引擎 + Multi-Agent + RAG + 记忆引擎 + Hook 链 + Human-in-the-Loop”的组合架构。确定性代码负责文件解析、字段映射、金额计算和数据库事务；规则引擎基于 YAML 声明式规则按 `scenario_type` 将异常流水分发到当前场景的处理分支；Multi-Agent（统一使用 DeepSeek V4 Pro）负责模糊摘要结构化、业务追溯、审计判断和报告生成；RAG 采用混合检索 + Reranker + Query Rewrite 全链路、按场景隔离知识库提供规则依据和审计溯源；记忆引擎提供三层记忆使 Agent 具备跨调用决策一致性；Hook 链作为 Pre/Post Processing 门禁负责权限校验、记忆注入、硬约束校验和审计日志；Human-in-the-Loop 在金融风险场景保留人工确认。

## 3. 产品范围与阶段规划

本项目采用 MVP-0 -> MVP-1 -> MVP-2a -> MVP-2b -> V1 -> V2 的递进式版本规划。六个版本不是互相独立的功能清单，而是围绕同一条主链路逐层加厚。

MVP-0 是后续阶段的前置子集，用于降低开发风险，先验证核心业务链路和 AI 审计链路是否成立。MVP-1 把后端能力变成本地可演示产品；MVP-2a 将确定性 Agent 升级为真实 LLM 调用并补齐增强 RAG；MVP-2b 再补 Hook 链、记忆引擎和工作流深度；V1 实现在线化能力和评测体系；V2 完成深度优化、安全验证和云端部署。

每个阶段都必须有可验收产物。MVP-0 的产物是 API、数据库记录、RAG/Agent JSON 和最小 trace；MVP-1 的产物是本地页面、人工复核流、YAML 规则和复核记录；MVP-2a 的产物是真实 LLM Agent 输出、增强 RAG trace 和 Fallback 日志；MVP-2b 的产物是 Hook/Memory 日志、Checkpoint 工作流和 Agent 回归测试；V1 的产物是 SSE 演示、评测报告和指标仪表板；V2 的产物是失败样本分析、A/B 对比、安全验证、压力测试报告和云端部署地址。

### 3.1 MVP-0：后端最小 AI 对账闭环

目标：先完成从模拟 Excel 到差错台账查询的后端主链路，证明“规则对账 + Agent 审计 + RAG 依据 + MySQL 台账”可以跑通。

核心链路：

```text
准备模拟 Excel 数据
  -> 上传 source_a_file（企业账簿）+ source_b_file（银行流水），scenario_type = BANK_ENTERPRISE
  -> Pandas 读取、字段校验、数据清洗、字段映射
  -> 基础规则对账
  -> 识别异常交易（AMOUNT_MISMATCH + 单边缺失：BANK_UNARRIVED / BOOK_UNRECORDED）
  -> 异常进入 Agent 审计流程
  -> RAG 检索规则依据（银企对账知识库，ChromaDB Top-K + 相似度阈值）
  -> AuditAgent 输出结构化审计建议（含 evidence 字段）
  -> 结果写入 MySQL 差错台账
  -> 通过 API 查询任务状态和差错明细
```

包含：

- 模拟主账源（企业账簿）和对账账源（银行流水）Excel（覆盖正常平账、金额差错、单边缺失 3 类场景，scenario_type = BANK_ENTERPRISE）。
- FastAPI 文件上传接口。
- Pandas 读取、字段校验和数据清洗。
- 基础规则对账和异常识别（if-else 规则，MVP-1 阶段升级为 YAML 引擎）。
- 简化 AuditAgent（确定性规则引擎，非 LLM 调用）。
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
- 真实 LLM 调用（Agent 为确定性规则）。
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

- 真实 LLM 调用（Agent 仍为确定性规则/正则/关键词匹配）。
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

### 3.3 MVP-2a：Agent 智能化闭环

目标：在 MVP-1 的本地产品闭环基础上，**以银企对账为主链路**将三个 Agent 从确定性规则升级为真实 LLM 调用（DeepSeek V4 Pro），完成端到端智能审计闭环，并补齐增强 RAG 和 Fallback 机制；**清算对账作为副链路只做最小闭环**，先支持少量典型异常（如清算单边 + 跨日切）。MVP-2a 的核心问题是“Agent 能基于 RAG 依据做出比 if-else 更准确的审计判断吗？”，因此所有新增能力都围绕这个核心问题展开。

**设计原则**：MVP-2a 只加“让 Agent 变聪明”的东西，不加“让系统变复杂”的东西。Hook 链、记忆引擎、并行执行等工程化深度留给 MVP-2b。

新增：

- **双场景接入**：以 `scenario_type` 区分银企对账（主）与清算对账（辅）；字段映射模板、规则库、RAG 知识库、Prompt 和报告模板均按场景隔离。银企对账作为主链路完整接入，清算对账先接入最小闭环。
- **Agent LLM 化（核心变更）**：
  - ExtractionAgent：从正则匹配升级为 DeepSeek V4 Pro 调用，从模糊摘要中结构化提取冲正/退款/作废线索和原流水号。
  - TraceAgent：从关键词匹配升级为 DeepSeek V4 Pro 调用，识别跨日切/T+1 线索并给出追溯建议。
  - AuditAgent：从 if-else 分支升级为 DeepSeek V4 Pro 调用，基于 RAG 证据和异常信息输出结构化审计决策（decision / risk_level / reason / confidence / evidence）。
  - 三个 Agent 均使用 DeepSeek V4 Pro，通过 OpenAI 兼容接口调用（`openai` SDK + `base_url=https://api.deepseek.com/v1`）。
  - 依赖新增：`openai>=1.0.0`（用于调用 DeepSeek API）。
- **增强 RAG**：
  - Dense + BM25 双路召回（新增依赖：`jieba`、`rank-bm25`）。
  - RRF（Reciprocal Rank Fusion）融合排序，取 Top-10。
  - Cross-Encoder Reranker 精排（BGE-Reranker-v2-m3），取 Top-5。
  - Query Rewrite（DeepSeek V4 Pro 调用）：将自然语言查询改写为规则检索关键词。
  - Reranker 和 Query Rewrite 必须可开关，保证主链路在本地资源不足时仍可运行。
  - RAG 检索日志补齐：记录 `rewritten_query`、`dense_score`、`bm25_score`、`reranker_score`、`fusion_rank` 等字段。
- **LangGraph 条件路由工作流**：
  - PreCheckNode → ExceptionRouter → 条件分支 → AuditAgent → END。
  - 条件分支根据 `exception_branch` 决定是否调用 ExtractionAgent、TraceAgent 或 RAG Subgraph。
  - MVP-2a 阶段保持**串行执行**（先不引入并行，等有了真实 LLM 延迟数据后再决定是否并行）。
- **ExceptionRouter 完整版**：覆盖银企对账异常分支全集（金额不一致、手续费 / 税费差异、银行未到账、企业未入账、摘要 / 客户名不一致、重复记账、跨期入账），并接入清算对账少量典型分支（清算单边、跨日切、冲正退款）。
- **3 级 Fallback**：
  - L1（标准）：标准 System Prompt + RAG 规则原文 + 当前异常项。
  - L2（增强）：追加 2-3 个同类异常的历史人工确认案例（来自差错台账表）。
  - L3（追溯）：TraceAgent 追加跨日切流水查询和冲正链路校验结果。
  - RAG 无命中 → 直接转人工，不触发 Fallback（无依据不可判断）。
- **structlog 结构化日志**：
  - 新增依赖 `structlog>=24.0.0`。
  - 所有 LLM 调用点输出 JSON 格式日志，携带 `trace_id`、`user_id`、`thread_id`、`agent_name`、`step`、`prompt_version`。
  - 当前 `print` / `logging` 调用全部替换为 structlog。
- **Prompt 版本管理**：
  - 所有 LLM 调用点的 Prompt 以独立文件存放（`prompts/extraction_v1.md`、`prompts/audit_v1.md`、`prompts/rewrite_v1.md` 等），纳入版本控制。
  - `t_agent_execution_log` 新增 `prompt_version` 字段，确保每次 Agent 决策可追溯到具体 Prompt 版本。
  - 附带一个简单的版本对比脚本：对同一批 mock 数据用不同 Prompt 版本各跑一次，对比 confidence 分布和 decision 一致性。
- **数据库改造**：
  - `t_rag_retrieval_log`：新增 `rewritten_query`、`dense_score`、`bm25_score`、`reranker_score`、`fusion_rank`、`selected_chunk_id` 字段。
  - `t_agent_execution_log`：新增 `prompt_version`、`fallback_level`、`llm_tokens` 字段。
  - `t_error_ledger`：新增 `exception_branch`、`fallback_path`、`rag_scores_json` 字段。
  - `t_reconciliation_task`：新增 `ai_processed_rows`、`fallback_l2_rows`、`fallback_l3_rows`、`total_llm_tokens` 字段。
- **端到端集成测试**：基于已知 mock Excel 的固定对账结果，验证从上传到台账落库的全链路正确性；覆盖正常平账、金额差错、单边缺失、冲正退款、跨日切五类场景的预期输出。
- **Agent 输出质量评估**（替代原“回归测试”）：给定固定 RAG 输入和异常项，验证 Agent 输出的 `decision` 在合法枚举内、`evidence` 非空、`reason` 包含关键业务信息、`confidence` 在合理区间。**不对 LLM 的非确定性做严格一致性断言**，而是用统计方法（同一输入跑 10 次，统计 decision 分布）检测漂移。

**MVP-2a 暂不包含**（留给 MVP-2b）：

- Hook 链（Pre/Post Processing 门禁）。
- 记忆引擎（短期/长期/摘要记忆）。
- Agent 并行执行。
- LangGraph Checkpoint（断点续跑）。
- Redis 依赖。
- 大模型调用频率控制。
- Agent 决策回归测试（严格一致性断言）。

**MVP-2a 成功标准**：同一个 mock 文件上传后，AuditAgent 的决策比 MVP-1 的 if-else 版本更细化——能区分“建议自动平账（confidence ≥ 0.85）”和“建议人工复核（confidence < 0.85 或无 RAG 命中）”，且 RAG 增强后的检索命中率和相关度显著优于纯 Dense 检索。

### 3.4 MVP-2b：Agent 工程化闭环

目标：在 MVP-2a 的智能化基础上，补全 Hook 链、记忆引擎和工作流深度，并把这些工程化能力接入两个场景（银企对账 + 清算对账），让系统从“Agent 能判断”升级为“Agent 可约束、可追踪、可复核”。MVP-2b 是 Agent 工程化能力的集中体现。

**设计原则**：MVP-2b 不引入新的外部服务依赖（不使用 Redis），所有能力基于 SQLite + 现有 MySQL 实现。

新增：

- **Hook 链核心 6 个**（非全部 11 个）：
  - Pre-Hooks（3 个）：
    - ① **AuthHook**：`X-User-ID` 校验 + user_id 与 task_id 归属校验。失败返回 403。
    - ② **ValidationHook**：输入数据完整性、金额精度、必填字段校验。失败返回 400。
    - ③ **MemoryHook**：调用 MemoryManager.build_context() 组装上下文，注入 Agent 的 System Prompt。失败降级（跳过记忆，仅用 System Prompt）。
  - Post-Hooks（3 个）：
    - ④ **SchemaHook**：Pydantic model_validate 校验 Agent JSON 输出。失败重试（最多 3 次）→ 转人工。
    - ⑤ **ConstraintHook**：硬约束校验（金额-风险一致性、evidence 非空、decision 枚举合法、confidence 与 decision 一致性）。失败直接转人工（不重试，业务规则不应被绕过）。
    - ⑥ **DecisionHook**：按 confidence 和 RAG 命中情况路由到不同 Fallback 级别或转人工。
  - 延迟到 V1 的 Hook：RateLimitHook（本地单用户无意义）、CacheHook（已有幂等设计）、MemoryUpdateHook（纳入 MemoryManager）、LogHook（纳入 TransactionHook 的事务后处理）。
- **事务与副作用分离**：
  - 核心事务（台账写入 + 队列更新 + 任务统计更新）独立于 Hook 链，作为基础设施保障。先走 Post-Hook 链校验，校验通过后进入事务写入，事务成功后再执行副作用操作（记忆更新、日志写入），副作用失败不影响主流程。
- **记忆引擎 SQLite-only 版**（不引入 Redis）：
  - **短期记忆**：SQLite 表 `t_short_term_memory`，按 `thread_id` 隔离，TTL 字段 + 定期清理（任务结束后 24h 过期）。
  - **长期记忆**：SQLite 表 `t_long_term_memory`，按 `user_id` 隔离，仅存储人工确认的最终结果。按 `error_type` + 关键字段做语义相似度检索。
  - **摘要记忆**：SQLite 表 `t_summary_memory`，按 `thread_id` 隔离。累计满 20 笔异常时触发 LLM 压缩（DeepSeek V4 Pro 调用），将前 N 笔决策模式压缩为约 300 token 的摘要文本。
  - **MemoryManager 接口**：`build_context()` 组装 Context Window（System Prompt → Long-term Memory → Short-term Memory → Summary Buffer → RAG Context → Current Item）；`update_after_decision()` 在决策后更新三层记忆。
  - 为什么 MVP-2b 不用 Redis：MVP-2 承诺“本地可运行”，引入 Redis 会增加环境复杂度。SQLite 在本地场景下延迟可接受（< 5ms），且与长期记忆存储统一。Redis 推迟到 V1（需要 Docker Compose 时一起引入）。
- **摘要压缩质量验证**（PRD 7.4 节详细设计）：
  - 压缩前保存：触发压缩时将 20 条原始记录写入临时快照（JSON）。
  - 压缩后回检：HIGH 风险条目是否被提及、PENDING_HUMAN 条目是否保留、flow_id 覆盖率 ≥ 80%。
  - 校验失败：丢弃压缩结果，保留全量记录，记录 WARNING 日志。
- **LangGraph Checkpoint**：
  - HumanReviewNode 支持断点挂起和恢复。
  - 使用 LangGraph `SqliteSaver` 持久化图状态（无需额外数据库）。
  - 人工审批后从 Checkpoint 恢复，继续执行后续节点。
- **Agent 并行执行**（基于 MVP-2a 的真实延迟数据决定）：
  - 如果 MVP-2a 中 ExtractionAgent（LLM 调用，约 1-3s）和 RAG Subgraph（增强检索，约 0.5-2s）的延迟在同一数量级，则通过 LangGraph Send API 并行执行并汇聚结果给 AuditAgent。
  - 如果其中一方显著快于另一方（如 RAG 在本地环境 < 100ms），则保持串行，避免不必要的并行复杂度。
- **Agent 决策回归测试（统计方法）**：
  - 对同一输入跑 10 次，统计 decision 分布。如果 `AUTO_FIXED` 和 `PENDING_HUMAN` 各占 50%，说明该 Prompt 对该类异常存在随机性，需要优化 Prompt 或提高阈值。
  - 断言仅检查：decision 在合法枚举内、evidence 非空、reason 非空、confidence 在 [0, 1] 内。
- **RAG 评测集骨架**：
  - 覆盖 5 个核心分支 × 10 条 query = 50 条评测数据。
  - 评测脚本输出 Recall@5、MRR、NDCG@5。
  - 评测集文件 `data/rag_eval_set.json`，评测脚本 `scripts/eval_rag.py`。

**MVP-2b 暂不包含**（留给 V1）：

- Redis 依赖（记忆引擎降级到 SQLite 后无需 Redis）。
- RateLimitHook、CacheHook。
- 大规模 RAG 评测集（V1 扩充至 120+ 条）。
- 在线量化指标仪表板。
- MCP 协议工具层。

### 3.5 V1：在线作品版

目标：形成可放到 GitHub 和服务器上演示的作品，补齐量化指标和评测体系，让项目从“能跑”升级为“能解释效果和失败原因”。

新增：

- **前端场景选择**：上传页按 `scenario_type` 切换字段模板，RAG 知识库、Prompt 和报告模板按场景自动切换。
- **Celery/ARQ 后台任务队列**：对账任务异步执行，上传接口即时返回 task_id。
- JWT 登录鉴权（替代 X-User-ID 模拟）。
- SSE 展示 Agent 执行过程（含 Pre/Post Hook 状态、RAG 检索详情、Fallback 层级）。
- **记忆引擎 Redis 升级**：将短期记忆从 SQLite 迁移到 Redis Sorted Set，提升并发性能。
- 原有的 RateLimitHook、CacheHook 接入 Redis。
- 手续费/批量业务差异样例。
- Markdown 审计报告。
- MCP 协议工具层可选演示：RAG Server、Ledger Server、Trace Server 以 MCP 形式提供；若时间不足，保留为 V2 增强。
- **RAG 评测集**：手写 120 条 (query, expected_rule_ids)，评测脚本输出 Recall@5/MRR/NDCG。
- **Agent Schema 符合性测试**：Pytest + Pydantic，统计通过率。
- **量化指标仪表板**：前端展示核心指标。
- README、演示数据和本地启动说明。

### 3.6 V2：深度优化版

目标：补充 AI 应用工程化能力，围绕”效果、稳定性、成本和失败分析”做深度优化。

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
- Docker Compose 一键启动（含 Nginx 反向代理、Redis）。
- 云服务器部署和部署说明。

## 4. 页面与交互设计

MVP-0 阶段不建设前端页面，通过 Swagger 或 curl 调用 API 演示。前端页面从 MVP-1 阶段开始建设。各阶段鉴权说明：MVP-1 至 MVP-2b 使用 `X-User-ID: demo_user` 模拟用户身份，V1 改为 JWT 登录。

### 4.1 账单上传页（MVP-1）

选择对账场景（`scenario_type`：银企对账 / 银行内部清算对账），按场景上传主账源 Source A 与对账账源 Source B Excel 文件（如企业账簿 / ERP 明细与银行流水）。展示字段校验结果和上传后统计（Source A / Source B 总笔数、自动平账数、待 AI 审计数）。文件格式错误或必填字段缺失时拒绝上传。上传成功后生成 task_id 并跳转任务看板。

### 4.2 任务看板（MVP-1）

展示对账任务列表、任务状态、自动平账率、待复核数、挂账数、异常类型分布。提供”启动 AI 审计”按钮。MVP-1/MVP-2a/MVP-2b 阶段手动刷新；V1 改为 SSE 实时更新。

### 4.3 Agent 流式工作台（V1）

通过 SSE 实时展示 Agent 执行事件：当前处理流水、Pre/Post Hook 状态、异常分支路由、RAG 检索详情（含 Dense/BM25/Reranker 分数）、AuditAgent 决策与置信度、Fallback 层级、最终决策。MVP-2a/MVP-2b 阶段使用轮询或后端日志返回。

### 4.4 人工复核页（MVP-1）

左侧主账源 Source A 流水 / 右侧对账账源 Source B 流水 / 中间 AI 推荐理由与 RAG 来源。支持确认平账、强制挂账、人工备注。每次操作必须记录操作人、时间、动作和备注，通过事务更新台账。

**复核超时机制**：`PENDING_HUMAN` 状态超过 24 小时自动标记 `OVERDUE`，任务看板高亮提示。MVP-1 按创建时间排序展示；MVP-2b 通过 DecisionHook 检测超时并写入日志；V1 支持配置超时时长 + SSE 推送提醒。

### 4.5 差错台账页（MVP-1）

分页查询，按任务、差错类型、处理状态、风险等级筛选。单笔详情含 AI 审计意见、RAG 来源、人工处理记录。MVP-2b 起支持 Agent 决策链路回放（本地 trace）。

### 4.6 报表审计页（V1）

展示总笔数/总金额/自动平账率/人工复核数/挂账金额、异常类型分布、Agent 决策分布、ReportAgent 生成的 Markdown 报告。V2 支持 PDF 导出。

### 4.7 RAG 知识库管理页（V2）

查看规则文档列表、切片策略、检索测试结果（含 Dense/BM25/Reranker 分数和 RRF 融合过程）。

### 4.8 量化指标仪表板（V1）

展示自动平账率、Agent 审计准确率、RAG Recall@5/MRR、Schema 符合率、人工复核触发率、单笔处理时延（P50/P95/P99）、LLM Token 消耗趋势。
- 展示 LLM Token 消耗趋势和成本估算。

## 5. 后端 API 设计

### 5.1 鉴权说明

所有 API 均需携带 `X-User-ID` Header（MVP-0/MVP-1/MVP-2a/MVP-2b 阶段为固定演示值，V1 阶段改为 JWT）。

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

- `scenario_type`（`BANK_ENTERPRISE` / `BANK_CLEARING`，缺省 `BANK_ENTERPRISE`）
- `source_a_file`（主账源：企业账簿 / ERP 明细，或银行核心流水）
- `source_b_file`（对账账源：银行流水，或清算端 / 支付通道流水）

响应（V1 改为异步，即时返回 task_id）：

```json
{
  "code": 200,
  "message": "upload success",
  "data": {
    "task_id": "TASK_20260526_001",
    "scenario_type": "BANK_ENTERPRISE",
    "total_source_a_rows": 5000,
    "total_source_b_rows": 4996,
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
    "scenario_type": "BANK_ENTERPRISE",
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
  "scenario_type": "BANK_CLEARING",
  "message": "命中跨日切处理规则（Hybrid Search + Reranker）",
  "payload": {
    "query_rewritten": "单边账 跨日切窗口 流水匹配失败 处理规则",
    "source": "rag_knowledge/bank_clearing/cutoff_cross_day.md#跨日切",
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
      "validation": "PASSED",
      "memory_injection": "PASSED (2 long-term + 8 short-term)"
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
    "scenario_type": "BANK_ENTERPRISE",
    "items": [
      {
        "queue_id": 1024,
        "error_type": "NARRATIVE_NAME_MISMATCH",
        "exception_branch": "BE-R004",
        "risk_level": "MEDIUM",
        "ai_suggestion": "APPROVED_MATCH",
        "ai_confidence": 0.72,
        "ai_reason": "金额与入账日期一致，但企业账簿摘要与银行流水客户名称不一致，疑似同一笔，建议人工确认",
        "rag_sources": [
          {
            "source": "rag_knowledge/bank_enterprise/basic_matching.md#摘要与户名不一致",
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
- MVP-2b 进一步更新 SQLite 短期记忆、长期记忆，并在累计满 20 笔时触发摘要压缩。

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

- `scenario_type`
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
    "scenario_type": "BANK_ENTERPRISE",
    "report_id": 18,
    "format": "markdown",
    "summary": {
      "total_source_a_rows": 5000,
      "total_source_b_rows": 4996,
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
  "scenario_type": "BANK_CLEARING",
  "query": "23:55 发生的单边账如何处理",
  "top_k": 5,
  "enable_rewrite": true,
  "enable_hybrid": true
}
```

响应（MVP-2a 版本，含混合检索细节）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "original_query": "23:55 发生的单边账如何处理",
    "rewritten_query": "单边账 跨日切窗口 日切时间 流水匹配失败 处理规则",
    "items": [
      {
        "source": "rag_knowledge/bank_clearing/cutoff_cross_day.md#跨日切",
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

### 5.12 记忆查询（MVP-2b 新增，调试用）

阶段：MVP-2b。

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

所有业务表均包含 `user_id` 列用于多租户隔离。所有 SQL 查询在中间件层强制注入 `WHERE user_id = ?` 条件。对账相关表（任务、流水、队列、台账、Agent 日志、RAG 日志、审计报告）均包含 `scenario_type` 列，用于区分银企对账与清算对账两个场景的数据、规则和报告，避免跨场景混用。

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

阶段：MVP-0（含 `scenario_type`，默认 `BANK_ENTERPRISE`，MVP-2a 起启用 `BANK_CLEARING`）。MVP-1 阶段补充 `batch_id` 和本地任务展示字段；MVP-2a 阶段补充 Agent/Fallback 统计字段。

```sql
CREATE TABLE t_reconciliation_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  batch_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  task_name VARCHAR(128) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',  -- MVP-0；MVP-2a 起启用 BANK_CLEARING
  status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
  total_source_a_rows INT NOT NULL DEFAULT 0,
  total_source_b_rows INT NOT NULL DEFAULT 0,
  auto_fixed_rows INT NOT NULL DEFAULT 0,
  pending_ai_rows INT NOT NULL DEFAULT 0,
  ai_processed_rows INT NOT NULL DEFAULT 0,       -- MVP-2a 新增
  ai_retrying_rows INT NOT NULL DEFAULT 0,
  fallback_l2_rows INT NOT NULL DEFAULT 0,         -- MVP-2a 新增
  fallback_l3_rows INT NOT NULL DEFAULT 0,         -- MVP-2a 新增
  pending_human_rows INT NOT NULL DEFAULT 0,
  unresolved_rows INT NOT NULL DEFAULT 0,
  total_llm_tokens INT NOT NULL DEFAULT 0,         -- MVP-2a 新增
  total_llm_cost DECIMAL(10,4) NOT NULL DEFAULT 0.0000,  -- MVP-2a 新增
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_task (user_id, task_id),
  INDEX idx_user_batch (user_id, batch_id),
  INDEX idx_user_scenario (user_id, scenario_type),
  INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.3 主账源流水表 `t_source_a_transaction`

阶段：MVP-0。主账源 Source A（`source_side = 'A'`，`source_type` = `ENTERPRISE_BOOK` 企业账簿 / `CORE_LEDGER` 银行核心）。字段与 `mock_data/source_a_*.xlsx` 保持一致，同时保留 `amount`、`trade_time`、`account_no_masked`、`customer_name_masked` 等标准化字段，便于后续基础匹配、差错台账和 Agent 上下文复用。MVP-1 阶段按 `task_id` 做 HASH 分区。

```sql
CREATE TABLE t_source_a_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  source_side CHAR(1) NOT NULL DEFAULT 'A',
  source_type VARCHAR(32) NOT NULL DEFAULT 'ENTERPRISE_BOOK',  -- ENTERPRISE_BOOK（银企）/ CORE_LEDGER（清算）
  flow_id VARCHAR(64),
  bank_serial_no VARCHAR(64),
  voucher_no VARCHAR(64),                -- 企业账簿凭证号（ENTERPRISE_BOOK，可空）
  accounting_period VARCHAR(16),         -- 会计期间（跨期入账判定，可空）
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
  matched_source_b_id BIGINT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_flow (user_id, task_id, flow_id),
  INDEX idx_user_task_time (user_id, task_id, trade_time),
  INDEX idx_user_serial (user_id, bank_serial_no),
  INDEX idx_match_status (task_id, match_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY HASH (CRC32(task_id)) PARTITIONS 8;
```

### 6.4 对账账源流水表 `t_source_b_transaction`

阶段：MVP-0。对账账源 Source B（`source_side = 'B'`，`source_type` = `BANK_STATEMENT` 银行流水 / `CLEARING_FILE` 清算端 / `CHANNEL_FILE` 支付通道）。字段与 `mock_data/source_b_*.xlsx` 保持一致，同时保留标准化 `amount`、`trade_time`、`summary` 字段。MVP-1 阶段按 `task_id` 做 HASH 分区。

```sql
CREATE TABLE t_source_b_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  source_side CHAR(1) NOT NULL DEFAULT 'B',
  source_type VARCHAR(32) NOT NULL DEFAULT 'BANK_STATEMENT',  -- BANK_STATEMENT（银企）/ CLEARING_FILE / CHANNEL_FILE（清算）
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
  matched_source_a_id BIGINT DEFAULT NULL,
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

阶段：MVP-0。MVP-1 阶段新增 `exception_branch`；MVP-2a 阶段新增 `fallback_level`。

```sql
CREATE TABLE t_reconciliation_queue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  source_a_transaction_id BIGINT NULL,
  source_b_transaction_id BIGINT NULL,
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

阶段：MVP-0。MVP-1 阶段新增 `exception_branch` 和 `ai_confidence`；MVP-2a 阶段新增 `rag_scores_json`、`fallback_path`。

```sql
CREATE TABLE t_error_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  error_type VARCHAR(32) NOT NULL,
  exception_branch VARCHAR(32) DEFAULT NULL,
  discrepancy_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  ai_cleaned_json JSON,
  ai_audit_opinion TEXT,
  ai_confidence DECIMAL(5,4) DEFAULT NULL,
  rag_scores_json JSON,                              -- MVP-2a 新增
  rag_source VARCHAR(512),
  fallback_path VARCHAR(128) DEFAULT NULL,            -- MVP-2a 新增
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

阶段：MVP-1。MVP-2a 版本新增 `prompt_version`、`fallback_level`、`llm_tokens`；MVP-2b 版本新增 JSON 虚拟列索引。

```sql
CREATE TABLE t_agent_execution_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',
  queue_id BIGINT,
  agent_name VARCHAR(64) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  input_payload JSON,
  output_payload JSON,
  pre_hook_results JSON,                              -- MVP-2b 新增
  post_hook_results JSON,                             -- MVP-2b 新增
  rag_retrieval_id BIGINT,
  prompt_version VARCHAR(16) DEFAULT NULL,            -- MVP-2a 新增
  fallback_level INT NOT NULL DEFAULT 0,              -- MVP-2a 新增
  llm_tokens INT NOT NULL DEFAULT 0,                  -- MVP-2a 新增
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_task_queue (user_id, task_id, queue_id),
  INDEX idx_agent_event (agent_name, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- MVP-2b: 对 output_payload 中的高频查询字段建虚拟列索引
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

阶段：MVP-0。MVP-2a 阶段新增混合检索细节字段。

```sql
CREATE TABLE t_rag_retrieval_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',  -- 决定检索哪个场景知识库
  queue_id BIGINT,
  original_query TEXT NOT NULL,
  rewritten_query TEXT,                               -- MVP-2a 新增
  top_k INT NOT NULL,
  dense_candidates INT DEFAULT 20,                    -- MVP-2a 新增
  sparse_candidates INT DEFAULT 20,                   -- MVP-2a 新增
  fusion_candidates INT DEFAULT 10,                   -- MVP-2a 新增
  after_rerank INT DEFAULT 5,                         -- MVP-2a 新增
  best_dense_score DECIMAL(8,4),                      -- MVP-2a 新增
  best_reranker_score DECIMAL(8,4),                   -- MVP-2a 新增
  sources JSON,
  selected_chunk_id VARCHAR(128),                     -- MVP-2a 新增
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
  scenario_type VARCHAR(32) NOT NULL DEFAULT 'BANK_ENTERPRISE',  -- 报告模板按场景区分
  report_format VARCHAR(16) NOT NULL DEFAULT 'markdown',
  report_content MEDIUMTEXT NOT NULL,
  report_metrics JSON,
  created_by VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_task (user_id, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.11 短期记忆表 `t_short_term_memory`（MVP-2b 新增）

阶段：MVP-2b。SQLite 存储，按 `thread_id` 隔离。

```sql
CREATE TABLE t_short_term_memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  queue_id INTEGER NOT NULL,
  error_type TEXT NOT NULL,
  decision TEXT NOT NULL,
  confidence REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_short_term_thread ON t_short_term_memory(thread_id, created_at);
```

### 6.12 长期记忆表 `t_long_term_memory`（MVP-2b 新增）

阶段：MVP-2b。SQLite 存储，按 `user_id` 隔离，仅存储人工确认的最终结果。

```sql
CREATE TABLE t_long_term_memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  error_type TEXT NOT NULL,
  exception_branch TEXT,
  flow_id TEXT NOT NULL,
  bank_amount TEXT,
  clear_amount TEXT,
  amount_diff TEXT,
  summary_keywords TEXT,
  human_decision TEXT NOT NULL,
  ai_suggestion TEXT,
  ai_confidence REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_long_term_user_error ON t_long_term_memory(user_id, error_type);
```

### 6.13 摘要记忆表 `t_summary_memory`（MVP-2b 新增）

阶段：MVP-2b。SQLite 存储，按 `thread_id` 隔离。

```sql
CREATE TABLE t_summary_memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL UNIQUE,
  summary_text TEXT NOT NULL,
  compressed_count INTEGER NOT NULL DEFAULT 0,
  last_compressed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.14 规则命中和效果统计表 `t_rule_hit_stats`（V2 新增）

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

阶段：MVP-2b。

记忆引擎是 Agent 从“无状态调用”升级为“有状态决策”的核心模块。MVP-1 只记录人工复核历史，不注入 Agent 上下文；MVP-2a 只做真实的单次 LLM 调用；MVP-2b 再引入短期、长期和摘要三层记忆。

**设计原则**：MVP-2b 的记忆引擎全部基于 SQLite（不引入 Redis），降低本地运行的环境复杂度。V1 将短期记忆迁移到 Redis 以提升并发性能。

详见 `overall-architecture.md` 2.6 节。

### 7.1 三层记忆模型

| 记忆层 | 作用域 | 存储 | 数据结构 | TTL | 更新触发 |
|--------|-------|------|---------|-----|---------|
| 短期记忆 | 本任务（thread_id） | SQLite | 结构化表（按时间排序） | 任务结束 + 24h | 每次 Agent 决策后 |
| 长期记忆 | 跨任务（user_id） | SQLite | 结构化表 | 永久 | 人工确认后 |
| 摘要记忆 | 本任务（thread_id） | SQLite | 结构化表（单行） | 任务结束 + 24h | 每 20 笔触发 LLM 压缩 |

### 7.2 Context Window 组装

```text
┌─────────────────────────────────────────────┐
│ System Prompt（约 500 token）                  │
├─────────────────────────────────────────────┤
│ Long-term Memory（约 800 token，SQLite 检索）   │
├─────────────────────────────────────────────┤
│ Short-term Memory（约 600 token，SQLite 读取）   │
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
    def __init__(self, sqlite_path: str):
        self.short_term = SQLiteShortTermMemory(sqlite_path)
        self.summary = SQLiteSummaryMemory(sqlite_path)
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

摘要记忆每 20 笔触发 LLM 压缩时（MVP-2b 使用 DeepSeek V4 Pro），存在关键信息丢失的风险（如遗漏某笔 HIGH 风险交易的处理结果）。压缩质量需要可验证。

- 压缩前保存：触发压缩时，将待压缩的 20 条原始记录写入临时快照（JSON）。
- 压缩后校验：对压缩后的摘要文本做关键字段回检——
  - 所有 `risk_level = HIGH` 的条目是否在摘要中被提及。
  - 所有 `decision = PENDING_HUMAN` 的条目是否保留。
  - 摘要中包含的 flow_id 数量是否 >= 原始条数的 80%（允许低风险条目被合并概括）。
- 校验失败：丢弃本次压缩结果，保留原始记录，记录 WARNING 日志。
- MVP-2b：实现快照保存和高风险条目回检；校验失败时降级为不压缩（保留全量记录）。
- V1：增加压缩前后语义相似度评分（Embedding cosine similarity），低于阈值则告警。

## 8. Hook 链与硬约束设计

阶段：MVP-2b（注意：MVP-2a 先不加 Hook 链，让 Agent 先能正常调用 LLM）。

Hook 链是保证 Agent 安全、质量和可追溯性的门禁系统。MVP-1 先通过普通 service 校验和本地 trace 保证主链路可演示；MVP-2b 再把权限、校验、约束、日志和事务写入沉淀为统一 Hook 链。

**MVP-2b 只实现 6 个核心 Hook**（非全部 11 个），其余推迟到 V1。详见 `overall-architecture.md` 2.5 节。

### 8.1 Pre-Hook 链（MVP-2b 实现）

| 序号 | Hook | 职责 | 失败策略 | 阶段 |
|------|------|------|---------|------|
| ① | AuthHook | user_id 与 task_id 归属校验、角色权限校验（X-User-ID 模拟，V1 接 JWT） | 返回 403 | MVP-2b |
| ② | ValidationHook | 输入数据完整性、金额精度、必填字段校验 | 返回 400 | MVP-2b |
| ③ | MemoryHook | 调用 MemoryManager.build_context() 组装上下文 | 降级（跳过记忆，仅用 System Prompt） | MVP-2b |
| ④ | RateLimitHook | Redis Sliding Window 单用户频率控制 | 返回 429 | **V1** |
| ⑤ | CacheHook | 检查同一 queue_id 是否已处理 | 命中返回缓存结果 | **V1** |

### 8.2 Post-Hook 链（MVP-2b 实现）

| 序号 | Hook | 职责 | 失败策略 | 阶段 |
|------|------|------|---------|------|
| ⑥ | SchemaHook | Pydantic model_validate 校验 JSON 输出 | 重试（最多 3 次）→ 转人工 | MVP-2b |
| ⑦ | ConstraintHook | 硬约束校验（金额-风险一致性、evidence 非空、枚举合法） | 转人工（不重试） | MVP-2b |
| ⑧ | DecisionHook | 按置信度路由（直接落库 / L2 Fallback / L3 Fallback / 转人工） | 路由到对应分支 | MVP-2b |
| ⑨ | MemoryUpdateHook | SQLite ← 短期记忆 + 长期记忆（仅人工确认） | 非阻塞日志 | **V1**（MVP-2b 直接由 MemoryManager 处理） |
| ⑩ | LogHook | MySQL + structlog + LangFuse 写入 | 非阻塞日志 | **V1**（MVP-2b 内联到各节点） |
| ⑪ | TransactionHook | MySQL 事务写入台账 + 队列更新 + 任务统计更新 | 回滚 + 标记 FAILED | **基础设施**（非 Hook，独立于 Hook 链） |

### 8.2.1 事务与副作用分离

MVP-2b 的关键设计改进：将事务写入从 Hook 链中独立出来，不作为可选 Hook。

```
Agent 执行 → Post-Hook 链（Schema → Constraint → Decision，纯校验，无副作用）
           → 决策路由（Fallback / 转人工 / 直接落库）
           → 数据库事务（台账 + 队列 + 任务统计）← 核心，必须成功
           → 副作用操作（MemoryManager 更新 + structlog 日志）← 非阻塞，失败不影响主流程
```

### 8.2.2 Hook 熔断机制

当 Hook 依赖的外部服务（如 ChromaDB）不可用时，如果每个请求仍然尝试连接、等待超时、再降级，会导致整体延迟飙升。熔断机制确保失败快速传播，保护系统资源。

- 每个依赖外部服务的 Hook 维护一个熔断状态机：**CLOSED（正常） → OPEN（熔断） → HALF_OPEN（探测）**。
- 连续失败 N 次（默认 5 次）后进入 OPEN 状态，直接跳过该 Hook 并记录日志，不再尝试连接外部服务。
- OPEN 状态持续一段时间后（默认 30s），自动进入 HALF_OPEN，允许下一次请求尝试连接。
  - 尝试成功：恢复 CLOSED 状态。
  - 尝试失败：回到 OPEN 状态，等待下一个探测窗口。
- 熔断事件必须记录在 Agent 执行日志中，包含：Hook 名称、触发时间、失败原因、当前状态。
- MVP-2b 实现 MemoryHook（SQLite）和 RAG Subgraph（ChromaDB）的熔断器。
- V1 扩展至所有 Pre/Post Hook（包括 Redis 相关）。

### 8.3 硬约束规则

| 约束 | 描述 | 实现 | 阶段 |
|------|------|------|------|
| C1 | `decision` 必须在枚举值 {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED} 内 | Pydantic Literal | MVP-2b |
| C2 | `evidence` 不能为空列表 | Pydantic field_validator | MVP-2b |
| C3 | `|diff| > 10000` 时 `risk_level` 不能为 LOW | 自定义 ConstraintValidator | MVP-2b |
| C4 | `decision = PENDING_HUMAN` 时 `reason` 必须说明依据不足的具体原因 | 自定义 ConstraintValidator | MVP-2b |
| C5 | `decision = AUTO_FIXED` 时 `confidence` 必须 >= 0.85 | 自定义 ConstraintValidator | MVP-2b |
| C6 | RAG 无命中，或有命中但 `best_score < 0.5` 时禁止 `decision = AUTO_FIXED` | 自定义 ConstraintValidator | MVP-2b |

## 9. Agent 工作流设计

### 9.1 全局状态

```python
from typing import Any, Dict, List, Optional, TypedDict

class ReconciliationState(TypedDict):
    task_id: str
    user_id: str
    thread_id: str
    scenario_type: str
    current_queue_id: Optional[int]
    source_a_item: Dict[str, Any]
    source_b_item: Dict[str, Any]
    error_type: Optional[str]
    exception_branch: Optional[str]
    math_result: Dict[str, str]
    extraction_result: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    long_term_memory: List[Dict[str, Any]]      -- MVP-2b 新增
    short_term_memory: List[Dict[str, Any]]     -- MVP-2b 新增
    summary_buffer: Optional[str]               -- MVP-2b 新增
    audit_decision: Dict[str, Any]
    confidence: Optional[float]
    retry_count: int
    fallback_level: int                         -- MVP-2a 新增
    next_action: str
    error_message: Optional[str]
    agent_logs: List[Dict[str, Any]]
```

### 9.2 节点定义

| 节点 | 类型 | 职责 | 阶段 |
| --- | --- | --- | --- |
| `AuthCheckNode` | Hook | 权限校验、user_id 归属校验 | MVP-2b |
| `PreCheckNode` | 确定性代码 | 基础匹配、字段校验、规则引擎、异常分支路由 | MVP-0/MVP-1 |
| `ExtractionAgent` | LLM Agent（DeepSeek V4 Pro） | 模糊摘要结构化 | MVP-2a |
| `AuditAgent` | LLM Agent（DeepSeek V4 Pro） | 基于 RAG、记忆和工具结果做结构化审计建议 | MVP-0（确定性）→ MVP-2a（LLM） |
| `TraceAgent` | LLM + Tool（DeepSeek V4 Pro） | 跨日切、冲正、退款链路追溯 | MVP-1（关键词）→ MVP-2a（LLM）→ V2（Tool） |
| `HumanReviewNode` | 状态节点 | MVP-1 提供人工复核记录；MVP-2b 支持 Checkpoint 挂起/恢复 | MVP-1/MVP-2b |
| `ReportAgent` | LLM + Tool（DeepSeek V4 Pro） | 生成审计摘要和报告（数据来自 SQL 聚合） | V1/V2 |

### 9.3 工作流路由（详见 Section 3 各阶段描述）

MVP-2a 阶段：串行 + 条件路由。AuthCheck → PreCheck（按 scenario_type 选规则库与异常分支集合）→ 条件分支（根据 exception_branch 决定调用 ExtractionAgent、TraceAgent 或 RAG Subgraph）→ AuditAgent → Fallback 决策 → 事务写入。

MVP-2b 阶段：在上述基础上增加 Pre-Hook 链（Auth → Validation → Memory）、Post-Hook 链（Schema → Constraint → Decision）、可选并行（ExtractionAgent ∥ RAG Subgraph）、HumanReviewNode Checkpoint 挂起/恢复。

### 9.4 Agent 输出约束

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
      "source": "rag_knowledge/bank_clearing/reversal_refund.md#冲正识别规则",
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
| DeepSeek API 不可用 | 熔断 → 降级为确定性规则（if-else）→ 全部标记 PENDING_HUMAN |

### 9.6.1 Fallback 分级策略

多级 Fallback 不是简单的“重试”，每一级有不同的 Prompt 策略和信息增量，确保逐级为 Agent 提供更多判断依据。

| 级别 | 策略 | Prompt 变化 | 新增信息 | 阶段 |
|------|------|------------|---------|------|
| L1（默认） | 标准审计 Prompt | System Prompt + 当前异常项 + RAG 规则原文 | — | MVP-2a |
| L2（增强） | Few-shot 注入 | 在 Prompt 中追加 2-3 个同类异常的历史人工确认案例 | 差错台账中的历史处理记录 | MVP-2a |
| L3（追溯） | TraceAgent 深度查询 | 追加跨日切流水查询、原交易追溯、冲正链路校验结果 | Tool 返回的关联流水和追溯链 | MVP-2a |

Fallback 触发条件：

- L1 输出 `confidence < 0.85`，或 RAG 有命中但 `best_score < 0.5` → 进入 L2。
- RAG 无命中 → 直接转人工复核，不触发 Fallback。
- L2 输出 `confidence < 0.85` → 进入 L3。
- L3 输出 `confidence < 0.85` → 转人工复核。
- 任意级别抛出异常 → 记录日志，直接转人工（不跨级重试）。

## 10. 异常分支网络设计

系统不是简单的“对上了/没对上”二元判断，而是按 `scenario_type` 选择该场景的声明式规则引擎和异常分支集合，覆盖真实账务核对中的各类差错场景。MVP-1 先覆盖银企对账核心分支，确保本地产品闭环可演示；MVP-2a 再覆盖银企对账分支全集并接入清算对账少量典型分支。两套分支详见 `overall-architecture.md` §5。

### 10.1 核心接口

```python
class ExceptionRouter:
    async def route(
        self, scenario_type: str, source_a_item: dict, source_b_item: dict, diff: Decimal
    ) -> RouteResult:
        """
        按 scenario_type 选定规则库，再按 YAML 规则优先级逐一匹配，返回命中的分支和处理策略。
        确定性规则可覆盖的分支直接处理，无法覆盖的才进入 Agent 链路。
        """
        for rule in self.rule_engine.rules_for(scenario_type):
            if rule.matches(source_a_item, source_b_item, diff):
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

### 10.2 规则版本管理

YAML 规则文件会随业务场景扩展而迭代。规则变更需要有版本标识和变更历史，确保任何一次对账任务都可以追溯到所使用的规则版本。

- 规则文件头部包含 `version` 字段（如 `version: "1.0.0"`）。
- `t_reconciliation_task` 表记录 `rule_version`，每次任务启动时写入。
- `t_rule_hit_stats` 表按 `rule_id + rule_version` 维度统计命中率，支撑规则优化。
- MVP-1：规则文件头部加 `version` 字段 + `t_reconciliation_task.rule_version`。
- MVP-2a：`t_rule_hit_stats` 按版本统计。
- V2：规则 A/B 对比框架借用版本字段进行效果对比。

### 10.3 规则冲突检测

ExceptionRouter 按优先级逐一匹配，第一个命中即返回。当两个规则同优先级且条件存在重叠时，匹配结果取决于 YAML 文件中的声明顺序，行为不稳定。

- 加载时检测：`RuleEngine._load_rules()` 完成后，对同 priority 的规则两两检查条件是否可能存在交集。
- 检测到潜在冲突时：记录 WARNING 级别日志，列出冲突规则 ID 和重叠条件。
- 运行时不阻塞：冲突检测仅作为告警，不影响匹配执行（以免误报阻断流程）。
- MVP-1：实现同优先级规则的条件重叠检测和日志告警。
- MVP-2a：支持在规则文件中显式声明 `override: true` 标记有意覆盖的场景。

## 11. RAG 工作流设计

MVP-0 使用 Markdown 规则文档 + ChromaDB Top-K 检索证明 RAG 依据链路成立；MVP-2a 再引入 Query Rewrite、Hybrid Search、RRF 和 Reranker。知识库按 `scenario_type` 隔离（`rag_knowledge/bank_enterprise/` 与 `rag_knowledge/bank_clearing/`），检索时只命中当前场景库。V1 阶段补齐系统性 RAG 评测集和指标报告。

### 11.1 增强 RAG 流程（MVP-2a）

```text
规则文档 Markdown/PDF
  -> 文档清洗
  -> 结构化切片（按 ## 标题 + 语义边界混合策略，min_chunk=200, max_chunk=800）
  -> Dense 向量化（BGE-large-zh-v1.5）+ BM25 稀疏索引（jieba 分词）
  -> 存入 ChromaDB（按 scenario_type 分 collection，同时存储 dense vector 和 sparse metadata）
  -> 用户/Agent 输入自然语言查询（带 scenario_type）
  -> Query Rewrite（DeepSeek V4 Pro 把自然语言映射为规则术语）
  -> 在当前 scenario_type 知识库内双路召回：Dense Top-20 + BM25 Top-20（并行执行）
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
你是一个多账源对账（银企 / 清算）领域的查询改写助手。将用户输入的自然语言查询改写为规则检索关键词。

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

阶段：MVP-2b 准备评测集骨架（银企对账核心分支各 10 条，共约 50 条），V1 扩充至两个场景完整评测集并系统化运行。评测集按 `scenario_type` 分别组织与统计。

评测集规模按阶段递进：

| 阶段 | 评测集规模 | 覆盖范围 | 用途 |
|------|-----------|---------|------|
| MVP-2b | 50 条（核心 5 分支 × 10 条） | 核心异常分支 | 验证 RAG 检索基本可用，发现明显缺陷 |
| V1 | 120-180 条（12 分支 × 10-15 条） | 所有分支 + 边界 case | 评测脚本输出 Recall@5/MRR/NDCG@5，提供量化指标支撑 |
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

本项目不使用真实银行流水、真实客户信息或银行内部制度。所有演示数据均为项目人工构造的模拟数据，字段结构和异常模式来自银企对账与银行清算对账业务抽象。

数据设计需要同时满足三点：

- **安全合规**：姓名、账号、流水号、金额、摘要均为虚构或脱敏样式。
- **业务可信**：样本覆盖真实对账中常见的差错模式。
- **结果可复现**：每类样本都有明确的预期识别结果，方便测试和演示。

### 12.2 模拟数据类型

MVP-0 阶段至少准备主账源 / 对账账源两类 Excel（默认 `scenario_type = BANK_ENTERPRISE`）：

- 主账源 Source A：银企对账下为企业账簿 / ERP 明细；清算对账下为银行核心流水。
- 对账账源 Source B：银企对账下为银行流水；清算对账下为清算端 / 支付通道流水。

样本场景按 `scenario_type` 分两组、按阶段扩展。

银企对账（主场景）：

| 场景 | 说明 | 预期异常类型 | 阶段 |
| --- | --- | --- | --- |
| 正常平账 | 双账源流水号、金额、日期可匹配 | — | MVP-0 |
| 基础金额差错 | 流水可匹配但金额不一致 | AMOUNT_MISMATCH | MVP-0 |
| 银行已到账企业未入账 | 银行(B)有、企业账簿(A)无 | BOOK_UNRECORDED | MVP-0 |
| 企业已记账银行未到账 | 企业账簿(A)有、银行(B)无 | BANK_UNARRIVED | MVP-1 |
| 摘要/客户名不一致 | 金额一致但摘要或户名不同，需要语义结构化 | NARRATIVE_NAME_MISMATCH | MVP-1 |
| 疑似重复记账 | 同主体同金额时间差 < 5min | DUPLICATE_BOOKING | MVP-1 |
| 手续费/税费差异 | 金额差恰好等于标准手续费 / 税费 | FEE_TAX_DIFF | MVP-2a |
| 跨期入账 | 入账日期跨会计期间 | CROSS_PERIOD_POSTING | MVP-2a |
| 多币种尾差 | 不同币种精度差异导致的尾差 | AMOUNT_MISMATCH | V2 |

银行清算对账（副场景）：

| 场景 | 说明 | 预期异常类型 | 阶段 |
| --- | --- | --- | --- |
| 清算单边 | 清算端(B)有、核心(A)无 | CLEARING_SINGLE_SIDE | MVP-2a |
| 跨日切单边 | 日切窗口内当天单边，T+1 出现补记 | CUTOFF_CROSS_DAY | MVP-2a |
| 冲正/撤销/退款 | 摘要不规范，需要语义结构化 | REVERSAL_REFUND | MVP-2a |
| 银行核心单边 | 核心(A)有、清算端(B)无 | CORE_SINGLE_SIDE | V1 |
| 通道延迟 | 通道回盘延迟导致的短期单边 | CHANNEL_DELAY | V1 |
| 手续费分离 | 净额与交易额分离导致的差异 | FEE_SEPARATION | V1 |
| 重复清算 | 同订单 / 同金额多次清算 | DUPLICATE_CLEARING | V2 |
| 批量轧差异常 | 批量轧差总额与明细不符 | BATCH_NETTING_ANOMALY | V2 |

### 12.3 审计依据来源

审计依据由三层组成。

第一层是公开制度依据：

- 中国人民银行《支付结算办法》
- 中国人民银行《人民币银行结算账户管理办法》
- 财政部《会计基础工作规范》
- 财政部等五部委《企业内部控制基本规范》
- 财政部、国家档案局《会计档案管理办法》

第二层是项目自定义业务规则（Markdown/YAML 格式，标注为演示规则），按 `scenario_type` 分库维护（`rag_knowledge/bank_enterprise/`、`rag_knowledge/bank_clearing/`）。

第三层是 Agent/RAG 运行证据，包括 RAG 命中的规则来源、Dense/Reranker 分数、Agent 输出 JSON、Fallback 路径、人工复核记录和差错台账记录。

## 13. 报表审计设计

### 13.1 报表指标

报告需要包含：

- 任务编号、对账场景（`scenario_type`）、对账日期、处理用户。
- 主账源（Source A）总笔数 / 对账账源（Source B）总笔数 / 总金额。
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
  "scenario_type": "BANK_ENTERPRISE",
  "metrics": {
    "total_source_a_rows": 5000,
    "total_source_b_rows": 4996,
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
    "BANK_UNARRIVED": 28,
    "BOOK_UNRECORDED": 24,
    "FEE_TAX_DIFF": 20,
    "NARRATIVE_NAME_MISMATCH": 12,
    "CROSS_PERIOD_POSTING": 4
  }
}
```

### 13.3 ReportAgent 输出

按 `scenario_type` 选择报告模板，输出 Markdown 报告，包含：

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

- 能准备并使用两份模拟 Excel：主账源 source_a（企业账簿）和对账账源 source_b（银行流水），`scenario_type = BANK_ENTERPRISE`。
- 能通过 FastAPI 上传两份 Excel，并生成对账任务。
- 能使用 Pandas 完成字段校验、数据清洗和标准化。
- 能通过基础规则识别自动平账交易和异常交易。
- 能至少识别基础金额差错（AMOUNT_MISMATCH）和单边缺失（BANK_UNARRIVED / BOOK_UNRECORDED）两类异常。
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
- ExceptionRouter 第一版能覆盖银企对账核心分支：金额不一致、银行未到账、企业未入账、摘要/客户名不一致、疑似重复记账。
- 能处理银行未到账、企业未入账、摘要/客户名不一致、疑似重复记账样例。
- 前端仍使用手动刷新或轮询，不要求 SSE。
- 能记录 Agent 执行日志和本地 JSON trace。
- 多租户中间件第一版可工作，所有业务查询按 `user_id` 过滤。

### 15.3 MVP-2a 验收标准（Agent 智能化闭环）

- ExtractionAgent 从正则匹配升级为 DeepSeek V4 Pro 调用，能从不规范摘要中提取冲正/退款线索和原流水号。
- TraceAgent 从关键词匹配升级为 DeepSeek V4 Pro 调用，能识别跨日切/T+1 线索并给出追溯建议。
- AuditAgent 从 if-else 分支升级为 DeepSeek V4 Pro 调用，能基于 RAG 证据输出结构化审计决策（decision / risk_level / reason / confidence / evidence）。
- Agent 输出包含 `confidence` 字段，区分“建议自动平账（≥ 0.85）”和“建议人工复核（< 0.85）”。
- 所有 LLM 调用通过 OpenAI 兼容接口调用 DeepSeek API（`openai` SDK + DeepSeek base_url）。
- RAG 增强：Dense + BM25 双路召回 + RRF 融合 + Reranker 精排 + Query Rewrite。
- Reranker 和 Query Rewrite 可开关，关闭后主链路仍能运行。
- ExceptionRouter 覆盖银企对账异常分支全集，并接入清算对账少量典型分支。
- 3 级 Fallback 可工作：L1 标准 → L2 Few-shot → L3 TraceAgent。RAG 无命中时直接转人工。
- structlog 结构化日志覆盖所有 LLM 调用点，携带 trace_id / prompt_version / fallback_level。
- Prompt 文件独立存放并纳入版本控制。
- 附带 Prompt 版本对比脚本，能对比不同版本的 confidence 分布和 decision 一致性。
- 数据库完成 MVP-2a 所需字段新增（prompt_version、fallback_level、llm_tokens、rag_scores_json 等）。
- 端到端集成测试覆盖银企对账主链路（正常平账、金额差错、银行未到账、企业未入账、手续费/税费差异）；清算对账覆盖少量典型场景（清算单边、跨日切）。
- Agent 输出质量评估脚本可运行：验证 decision 合法性、evidence 非空、confidence 在合理区间。
- 同一异常输入跑 10 次，decision 分布不出现 A/B 各半的随机情况（否则 Prompt 需优化）。

### 15.4 MVP-2b 验收标准（Agent 工程化闭环）

- Hook 链、记忆引擎、Checkpoint 接入银企对账与清算对账两个场景。
- Hook 链核心 6 个可工作：AuthHook、ValidationHook、MemoryHook → SchemaHook、ConstraintHook、DecisionHook。
- 事务写入从 Hook 链独立，作为基础设施保障。副作用操作（记忆更新、日志）非阻塞。
- 记忆引擎 SQLite-only 版可工作：短期记忆（thread_id 隔离 + TTL 清理）、长期记忆（user_id 隔离）、摘要记忆（满 20 笔触发 DeepSeek 压缩）。
- MemoryManager.build_context() 能组装完整 Context Window（System → Long-term → Short-term → Summary → RAG → Current Item）。
- 摘要压缩质量验证可工作：快照保存、高风险回检、失败降级。
- MemoryHook 和 RAG Subgraph 熔断器可工作（CLOSED → OPEN → HALF_OPEN）。
- LangGraph HumanReviewNode 支持 Checkpoint 挂起和恢复。
- Agent 并行执行决策：基于 MVP-2a 的真实延迟数据，决定是否引入 ExtractionAgent ∥ RAG Subgraph 并行。
- Agent 决策回归测试（统计方法）：同一输入跑 10 次，统计 decision 分布，断言仅检查结构化字段合法性。
- RAG 评测集约 50 条（银企对账核心分支各 10 条），评测脚本按 `scenario_type` 输出 Recall@5/MRR/NDCG@5。
- structlog 日志和本地 JSON trace 能记录 Hook、Fallback、RAG 和 Agent 输出。

### 15.5 V1 验收标准

- 前端支持场景选择，上传页按 `scenario_type` 切换字段模板，RAG / Prompt / 报告模板自动切换。
- Celery/ARQ 后台异步对账任务。
- 支持 JWT 登录。
- 记忆引擎 Redis 升级完成（短期记忆从 SQLite 迁移到 Redis）。
- RateLimitHook、CacheHook 接入 Redis。
- Agent 执行过程通过 SSE 展示（含 Pre/Post Hook 状态、Fallback 层级）。
- 支持手续费/批量业务差异样例。
- 支持 Markdown 审计报告。
- RAG 评测集可用（120+ 条），输出 Recall@5/MRR/NDCG 数据。
- Agent Schema 符合性测试可运行。
- 量化指标仪表板可用。
- README 包含本地启动和演示账号。
- MCP 协议工具层可作为加分项独立运行，不作为 V1 必须验收项。

### 15.6 V2 验收标准

- 支持重复入账和漏记账样例。
- RAG A/B 对比框架可运行。
- Agent 执行日志离线分析可用。
- 支持 Prompt 版本记录和效果对比。
- 支持 PDF 报告导出（含图表）。
- 能输出失败样本分析报告。
- 压力测试通过（单任务 50000 笔流水），并记录 P50/P95/P99、内存峰值和数据库写入耗时。
- 能输出失败样本分类：RAG 未命中、规则冲突、Agent JSON 失败、证据不足、人工推翻。
- 能完成基础安全验证：越权访问、user_id 隔离、日志脱敏、Prompt injection 基础防护。
- Docker Compose 可启动前端、后端、MySQL、Redis 和 ChromaDB。
- 项目可部署到云服务器。

## 16. 生产级可靠性保障

### 16.1 Agent 工具调用权限模型

大模型能力强大，但 Agent 在真实企业环境中不能随意调用工具或访问数据库。本系统定义三级权限边界，从 MVP-2a 阶段开始逐步落地。

| 权限级别 | 范围 | 说明 | 阶段 |
|---------|------|------|------|
| L0 - 只读查询 | RAG 检索、差错台账查询、历史记忆检索 | Agent 可自由调用，不修改任何数据 | MVP-2a |
| L1 - 结构化输出 | Agent 输出 JSON 审计建议 | 输出必须通过 Schema + Constraint Hook 校验才能被消费 | MVP-2a |
| L2 - 数据库写入 | 台账落库、队列更新、任务统计 | Agent **禁止直接写入**，必须通过 TransactionHook 事务保障 | MVP-2b |

每个 Agent 节点的工具调用白名单：

| Agent | 可调用工具 | 禁止操作 |
|-------|-----------|---------|
| ExtractionAgent | 无（纯 LLM 推理） | 禁止调用任何数据库操作 |
| AuditAgent | RAG 检索（只读）、差距计算函数调用结果 | 禁止修改台账、禁止修改队列状态 |
| TraceAgent | T+1 流水查询（只读）、历史追溯查询（只读） | 禁止修改流水数据 |

Agent 越权检测机制：
- Hook 链的 Post-Constraint Hook 校验 Agent 输出中是否包含不应有的数据库操作指令。
- 若检测到 Agent 尝试越权（如在 `reason` 字段中建议直接修改台账），立即标记为 `PENDING_HUMAN` 并记录安全事件日志。
- V1 阶段增加 Prompt Injection 基础防护：检测用户上传的 Excel 摘要字段是否包含指令注入模式。

### 16.2 可靠性保障

**优雅降级**（MVP-2a）：
- DeepSeek API 不可用 → 自动降级为确定性规则引擎（if-else），所有异常标记为 `PENDING_HUMAN`。
- RAG ChromaDB 不可用 → Agent 使用"无 RAG"模式，`evidence` 为空列表，`decision` 强制为 `PENDING_HUMAN`。
- 降级事件必须记录 WARNING 级别日志，包含降级原因、触发时间、影响范围。

**重试与熔断**（MVP-2a）：
- LLM API 调用失败：最多重试 3 次，使用指数退避（1s / 2s / 4s）。
- 连续 5 次失败 → 熔断器 OPEN，后续请求直接跳过 LLM 调用（降级为确定性规则），30s 后 HALF_OPEN 探测。
- 熔断状态机与 Hook 熔断机制共用实现。

**Token 预算上限**（MVP-2a）：
- 单笔异常处理的最大 Token 预算：输入 4000 + 输出 1000 = 5000 token。
- 超出预算仍无结果 → 降级为确定性规则，标记 `PENDING_HUMAN`。
- 单批次对账任务的总 Token 上限：可配置（默认 500,000 token），达到上限后剩余异常全部标记 `PENDING_HUMAN`。

### 16.3 记忆一致性保障

记忆引擎（MVP-2b）需要解决"记住一步忘记三步"的问题：

**写入事务保证**：
- 短期记忆写入与台账事务同步：同一事务内完成台账落库 + 短期记忆写入，回滚时两边一致。
- 长期记忆仅写入人工确认结果：`is_human_confirmed=True` 时才写入长期记忆，避免 Agent 的错误判断污染长期记忆。

**并发读取一致性**：
- 同一 `thread_id` 内的记忆读写串行化，通过数据库行锁保证。
- 摘要压缩触发时，先保存快照（JSON），压缩完成并校验通过后，再原子替换旧摘要。校验失败则保留旧摘要不变。

**记忆回滚**：
- 人工复核推翻 Agent 建议时（如 Agent 建议 `AUTO_FIXED` 但人工判为 `FORCE_HOLD`），从短期记忆中删除该条记录，避免后续 Agent 被错误上下文影响。

## 17. 风险与边界

### 17.1 数据边界

- 只使用模拟数据和脱敏数据。
- 不使用真实客户数据。
- 不使用银行内部资料。
- 演示数据中的姓名、账号、流水号均为虚构或脱敏。
- 公开制度依据只作为项目规则设计参考，不直接等同于真实银行内部审计制度。
- 项目自定义规则必须明确标注为演示规则，不冒充银行内部制度。
- 公开制度依据与项目自定义规则按 `scenario_type` 分库作为 RAG 知识来源（银企对账侧重会计基础与内部控制，清算对账侧重支付结算），不使用任何银行内部资料或真实客户数据。

### 17.2 AI 决策边界

- AI 不做金额计算（只读取工具返回的 READ-ONLY 结果）。
- AI 不直接修改账务状态（所有写入经事务保障）。
- AI 不做最终金融决策（低置信度 + 无依据 + 高风险均转人工）。
- AI 只提供结构化分析、规则引用和处理建议。

### 17.3 安全与隔离边界

- 所有 API 请求必须携带 X-User-ID。
- 所有数据库查询由中间件强制注入 WHERE user_id 条件。
- 记忆检索（SQLite）按 user_id 隔离。
- RAG 知识库、规则库与报告模板按 scenario_type 隔离，避免跨场景串用。
- LangGraph 会话状态按 thread_id 隔离。
- AuthHook 是 Pre-Hook 链的首节点，任何权限校验失败均不启动 Agent。

### 17.4 项目边界与 SLA 目标

本项目为个人开源项目，不宣称可直接用于真实生产银行系统。以下为各阶段的目标 SLA：

| 指标 | MVP-2a 目标 | V1 目标 | V2 目标 |
|------|-----------|--------|--------|
| 单笔异常处理延迟（P95） | < 5s（含 LLM 调用） | < 3s（异步队列） | < 2s |
| Agent 决策可用率 | > 95%（含降级） | > 99% | > 99.5% |
| 单任务最大流水行数 | 1,000 | 10,000 | 50,000 |
| 上传接口响应时间 | 同步（< 30s） | 异步（< 1s 返回 task_id） | 异步 + 进度回调 |

**安全审查清单**（V2 阶段执行）：
- 依赖安全扫描：`pip-audit`（Python）/ `npm audit`（前端）
- 静态代码分析：Bandit（Python）/ Semgrep（通用）
- OWASP Top 10 检查：SQL 注入、XSS、路径遍历、敏感信息泄露、SSRF
- Prompt Injection 基础防护：上传数据中的指令注入模式检测
- 越权测试：user_id 隔离验证、task_id 跨用户访问测试
- 日志脱敏：确保 trace/日志中不出现完整账号、姓名等模拟敏感字段

## 18. LLM 选型说明

### 18.1 为什么选择 DeepSeek V4 Pro

| 维度 | DeepSeek V4 Pro | 其他方案 | 选择理由 |
|------|---------------|---------|---------|
| **成本** | 极低（输入约 ¥1/百万 token，输出约 ¥2/百万 token） | Claude Opus 约 ¥75/百万 token | 个人项目可承受大量调试调用 |
| **中文能力** | 顶级（C-Eval、CMMLU 等中文基准领先） | 多数海外模型中文训练数据有限 | 多账源对账场景全部是中文 |
| **安全性** | 国内模型，无需跨境数据传输 | 海外模型 API 涉及数据出境 | 银行场景的合规直觉 |
| **接口兼容** | OpenAI 兼容接口（`openai` SDK + 自定义 base_url） | — | 零迁移成本，生态兼容性好 |
| **开源可私有化** | 提供开源权重 | 闭源模型无法本地部署 | V2 阶段可本地部署以消除 API 依赖 |

### 18.2 DeepSeek API 集成方式

```python
# 使用 openai SDK，指向 DeepSeek API
from openai import OpenAI

client = OpenAI(
    api_key="sk-xxx",  # DeepSeek API Key
    base_url="https://api.deepseek.com/v1",
)

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "你是多账源对账审计助手..."},
        {"role": "user", "content": "请判断以下异常..."},
    ],
    temperature=0.1,  # 金融场景需要低温度
    response_format={"type": "json_object"},  # 结构化输出
)
```

### 18.3 依赖管理

MVP-2a 新增依赖：

```toml
# pyproject.toml 新增
"openai>=1.0.0",            # DeepSeek API 调用（OpenAI 兼容接口）
"structlog>=24.0.0",        # 结构化日志
"jieba>=0.42.0",            # BM25 中文分词
"rank-bm25>=0.2.0",         # BM25 稀疏检索
```

MVP-2b 无新增外部依赖（记忆引擎全用 SQLite，无需 Redis）。
