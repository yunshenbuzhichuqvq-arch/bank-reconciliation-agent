# ADR-21.2: bge_small 是最低真实 backend 要求，bge_m3 best-effort

**Slug**: `bge-small-minimum-real-backend-bge-m3-opportunistic`
**Status**: accepted
**Date**: 2026-07-08

### Context

后续补全清单中的最低要求是至少跑通一个真实 embedding backend，例如 `bge_small`，并与 hash
比较。历史 real-vs-hash 证据显示 `bge_small` 和 `bge_m3` 都在 weighted ranking metrics
上优于 hash，但 `bge_m3` 更大，更容易受本地资源、模型缓存和 CPU 性能影响。ADR-088 也明确
真实 embedding 路径是 opt-in 且与环境有关。

本阶段需要一个有价值但不过度脆弱的验收口径。

### Options Considered

- Option A: 要求 `bge_small` 和 `bge_m3` 都 measured，本阶段才算通过。
  Pros: 对比最完整。
  Cons: 阶段成败被最重模型绑定；即使项目已能证明一个真实语义 backend，`bge_m3` 缓存或资源问题
  仍会阻塞。
- Option B: 要求 `hash` 加至少 `bge_small`；`bge_m3` 尽力运行，并在报告中记录 measured 或
  unavailable。
  Pros: 满足最低真实 embedding 要求，同时保留比较更强 backend 的机会。
  Cons: 如果 `bge_m3` 不可用，报告无法完成所有目标真实 backend 对比。
- Option C: 所有真实 backend 都可选，接受 hash-only matrix。
  Pros: 总能运行。
  Cons: 重复当前 `real_backend_policy=skip` 缺口，无法支撑 real embedding quality claim。

### Decision

采用 Option B。

Matrix 必须始终测量 `hash`。要满足本阶段，必须至少产出一个 measured non-hash row，其中
`bge_small` 是最低真实 backend 要求。`bge_m3` 在本地环境支持时应尝试运行，但如果 `bge_small`
已 measured，`bge_m3` 的 unavailable row 不作为 blocking，前提是报告写清原因。

### Consequences

- Positive: 阶段可以在现实本地开发环境中完成。
- Positive: 报告仍能证明 harness 不只是 hash，而是能使用真实语义 embedding backend。
- Negative: 如果只有 `bge_small` measured，报告可能低估或遗漏 `bge_m3` 行为。
- Negative: Reviewer 必须读取 status metadata，不能假设每个 backend row 都 measured。
- Constraint: `bge_small` 或 `bge_m3` fallback 到 hash，不满足 non-hash backend 要求。
