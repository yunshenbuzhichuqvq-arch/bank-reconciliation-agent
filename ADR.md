# Stage 28 — Architectural Decisions

## ADR-28.1: 固定只读 Tool 采用确定性执行边界

**Slug**: `deterministic-readonly-tool-boundary`
**Status**: accepted
**Date**: 2026-07-12

### Context

当前工作流分别直接调用 RAG retriever、已确认历史案例查询和上传阶段计算得到的 T+1
候选，三种能力没有统一的 schema、调用上下文、权限校验、错误语义和观测边界。Stage 29
计划把 Tool、RAG、Agent、Guard 和 Fallback 投影为统一 `TraceSpan`，因此 Stage 28 必须先冻结
Tool 的名称、信任边界和稳定执行契约。

本项目是财务对账 Agent。工具选择必须继续由确定性 `exception_branch` 和 fallback 状态驱动，
不能因为引入统一执行器而扩大 LLM 的权限或增加有副作用能力。

### Options Considered

- **Option A：固定 registry + 确定性 `ToolExecutor`（采纳）**
  - Pros：用最小边界统一 schema、权限、超时、错误和观测；保留现有工作流控制权；三个真实能力可以被一致测试，并为 Stage 29 提供稳定输入。
  - Cons：工作流需要把当前直接调用迁移到统一信封；静态 registry 不支持运行时扩展，增加工具时需要显式修改代码和测试。
- **Option B：使用 LLM function calling 或自主 Tool 选择**
  - Pros：模型可以根据上下文灵活选择和组合工具；更接近通用 Agent 工具平台。
  - Cons：扩大不可预测分支和权限面；难以证明财务场景的 fail-closed；需要额外治理 prompt、工具选择、循环上限和副作用，不符合本 Stage 的最小范围。
- **Option C：保留三个直接调用，只补充局部日志和异常处理**
  - Pros：代码改动最少；不需要新的统一入口。
  - Cons：schema、权限和错误语义继续分散；Stage 29 仍需从不同调用形态反推统一 span，无法形成稳定 Tool contract。

### Decision

采用 **Option A**。

- Tool 固定为 `search_rules`、`load_confirmed_cases`、`lookup_t1_context`，不得在 Stage 28 增加写工具、动态插件或远程工具市场。
- 使用轻量静态 registry 和统一 `ToolExecutor.execute(name, args, context)` 语义；registry 显式绑定工具名、输入/输出 schema、执行适配器、超时策略和允许场景。
- Tool 只能由确定性工作流选择。LLM 可以消费 Tool 结果，但不得选择、组合或自主调用 Tool。
- `Tool Context` 由已认证请求或可信 ARQ job payload 建立，至少承载 `user_id`、`task_id`、`flow_id`、`scenario_type` 和 `exception_branch`。Tool 参数不得携带或覆盖身份与资源归属字段。
- 所有 Tool 调用前先验证任务归属；任务不存在与不属于当前用户使用相同拒绝语义，避免泄露资源是否存在。流水查询必须按 `user_id + task_id + flow_id` 限定。
- registry 使用场景 allowlist：`search_rules` 只允许已支持的对账场景；`load_confirmed_cases` 只允许低置信度 L2 fallback；`lookup_t1_context` 只允许 `BANK_CLEARING + BC-R003`。
- Tool 不新增独立 HTTP API，也不改变现有认证 scheme、业务路由或底层业务算法。

### Consequences

- 正面：Tool 的身份、权限、输入输出和调用控制权变成显式契约；未知名称、非法参数和越权上下文可以在进入底层能力前 fail closed。
- 正面：Stage 29 可以依赖固定工具名和稳定观测字段，不需要再次改变 Tool API。
- 负面：静态 registry 有意放弃动态扩展能力；未来新增 Tool 必须修改 registry、schema、场景策略和测试。
- 负面：所有内部调用都需要构造可信 `Tool Context` 并验证任务归属，会增加少量查询与集成代码。
- 约束：本决策不建设 MCP Server、通用 Agent SDK、工具市场、L2 写库工具、补偿事务或 LLM 自主执行机制。

## ADR-28.2: Tool 采用三态结果并对关键证据缺失 fail closed

**Slug**: `typed-tool-outcome-and-fail-closed`
**Status**: superseded
**Date**: 2026-07-12

> Superseded by ADR-28.5。三态结果与 fail-closed 语义继续有效；T+1 持久化字段边界由
> ADR-28.5 补充并取代本条中“无需 schema 变更即可复用匹配算法”的隐含前提。

### Context

单一 `success: bool` 无法区分“调用正常完成但没有业务结果”和“依赖、权限或执行失败”。当前
RAG 异常会被压成空检索，历史案例查询直接返回列表，T+1 candidate 则在上传分类阶段从 DataFrame
预先计算；这些差异会让工作流和未来 Trace 错误解释失败率与 fallback 原因。

其中 `lookup_t1_context` 目前不是可独立调用的只读能力：`ExceptionRouter` 在持久化之前计算
`t1_candidate`，后续工作流只消费缓存结果。仅包装该字段无法证明任务归属、跨用户隔离、查询超时或
失败语义。

### Options Considered

- **Option A：`SUCCEEDED / EMPTY / FAILED` 三态 + 真实租户限定 T+1 查询（采纳）**
  - Pros：正常无结果与故障可被稳定区分；三个工具可以使用同一结果信封；T+1 查询能真实验证租户隔离，并复用现有确定性匹配规则。
  - Cons：BC-R003 路径增加一次持久化流水读取；工作流必须为每个 Tool 明确 `EMPTY` 与 `FAILED` 的不同收口行为。
- **Option B：只保留 `success: bool`，T+1 Tool 包装预计算 candidate**
  - Pros：实现最少；几乎不改变现有数据流。
  - Cons：空结果与失败继续混淆；T+1 Tool 只是内存字段读取，无法证明权限、超时或真实查询契约。
- **Option C：所有空结果和错误都通过异常表达**
  - Pros：调用方只处理成功结果或异常；控制流直观。
  - Cons：正常业务无命中被错误计为系统故障；容易触发无意义重试，并破坏 RAG 无证据转人工的业务语义。

### Decision

采用 **Option A**。

- `Tool Outcome` 的权威状态只允许 `SUCCEEDED`、`EMPTY`、`FAILED`。`success` 是由状态派生的兼容字段，不得独立赋值：`SUCCEEDED/EMPTY` 为 `true`，`FAILED` 为 `false`。
- `EMPTY` 表示 Tool 正常执行但没有业务结果，不设置 `error_type`、不触发重试。`FAILED` 必须携带稳定 `error_type` 和 `fallback_reason`。
- 三个 Tool 分别定义 Pydantic 输入和输出 schema；底层返回必须先通过输出 schema 校验，再进入统一结果信封。
- `lookup_t1_context` 对已持久化流水执行真实只读查询，租户范围来自 `Tool Context`。上传分类和 Tool 查询复用同一个确定性 T+1 匹配规则，不复制或改写业务算法；预计算 candidate 不再作为 Tool 的事实来源。
- `search_rules=EMPTY` 时直接进入 `PENDING_HUMAN`，不得在无 evidence 时继续调用 AuditAgent；`search_rules=FAILED` 同样转人工。
- `load_confirmed_cases=EMPTY` 表示低置信度 L1 没有 L2 案例支撑，直接进入 `PENDING_HUMAN`；`FAILED` 同样转人工，不继续消耗下游 Tool 或 LLM。
- `lookup_t1_context=EMPTY` 是“真实查询后没有 T+1 匹配”的业务结果，继续既有无 T+1 candidate 路径；`FAILED` 则直接进入 `PENDING_HUMAN`。
- 除 ADR-28.3 声明需要上抛 ARQ 的基础设施异常外，`FAILED` 都在当前 item 内安全收口，且停止该 item 的后续 Tool 与 LLM 调用。
- 完整 Tool `result` 只在当前工作流内存中传递，不进入通用结构化日志或未来 Trace；持久观测只保存 ADR-28.4 定义的安全投影。

### Consequences

- 正面：业务无结果、权限拒绝和依赖故障具有不同且可查询的语义；RAG 不可用不再被统计为正常无命中。
- 正面：缺失关键证据时不再继续生成 LLM 结论，保持 RAG 无 evidence 转人工和财务决策 fail-closed 红线。
- 负面：RAG 无命中和 L2 无历史案例路径会减少当前存在但最终仍转人工的 LLM 调用，内部调用次数与旧行为不同，相关测试和指标需要同步。
- 负面：真实 T+1 查询增加一次数据库读取，并要求分类路径和查询路径共享同一匹配规则；共享边界若设计不当可能产生耦合。
- 约束：本决策不改变三个底层能力的业务算法，不新增自动处理路径，也不把 `EMPTY` 当作可重试错误。

## ADR-28.3: Tool 使用有界超时与局部重试并保留 ARQ 和 RAG breaker 边界

**Slug**: `bounded-tool-timeout-retry-and-breaker`
**Status**: accepted
**Date**: 2026-07-12

### Context

三个底层能力当前都是同步调用。仅在函数返回后统计耗时不能形成可验证的 timeout contract；只依赖
各依赖自行抛出超时，又无法为 SQL、Chroma 和本地适配器提供统一故障注入语义。

Stage 25 与 `decisions/ADR-25.1-attempt-aware-arq-retry-contract.md` 已冻结 job retry 边界：
`RedisConnectionError` 和 SQLAlchemy `OperationalError` 必须到达 worker，由 ARQ 执行最多三个 job
attempts。Stage 28 不得把这些错误吞成普通 Tool failure。

同时，`decisions/ADR-029-circuit-breaker-rag-only.md` 已决定 breaker 只保护 RAG，但其 OPEN 时返回空
检索的旧表达会把依赖故障与 ADR-28.2 的 `EMPTY` 混为一谈。

### Options Considered

- **Option A：有界共享线程池 + Tool 内一次重试 + 保留 ARQ/RAG 专属边界（采纳）**
  - Pros：不引入新依赖即可为同步 Tool 提供统一且可测试的 timeout；只读调用允许安全的有限重试；保留既有 job recovery 和 RAG breaker 能力。
  - Cons：Python 线程无法被安全强杀，timeout 后底层调用可能短暂继续占用线程；Tool 与 ARQ 形成两层 attempt 计数，需要清晰观测。
- **Option B：只依赖底层依赖的原生 timeout**
  - Pros：不增加线程池；依赖最了解自己的取消语义。
  - Cons：三个 Tool 无法形成统一 contract；部分本地同步调用没有可注入 timeout，测试只能模拟异常而不能验证执行边界。
- **Option C：迁移为异步调用、独立进程或外部任务系统**
  - Pros：可以获得更强的取消和资源隔离能力。
  - Cons：需要改造同步工作流、依赖和部署拓扑，明显超出 Stage 28；为三个只读 Tool 引入过度复杂度。

### Decision

采用 **Option A**。

- Tool 底层调用在共享、固定容量的线程池中执行；registry 为每个 Tool 声明固定 timeout，调用方不得自行扩大预算。
- 达到 timeout 后执行 best-effort `cancel()` 并记录 `TIMEOUT`。因为运行中的 Python 线程不能被强制终止，所有 Stage 28 Tool 必须保持只读，晚完成不得产生业务写副作用。
- `TIMEOUT` 和明确声明的 `TRANSIENT_READ_ERROR` 最多原地重试一次，因此单个逻辑 Tool call 最多两个 1-based physical attempts。
- `UNKNOWN_TOOL`、`VALIDATION_ERROR`、`PERMISSION_DENIED`、`INTERNAL_ERROR` 和 `CIRCUIT_OPEN` 不重试；`EMPTY` 不是错误，也不重试。
- Tool timeout、线程池容量、退避与重试上限引用单一策略来源，禁止在 adapter 和 executor 中维护可漂移的重复数值。
- `RedisConnectionError` 和 SQLAlchemy `OperationalError` 在 Tool 层最终仍原样上抛，不转换为终态 `ToolCallResult`，由 ADR-25.1 的 worker 边界决定 ARQ job retry 或 exhaustion。Tool attempt 与 ARQ job attempt 分别记录，不合并成一个计数。
- RAG circuit breaker 继续只保护 `search_rules`，不扩展到另两个 Tool。其状态协调下沉到 `search_rules` Tool 边界，每个物理检索失败按现有状态机计入 breaker。
- breaker OPEN 时返回 `FAILED/CIRCUIT_OPEN` 且不可重试，工作流仍转人工。本条只修订 ADR-029 中“OPEN 表达为空检索”的结果语义，不改变 RAG-only breaker 的选择、阈值或状态机。

### Consequences

- 正面：三个同步 Tool 获得一致、可故障注入的 timeout/retry contract；瞬时只读故障可以在不重放整个 job 的情况下恢复。
- 正面：Redis/DB job recovery 与 RAG breaker 的既有职责继续保留，依赖不可用和正常无命中可以被准确区分。
- 负面：timeout 无法终止已经运行的 Python 线程；连续慢调用可能暂时耗尽有界线程池，必须通过容量限制、测试和观测承认该风险。
- 负面：同一异步任务可能经历最多两个 Tool attempts 和最多三个 ARQ job attempts；排查时必须同时展示两层计数，不能将其宣传为单一重试机制。
- 约束：本决策不引入新的 timeout 库、异步框架迁移、子进程执行器、Celery 或通用 resilience 平台。

## ADR-28.4: Tool attempt 使用安全投影并生成离线证据报告

**Slug**: `tool-attempt-observability-and-evidence`
**Status**: accepted
**Date**: 2026-07-12

### Context

Stage 28 需要证明 Tool success、validation failure、permission denial、timeout、retry recovery 和
P50/P95 duration，并为 Stage 29 提供稳定的 attempt 输入。如果结果只保留最终 `attempt=2`，就无法解释
第一次失败的类型；如果记录完整 args、query、结果或异常，又会复制金额、历史审计意见、流水信息和
连接细节。

Stage 29 已负责统一 TraceSpan、持久化和回放。Stage 28 不应提前新增 trace 表或前端 timeline，但也
不能把证据只写在测试终端或 PR 文案中。

### Options Considered

- **Option A：顶层摘要 + bounded attempt records + 安全投影 + 双格式离线报告（采纳）**
  - Pros：可以解释 retry recovery；不保存敏感输入输出；JSON 提供机器可审查事实源，Markdown 便于人工 review；Stage 29 可直接投影稳定字段。
  - Cons：结果 schema 比只保留最终状态更大；离线 P50/P95 受机器环境影响，不能直接作为生产性能结论。
- **Option B：只保留最终 Tool 状态并依赖 pytest 输出**
  - Pros：schema 和实现最简单；无需报告脚本。
  - Cons：无法回答首次失败原因；Stage 收尾后缺少可复查统计；P50/P95 和 failure distribution 容易被手工文案替代。
- **Option C：Stage 28 新增完整 Tool attempt 数据表和查询 API**
  - Pros：跨进程持久化和聚合完整；可以直接建设回放页面。
  - Cons：与 Stage 29 的 Trace/Replay 重复，新增 schema、保留策略和 API，扩大当前 Stage 范围。

### Decision

采用 **Option A**。

- `ToolCallResult` 保留最终顶层摘要和最多两条脱敏 attempt records。顶层至少包含 `tool_name`、`status`、派生 `success`、`result`、`error_type`、`retryable`、总 `attempt`、`retry_recovered` 和逻辑调用总 `duration_ms`。
- 每条 attempt record 只包含 1-based `attempt`、`status`、`duration_ms`、稳定 `error_type` 和 `retryable`。不得包含 args、完整 query、完整结果、异常对象、traceback、连接信息或认证数据。
- 最终重试恢复时，顶层状态为 `SUCCEEDED` 或 `EMPTY`、`error_type=None`、`retry_recovered=true`；首条 attempt record 保留最初稳定错误类型。
- 完整 `result` 只供当前工作流消费。结构化日志、现有 Agent execution payload 和未来 Trace 只保存安全投影：状态、耗时、attempt、recovery、error/fallback、result count 和 evidence IDs。
- evidence IDs 仅允许：`search_rules` 的 `chunk_id`、`load_confirmed_cases` 的 `flow_id`、`lookup_t1_context` 的匹配 `flow_id`。不得记录完整 RAG query、规则正文、历史审计意见、原始流水或 Tool 原始参数。
- Stage 28 不新增 Tool/Trace 数据表。Stage 29 复用这些稳定字段形成 TraceSpan，需要详情时按当前用户权限和 evidence ID 查询，不把敏感正文复制进 trace。
- 新增 `scripts/eval_tools.py`，从同一内存结果生成 `reports/tool_executor_evidence.json` 和 `reports/tool_executor_evidence.md`。JSON 是机器可审查事实源，Markdown 不得独立计算或手填指标。
- 证据脚本使用固定 SQLite 数据、hash embedding、本地规则集和确定性故障注入，报告各 Tool 的 outcome/error/retry 分布及 P50/P95 duration。正常与空结果调用真实本地 adapter，permission、timeout 和 recovery 使用可复现故障注入。
- P50/P95 只描述本地离线运行，不设置性能 pass gate，不表述为生产 SLA。CI 运行确定性 schema/计数测试；报告生成进入 Stage DoD，但机器差异导致的延迟变化不阻断 CI。

### Consequences

- 正面：Stage 28 能以可复查报告证明调用、失败和恢复行为；Stage 29 不需要从自由文本日志反推 Tool attempts。
- 正面：敏感业务内容不进入通用日志或未来 trace，降低跨用户泄漏和长期复制风险。
- 负面：安全投影不能单独重建完整 Tool 输入输出；排查业务详情时仍需在授权上下文中按 evidence ID 查询原始来源。
- 负面：离线 latency 受硬件、缓存冷热和本地依赖状态影响，只能作为观察基线；报告必须持续携带环境与 claim boundary。
- 约束：本决策不新增 trace 表、回放 API、前端 timeline、外部观测平台、告警系统或生产性能承诺。

## ADR-28.5: T+1 持久化查询补齐银行流水关联字段

**Slug**: `persist-bank-t1-reference-fields`
**Status**: accepted
**Date**: 2026-07-12

### Context

ADR-28.2 要求 `lookup_t1_context` 从已持久化流水执行真实租户限定查询，并与上传分类复用同一个
确定性 T+1 匹配规则。现有规则同时比较金额、次日 `accounting_date` 和
`reference_no / merchant_order_no / voucher_no` 的交集。

上传阶段的 bank DataFrame 已包含这三个关联字段，但 `t_bank_transaction` 的 SQLAlchemy `Table`、
`db/schema.sql` 和写入映射没有保存它们；clear 表则已经保存。因此，持久化后无法在不丢失判别条件
的前提下复现上传阶段 candidate。仅依赖 bank 表现有列会改变匹配算法，并可能把相同金额、相同日期
但不同业务引用的流水误判为 T+1 candidate。

### Options Considered

- **Option A：为 bank 表补齐三个 nullable 关联字段并同步双 schema（采纳）**
  - Pros：保持现有 T+1 算法和上传/查询结果一致；字段已经存在于标准化输入，不增加新的业务数据源；改动局限于同一表定义、DDL、写入映射和测试。
  - Cons：Stage 28 必须承担一次窄范围 schema 扩展；已有数据库不会被 SQLAlchemy `create_all()` 自动 ALTER，需要使用更新后的 DDL 重建或由操作者显式迁移。
- **Option B：持久化查询只使用 bank 表已有的金额、日期等字段**
  - Pros：无需修改 schema；实现路径较短。
  - Cons：删除 reference 交集这一既有判别条件，改变业务算法并扩大误匹配风险；违反 Stage 28 的零算法漂移边界。
- **Option C：继续把上传阶段预计算 candidate 作为 Tool 事实来源**
  - Pros：无需 schema 变更，也无需再次查询候选流水。
  - Cons：不能证明持久化查询、租户隔离、timeout 或查询失败语义；与真实只读 Tool 的 accepted 边界冲突。

### Decision

采用 **Option A**，并取代 ADR-28.2 中关于 T+1 持久化实现前提的部分；ADR-28.2 的三态结果、
EMPTY/FAILED 区分和工作流 fail-closed 语义保持不变。

- 在 `t_bank_transaction` 增加 nullable `VARCHAR(64)` 字段：`reference_no`、
  `merchant_order_no`、`voucher_no`。
- 同步修改 `src/bank_reconciliation_agent/services/transactions.py` 的 SQLAlchemy `Table` 与 bank
  insert 映射，以及 `src/bank_reconciliation_agent/db/schema.sql` 的 MySQL DDL。两份 schema 必须
  保持字段名、类型和 nullable 语义一致。
- 不为三个字段新增索引。`lookup_t1_context` 先按 `user_id + task_id` 限定任务内 bank rows，再调用
  共享确定性函数；Stage 28 不引入新的全表查询或生产查询优化。
- T+1 匹配规则保持不变：金额相等、bank `accounting_date` 等于 clear `trade_date + 1 day`，且三个
  reference 字段至少一个非空值相交。
- 测试必须证明三个字段能从 bank DataFrame 写入并读回、SQLAlchemy 与 `schema.sql` 对齐、上传分类
  与持久化 Tool 查询对同一 fixture 返回相同 candidate。
- 本 Stage 不引入 Alembic 或自建 migration framework。既有数据库的升级/重建要求必须在 Report
  Back 和 PR 风险中如实说明；不得声称 `create_all()` 会修改已有表。

### Consequences

- 正面：`lookup_t1_context` 可以从真实持久化数据复现上传阶段 candidate，同时保留租户隔离和原有
  防误匹配条件。
- 正面：bank/clear 两侧关联字段语义对齐，Stage 28 不需要弱化算法或信任内存 candidate。
- 负面：`t_bank_transaction` 增加三个 nullable 列，schema 改动范围大于原 Stage 28 计划。
- 负面：已有 MySQL/Compose 数据卷不会被 `create_all()` 自动升级；未显式迁移或重建时，新代码可能
  因缺列失败。
- 约束：除这三个 bank 关联字段及其写入/测试外，不修改其他表、索引、API schema 或 T+1 算法。
