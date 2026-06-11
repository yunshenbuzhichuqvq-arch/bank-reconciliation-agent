# ADR-027: MemoryManager 接口 + Context Window 组装 + 长期记忆结构化检索

- Status: Accepted (2026-06-10)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/memory/manager.py, services/hooks.py(memory_hook), agents/audit_agent.py(decide_with_llm), decisions/ADR-021, decisions/ADR-026

## Context

PRD §7.2/§7.3 定义 `build_context` 组装顺序(System Prompt → Long-term → Short-term → Summary → RAG → Current Item → Tool Results)与 `MemoryManager` 接口(`build_context` / `update_after_decision`)。MemoryHook(ADR-021)在 2b-1 是占位降级,本 stage 接真。长期记忆 PRD 说「按 `error_type` + 关键字段做语义相似度检索」,但记忆是纯 SQLite(ADR-026),无向量检索能力。

## Options

- **A. 长期检索用结构化/关键字匹配(采纳)** — `error_type` 精确匹配 + `summary_keywords` 关键字重叠打分,SQLite SQL 直接做,取 Top-N。Pros: 纯 SQLite、零额外依赖、确定性可测、契合 SQLite-only 与「能用确定性规则就不交 LLM」。Cons: 非真向量语义,关键字漏配则召回弱(真语义留 V1,届时本有部署环境)。
- **B. 复用 ChromaDB/embedding 向量** — Pros: 更「语义」。 Cons: 给记忆加一套向量存储、与 SQLite-only 冲突、耦合上升。
- **C. LLM 判定相似** — Cons: 每次检索一次 LLM 调用,成本/延迟高,与「确定性优先」相悖。

## Decision

采用 **A**。`build_context()` 按 §7.2 顺序拼文本,**各层设 token 预算上限、超出截断**;MemoryHook 调 `build_context` 注入 System Prompt,失败沿用 2b-1 降级(跳过记忆,仅 System Prompt)。`build_context` 只读组装;写入在 `update_after_decision`(走 ADR-026 副作用通道)。

## Consequences

- 正面:确定性、可测、零依赖;MemoryHook 从占位变真且保留降级。
- 负面:结构化召回弱于向量,`summary_keywords` 质量决定召回(写入时需抽取合理关键字);各层 token 预算/截断策略须在 spec 定死,防 prompt 膨胀。

## Notes

- 实现期发现并修复:召回侧 query keywords 抽取须与写入侧 `summary_keywords` 同口径(金额档 + 摘要分词),否则结构化召回退化为仅 `error_type` 维度(TASK-2b2.10,见 hooks.py `_memory_current_item`)。
