# ADR-17.1: Real Evidence Benchmark is a measurement stage, not a feature or optimization stage

**Slug**: `real-evidence-benchmark-scope`
**Status**: accepted
**Date**: 2026-07-07

## Context

上一阶段已经把关键缺口说清楚：hash RAG baseline 低于 PRD 目标，real embedding 没有纳入完整矩阵，真实 DeepSeek Agent Eval 没有可引用证据，线上采纳率、生产延迟和成本仍未测量。

本阶段目标是补齐“简历可引用的实测数据”，不是继续做产品功能，也不是立即优化指标。需要产出能支撑简历 bullet 和面试追问的证据，包括：

- RAG real embedding 对比：`hash / bge_small / bge_m3` × `dense / hybrid / hybrid_rerank`。
- DeepSeek Agent Eval：真实 provider 下的决策质量和金融安全红线。
- 性能 / 成本 benchmark：平均耗时、P95、token、估算成本。

## Options Considered

- Option A: 在本 stage 同时做测量、优化和默认配置切换。Pros: 数字可能更好看，短期成就感更强。Cons: 会混淆“真实测得的问题”和“调参后的结果”；也可能违反 ADR-RQT.1 / ADR-RQT.2 的默认 CI 与生产配置边界。
- Option B: 只跑零散命令，把输出手工摘到简历。Pros: 最快。Cons: 不可复查，不适合 PR review；容易把 fake/hash、real embedding、real LLM 和环境缺口混在一起。
- Option C: 建立 Real Evidence Benchmark 汇总层，只做测量、证据汇总和简历口径，不做功能扩展或优化（采纳）。Pros: 证据可追溯、可复跑、能清楚区分 measured pass / measured gap / environment gap。Cons: 本 stage 可能不会提升指标，只会更诚实地暴露缺口。

## Decision

采用 Option C。

本 stage 只产出 Real Evidence Benchmark：

- 复用现有 `scripts/eval_rag.py`、`scripts/eval_agent.py`、`scripts/eval_quality_triage.py` 和 `scripts/bench_agent_latency.py` 的评测边界。
- 可以补充报告汇总脚本或 benchmark 输出格式，但不修改业务 API、前端页面、数据库 schema 或生产 runtime 默认行为。
- 所有结论必须指向具体 JSON / Markdown report。
- 简历 bullet 只允许引用真实报告中存在的数字；没有运行成功的部分必须写成 environment gap，而不是“通过”。

## Consequences

- 正向：本阶段完成后，简历可以引用“在 120 条 RAG 评测集上量化 Hit@1 / Recall@5 / MRR / NDCG@5，并区分 hash 与 real embedding 证据”这类可复查表述。
- 正向：DeepSeek 真实评测、性能、成本与安全红线会有统一口径，不再散落在多个脚本输出中。
- 负向：如果真实模型、API key 或本地模型缓存不可用，本 stage 可能只能产出环境缺口，而不是漂亮数字。
- 负向：本 stage 不修复观测到的 RAG miss 或 Agent miss；后续优化必须另开 stage 或修订 ADR。
