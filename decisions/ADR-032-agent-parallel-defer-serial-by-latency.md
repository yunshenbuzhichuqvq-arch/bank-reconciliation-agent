# ADR-032: Agent 并行执行——延迟驱动保持串行

- Status: Accepted (2026-06-11)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: scripts/bench_agent_latency.py, services/workflow.py(保持串行,不引 Send), decisions/ADR-006

## Context

PRD §3.4 行211-213 / §15.4 行1708:基于 MVP-2a 真实延迟数据决定 `ExtractionAgent ∥ RAG Subgraph` 是否并行;若一方显著快于另一方(如 RAG 本地 < 100ms)则保持串行,避免不必要的并行复杂度。本 stage 须给出该决策。

## Options

- **A. 测延迟后保持串行,登记不实装(采纳)** — 量 `ExtractionAgent`(真实 LLM 1-3s 量级)与 RAG(本地检索 < 100ms 量级)延迟,差一个数量级 → 串行无瓶颈,引 `Send` 并行纯增复杂度与测试面。
  - Pros: YAGNI、零回归、有数据支撑且对齐 PRD 决策条件。
  - Cons: 与 PRD「可选并行」字面是「选择不做」(本 ADR 登记)。
- **B. 实装 `Send` 并行** — Cons: RAG 太快无并行收益;增图复杂度;与最小 Checkpoint 范围不符。

## Decision

采用 **A**。保持串行,登记不实装并行;留 V1(若 RAG 迁远程或延迟上升再评估)。

## Consequences

- 正面:不背无收益的并行复杂度。
- 负面:PRD「可选并行」记为不做(登记,留 main 同步);并行实战留 V1。
- 工具(2b3.10):`scripts/bench_agent_latency.py` 随配置 provider(默认 fake),结论按实测 `ratio` 给出。fake 下 RAG 因真实检索+冷启动首样本反而慢于 fake Extraction(实测 ratio≈0),脚本据此提示「fake 数据谨慎解读」;真实 1–3s vs <100ms 的数量级差异保留为 note,需有 key 时实测复核。
