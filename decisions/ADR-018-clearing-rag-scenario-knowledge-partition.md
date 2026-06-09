# ADR-018: 清算 RAG 分库知识构建与 scenario-aware ingest

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: rag/retriever.py(_sync_chunks / _chunks_path_for_scenario / _get_sparse_index), scripts/build_rule_chunks.py, data/rag/raw_sources/bank_clearing/, data/rag/rule_chunks_bank_clearing.jsonl, decisions/ADR-009, decisions/ADR-010, decisions/ADR-011, decisions/ADR-012, decisions/ADR-013

## Context

retriever collection 命名 `rule_chunks_{scenario.lower()}`,`store.collection(scenario)` 已支持多场景查询;但 `_sync_chunks` 硬 gate 在 `BANK_ENTERPRISE`——非银企场景 collection 建空、永不灌数据(即 ADR-012「只做银企」的代码形态)。chunks 来自单一 `data/rag/rule_chunks.jsonl`(无 scenario 维度),由 `build_rule_chunks.py` 从 `data/rag/raw_sources/*.md`(front-matter + `##` 切分)构建。清算需支付结算/清算领域知识作为 BC-R001/R003 的 RAG 依据。

## Options

- **A. raw_sources/chunks 按场景分区(采纳)** — `data/rag/raw_sources/<scenario>/*.md` + 构建 `data/rag/rule_chunks_<scenario>.jsonl`;`_sync_chunks` 去 BANK_ENTERPRISE 硬 gate,按 scenario 加载对应 jsonl 灌 `rule_chunks_bank_clearing`。Pros: 与 collection 隔离一致、各场景知识物理隔离、改动收敛、对齐架构「知识库相互隔离」。Cons: 银企现有 jsonl 需迁到分区命名(一次性);build/sync 要识别 scenario 路径。
- **B. 单 jsonl 加 `scenario_type` 字段 + 过滤** — Pros: 单文件、迁移最小。Cons: 混库存放易串场景,与「知识库相互隔离」略背。
- **C. 保留 gate、为清算硬编码第二灌库路径** — Cons: 重复、不可扩展,把分库写死。

## Decision

采用 **A**。新增 `data/rag/raw_sources/bank_clearing/` 放清算领域 markdown(项目自构造模拟规则依据,沿用 front-matter + `##` 切分);`build_rule_chunks` 支持按 scenario 产出 jsonl;`_sync_chunks` 改为按 scenario 加载对应 chunks(银企路径行为不变=零回归)。embedding(`HashEmbeddingFunction`)、检索管线、toggles 全复用(承 ADR-009/010/011/013),检索签名不改(ADR-012 已铺)。BM25 稀疏索引按 scenario 分缓存(`_sparse_indexes`),避免混库串场景。

## Consequences

- 负向:银企 `rule_chunks.jsonl` → 分区命名(`rule_chunks_bank_enterprise.jsonl`)是一次性迁移,需同步 retriever `DEFAULT_CHUNKS_PATH` 与 `_chunks_path_for_scenario` 逻辑并重建本地 `chroma_data`(scripts 处理;tmp chroma 测试不受影响)。
- 清算知识为**项目自构造模拟内容**(红线:不用真实银行资料/客户数据);来源 markdown front-matter 的 source_name/url 为模拟占位。
- 清算接库零接口改动,2a-3 只填内容 + 解 gate。
