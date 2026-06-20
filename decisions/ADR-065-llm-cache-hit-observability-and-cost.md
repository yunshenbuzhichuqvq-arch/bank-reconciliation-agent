# ADR-065: 命中可观测与成本记账

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/cache.py(metrics_snapshot / llm_cache_hit 事件 / LLMResult.cached), src/bank_reconciliation_agent/services/metrics.py(get_llm_cache_metrics), src/bank_reconciliation_agent/services/reconciliation.py(consumed/saved 拆分), src/bank_reconciliation_agent/services/workflow.py(_llm_usage 携带 cached), decisions/ADR-047(metrics 数据源分层)/ADR-054(per-task 聚合)/ADR-008(structlog + prompt 版本)

## Context
`core/llm/cost.py` 的 `compute_cost(prompt_tokens, completion_tokens)` 按 token 计费;缓存命中**没有新 token 消耗**。指标盘(ADR-047 数据源分层 / ADR-054 per-task 聚合)要能体现缓存省了多少。但现有 `LLMResult` 无 hit/miss 信号,直接复用缓存里的 token 数会把已省的成本**重复计入**。

## Options Considered
- **hit 信号怎么带**:
  - `LLMResult` 增 `cached: bool = False` 字段。Pros:显式、调用点可分辨;Cons:schema 变更,触及所有读 token 的调用点。
  - 命中时把 token 清零。Pros:成本天然算 0;Cons:丢失"原本要花多少"的省本信号,且掩盖真实 prompt 规模。
  - provider 外挂旁路信号(如返回值外的线程局部)。Pros:不动 schema;Cons:隐式、易漏、并发不安全。
- **成本口径**:命中计 0 新成本(真实)vs 命中仍按原 token 计(会与"省本"重复)。

## Decision
- `LLMResult` 增 `cached: bool = False`;命中返回**缓存里的原始 token 数**但置 `cached=True`。
- **成本记账**:`cached=True` 时本次**计 0 新成本**;省下的成本 = 用缓存原始 token 反算,作为**单独**的 saved-cost 指标,不混入实付成本。
- structlog 增 `llm_cache_hit` 事件;命中率 / 省本接入指标盘**数据源层**(扩展 ADR-047,聚合方式对齐 ADR-054)。

> 实现注记(收尾 review):provider 层不可靠获得 `agent_name` / `prompt_version`,命中事件仅记可得的 `model` 与短 cache key(诚实优先,不编造字段);命中率/省本经 `CachingLLMProvider` 进程内计数器暴露,`source` 标注 `runtime_memory`、无数据返回零值,不伪装持久化 SQL 指标。per-task consumed token 拆分(排除缓存命中)在 `reconciliation.py` 落地,保证默认关时口径与改前完全一致。

## Consequences
- 正面:实付成本不被缓存污染;省本可量化、命中可追踪,正好作为作品化的量化指标卖点。
- 负面:`LLMResult` schema 变更需同步所有读 token 的调用点(audit / extraction / report 及 metrics 聚合识别 `cached`),改动面比纯加缓存大。进程内计数器服务重启归零(已标注口径,不伪装持久化)。
