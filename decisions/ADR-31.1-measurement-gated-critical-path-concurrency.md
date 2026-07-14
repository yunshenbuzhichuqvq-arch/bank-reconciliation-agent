# ADR-31.1: 使用测量门禁决定关键路径并行，并允许以 no-go 收尾

**Slug**: `measurement-gated-critical-path-concurrency`
**Status**: accepted
**Date**: 2026-07-13

## Context

`decisions/ADR-032-agent-parallel-defer-serial-by-latency.md` 依据当时的独立组件 benchmark，决定
`ExtractionAgent` 与 RAG 保持串行。该决策认为本地稳定态 RAG 明显快于真实 LLM，直接引入并行只会
增加工作流和测试复杂度；只有未来延迟结构发生变化且有真实证据时才重新评估。

Stage 29 已增加持久化 Execution Trace，但其确定性 evidence 使用 Fake provider、hash embedding 和
本地 SQLite，目标是验证 Trace/Replay contract，不是证明真实关键路径性能。现有 Stage 23 benchmark
虽然使用真实 DeepSeek，但只分别测量 `ExtractionAgent` 和 RAG，样本数为 5，首个 RAG 样本混入模型
加载，且没有运行真实 `run_item()` 或生成可关联的端到端 Trace。因此它不能直接推翻 ADR-032。

当前代码只有 `BE-R004` 且摘要命中冲正类关键词时同时执行 `ExtractionAgent` 与 `search_rules`。
RAG query 不读取 `extraction_result`，存在数据独立的可能；但 `TraceRecorder`、SSE、Agent 日志、Tool
attempt/breaker 和失败路径仍可能产生共享或顺序相关副作用。尤其在当前串行语义下，Extraction 失败
会直接转人工且不会继续执行 RAG；任何候选并发方案都必须显式处理这一差异，不能只比较 happy path。

原本地路线图要求在创建 Stage 31 分支前证明全部入口门禁。实际 Stage 29 证据不足以完成该证明，
但用户已明确覆盖该前置约束，并决定把 Stage 31 保留为最后一个 Stage。覆盖的含义不是预先批准
并行实现，而是允许在 Stage 31 内先补齐可信测量，再由门禁决定是否存在候选实现。

## Options Considered

### Option A：维持原路线图，Stage 31 no-go

- 优点：完全沿用 ADR-032 和原入口门禁，不增加任何代码或真实 provider 成本。
- 缺点：无法用 Stage 29 Trace 重新验证关键路径；用户已明确要求覆盖并继续最后一个 Stage。

### Option B：直接并行 Extraction 与 RAG

- 优点：最快获得并行代码和 after 数字。
- 缺点：没有可信 warm 端到端 baseline；无法证明数据与副作用独立；可能改变失败顺序、Tool 调用、
  Trace/SSE 顺序和成本；若收益不足，先承担了不必要的实现与回滚成本。

### Option C：Stage 内测量门禁，达标后才允许一个最小候选（采纳）

- 优点：保留 Stage 31，同时保持 ADR-032 的默认串行边界；可以诚实得到
  `candidate_allowed`、`no_go` 或 `environment_gap`；只有可证明的收益和安全性才扩大到运行时代码。
- 缺点：需要扩展 benchmark contract、运行真实 DeepSeek/bge_m3，并可能在没有性能实现的情况下
  结束 Stage。

## Decision

采用 **Option C**。

### 1. Stage 31 可以开始，但运行时默认保持串行

- 用户对原“分支创建前门禁”作出明确覆盖，允许正式创建 Stage 31 ADR/spec 和 baseline evidence。
- 覆盖不推翻 ADR-032 的串行结论。`workflow.py` 在 baseline gate 给出
  `candidate_allowed` 之前不得修改。
- `no_go` 是完整、可接受的 Stage 结果，不得为了交付并行代码而降低阈值或更换 benchmark 输入。
- `environment_gap` 必须与 measured `no_go` 区分；它只能说明真实环境未能完成测量，不能说明并行
  有收益或无收益。

### 2. Baseline 必须测量真实、同一次 flow 的关键路径

Stage 31 benchmark 必须满足：

- 固定使用会真实进入 `ExtractionAgent → search_rules → AuditAgent` 的
  `BANK_ENTERPRISE / BE-R004 / NARRATIVE_NAME_MISMATCH` 冲正类输入。
- 通过真实 `run_item()` 边界运行，不再把两个组件的独立 microbenchmark 当作端到端证据。
- 使用 Stage 29 canonical `TraceSpan` 关联同一 `trace_id` 内的 `WORKFLOW`、
  `AGENT(name=ExtractionAgent)` 和 `TOOL(name=search_rules)`。
- requested/effective provider 必须均为 `deepseek`；requested/effective embedding backend 必须均为
  `bge_m3`。任何 fallback、缺少凭据、网络或模型不可用都记为 `environment_gap`。
- 单独记录一个 cold probe 和至少一个不计入统计的 warm-up；性能门禁只使用不少于 20 个完整 warm
  measured runs。
- 报告固定输入 hash、Git revision、环境、模型、embedding backend、retrieval mode、运行数量、
  Trace completeness、错误率、token 和估算成本。离线数据不得表述为生产 SLA。

每个 warm run 按同一 Trace 计算：

```text
predicted_parallel_e2e_ms
  = actual_e2e_ms
    - extraction_duration_ms
    - rag_duration_ms
    + max(extraction_duration_ms, rag_duration_ms)
```

然后分别对 `actual_e2e_ms` 与 `predicted_parallel_e2e_ms` 的同组 warm samples 计算 P95：

```text
theoretical_p95_improvement_pct
  = (actual_warm_p95 - predicted_parallel_warm_p95)
    / actual_warm_p95 * 100
```

不得把 Extraction P95 与 RAG P95 独立相加，也不得把 cold 样本混入 warm P95。

### 3. Candidate gate 必须 fail closed

只有以下条件全部满足，baseline 才输出 `candidate_allowed`：

1. 真实 provider/backend 和全部 trust metadata 满足要求。
2. 至少 20 个 warm measured runs 全部产生结构完整、可关联的 Trace，且包含恰好一个
   Extraction span 与一个 `search_rules` span。
3. 静态与动态证据均证明两项工作无数据依赖；并发执行不要求 worker 修改共享
   `ReconciliationState`、Trace recorder、SSE emitter 或持久化状态。
4. 失败顺序、Tool attempt/breaker、日志、token/cost 等副作用已被列举，并存在不扩大业务权限、
   不泄露数据且可测试的处理方案。
5. `theoretical_p95_improvement_pct >= 20.0`。

任何条件不满足时输出 `no_go`，保持运行时串行，不创建 after candidate。若条件无法测量，则输出
`environment_gap`，同样禁止 runtime candidate。

### 4. 达标后只允许一个窄范围候选

若且仅若 baseline 为 `candidate_allowed`：

- 只允许并行 `BE-R004` 冲正类路径中的 Extraction 与 `search_rules`，其他分支保持原顺序。
- 使用 Python 标准库内的有界线程能力适配现有同步调用；不引入新依赖，不迁移 LangGraph 主图，
  不改变 HTTP、数据库或 Tool 公共 contract。
- worker 不得直接修改共享 `ReconciliationState`、写数据库、发送 SSE 或操作 `TraceRecorder`。
  两侧返回独立结果，由父执行流按 canonical 顺序完成校验、状态合并、日志、Trace 和 SSE 投影。
- 任一侧失败、取消或超时时不得使用另一侧的部分结果继续自动判断。最终业务结果必须继续遵守现有
  fail-closed 和 RAG 无证据转人工语义。
- 运行中的同步调用若无法可靠取消，必须有有界等待和资源回收测试；不得留下后台线程继续修改
  共享状态。若现有 provider/retriever contract 无法满足该要求，候选应判定不可实现并 no-go。

### 5. 实现保留门禁

candidate before/after 必须使用相同输入、环境、provider/model、embedding backend/mode 和样本数量。
只有以下条件全部满足才保留运行时并行：

- 实测 warm 端到端 P95 改善 `>= 20.0%`。
- 业务输出、RAG evidence、Audit 安全决策、Fallback 和 Trace 结构无回归。
- focused concurrency/failure tests、全量 pytest 和 Ruff gate 满足 Stage spec。
- successful path 的逻辑 Agent/Tool 调用数量不增加。
- 每成功样本 token 与估算成本不高于 baseline 的 105%，错误率不高于 baseline 5 个百分点；任何
  变化都必须在 comparison 中列出。

任一条件失败时必须撤销 runtime candidate，只保留 benchmark contract、baseline/after/comparison
报告和 `optimization_rejected` 结论。不得将理论收益包装为实测收益。

## Consequences

- 正面：Stage 31 可以作为最后一个 Stage 完成，同时允许可信 no-go，而不是强行交付并行代码。
- 正面：ADR-032 只有在同 flow、warm、端到端 Trace 证据满足门禁时才会被实证覆盖。
- 正面：cold 模型加载、真实 provider 环境缺口、并发失败语义和成本变化均进入机器可审查报告。
- 负面：真实 DeepSeek/bge_m3 benchmark 依赖本地凭据、网络、模型和机器状态，可能以
  `environment_gap` 结束。
- 负面：20 个 warm runs 仍只是本机离线样本，不足以声明生产 P95、容量或 SLA。
- 负面：如果 Extraction 失败时的 speculative RAG 调用或 Trace/SSE 并发无法保持安全边界，Stage
  将在 independence gate 得到 no-go，不会进入实现。
