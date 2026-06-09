# ADR-011: Query Rewrite 的 LLM 集成与降级

- Status: Accepted (2026-06-08)
- Deciders: 用户(确认), Claude Code(提案)
- Related: system-prd.md §11.2, decisions/ADR-005(LLMProvider 抽象), decisions/ADR-008(prompt 版本治理), prompts/query_rewrite_v1.md, rag/query_rewrite.py

## Context

Query Rewrite 用 LLM 把自然语言查询改写为规则检索关键词(PRD §11.2 已给 prompt 草案)。项目已有 LLMProvider 抽象(ADR-005:`get_llm_provider()` / `FakeLLMProvider` 确定性 / `LLMUnavailable`)+ prompt registry(ADR-008:`load_prompt(name) → (text, version)`,按 `prompts/{name}_v{N}.md` 取最高版本)。

## Options

- **A. 组件内直接调 `openai` SDK** — Cons: 绕开 Provider 抽象、Fake 模式不可测、违 ADR-005。
- **B. 经 `get_llm_provider()` + `load_prompt("query_rewrite")`** — Pros: 复用既有抽象、Fake 下确定性、prompt 纳入版本治理。Cons: 依赖 prompt 文件存在。
- **C. 纯规则式改写,不用 LLM** — Pros: 零 LLM 成本。Cons: 不满足 PRD「Query Rewrite(DeepSeek 调用)」,改写质量差。

## Decision

采用 **B**。新增 `prompts/query_rewrite_v1.md`(基于 PRD §11.2)。`QueryRewriter` 经 `get_llm_provider().complete()` 调用。降级链:`enable_rewrite=False` → 用原 query;`LLMUnavailable` / 解析失败 → 捕获并回退原 query(不阻断检索)。`FakeLLMProvider` 增加 `query_rewrite` 分支,返回确定性结果(原 query + 固定关键词扩展),保证离线测试稳定。

## Consequences

- 需小幅加厚 2a-1 资产 `provider.py`(`FakeLLMProvider._payload_for` 增 rewrite 分支)。
- `rewritten_query` 落入检索日志(ADR-013);未改写时 `rewritten_query = 原 query`。
- 改写失败静默降级,不影响主链路可用性,但须 structlog 记录降级事件(对齐 ADR-008 可观测)。
