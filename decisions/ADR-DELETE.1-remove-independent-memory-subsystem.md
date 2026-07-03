# ADR-DELETE.1: 移除独立 memory 子系统

> 归档自 stage-delete-code scratchpad `ADR.md`。

**Slug**: `remove-independent-memory-subsystem`

**Status**: accepted

**Date**: 2026-07-02

### Context

当前 `overall-architecture.md` 和 `system-prd.md` 已经把三层记忆引擎从正式架构中移除:

- `overall-architecture.md` §2.4.2 明确说明 Agent 决策不再依赖独立记忆子系统,而是在 Fallback L2 按需检索历史人工确认案例。
- `overall-architecture.md` §2.5 明确说明 Hook 链不再承担记忆注入,记忆相关环节随记忆引擎一并移除。
- `system-prd.md` §5 明确说明已删除 `GET /api/v1/memory/{user_id}/context`。
- `system-prd.md` §6 明确说明已删除 `t_short_term_memory` / `t_long_term_memory` / `t_summary_memory` 三张记忆表。

但当前代码仍保留 `services/memory/`、`api/v1/memory.py`、`schemas/memory.py`、`memory_hook`、`memory_manager` 副作用写入和 memory 专用测试。这导致代码实现与 main 文档的架构边界不一致。

本决策 supersede 以下历史 ADR 中与独立 memory 子系统相关的结论:

- `decisions/ADR-026-memory-engine-dedicated-sqlite-store.md`
- `decisions/ADR-027-memory-manager-context-and-structured-recall.md`
- `decisions/ADR-028-summary-compression-quality-gate.md`
- `decisions/ADR-035-memory-rollback-on-human-override.md`

`decisions/ADR-021-hook-chain-plain-python-pipeline.md`、`decisions/ADR-023-transaction-side-effect-separation.md`、`decisions/ADR-031-checkpoint-state-persistence-and-idempotency.md` 中提到 memory hook / memory 副作用的局部内容也随本决策被取代,但这些 ADR 的非 memory 部分继续有效。

### Options Considered

- Option A: 删除独立 memory 子系统,保留当前文档定义的历史人工确认案例 few-shot 方向。
  - Pros: 代码与 main 文档重新一致;删除独立 SQLite 记忆存储、memory API、Hook 注入和副作用写入;减少测试和运行时状态面。
  - Cons: 需要同步调整多处调用链和测试;旧 memory API 消失;如果历史 few-shot 尚未完整实现,不能在本 stage 顺手补成新功能。
- Option B: 保留 memory 子系统,仅删除 `data/memory.sqlite`。
  - Pros: 改动小,现有 memory 测试可保留。
  - Cons: 与当前 main 文档直接冲突;继续维护一个被正式架构删除的能力;后续开发会误以为 memory 仍是 Agent 上下文来源。
- Option C: 把 memory 子系统改成 no-op 或内部隐藏能力。
  - Pros: API 和调用点变动较少。
  - Cons: 留下无业务价值的空壳;测试容易验证空行为而不是真实业务;不能消除维护负担。

### Decision

采用 Option A。

本 stage 将独立 memory 子系统作为冗余代码删除。删除范围包括 memory API、schema、service、专用 SQLite 引擎、Hook 注入、决策后 memory 副作用、人工推翻时 memory 回滚、memory 专用测试和相关运行态数据文件。

本 stage 不新增历史 few-shot 能力。若当前代码尚未完全实现 `overall-architecture.md` 中的 Fallback L2 历史人工确认案例检索,该能力应作为后续功能 stage 单独规划,不能夹带在本次删除 stage 中。

### Consequences

- 正向: 代码边界与 main 文档一致;删除废弃 API 和运行态表;降低 SQLite 本地状态、Hook 降级分支和副作用失败分支的维护成本。
- 正向: 测试集会从验证旧 memory 能力转为验证当前架构下的 fallback / review / workflow 行为。
- 负向: 这是行为删除,不是纯文件清理;需要回归 `workflow`、`reconciliation`、`review`、`audit_agent`、API router 和相关测试。
- 负向: 旧 memory ADR 仍存在于 `decisions/` 历史记录中,需要通过本 stage 归档 ADR 明确 supersede,避免后续误读。
- 负向: 若外部调用者仍依赖 `/api/v1/memory/{user_id}/context`,本次删除会使该接口不可用;当前主文档已声明接口删除,因此不保留兼容 shim。
