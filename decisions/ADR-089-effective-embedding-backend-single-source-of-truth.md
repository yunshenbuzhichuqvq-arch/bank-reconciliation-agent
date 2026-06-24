# ADR-089: 降级后「实际生效 backend」单一事实源(承 ADR-RE.2 / RE.3,review 补)

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.7)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

**Slug**: `effective-embedding-backend-single-source-of-truth`
**Status**: accepted
**Date**: 2026-06-23

### Context
- review 发现 ADR-RE.2 降级链与 ADR-RE.3 collection 命名的接缝未对齐:`ChromaRuleStore` 用**请求的** backend(默认 `bge_m3`)算 `collection_name` / `embedding_backend`,而 `build_embedding_function` 在依赖缺失或模型加载失败时**静默降级**返回 `HashEmbeddingFunction`(128 维)。结果:hash 向量被写进名为 `..._bge_m3` 的 collection。
- 直接违背 ADR-RE.3「异维度不混入同一 collection」:环境恢复后真实 bge_m3(1024 维)命中同名 collection → 维度冲突 / 污染。
- 第二处不一致:`config.rag_dense_min_score_for_backend` 用 `importlib.util.find_spec` 探测依赖决定 floor,工厂却用 try-load 探活——「装了依赖但模型加载失败」时 floor 取 0.5、实际嵌入是 hash → 有据场景被 0.5 floor 误杀,打穿 ADR-RE.4 护栏。
- 根因:RE.2 / RE.3 未规定「降级后系统以哪个 backend 为准」,埋下名实不符。

### Options Considered
- **A. 降级后以「实际生效 backend」为单一事实源(采纳)** — 工厂返回 / 暴露实际选定 backend;`collection_name` / 维度 / dense floor 一律跟随实际 backend;floor 依赖判定与工厂降级探活统一为同一处。Pros: 名实一致、维度隔离不被降级破坏、护栏口径正确。Cons: 工厂签名 / store 需暴露 effective backend,workflow 取 floor 经 effective backend(接口微调)。
- **B. 降级即 raise,拒绝建 collection** — Pros: 绝不名实不符。Cons: 违 RE.2「主链路不崩」,无模型环境(本地 demo / 未装 extra)直接挂,过严。**否决**。
- **C. 维持现状(请求 backend 定命名,实际可降级)** — 即本 review 的 B1,名实不符 + 跨维度污染。**否决**。

### Decision
采用 **A**:
- `build_embedding_function` 暴露实际选定 backend(返回值含 effective backend,或 store 据探活回写 `self.embedding_backend`)。
- `collection_name`、嵌入维度、`rag_dense_min_score_for_backend` 全部从**实际生效 backend**推导;降级到 hash → collection `..._hash` + floor 0.341,三者一致。
- floor 的依赖判定与工厂降级探活**统一口径**,消除 find_spec vs try-load 分叉。
- 降级仍按 RE.2 structlog 告警、主链路不崩。

### Consequences
- 负向:工厂 / store 接口微调;workflow 取 floor 须经 effective backend(非直接 settings 猜)。
- 负向:默认 `bge_m3` 在无模型环境会名正言顺落到 `..._hash` collection(隐性但有据可查的降级),用户靠告警感知。
- 正向:维度隔离(RE.3)在降级下仍成立;护栏(RE.4)口径正确;名实一致便于排查。

### 实现落地(TASK-RE.6)
新增 `BuiltEmbeddingFunction(embedding_function, effective_backend)` dataclass 作单一事实源;`ChromaRuleStore` 据 `effective_backend` 定 `collection_name` 与 `embedding_backend`;删除 `config._real_embedding_dependency_available`(find_spec),workflow/eval 经 `store.embedding_backend` 取 floor。测试以注入不同维度 fake function 真验证异维度隔离 + 降级后名实一致。
