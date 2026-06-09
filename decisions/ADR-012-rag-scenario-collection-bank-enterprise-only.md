# ADR-012: scenario_type 分库边界 —— 银企单库 + 预留维度

- Status: Accepted (2026-06-08)
- Deciders: 用户(拍板,决策 B), Claude Code(提案)
- Related: system-prd.md §11, t_rag_retrieval_log.scenario_type, rag/retriever.py(ChromaRuleStore/RuleRetriever)

## Context

PRD §11 要求 RAG 知识库按 `scenario_type` 分 collection(`bank_enterprise` / `bank_clearing`)。2a-1 既定边界:银企主链路,清算副链路留 2a-3。现状单 collection `mvp0_rule_chunks`,无 scenario 维度;`t_rag_retrieval_log` 已有 `scenario_type` 列(默认 `BANK_ENTERPRISE`)。

## Options

- **A. 银企单库 + 预留 scenario 维度** — Pros: 守 2a-3 边界、检索接口前向兼容清算、不返工。Cons: 分库能力 2a-2 未端到端验证(只跑银企)。
- **B. 双库全做(银企 + 清算)** — Cons: 越界 2a-3、清算规则知识库 2a-2 尚无来源。

## Decision

采用 **A**。collection 命名引入 scenario:`rule_chunks_bank_enterprise`。`ChromaRuleStore` / `RuleRetriever` 接受 `scenario_type` 参数(默认 `BANK_ENTERPRISE`),按 scenario 选 collection。`RagSearchRequest` 增可选 `scenario_type` 字段(默认 `BANK_ENTERPRISE`)。2a-2 只建银企库;清算库 2a-3 填充。

## Consequences

- collection 改名(`mvp0_rule_chunks` → `rule_chunks_bank_enterprise`),需迁移/重建本地 `chroma_data`(一次性,由 scripts 处理);测试用 tmp chroma 不受影响。
- 检索接口已带 scenario 维度,2a-3 接清算只需建库 + 灌数据,不改签名。
