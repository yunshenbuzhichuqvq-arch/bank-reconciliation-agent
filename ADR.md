# Stage 17 — Real Evidence Benchmark Architectural Decisions

## ADR-17.1: Real Evidence Benchmark is a measurement stage, not a feature or optimization stage

**Slug**: `real-evidence-benchmark-scope`
**Status**: accepted
**Date**: 2026-07-07

### Context

上一阶段已经把关键缺口说清楚：hash RAG baseline 低于 PRD 目标，real embedding 没有纳入完整矩阵，真实 DeepSeek Agent Eval 没有可引用证据，线上采纳率、生产延迟和成本仍未测量。

本阶段目标是补齐“简历可引用的实测数据”，不是继续做产品功能，也不是立即优化指标。需要产出能支撑简历 bullet 和面试追问的证据，包括：

- RAG real embedding 对比：`hash / bge_small / bge_m3` × `dense / hybrid / hybrid_rerank`。
- DeepSeek Agent Eval：真实 provider 下的决策质量和金融安全红线。
- 性能 / 成本 benchmark：平均耗时、P95、token、估算成本。

### Options Considered

- Option A: 在本 stage 同时做测量、优化和默认配置切换。Pros: 数字可能更好看，短期成就感更强。Cons: 会混淆“真实测得的问题”和“调参后的结果”；也可能违反 ADR-RQT.1 / ADR-RQT.2 的默认 CI 与生产配置边界。
- Option B: 只跑零散命令，把输出手工摘到简历。Pros: 最快。Cons: 不可复查，不适合 PR review；容易把 fake/hash、real embedding、real LLM 和环境缺口混在一起。
- Option C: 建立 Real Evidence Benchmark 汇总层，只做测量、证据汇总和简历口径，不做功能扩展或优化（采纳）。Pros: 证据可追溯、可复跑、能清楚区分 measured pass / measured gap / environment gap。Cons: 本 stage 可能不会提升指标，只会更诚实地暴露缺口。

### Decision

采用 Option C。

本 stage 只产出 Real Evidence Benchmark：

- 复用现有 `scripts/eval_rag.py`、`scripts/eval_agent.py`、`scripts/eval_quality_triage.py` 和 `scripts/bench_agent_latency.py` 的评测边界。
- 可以补充报告汇总脚本或 benchmark 输出格式，但不修改业务 API、前端页面、数据库 schema 或生产 runtime 默认行为。
- 所有结论必须指向具体 JSON / Markdown report。
- 简历 bullet 只允许引用真实报告中存在的数字；没有运行成功的部分必须写成 environment gap，而不是“通过”。

### Consequences

- 正向：本阶段完成后，简历可以引用“在 120 条 RAG 评测集上量化 Hit@1 / Recall@5 / MRR / NDCG@5，并区分 hash 与 real embedding 证据”这类可复查表述。
- 正向：DeepSeek 真实评测、性能、成本与安全红线会有统一口径，不再散落在多个脚本输出中。
- 负向：如果真实模型、API key 或本地模型缓存不可用，本 stage 可能只能产出环境缺口，而不是漂亮数字。
- 负向：本 stage 不修复观测到的 RAG miss 或 Agent miss；后续优化必须另开 stage 或修订 ADR。

## ADR-17.2: RAG evidence uses backend-by-mode matrix with trusted backend metadata

**Slug**: `rag-real-embedding-matrix-evidence`
**Status**: accepted
**Date**: 2026-07-07

### Context

现有 RAG 证据有两类：

- hash baseline 已测得 `hybrid_rerank` 约为 Recall@5=0.658、MRR=0.568、NDCG@5=0.553，低于 PRD 目标。
- 历史 real embedding 报告证明 `bge_small` / `bge_m3` 在 dense 模式下优于 hash，但还不能完整回答“real embedding × hybrid/rerank 的组合是否更好”。

ADR-RQT.2 已要求 RAG quality matrix 分离 CI hash baseline 和 opt-in real embeddings。本阶段需要把这份矩阵变成简历可引用证据，而不是只作为内部诊断。

### Options Considered

- Option A: 只引用 hash baseline。Pros: 默认环境稳定、可复跑。Cons: hash embedding 不是语义检索质量的代表，简历上只写 hash 指标会削弱 RAG 说服力。
- Option B: 只跑 best real backend 的单一模式。Pros: 输出简单。Cons: 无法说明 dense / hybrid / rerank 的真实贡献，也无法和 hash baseline 公平对比。
- Option C: 固定使用 backend-by-mode matrix，并保留 effective backend / status metadata（采纳）。Pros: 能同时比较 backend 与 retrieval mode；fallback 到 hash 或未运行会被显式暴露。Cons: 跑全矩阵可能慢，`bge_m3` 对本地资源要求更高。

### Decision

采用 Option C。

RAG benchmark contract：

- Eval set 固定为 `data/rag_eval_set.json`，case count 以报告 metadata 为准，当前目标是 120 cases。
- Backends: `hash`, `bge_small`, `bge_m3`。
- Modes: `dense`, `hybrid`, `hybrid_rerank`。
- Metrics: `hit_at_1`, `recall_at_5`, `mrr`, `ndcg_at_5`。
- Ranking-quality 测量保持 `min_score=0.0`，延续 ADR-RQT.2。
- 报告必须包含 `requested_backend`、`effective_backend`、`status`、`selected_mode` 和 `reason`。
- 不能为了提升指标修改 eval labels、删除 miss case 或改写 query 到适配当前输出。
- 不因 real embedding 指标更好而自动切换生产默认或默认 DoD。

### Consequences

- 正向：可以形成“hash baseline vs bge_small/bge_m3 real embedding”的清晰数据表，适合写进简历和 PR。
- 正向：如果 real embedding 不可用，报告仍能把缺口归类为 environment gap。
- 负向：完整矩阵可能运行时间长；`bge_m3` 可能受本地模型缓存、CPU 性能和内存影响。
- 负向：如果 `hybrid_rerank` 在某些 real backend 下不提升，报告必须如实记录，不能只展示最好看的行。

## ADR-17.3: DeepSeek Agent Eval is trusted only with real-provider metadata and safety redlines

**Slug**: `deepseek-agent-eval-trusted-safety-evidence`
**Status**: accepted
**Date**: 2026-07-07

### Context

当前 fake-provider Agent Eval 能证明 deterministic baseline 和安全门禁，但不能证明真实 DeepSeek 行为。用户本阶段需要的数据是“真实 LLM 下是否仍守住金融安全红线”，重点指标包括：

- `decision_accuracy`
- `risk_accuracy`
- `evidence_citation_rate`
- `unsafe_auto_fix_rate`
- `hard_constraint_violation_rate`

ADR-RQT.3 已规定真实 LLM Agent Eval 是 opt-in diagnostic evidence，不能变成默认 DoD。

### Options Considered

- Option A: 把 DeepSeek Eval 加入默认 DoD。Pros: 每次都覆盖真实模型。Cons: 依赖网络、API key、模型可用性和费用；不适合 CI，也会让本地开发不稳定。
- Option B: 继续只跑 fake provider，然后在简历中泛称 Agent Eval。Pros: 稳定、成本低。Cons: 不能支持“真实 DeepSeek 下”的结论，容易被面试追问击穿。
- Option C: 保留 fake baseline，同时增加 provider-specific DeepSeek report，并只信任带 `real_provider_call=true` 的结果（采纳）。Pros: 可证明真实调用；不污染 fake baseline；没有 API key 时能诚实记录 environment gap。Cons: 真实 LLM 输出有非确定性，case 数小的时候不能过度泛化。

### Decision

采用 Option C。

DeepSeek benchmark contract：

- 默认 fake-provider Agent Eval 继续作为离线 safety baseline。
- DeepSeek 运行必须显式使用 provider-specific 输出路径，例如 `reports/agent_eval_deepseek_flash.md` 和 `reports/agent_eval_deepseek_flash_metrics.json`。
- 报告必须包含 `provider_requested`、`provider_effective`、`model_requested`、`model_effective`、`real_provider_call`、`evaluated_at` 和 per-case result。
- 只有 `provider_effective=deepseek` 且 `real_provider_call=true` 的报告，才能被 Real Evidence Benchmark 计为真实 LLM 证据。
- `unsafe_auto_fix_rate > 0` 或 `hard_constraint_violation_rate > 0` 是 blocking finding，不能包装成“总体可接受”。
- 缺少 `DEEPSEEK_API_KEY`、网络不可用或 provider fallback，必须计为 environment gap。

### Consequences

- 正向：简历可写“使用真实 DeepSeek 对 Agent 安全红线做离线评测”，但前提是报告确实存在且 metadata 可信。
- 正向：fake baseline 与 real-provider evidence 不会混淆。
- 负向：如果 DeepSeek 输出波动，单次 run 只能作为诊断证据，不能代表生产长期稳定性。
- 负向：真实 API 调用会产生费用和网络依赖，需要在 Report Back 中明确是否运行、运行命令和结果。

## ADR-17.4: Performance and cost benchmark uses offline measured latency plus explicit cost assumptions

**Slug**: `performance-cost-offline-benchmark-evidence`
**Status**: accepted
**Date**: 2026-07-07

### Context

简历 bullet 需要的不只是准确率，还包括工程代价：平均耗时、P95、token 数、估算成本。现有 `scripts/bench_agent_latency.py` 主要为 ADR-032 服务，只测少量 ExtractionAgent 与 RAG 样本，且 fake provider 下不代表真实 LLM latency。

本 stage 需要把性能/成本变成可引用的 offline benchmark，但不能把它冒充为生产在线指标。

### Options Considered

- Option A: 只记录功能评测指标，不做性能/成本。Pros: scope 更小。Cons: 简历缺少“效果-成本”视角，不能回答真实 Agent 应用的延迟和费用问题。
- Option B: 直接宣称生产 P95 和线上成本。Pros: 表述更像生产项目。Cons: 当前没有真实线上流量、人工复核采纳数据或生产监控，属于过度声明。
- Option C: 建立 offline performance/cost benchmark，明确测量环境和成本假设（采纳）。Pros: 能量化工程代价，同时保持诚实边界。Cons: offline 数字不等同于生产 SLA，且真实 LLM 成本依赖模型价格和 token 统计口径。

### Decision

采用 Option C。

性能/成本 benchmark contract：

- 以离线批量评测为范围，不声明线上 SLA。
- 至少输出 `run_count`、`avg_latency_ms`、`p95_latency_ms`、`min_latency_ms`、`max_latency_ms`。
- 如果使用真实 DeepSeek，必须记录 `input_tokens`、`output_tokens`、`total_tokens` 和 `estimated_cost`；如果 provider 不返回 token usage，则报告必须标为 `token_usage_unavailable`。
- 成本估算必须在报告中写明模型、单价来源或手工配置假设；不能只给最终费用。
- fake provider 下的 latency 只能作为本地代码路径开销，不能写成真实 LLM 延迟。
- RAG embedding benchmark 要区分 index/build 成本和 query latency，避免把一次性建库成本混进单 query 延迟。

### Consequences

- 正向：简历可以用“离线 benchmark 记录平均耗时、P95、token 与估算成本”这种可追溯表述。
- 正向：能为后续 cache、限流、批处理或减少 Agent 调用提供依据。
- 负向：本阶段的性能数字受本机 CPU、模型缓存、网络波动和 API 返回 token 口径影响，不应作为生产 SLA。
- 负向：如果真实 provider 不返回 token usage，需要额外标注成本不可测或使用明确假设估算。

## ADR-17.5: Resume evidence summary must separate measured facts from resume wording

**Slug**: `resume-evidence-summary-boundary`
**Status**: accepted
**Date**: 2026-07-07

### Context

用户明确目标是完善简历 bullet。简历需要短句，但项目报告必须能支撑每个数字。若直接在代码或报告中写“提升显著”“保障金融安全”这类结论，会有两个风险：

- 数字来源不清，面试时无法解释。
- 把 offline eval 结果包装成生产效果，违反项目“不得夸大落地情况”的原则。

### Options Considered

- Option A: 在 README 或 PR 描述里直接写最终简历 bullet。Pros: 快。Cons: 容易和真实报告脱节，也可能提前写入未经验证的数字。
- Option B: 只保留原始报告，不产出简历摘要。Pros: 最严谨。Cons: 用户还需要手工从多个报告提炼 bullet，容易漏掉边界条件。
- Option C: 产出 evidence summary，包含“可引用数字”和“建议简历表述草稿”两个区块（采纳）。Pros: 既保留证据链，又服务简历。Cons: 需要明确草稿不是生产声明，且数字必须来自报告。

### Decision

采用 Option C。

Real Evidence Benchmark 最终报告应包含：

- Source reports：RAG matrix、Agent fake baseline、DeepSeek Agent Eval、performance/cost benchmark。
- Resume-safe facts：逐条列出可引用数字和对应文件。
- Resume bullet draft：把事实改写为 2-4 条简历 bullet 草稿。
- Claim boundary：明确数据集规模、离线/真实 provider、fake provider、environment gap 和 out-of-scope。

任何 bullet 草稿都必须满足：

- 不写“生产”“线上”“真实客户”除非确有线上证据。
- 不写“DeepSeek 实测”除非 `real_provider_call=true`。
- 不写“成本下降”除非有 before/after 成本对比。
- 不写“安全违规率 0”除非对应报告中 `unsafe_auto_fix_rate=0` 且 `hard_constraint_violation_rate=0`。

### Consequences

- 正向：最终产物能直接服务求职，同时不会牺牲证据严谨性。
- 正向：PR reviewer 可以从 bullet 反查报告，避免“简历话术”和代码事实割裂。
- 负向：如果某些结果没跑出来，bullet 草稿会更保守。
- 负向：需要维护一份汇总报告，避免后续报告更新后摘要陈旧。
