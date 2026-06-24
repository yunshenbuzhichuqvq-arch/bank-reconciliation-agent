# ADR-084: embedding 接入抽象 —— 在 chroma EmbeddingFunction 层做可配置,处置 EmbeddingProvider 孤儿抽象

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.2)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

**Slug**: `embedding-backend-configurable-at-chroma-embeddingfunction`
**Status**: accepted
**Date**: 2026-06-23

### Context
- **已核实的 design-impl gap**:ADR-009 声称定义 `EmbeddingProvider` Protocol(`rag/embedding.py:8`)+ `HashEmbeddingProvider`(:12)为换 BGE 铺路,但 `ChromaRuleStore`(`retriever.py:58`)写死 `self.embedding_function = HashEmbeddingFunction()`,**从未使用 `EmbeddingProvider`**;且 `embedding.py` 反向 import `retriever._embed_text`。chroma collection 绑定的是 `EmbeddingFunction`(:69),决定 dense 向量的是它,不是那个 Protocol。
- 即真正可换的接入点是 **chroma `EmbeddingFunction`**;`EmbeddingProvider` 是接错层的孤儿抽象,换 embedding 时用不上。
- 需求:三后端(hash / bge-small / bge-m3)按配置选,且要能 fallback 降级。

### Options Considered
- **A. 在 chroma `EmbeddingFunction` 层做可配置(采纳)** — 新增实现 chroma `EmbeddingFunction` 接口的 `SentenceTransformerEmbeddingFunction`(包 bge-m3/bge-small),`ChromaRuleStore` 按 `settings.embedding_backend` 选 hash/真实;模型加载失败按既定降级链告警降级(类比 ADR-010 「未装则开关视为关闭 + structlog 告警」)。Pros: 顺 chroma 集成本质、改动集中在真正注入点、对齐 ADR-005 Provider 风格。Cons: 与孤儿 `EmbeddingProvider` 抽象并存须显式处置。
- **B. 重构走 EmbeddingProvider 抽象** — 把 chroma 改成消费 `EmbeddingProvider`,各 backend 实现 Provider。Pros: 抽象统一。Cons: chroma 的 `EmbeddingFunction` 是其索引契约,硬塞 Provider 反而多一层适配;改动面大、收益低。
- **C. 维持写死 + if-else** — Pros: 最少代码。Cons: 不可配置、违 fallback 需求、`search()`/store 膨胀。

### Decision
采用 **A**:
- 新增 `settings.embedding_backend: Literal["hash","bge_small","bge_m3"]`(默认 `bge_m3`;CI/测试 override 为 `hash`)。
- `ChromaRuleStore.embedding_function` 由工厂按 backend 构造;真实后端实现 chroma `EmbeddingFunction` 接口(`name()`/`build_from_config()`/`get_config()` 齐全,供 chroma 持久化校验)。
- **孤儿 `EmbeddingProvider` 处置**:`embedding.py` 现仅服务该孤儿抽象且反依赖 retriever 私有函数 —— 由 Codex 在实现期确认无其他引用后**删除**(留 follow-up 标注),不在主路径保留死抽象。
- 模型加载失败 → 按 backend 降级(bge_m3 失败可降 bge_small,再失败降 hash)并 structlog 告警,主链路不崩。

### Consequences
- 负向:删除 `EmbeddingProvider`/`HashEmbeddingProvider` 须 grep 全仓确认零引用(`scripts/`、`tests/` 含)再删,否则破坏。
- 负向:降级链跨维度 = 触发索引重建(见 ADR-RE.3),非零成本,须日志显式可观测。
- 正向:换 embedding 的接入点收敛到单一工厂;后续接 reranker 真模型同法可循。
- 降级后「实际生效 backend」与 collection 命名/floor 的一致性,见 ADR-RE.7(本 stage review 补)。
