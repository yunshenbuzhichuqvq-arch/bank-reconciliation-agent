# ADR-17.4: Performance and cost benchmark uses offline measured latency plus explicit cost assumptions

**Slug**: `performance-cost-offline-benchmark-evidence`
**Status**: accepted
**Date**: 2026-07-07

## Context

简历 bullet 需要的不只是准确率，还包括工程代价：平均耗时、P95、token 数、估算成本。现有 `scripts/bench_agent_latency.py` 主要为 ADR-032 服务，只测少量 ExtractionAgent 与 RAG 样本，且 fake provider 下不代表真实 LLM latency。

本 stage 需要把性能/成本变成可引用的 offline benchmark，但不能把它冒充为生产在线指标。

## Options Considered

- Option A: 只记录功能评测指标，不做性能/成本。Pros: scope 更小。Cons: 简历缺少“效果-成本”视角，不能回答真实 Agent 应用的延迟和费用问题。
- Option B: 直接宣称生产 P95 和线上成本。Pros: 表述更像生产项目。Cons: 当前没有真实线上流量、人工复核采纳数据或生产监控，属于过度声明。
- Option C: 建立 offline performance/cost benchmark，明确测量环境和成本假设（采纳）。Pros: 能量化工程代价，同时保持诚实边界。Cons: offline 数字不等同于生产 SLA，且真实 LLM 成本依赖模型价格和 token 统计口径。

## Decision

采用 Option C。

性能/成本 benchmark contract：

- 以离线批量评测为范围，不声明线上 SLA。
- 至少输出 `run_count`、`avg_latency_ms`、`p95_latency_ms`、`min_latency_ms`、`max_latency_ms`。
- 如果使用真实 DeepSeek，必须记录 `input_tokens`、`output_tokens`、`total_tokens` 和 `estimated_cost`；如果 provider 不返回 token usage，则报告必须标为 `token_usage_unavailable`。
- 成本估算必须在报告中写明模型、单价来源或手工配置假设；不能只给最终费用。
- fake provider 下的 latency 只能作为本地代码路径开销，不能写成真实 LLM 延迟。
- RAG embedding benchmark 要区分 index/build 成本和 query latency，避免把一次性建库成本混进单 query 延迟。

## Consequences

- 正向：简历可以用“离线 benchmark 记录平均耗时、P95、token 与估算成本”这种可追溯表述。
- 正向：能为后续 cache、限流、批处理或减少 Agent 调用提供依据。
- 负向：本阶段的性能数字受本机 CPU、模型缓存、网络波动和 API 返回 token 口径影响，不应作为生产 SLA。
- 负向：如果真实 provider 不返回 token usage，需要额外标注成本不可测或使用明确假设估算。
