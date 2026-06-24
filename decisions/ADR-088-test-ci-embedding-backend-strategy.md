# ADR-088: 测试 / CI embedding 策略

> 归档自 stage real-embedding(scratchpad 原编号 ADR-RE.6)。本 stage 决策归档为 ADR-083(RE.1)/084(RE.2)/085(RE.3)/086(RE.4)/087(RE.5)/088(RE.6)/089(RE.7);正文 `ADR-RE.x` 即同 stage 决策,对应 ADR-(082+x)。

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
