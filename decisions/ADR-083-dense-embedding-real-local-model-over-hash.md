# ADR-083: dense embedding 从 hash 占位升级到本地真实语义模型

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.1)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

**Slug**: `dense-embedding-real-local-model-over-hash`
**Status**: accepted
**Date**: 2026-06-23
**Supersedes**: ADR-009(`enhanced-rag-lightweight-default-over-bge` 的「轻量 hash 默认、BGE 仅留接口」决策)

### Context
- 现状 dense 向量来自 `HashEmbeddingFunction`(`rag/retriever.py:26`,128 维 sha256 分桶 + L2 归一,`_embed_text`),**零语义**,只按 token 字面重合命中。
- ADR-009 当初因「红线 4 不引重依赖 + DoD 须无 GPU 跑绿」选轻量 hash 默认,BGE 仅留 TODO 接口,显式「留 V1/V2」。本 stage 即兑现该 V1/V2。
- PRD §11.1 字面指定 Embedding=`BGE-large-zh-v1.5`、Reranker=`BGE-Reranker-v2-m3`(见 ADR-009 Context 转述)。
- 已核实(官方 API 文档 + GitHub issue #806):**DeepSeek 无 embedding endpoint**,故「embedding 复用现有 DeepSeek 接入」不可行,外部 API 路线须引入全新 provider。
- 项目无 `torch`/`transformers`/`sentence-transformers`;已有 `chromadb`/`rank-bm25`/`jieba`/`openai`。

### Options Considered
- **A. 维持 hash 占位** — Pros: 零依赖、CI 快。Cons: 评测被锁死在 token 重合(评测集 query 被迫关键词堆砌),「无据不判定」护栏只能挡近正交输入(ADR-082 已诚实记录),召回闸无意义。**否决**(本 stage 初衷即治此)。
- **B. 外部 embedding API** — Pros: 无本地重依赖。Cons: DeepSeek 不行须引新 provider + key + 数据出境合规;评测基线吊在网络上、CI 不确定。**否决**(银行数据合规 + 评测确定性)。
- **C. 本地真实语义模型(采纳)** — Pros: 离线、数据不出境、嵌入确定可复现(评测/召回闸有稳定基线)、无调用成本。Cons: 新增 `torch+transformers+sentence-transformers` 重依赖(数百 MB)、首次下载模型、维度变更需重建索引。

### Decision
采用 **C**,本地 `sentence-transformers`,**三层模型策略**(可配置,见 ADR-RE.2):
- **默认(生产 + `eval_rag`)**:`BAAI/bge-m3`(1024 维)。选 bge-m3 而非 PRD 字面的 `bge-large-zh-v1.5`:同为 1024 维,bge-m3 是 2024/2026 中文开源标杆、更新更强;视作对 PRD §11.1 的合理升级而非偏离。
- **低配 fallback**:`BAAI/bge-small-zh-v1.5`(512 维),供跑不动 bge-m3 的机器降级。
- **CI / 单元测试**:维持 hash(快、确定)。
- Reranker 维持 ADR-009 的 `LexicalReranker`,PRD 的 `bge-reranker-v2-m3` 不在本 stage(out of scope)。

### Consequences
- 负向:新增重依赖,wheel/环境体积显著增大;首次运行需下载模型(bge-m3 ~2GB);CI 须缓存或回避真实模型(见 ADR-RE.6)。
- 负向:三层模型 = 三种维度(128/512/1024),不能共用索引(见 ADR-RE.3)。
- 负向:bge-m3 CPU 推理慢于 hash,`eval_rag` 跑时变长(可接受,离线)。
- 正向:dense 召回首次具备真实语义能力;评测集可语义化(ADR-RE.5);为后续召回闸(拆后续)提供可信基线。
- ADR-009 的「接口抽象」思路保留但需修正落点(其抽象建在 `EmbeddingProvider`,而非 chroma 实际使用的 `EmbeddingFunction`,见 ADR-RE.2)。
