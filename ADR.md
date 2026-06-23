# Stage real-embedding — Architectural Decisions

> 目标:把 RAG dense 检索从 hash 占位(128 维 sha256,无语义)升级到本地真实语义 embedding,语义化评测集,并用评测证明真实 embedding 的召回质量碾压 hash。
> Scope 聚焦决策点 1–6;**召回闸、对账 Faker 数据、hybrid/reranker 改动均 out of scope(拆后续)**。

---

## ADR-RE.1: dense embedding 从 hash 占位升级到本地真实语义模型

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

---

## ADR-RE.2: embedding 接入抽象 —— 在 chroma EmbeddingFunction 层做可配置,处置 EmbeddingProvider 孤儿抽象

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

---

## ADR-RE.3: 多后端 / 多维度索引重建与 collection 命名

**Slug**: `multi-backend-dimension-index-rebuild-and-collection-naming`
**Status**: accepted
**Date**: 2026-06-23

### Context
- 三后端三维度(hash 128 / bge-small 512 / bge-m3 1024)。chroma collection 创建时即绑定 embedding function 与维度,**异维度向量不可混入同一 collection**。
- 现 collection 命名 `rule_chunks_{scenario_type.lower()}`(`retriever.py:152`),两 scenario:`bank_enterprise` / `bank_clearing`(ADR-012/018)。
- 现 `_sync_chunks` 在首次取 collection 时 upsert(`retriever.py:115`),无维度隔离概念。

### Options Considered
- **A. collection 名编码 backend(采纳)** — `rule_chunks_{scenario}_{backend}`(或 `_{dims}`)。Pros: 多后端索引并存、切后端不互相污染、fallback 可预建、可复跑评测对比 hash/真实。Cons: chroma 目录占用增加;命名与既有 `rule_chunks_{scenario}` 不兼容,须迁移调试 API 与 eval 取数路径。
- **B. 单 collection,切后端整体清空重建** — Pros: 命名不变。Cons: 切后端即销毁旧索引,无法 hash↔真实并存对比(评测 ADR-RE.5 要对比基线);fallback 与默认互斥。
- **C. 进程内多 client/path** — Cons: 复杂度高,2 后端无此需要,过度设计。

### Decision
采用 **A**:collection 命名加 backend 维度(具体 `_{backend}` 还是 `_{dims}` 由 Codex 在 spec 边界内择一,需同步 `eval_rag.py` 与 `/rag/search` 取数路径)。索引重建覆盖 `bank_enterprise` + `bank_clearing` 两 scenario。提供一次性重建入口(脚本或 store 方法),避免靠「首次 query 隐式 upsert」做大规模重建。

### Consequences
- 负向:迁移既有 collection 命名,触及 retriever/eval/调试 API 的取数路径,须全量回归。
- 负向:chroma 持久化目录体积随后端数增长。
- 正向:hash 与真实后端索引并存 → ADR-RE.5 能直接跑「同评测集、hash vs bge-m3」对比,坐实「碾压」论断。

---

## ADR-RE.4: dense 阈值按真实嵌入重新校准(承 ADR-082)

**Slug**: `dense-threshold-recalibration-for-real-embedding`
**Status**: accepted
**Date**: 2026-06-23

### Context
- ADR-082 把 `rag_dense_min_score` 校准到 **0.341**,明确这是 **hash 占位口径**(实测有据 0.35–0.43、正交≈0.33);架构 §6.7 的 **0.5 是真实语义嵌入口径**,并预告「floor 待真实嵌入随闸复校」。
- bge-m3 / bge-small 的分数分布(余弦/距离→score 经 `_score_from_distance`)与 hash 完全不同口径,0.341 对真实模型无意义。
- floor 影响主链路「无据→PENDING_HUMAN」护栏(§6.7 / ADR-082)与 SSE 断言 `_has_readable_decision_and_evidence`。

### Options Considered
- **A. 每后端独立 floor + 实测校准(采纳)** — `rag_dense_min_score` 随 backend 取值(hash 保留 0.341;bge-m3 / bge-small 各自实测校准)。Pros: 各后端口径正确、护栏在真实嵌入下才真正成立。Cons: 配置项随后端分叉,须实测取值并留痕。
- **B. 单一 floor 沿用 0.341** — Pros: 不动配置。Cons: 对真实模型是错值,误杀或漏挡,使护栏失真。**否决**。
- **C. 本 stage 不接 floor(min_score=0)** — Pros: 省校准。Cons: 退回 ADR-082 修复前的「护栏形同虚设」,倒退。**否决**。

### Decision
采用 **A**:floor 随 `embedding_backend` 取值;bge-m3/bge-small 的校准值由实测定(量「正确命中规则最低分」与「完全无关 query 基线」,取其间),实测数据在实现期留痕。**不迁就 SSE 断言**:真实嵌入下有据场景 evidence 应自然非空、断言自然过(承 ADR-082 立场,改断言接受空 evidence=掩盖退化,否决)。同步更新 `test_mvp2a2_schema_config.py` 的阈值断言与 `eval_rag` 口径。

### Consequences
- 负向:多一组按 backend 的阈值,须文档化每个值的实测来源。
- 负向:真实嵌入下若 §6.7 的 0.5 经实测仍偏高/偏低,需以实测为准并在 ADR/spec 记录与 §6.7 的差异。
- 正向:「无据不判定」首次建立在真实语义分数上,不再只是「挡近正交」。

---

## ADR-RE.5: 评测集语义化(承 ADR-034,直面饱和局限)

**Slug**: `eval-set-semantic-rewrite-and-desaturation`
**Status**: accepted
**Date**: 2026-06-23

### Context
- 现 `data/rag_eval_set.json`(ADR-034)query 是**关键词堆砌**(如 be-r002-01..10 十条同义、均指向单一 `unionpay_reconciliation_faq_001`),这是被 hash「只认 token 重合」逼出来的形态。
- ADR-034 已知局限:银企语料仅 6 chunk → `top_k=5` 下 **Recall@5 结构性饱和(恒 1.0)**,判别力靠 Hit@1(0.62)/MRR/NDCG;语料扩到 120+ 才恢复区分力。语料库近期已扩(recon-hardening corpus expansion)。
- 评测脚本 `_evaluate_case` 用 `min_score=0.0`、按 `expected_chunk_ids` 算 Hit@1/Recall@5/MRR/NDCG@5。

### Options Considered
- **A. query 自然语言化 + ground truth 重标 + 去重去饱和(采纳)** — query 改成真实问法(用户/系统会问的自然语言);ground truth 按语义相关重标(允许一 query 对多 chunk);砍重复同义灌水;结合已扩语料评估 Recall@5 是否恢复区分力。Pros: 评测真正测语义召回、与真实嵌入匹配、可对比 hash 暴露差距。Cons: 人工标注成本高、标注质量决定指标可信度(ADR-034 既有风险)。
- **B. 维持关键词 query,仅扩量** — Pros: 省事。Cons: 继续测 token 重合,与换真实嵌入的初衷矛盾。**否决**。
- **C. LLM 生成 query + 人工校验** — 用 LLM 基于语料生成自然语言 query、人工校验标注。Pros: 提效。Cons: 引入 LLM 生成偏差需校验闸;可作为 A 的辅助手段(实现期可选),不单列为方案。

### Decision
采用 **A**(C 作为可选提效手段):评测集 query 自然语言化、ground truth 语义重标、去同义灌水;保留 `scenario_type`/`error_type` 维度与 EvalCase schema。**本 stage 终点是"用语义评测集跑出 hash vs bge-m3 的对比数字、证明真实嵌入召回更优",不锁定召回硬闸**(闸拆后续 stage,避免在数据刚定稿时即锁门柱——重蹈 recon-hardening 推迟召回闸的覆辙)。

### Consequences
- 负向:标注工作量与质量风险(承 ADR-034);自然语言 query 在 hash 后端下分数会更低,但那正是要暴露的真相。
- 负向:若语料规模仍不足,Recall@5 可能仍部分饱和,须以 Hit@1/MRR/NDCG 辅判并诚实记录。
- 正向:评测集脱离 token 重合,成为真实语义召回的可信尺;为后续召回闸提供定稿数据。

---

## ADR-RE.6: 测试 / CI embedding 策略

**Slug**: `test-ci-embedding-backend-strategy`
**Status**: accepted
**Date**: 2026-06-23

### Context
- 真实模型大(bge-m3 ~2GB)、CPU 推理慢、首次需下载;CI 须快且确定、无 GPU、不依赖网络。
- 项目已有 pytest `live` marker(「opt-in tests that call external live services」)与「未装依赖则降级 + 告警」先例(ADR-010)。

### Options Considered
- **A. CI 用 hash、真实模型测试 opt-in(采纳)** — 单元/全量 `uv run pytest` 默认 `embedding_backend=hash`(行为/契约/零回归用确定 hash);真实模型路径(加载、维度、索引重建、bge-m3 召回)单独标记(复用/类比 `live` marker 或新增 `embedding_real` marker),默认不跑、opt-in。Pros: CI 快/确定、套件不被 2GB 模型拖垮、契约仍全测。Cons: 默认 CI **不覆盖真实模型路径**(真实召回质量靠手动跑 `eval_rag` + opt-in 测试把关)。
- **B. CI 也跑真实模型** — Pros: 全路径覆盖。Cons: CI 拉 2GB 模型、慢且不稳、可能需缓存基建,得不偿失。**否决**。
- **C. 真实模型路径完全不测** — Cons: 加载/维度/降级无任何自动验证,回归无网。**否决**。

### Decision
采用 **A**:`embedding_backend` 测试默认 hash;新增真实模型 opt-in 测试(模型加载成功→维度正确、索引按维度重建、降级链触发告警);真实召回质量由手动 `eval_rag`(bge-m3)出报告把关。模型下载/缓存策略(预下载或首次惰性 + 缓存目录)在 spec 明确,避免 opt-in 测试每次重下。

### Consequences
- 负向:默认 CI 绿 ≠ 真实模型路径绿(诚实记录此盲区);真实模型回归依赖 opt-in 主动跑。
- 负向:opt-in 测试需要模型与缓存,贡献者环境差异大。
- 正向:全量套件保持快与确定;真实模型的重成本只在需要时付。
