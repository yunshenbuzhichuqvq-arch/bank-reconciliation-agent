# ADR-029: 熔断器只实装 RAG(ChromaDB),MemoryHook(SQLite) 仅降级

- Status: Accepted (2026-06-10)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/circuit_breaker.py, services/workflow.py(_retrieve_rag_response), core/config.py(rag_breaker_*), decisions/ADR-021

## Context

PRD §8.2.2 要给 MemoryHook(SQLite) + RAG Subgraph(ChromaDB) 都上 CLOSED→OPEN→HALF_OPEN 熔断器,理由是外部服务不可用时 fail-fast、保护资源。但 SQLite 是本地进程内、无网络往返,熔断器核心价值(避免反复「连接-等超时-降级」)几乎不适用;ChromaDB 才是真外部依赖。本 stage 把 2b-1 推迟的熔断器补上。

## Options

- **A. 只 RAG 实装熔断 + MemoryHook 仅降级(采纳)** — 给 RAG 检索(ChromaDB)实装「连续失败 N 次→OPEN→30s→HALF_OPEN」状态机,熔断事件入 Agent 日志;MemoryHook(SQLite)沿用 ADR-021「出错即降级(跳过记忆)」,不上完整熔断。
  - Pros: 熔断用在真有收益处(ChromaDB);不为 SQLite 背状态机复杂度;契合「不加无理由复杂度」。
  - Cons: 与 PRD §8.2.2 字面偏离(本 ADR 登记)。
- **B. 两者都按 PRD 实装完整状态机** — Cons: SQLite 那套收益小、纯增复杂度与测试面。
- **C. 熔断都推迟 V1** — Cons: ChromaDB 超时会拖慢整体,RAG 熔断在 2b 有实际价值,不该推。

## Decision

采用 **A**。RAG(ChromaDB)实装熔断器;MemoryHook(SQLite)仅降级。N(默认 5)、OPEN 窗口(默认 30s)可配置。OPEN 时返回空检索 → 既有「无命中转人工」路径接管,不臆造。

## Consequences

- 正面:复杂度用在刀刃上;RAG 故障 fail-fast,不再反复等超时。
- 负面:与 PRD §8.2.2 字面偏离(属 main 自有文档,留 main 同步);MemoryHook 无熔断,若 V1 记忆迁 Redis(变真网络依赖)需重新评估加熔断。
