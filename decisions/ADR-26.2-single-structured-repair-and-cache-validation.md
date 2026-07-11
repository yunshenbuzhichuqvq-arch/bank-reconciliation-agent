# ADR-26.2: 结构化输出仅允许一次 Agent 级修复并延迟缓存验收

**Slug**: `single-structured-repair-and-cache-validation`
**Status**: accepted
**Date**: 2026-07-11

## Context

ExtractionAgent 与 TraceAgent 当前在 JSON/Pydantic 校验失败后重复相同请求；Audit 工作流还存在最多
3 次 SchemaHook 重试。这些路径没有向模型提供针对性的 correction 信息，也未统一区分
`invalid_json` 与 `schema_invalid`。同时，现有缓存包装器在 Agent 完成结构校验前保存 provider 原始结果，
导致结构无效输出可能被缓存并在后续调用中重复命中。

结构修复与业务安全判断属于不同问题：JSON/Pydantic 错误可以通过一次短 correction prompt 尝试修复；
金额、evidence、高风险重复记账等 hard constraint 必须由确定性 Safety Policy Gate 处理，不能要求模型
“自我修复”后绕过红线。

## Options Considered

- **Option A：Agent 持有 schema，一次定向 correction；Cache 通过通用 validator 延迟写入（采纳）**
  - Pros：schema 所有权留在 Agent；修复提示可以包含具体校验原因；无效输出不会污染缓存；Safety
    Policy 仍是独立、确定性的后置门禁。
  - Cons：`LLMProvider.complete()` 需要增加可选 validator contract，所有包装器必须透明透传；Agent
    调用契约和缓存测试均需同步调整。
- **Option B：把所有 Agent schema 移入 Provider/Cache 层校验**
  - Pros：缓存天然只接收有效输出；调用方代码较少。
  - Cons：基础设施层依赖 Audit/Extraction/Trace 业务模型，模块边界倒置；每增加 Agent 都要修改
    Provider；Safety Policy 与结构校验容易耦合。
- **Option C：保留重复原请求，修复时使用不同 cache key**
  - Pros：改动最小；无需扩展 Provider contract。
  - Cons：模型没有收到校验反馈；首次无效值仍留在缓存；无法满足“无效输出不得缓存”的验收要求。

## Decision

采用 **Option A**。

- Agent 对首次返回执行 JSON 解析和自身 Pydantic schema 校验，并稳定区分 `invalid_json` 与
  `schema_invalid`。
- 首次结构校验失败后只允许追加 1 次短 correction prompt。prompt 包含必要的脱敏校验原因和待修复
  输出，不扩展业务任务、不请求模型修改金额或绕过硬约束。
- correction 是第二个逻辑生成步骤，也适用 ADR-26.1 的 transport 策略。因此首次生成最多 3 次物理
  调用，correction 最多 3 次物理调用，单个 Agent 操作的理论上限为 6 次真实调用。
- correction 仍失败时必须稳定收口到调用方既有的安全 fallback；无法产生确定性安全结果时转为
  `PENDING_HUMAN`。不得继续第三次结构生成。
- 现有 Audit SchemaHook 的三次盲重试、Extraction/Trace 的原请求重复方式统一收敛为上述“一次定向
  correction”契约。
- Provider contract 增加可选、通用的 response validator。schema 仍由 Agent 定义；Cache wrapper
  在 validator 通过后才能写值，Cache hit 也必须重新校验，失败时删除旧值并按 miss 处理。未启用缓存
  时，Agent 仍在自身边界执行相同校验。
- validator 只覆盖 JSON 与 Pydantic schema，不执行 Safety Policy。结构有效但违反 hard constraint
  的输出可以作为原始模型输出缓存，但每次消费时都必须重新经过确定性 Safety Policy Gate。
- hard constraint violation 不触发 transport retry 或 correction；Safety Policy 直接覆盖危险决策并
  fail closed，保留 raw decision 与介入原因供审计。

## Consequences

- 正向：所有 Agent 的结构修复上限一致，模型获得一次有针对性的修复机会，同时避免盲目重复调用。
- 正向：无效 JSON/schema 不再形成持久坏缓存；schema 演进后，旧缓存值也可在读取时被淘汰。
- 负向：单个 Agent 操作在“首次生成和 correction 都经历 transport 重试”的极端情况下可达到 6 次
  真实调用，尾延迟和成本高于当前路径。
- 负向：Provider 协议增加 validator 参数后，Fake、DeepSeek、Cache、RateLimit、Retry、Breaker 等
  实现都必须保持签名与透传一致，增加 contract 回归面。
- 约束：本决策不允许 LLM 修复 hard constraint，不新增通用 schema registry，也不改变确定性金额、
  evidence 和人工复核红线。
