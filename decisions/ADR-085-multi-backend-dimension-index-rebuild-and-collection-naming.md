# ADR-085: 多后端 / 多维度索引重建与 collection 命名

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.3)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

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
- 降级跨维度时 collection 名须跟随实际生效 backend(否则异维度污染),见 ADR-RE.7。
