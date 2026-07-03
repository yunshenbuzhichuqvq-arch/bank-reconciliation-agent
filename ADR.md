# Stage Delete-Code - Architectural Decisions

## ADR-DELETE.1: 移除独立 memory 子系统

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

## ADR-DELETE.2: 清理运行态数据与本地资产边界

**Slug**: `runtime-artifact-boundary`

**Status**: accepted

**Date**: 2026-07-02

### Context

仓库当前跟踪了 `data/memory.sqlite`。该文件是 memory 子系统的本地运行态数据库,且当前文档已经删除三张 memory 表。仓库 `.gitignore` 已忽略 `spec.md`、`tasks.md`、`PR.md`,但缺少项目说明要求的 `/docs/interview/*.md`。此外,SQLite 运行态文件和 WAL/SHM 旁路文件不应进入 main。

### Options Considered

- Option A: 删除 tracked `data/memory.sqlite`,并忽略 `data/*.sqlite`、`data/*.sqlite-*`、`/docs/interview/*.md`。
  - Pros: 防止本地运行数据继续进入 PR;满足 `AGENTS.md` 对面试资产 gitignore 的要求;对正式 RAG 原始资料和评测集无影响。
  - Cons: 本地已有 SQLite 数据不会随仓库保留;需要依赖代码或测试在运行时创建必要数据库。
- Option B: 只删除 `data/memory.sqlite`,不补充 ignore 规则。
  - Pros: 当前 diff 更小。
  - Cons: 后续运行仍可能重新生成并误提交 SQLite 文件;`docs/interview/*.md` 仍不满足项目规则。
- Option C: 保留 `data/memory.sqlite` 作为样例数据。
  - Pros: 本地可观察旧 memory 数据。
  - Cons: 与 memory 删除决策冲突;运行态 DB 不可审查、不可复现,不应作为样例资产。

### Decision

采用 Option A。

本 stage 删除 `data/memory.sqlite`,并补充 `.gitignore`:

- `data/*.sqlite`
- `data/*.sqlite-*`
- `/docs/interview/*.md`

保留 `data/rag/`、`data/rag_eval_set.json` 等正式 RAG 资料与评测资产,因为它们不是运行态数据库。

### Consequences

- 正向: PR 不再携带本地 SQLite 状态;`docs/interview/` 本地复盘材料符合项目规则;运行态文件边界更清晰。
- 负向: 开发者本地如需保留旧 `data/memory.sqlite` 内容,需要自行备份到仓库外;删除后不能通过 Git 恢复该本地运行态内容。
- 负向: 如果后续新增其他持久化 SQLite 文件,需要明确判断是可复现资产还是运行态产物,不能默认提交。

## ADR-DELETE.3: 收敛 mock 数据生成入口

**Slug**: `retire-legacy-mock-generator`

**Status**: accepted

**Date**: 2026-07-02

### Context

当前 `scripts/generate_mock_excel.py` 同时保留旧版 `generate_mock_excel()` 和当前 MVP1 场景生成入口 `generate_mvp1_mock_excel()`。仓库中也同时跟踪:

- `mock_data/bank_transactions.xlsx`
- `mock_data/clear_transactions.xlsx`
- `mock_data/mvp1_bank.xlsx`
- `mock_data/mvp1_clear.xlsx`

README 与现有主流程更偏向 `mvp1_*` 固定样本。旧版 `bank_transactions.xlsx` / `clear_transactions.xlsx` 与当前场景化命名并存,会增加测试入口和样本口径的歧义。

### Options Considered

- Option A: 退役旧版生成入口和旧版 Excel 样本,统一使用 `generate_mvp1_mock_excel()` 与 `mvp1_*` 文件。
  - Pros: 样本命名与场景化方向一致;减少测试夹具重复;降低脚本维护面。
  - Cons: 需要迁移仍引用旧文件名或旧函数的测试;旧文件名不再可用。
- Option B: 保留两套样本,只补文档说明差异。
  - Pros: 无需迁移测试。
  - Cons: 继续保留重复入口;使用者仍需要判断哪套才是当前标准样本。
- Option C: 删除所有 Excel 样本,测试全部运行时生成。
  - Pros: 仓库更轻。
  - Cons: 改动过大;会影响固定样本可审查性;不符合本 stage 的删除冗余目标。

### Decision

采用 Option A。

本 stage 将旧版 `generate_mock_excel()`、`mock_data/bank_transactions.xlsx`、`mock_data/clear_transactions.xlsx` 视为冗余。实现任务应先迁移仍依赖旧入口的测试,再删除旧函数和旧样本文件。

当前 stage 不改变 clearing 场景样本,不重写 mock 数据分布算法,不引入新的数据生成依赖。

### Consequences

- 正向: mock 数据入口减少到当前主线;测试和 README 对样本文件的说明更一致。
- 正向: 删除旧 Excel 样本可减少仓库中固定二进制文件数量。
- 负向: 由于 Excel 是二进制文件,删除和测试迁移需要仔细核对 diff 和回归命令。
- 负向: 如果仍有外部脚本依赖旧文件名,需要改用 `mvp1_bank.xlsx` / `mvp1_clear.xlsx`。
