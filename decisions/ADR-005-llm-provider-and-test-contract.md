# ADR-005: LLMProvider 抽象与测试契约

- Status: Accepted (2026-06-08)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: system-prd.md §3.3 / §9.6, AGENTS.md 红线 1/2, decisions/ADR-002.md

## Context

MVP-2a 要把三个 Agent 从确定性 if-else 升级为真实 DeepSeek V4 Pro 调用——这是项目首个付费、非确定、需联网的外部依赖。当前 `src` 无任何 LLM 代码,且整套测试范式建立在离线 + 确定之上(pytest+sqlite、hash 向量、`audit_agent.py` 纯 if-else)。真实 LLM 与"CI 离线确定"直接冲突,必须先定下接入方式与测试契约。

约束:AGENTS 红线 1(金额绝不交给 LLM,一律 `Decimal`)、红线 2(RAG 无命中不臆造 evidence);PRD §3.3(经 OpenAI 兼容接口调 DeepSeek,`openai` SDK + `base_url`);PRD §9.6(DeepSeek 不可用 → 熔断 → 降级为确定性规则 → 全标 `PENDING_HUMAN`)。

## Options

1. **抽象 `LLMProvider` 接口 + 确定性 Fake 作 CI 默认,真实 DeepSeek 藏 flag 后 + 一条 opt-in live-smoke** — CI 保持离线/确定/零 token,真实链路仍可手动验证,Provider 边界为 2b(缓存/限流/记忆注入)留缝;代价是 Fake 与真实输出会漂移、多一层抽象。
2. **CI 直连真实 DeepSeek** — 测的就是真链路,但烧 token、非确定、需 key 常驻 CI、断网即红,与现有离线确定性范式正面冲突。
3. **暂不接真实,只留接口 + Fake** — 最省,但不兑现 MVP-2a "真实 LLM" 目标。

## Decision

采用 **Option 1**。
- 定义 `LLMProvider` 协议(同步即可,2a 串行):`complete(messages, *, temperature, response_format) -> LLMResult`;`LLMResult` 含 `text / prompt_tokens / completion_tokens / model`。
- 两实现:`FakeLLMProvider`(测试默认,按 prompt 关键字返回固定合法 JSON,确定性)、`DeepSeekProvider`(`openai` SDK,`base_url=https://api.deepseek.com/v1`,key 读 `settings`/`.env`)。
- 选择由 config 开关 `settings.llm_provider`(`fake`|`deepseek`),默认 `fake`;真实链路一条 `@pytest.mark.live` opt-in smoke,无 key 自动 skip。
- 熔断:`DeepSeekProvider` 调用失败(超时 / 5xx / 无 key)→ 抛 `LLMUnavailable` → 编排层捕获 → 降级为现有确定性 if-else(保留 MVP-1 `AuditAgent` 逻辑作 fallback)→ 该批全标 `PENDING_HUMAN`,structlog 记 WARN。
- token/cost 计量:每次调用累加 `t_reconciliation_task.total_llm_tokens` 与 `total_llm_cost`(`Decimal`);`t_agent_execution_log.llm_tokens` 记单次。成本按 DeepSeek 价目表常量换算(配置化)。
- 新增依赖:`openai>=1.0.0`。

## Consequences

- 正面:CI 维持绿色离线;真实链路可控接入;Provider 抽象为 2b 留边界。
- 负向:Fake 与真实输出会漂移 → spec 须约定 Fake 契约(返回合法 JSON、覆盖五类分支),2a 收尾跑一次 live-smoke 校准;多一层接口;成本常量需手维护,DeepSeek 调价要同步更新。
- 旧的确定性 `AuditAgent` 逻辑不删,转为熔断降级路径(与 surgical-changes 一致)。
