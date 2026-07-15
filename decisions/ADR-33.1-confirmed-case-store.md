# ADR-33.1: 以可追溯人工确认案例库替代通用记忆引擎

- **Status**: accepted
- **Date**: 2026-07-15
- **Stage**: `stage-33-confirmed-case-store`
- **Deciders**: 用户（2026-07-15 确认 ADR）、Codex（提案与整理）
- **Related**: `decisions/ADR-DELETE.1-remove-independent-memory-subsystem.md`、
  `decisions/ADR-28.1-deterministic-readonly-tool-boundary.md`、
  `decisions/ADR-28.2-typed-tool-outcome-and-fail-closed.md`、
  `decisions/ADR-29.1-persistent-execution-trace-model.md`、
  `decisions/ADR-32.1-minimal-review-decision-context.md`

## Context

本项目曾有短期、长期、摘要三层 memory 子系统。`ADR-DELETE.1` 已明确将其从正式架构中移除：
对账 Agent 不应默认消费跨任务的自由文本记忆，而应在低置信度 Fallback L2 按需读取可追溯的历史人工
确认案例。

当前实现已经有最小历史案例查询，但它只是 `LedgerFallbackCaseProvider` 对 `t_error_ledger` 的直接查询：

- 按 `user_id + exception_branch` 过滤 `FIXED / HELD`；
- 按处理时间取最近 3 条；
- 返回 `flow_id`、异常类型、AI 意见、置信度和处理状态；
- 通过既有 `load_confirmed_cases` 只读 Tool 在 L2 使用。

该实现不能作为稳定案例库：

- `LedgerService.replace_task_rows()` 会在任务重跑时删除并重建该任务的台账行，历史案例可能被覆盖；
- 台账没有案例状态、版本链、失效原因、签名、规则内容版本或质量门禁；
- 当前查询不能区分重复案例、正反案例冲突和弱匹配；
- `rag_source` 是展示型字符串，硬约束结果分散在 Agent 日志，人工复核时难以构造规范化案例快照；
- 人工复核请求允许客户端提交 `handler_username`，操作人身份不是可信审计事实；
- `BC-R003` 的 T+1 候选查找返回第一个满足条件的候选，未显式处理多个候选；
- 当前 Prompt 直接消费案例字段，没有案例专属安全投影和上下文预算契约。

本项目是财务对账原型。历史案例只能辅助当前有规则证据的低置信判断，不能成为隐式业务规则、
跨租户画像、实体识别系统或自动多数投票机制。

## Decision Drivers

- 人工确认案例必须能追溯到原始复核、业务事实、规则证据和硬约束结果。
- 任务重跑、规则变化和案例纠错不能改写已经被 Agent 使用过的历史事实。
- 案例检索必须显式按 `user_id` 隔离，并在缺证据、冲突或工具失败时 fail closed。
- 金额、日期、候选唯一性和适用范围由确定性代码处理，不交给 LLM 推断。
- V1 应复用现有 MySQL、Tool Executor、Trace Store 和 L2 工作流，不引入新基础设施。
- 先证明安全、可追溯和质量不退化；没有可信实测时不得宣称准确率提升。

## Options Considered

### Option A：恢复短期、长期、摘要三层 Memory Engine

优点：可以统一保存会话内容、人工结论和摘要，并提供通用上下文组装能力。

缺点：重新引入已被 `ADR-DELETE.1` 删除的独立状态面；自由文本记忆容易产生跨任务污染、错误累积、
租户隔离风险和摘要证据损失；与当前“规则证据优先、历史案例仅作 L2 辅助”的架构冲突。

### Option B：继续直接查询 `t_error_ledger`

优点：改动最少，不新增表或写入路径。

缺点：台账是当前任务状态而不是稳定历史投影；任务重跑可以覆盖记录；无法表达案例质量、版本、规则
兼容、冲突、撤销和可解释匹配，不能满足长期可审计的案例复用契约。

### Option C：独立 Confirmed Case Store，使用确定性结构化检索（采纳）

在现有 MySQL 中新增 `t_confirmed_case`，由人工复核事务生成不可变案例快照；只将通过确定性质量门禁
的案例提供给 L2。检索继续通过 `load_confirmed_cases` Tool，V1 不使用向量检索。

优点：案例生命周期和当前台账状态解耦；可以版本化、撤销、失效、检测冲突并保留完整审计链；复用
现有数据库和 Tool/Trace 边界，不恢复通用记忆引擎。

缺点：新增持久化模型、复核请求字段、规则/签名 policy 和 shadow 发布门禁；案例写入进入人工复核
核心事务，数据库约束或写入失败会使复核回滚。

### Option D：独立案例库并以 Embedding / ChromaDB 做首版检索

优点：可以召回文本表达不同但语义相近的案例。

缺点：缺少可信案例规模和离线相关性证据；相似度阈值难以解释；会增加向量索引一致性、Embedding
版本和额外故障面。V1 的两个试点分支都有足够的结构化事实，不需要先引入语义检索。

## Decision

采用 **Option C**。

### 1. 能力边界与命名

项目不使用统一 `Memory Engine`。状态能力继续拆分为：

- `ReconciliationState`：单次运行内的 Session/Workflow State；
- LangGraph `SqliteSaver`：人工复核子图的 Checkpoint Store；
- `t_confirmed_case`：人工确认案例的 Historical Case Store；
- `t_trace_span`：append-only Trace Store。

Historical Case Store 复用的是异常处理模式，不建立用户画像，不承担实体识别、会话历史或自由文本长期
记忆。案例只在低置信度 Fallback L2 按需读取，不进入默认 L1 Prompt。

### 2. 来源事实、独立投影与不可变生命周期

`t_error_ledger` 继续表示当前差错状态，`t_human_review` 继续表示人工操作事实；新增
`t_confirmed_case` 作为人工确认事实的稳定检索投影，不取代前两者的 source of truth。

每次有效人工终态都生成独立案例，包括：

- `APPROVED_MATCH → FIXED` 正向案例；
- `FORCE_HOLD → HELD` 反向案例。

案例不可原地改写或物理删除。生命周期至少包含：

- `RECORDED`：已保存，但不可检索；
- `ACTIVE`：通过质量门禁，可以检索；
- `SUPERSEDED`：被后继案例版本取代；
- `REVOKED`：确认原案例错误；
- `EXPIRED`：规则、适用期或业务边界失效。

纠错必须创建新版本并通过 `supersedes_case_id` 形成版本链。检索只读取 `ACTIVE`。撤销、失效和替代
必须记录操作人、时间和原因。

### 3. 全部记录、门禁激活

所有人工终态都写入案例快照；只有通过确定性质量门禁的案例自动成为 `ACTIVE`，不增加第二名案例
管理员审批，也不调用 LLM 判断案例质量。

`ACTIVE` 至少要求：

- 当前分支存在受支持且版本化的 Case Policy；
- 能生成完整、合法的 `case_signature`；
- 有可信 `source_review_id` 和人工最终动作；
- 有该分支允许的结构化 `decision_reason_code`；
- 有决策所需的业务事实快照和硬约束执行结果；
- 至少有一个可追溯的正式规则/政策证据；
- 规则内容版本与 Case Policy 兼容；
- 不属于 V1 明确禁止激活的多候选场景。

质量不足不是人工复核失败：案例正常写为 `RECORDED`，并保存结构化 `gate_failures`。人工结论本身
不能替代正式规则证据。`OTHER` 必须有备注，但 V1 默认只能生成 `RECORDED` 案例。

### 4. 原因码治理

`decision_reason_code` 按 `exception_branch` 维护受控、版本化目录，仅保留少量全局兜底码。原因码进入
版本控制，不允许数据库或前端自由新增；案例保存 `reason_catalog_version`。

原因码用于案例门禁、结果分层和统计，不直接决定最终动作，也不作为当前交易的相似匹配输入。当前待
判断交易尚无人工原因码；将原因码放进匹配签名会掩盖本应暴露的相反结论冲突。

具体原因码集合属于 Stage spec，不在本 ADR 中冻结。

### 5. 单表混合数据模型

使用一个 `t_confirmed_case`，不为每个异常分支建表，不使用 EAV，也不把全部字段放进不可索引 JSON。

公共强类型列至少覆盖：

- 标识与隔离：`id`、`user_id`、`source_review_id`；
- 分类：`scenario_type`、`exception_branch`、`error_type`；
- 结论：`final_action`、`final_status`、`ai_suggestion`、人工是否推翻 Agent；
- 治理：`decision_reason_code`、原因码版本、案例状态、版本关系和失效审计字段；
- 匹配：签名版本/hash、规则集合 hash、币种、方向、金额、代表性日期/时间；
- 时间：`valid_from`、`valid_to`、`created_at`。

分支专属结构使用严格 Pydantic schema 校验的版本化 JSON：

- `signature_payload`；
- `facts_snapshot`；
- `evidence_refs`；
- `constraint_results`；
- `source_refs`；
- `gate_failures`。

金额同时使用 `Decimal / DECIMAL` 强类型列，不依赖 JSON 字符串参与业务检索。V1 不依赖 MySQL JSON
虚拟列索引。

### 6. 最小不可变快照与安全投影

案例保存足以解释当时结论的最小不可变业务事实，同时保存指向原始 review、ledger、transaction 和
Trace 的来源引用。它不复制整份上传文件、完整 Prompt、完整 Trace 或无关交易字段。

案例只复用项目已有脱敏字段；完整账号、完整流水号、未脱敏主体名称和 reviewer 身份不得进入
Historical Case Prompt。深度审计通过 tenant-scoped `source_refs` 回查；来源缺失必须明确显示
`SOURCE_UNAVAILABLE`，不得补造数据。

原始人工 `remark` 保存在案例审计快照中，但 V1 永不将其注入 Prompt、Tool 安全投影或普通 Trace，
避免自由文本成为跨任务 Prompt injection 通道。Prompt 只使用结构化原因码及其受控说明。

### 7. 规范化最终决策上下文

案例生成不得扫描 Agent 日志并猜测最终一次调用。工作流落库时同步在 `t_error_ledger` 保存规范化的
canonical decision context，至少包括：

- 结构化 `evidence_refs`；
- 结构化硬约束结果；
- 最终 Prompt 版本；
- 实际规则集合 hash；
- decision context schema version。

只保存最终落库决策对应的证据，不混入失败重试的中间输出。既有 `rag_source` 可以作为兼容展示字段
继续存在，但不能承担 Case Store 的证据契约。Agent 日志和 Trace 继续用于执行审计，不作为案例快照
的 canonical source。

### 8. 人工复核与案例写入原子提交

人工复核记录、差错台账终态、队列/任务更新和案例快照在同一个 `engine.begin()` 事务中原子提交。

- `source_review_id` 使用唯一约束防止重复审批或 Checkpoint 恢复生成重复案例；
- 质量门禁不通过时写 `RECORDED`，不得抛出业务异常阻塞复核；
- Case Store 数据库写入或约束失败时整个复核事务回滚，避免部分成功；
- 未来若增加向量索引，索引写入必须是可重建的事务后投影，不能进入核心事务。

人工复核请求不再信任客户端提交的 `handler_username`。复核和案例治理 actor 统一来自 JWT `sub`；
前端可以显示当前用户，但不能编辑操作人。

### 9. Tool 与工作流接入

继续复用 `load_confirmed_cases` Tool 和现有确定性 Tool Executor：

```text
Workflow L2
  → ToolExecutor.execute("load_confirmed_cases")
    → ConfirmedCaseStore.search()
      → t_confirmed_case
```

- AuditAgent 不直接访问数据库；
- Tool 只允许 `fallback_level=2`，身份和资源归属来自可信 `ToolContext`；
- RAG 无命中仍直接转人工，历史案例不得替代当前正式规则证据；
- L1 高置信时不查询案例，避免历史锚定；
- Tool `EMPTY`、技术 `FAILED` 或领域冲突都稳定进入人工路径。

通用 ToolStatus 保持 `SUCCEEDED / EMPTY / FAILED`。案例冲突是技术执行成功后的领域结果：

```text
ConfirmedCaseRetrievalOutcome = MATCHES | CONFLICTING_CASES
```

`SUCCEEDED + CONFLICTING_CASES` 必须被 Workflow 显式路由到 `PENDING_HUMAN`，并记录稳定
`fallback_reason`；不能误报成基础设施失败，也不能继续让 LLM 裁决。

### 10. 确定性结构化检索与结果组合

V1 不使用 Embedding。候选先经过硬过滤：

- 相同 `user_id`；
- `case_status = ACTIVE`；
- 相同场景和异常分支；
- 兼容错误类型、规则内容版本、Case Policy 和适用期。

匹配使用分支级可解释等级，不输出跨分支的伪精确统一分数：

- `EXACT_SIGNATURE`：版本化签名完全一致，可参与硬冲突检测；
- `STRONG_MATCH`：满足该分支全部必需业务类别，可进入 Prompt；
- `WEAK_MATCH`：只用于诊断统计，不能为凑 Top-K 注入 Prompt。

每条结果输出 `match_level`、`matched_fields`、`mismatched_fields` 和必要的距离事实。连续金额/时间距离
只在同一业务匹配等级内排序，不绕过硬过滤。

V1 最多返回 3 条、优先覆盖正反案例：最高排名正例 1 条、最高排名反例 1 条、能够补充不同规则或
原因的最高排名案例 1 条。缺少某类时允许少于 3 条，不使用弱案例补满。历史多数、
`historical_approve_rate` 或重复出现次数不得直接决定当前动作。

相同 `signature_hash + final_action + decision_reason_code + rule_set_hash` 的案例全部保留审计记录，但
检索时折叠为一个代表案例；`support_count` 只进入指标和管理查询，默认不进入 Prompt。

### 11. 冲突、规则版本和适用期

相同版本化签名下出现相反人工结论时返回 `CONFLICTING_CASES`：

- 不覆盖、不合并、不选择较新案例；
- 不交给 LLM 选择；
- 当前流程 fail closed 转人工；
- competing cases 保留，直到人工撤销、失效、替代或补充更精确的适用范围。

案例绑定实际参与决策的规则 ID 集合和内容 hash。当前规则内容不兼容时，旧案例立即退出检索；不能仅
因 `rule_id` 相同继续使用。重新验证后必须创建新案例版本，不原地更新 hash。

不设置无业务依据的全局 TTL。案例有效性以规则内容版本、`valid_from / valid_to` 和分支 policy 为主；
只有正式业务规则声明最大年龄时才允许设置 `max_case_age_days`。案例新鲜度可以作为同级排序因素。

### 12. V1 试点分支

公共案例模型记录全部人工终态，但 V1 只有以下分支具备激活和检索 policy：

- `BE-R002 / AMOUNT_MISMATCH`；
- `BC-R003 / CUTOFF_CROSS_DAY`。

其他分支只生成 `RECORDED`，后续每增加一个分支都必须明确原因码、签名、强匹配规则和离线评测样例。

#### 12.1 `BE-R002` policy

`EXACT_SIGNATURE` 只包含确定性输入事实和规则版本：场景、分支、错误类型、规则集合 hash、币种、
交易方向、交易类型、两侧金额、差额、可用费用和直接相关 posting/status 特征。金额先以 Decimal
规范化到数据库精度。

签名不包含结论、原因码、Agent confidence、reviewer、自由文本、task/flow 标识、实体名称或绝对
业务日期。

`STRONG_MATCH` 要求规则、币种、方向、兼容交易类型、差额正负方向、C3 `10000` 风险边界和费用
关系类别一致。费用关系由确定性代码计算为 `DIFF_EQUALS_FEE`、
`DIFF_PARTIALLY_EXPLAINED_BY_FEE` 或 `NO_FEE_EXPLANATION`。绝对/相对差额和金额规模距离只用于
同级排序，不设置未经评测的全局百分比准入阈值。

#### 12.2 `BC-R003` policy

现有 T+1 候选查询必须从“返回第一个”改为显式区分：

- 0 个：`EMPTY`；
- 1 个：`UNIQUE_MATCH`；
- 多个：`COMPETING_CANDIDATES`。

多个候选不按顺序或分数自动选择，直接转人工。即使人工选定一个候选，该案例在 V1 仍只能
`RECORDED`；在没有候选消歧或 Entity Resolution 前不能激活。

`EXACT_SIGNATURE` 包含场景、分支、错误类型、规则集合 hash、cutoff policy/version 和实际时间窗口、
币种、交易类型、渠道、清算金额、trade date/time、cutoff 命中结果和 T+1 候选状态。唯一候选存在时
还包含候选金额、accounting date、日期偏移和命中的引用类型集合，但不包含实际流水号、引用号内容、
实体名称、结论或自由文本。

日期和时间按明确时区规范化；金额使用 Decimal；cutoff 配置变化产生新的 policy/hash。

`STRONG_MATCH` 要求规则和 cutoff policy、币种、兼容交易类型/渠道、cutoff 命中、工作日/周末类别、
候选状态一致。`UNIQUE_MATCH` 还要求金额相等、accounting date 为 trade date + 1 calendar day，且引用
类型兼容。时间位置、金额规模、交易日期和新鲜度只用于排序。

V1 不引入节假日日历，因此不得宣称识别“下一工作日”。未来引入正式日历时必须升级 policy 和签名
版本。

### 13. Prompt 安全投影与预算

Case Prompt Projection 只包含案例 ID、关键业务事实、最终动作、结构化原因码及标准说明、规则证据、
硬约束结果、匹配等级和命中理由。它不包含原始 remark、完整 Trace、完整 Prompt 或敏感标识。

V1 不建设 evidence-aware semantic compression，不增加模型专属 tokenizer 依赖。调用前使用固定 schema、
字段白名单、最多 3 条案例和独立序列化大小上限；超预算时整条删除最低排名案例，不截断金额、日期、
规则 ID 或硬约束字段，也不能让历史案例挤出当前事实和当前 RAG 证据。

调用后记录 provider 返回的真实 `prompt_tokens`、延迟和成本，用 shadow baseline 校准默认大小上限。
如果删除全部案例仍无法满足整体安全上限，转人工，不发送残缺 Prompt。

### 14. 旧数据迁移与治理接口

已有 `t_human_review` 记录允许通过幂等迁移脚本生成 `RECORDED` 案例，但绝不自动激活：

- 只迁移能够关联真实人工复核的终态；
- 不从自由文本猜测原因码；
- 不用当前规则反推历史规则 hash；
- 缺失字段原样记录在 `gate_failures`；
- 无法可靠关联的记录只进入迁移报告，不生成伪案例。

V1 不提供通用 CRUD、手工直接创建/编辑案例或独立管理页面。案例只能由人工复核事务生成；提供
tenant-scoped 只读列表/详情/来源/版本链，以及有限的 revoke 和 successor version 操作。不能直接把
`RECORDED` 改为 `ACTIVE`。

V1 不引入完整 RBAC 或 maker-checker。所有治理操作使用 JWT actor，并显式按 `user_id` 隔离。

### 15. Shadow 发布和证据门禁

Case Store 使用 `off → shadow → active` 三态：

- `off`：不读写新 Case Store，仅用于紧急回退；
- `shadow`：生成案例并执行新检索，记录结果，但不把新案例注入 Prompt或改变当前决策；
- `active`：新 Case Store 成为 `load_confirmed_cases` 的正式 provider。

默认先进入 `shadow`。进入 `active` 至少要求：

- 跨用户案例泄漏为 0；
- 非 `ACTIVE`、规则不兼容和过期案例泄漏为 0；
- exact-signature 冲突无漏检；
- competing T+1 candidates 不被当作唯一候选；
- Prompt 投影保留金额、日期、规则引用和硬约束结果；
- 工具失败、空结果和冲突都稳定转人工；
- 两个试点分支的固定 fixture 检索结果符合标注；
- 固定评测集上 L2 决策质量不低于 baseline，硬约束通过率不下降；
- token、延迟和成本增量处于 Stage spec 依据 shadow 数据设定的边界内。

安全契约通过且质量不退化即可激活；真实样本不足时，准确率收益记为 `not_measured`，不得宣称提升。
只有在独立人工标注集和固定真实 provider 上取得可信结果后，才允许发布提升百分比。

旧台账检索与新 Case Store 不作为两套长期正式逻辑维护。`active` 稳定后应移除旧 provider，只保留
明确的紧急回退边界。

## Consequences

### Positive

- 历史案例从可被任务重跑覆盖的台账查询，变为稳定、版本化、可撤销的审计投影。
- 正反案例、弱匹配、规则失效和冲突都有确定性语义，历史案例不会成为隐式多数投票。
- 复用现有 MySQL、Tool Executor、Trace Store 和 L2 工作流，不恢复通用记忆或新增向量基础设施。
- 案例写入、人工复核和台账状态原子一致；每条 Prompt 案例可追溯到人工结论、规则证据和业务事实。
- Shadow 和 fail-closed 门禁允许在不夸大准确率收益的情况下证明安全与可维护性。

### Negative

- 人工复核事务新增案例表写入；Case Store 数据库错误会阻止复核提交。
- `t_error_ledger` 需要新增规范化决策上下文字段，schema、service Table 和写入链路必须同步。
- Review API 移除客户端 `handler_username` 并增加原因码，后端、前端和测试需要同步修改。
- 每个新异常分支都需要独立原因码、签名、匹配和评测 policy，不能通过一个通用算法自动扩展。
- 初期大量旧案例会停留在 `RECORDED`，可检索覆盖率可能很低；这是质量门禁的预期结果。

### Risks

- 签名遗漏关键业务维度可能制造假冲突；解决方式是 fail closed，并通过新 policy version 补充字段。
- 签名过严可能导致检索经常为空；不得通过放宽租户、规则或候选唯一性门禁提高召回。
- Shadow 样本不足时只能证明契约正确，不能证明决策收益；发布说明必须保持该边界。
- 同一事务写案例增加复核路径耦合；实现必须让“质量不足”落为 `RECORDED`，只让真实数据库失败回滚。

## Out of Scope

- 短期、长期、摘要 Memory Engine 或对话历史注入；
- Embedding、ChromaDB 案例索引或语义检索；
- 通用 evidence-aware semantic compression；
- Entity Resolution、客户画像或实体候选自动合并；
- `BE-R007`、`BE-R008` 及其他非试点分支的激活检索 policy；
- 节假日日历和“下一工作日”语义；
- 完整 RBAC、maker-checker、案例运营后台或通用 CRUD；
- LLM 自主 Tool 选择、案例多数投票或自动修改业务规则；
- 未经可信评测的准确率提升声明。
