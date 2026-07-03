# ADR-DELETE.2: 清理运行态数据与本地资产边界

> 归档自 stage-delete-code scratchpad `ADR.md`。

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
