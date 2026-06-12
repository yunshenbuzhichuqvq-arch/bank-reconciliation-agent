# ADR-031: Checkpoint 状态持久化与恢复幂等

- Status: Accepted (2026-06-11)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: services/review_graph.py(SqliteSaver, thread_id), services/review.py(apply_checkpoint_decision, 终态幂等), decisions/ADR-030, decisions/ADR-023

## Context

ADR-030 的 Checkpoint 子图需定「持久化粒度」与「恢复幂等」。架构 §2.4.3:同 `queue_id` 重复审批不得产生重复台账记录。现有 `review.approve` 已有幂等(状态机更新)。Checkpoint 路径下图状态存 `SqliteSaver`,恢复后节点要更新台账/队列/任务 + 写记忆,必须与 ADR-023 事务边界、2b-2 记忆副作用语义一致。

## Options

- **A. `thread_id = task_id:queue_id` 粒度 + 恢复前幂等校验(采纳)** — `SqliteSaver` 按 `thread_id`(含 `queue_id`)隔离图状态,每个待审条目一个图线程;`HumanReviewNode` `interrupt` 挂起,人工 `action` 作 `resume` 输入;恢复后「应用决策」节点在**核心事务内**更新台账/队列/任务,**事务后副作用**写记忆(复用 ADR-023 / 2b-2);幂等:恢复前若该 `queue_id` 已是终态则跳过,不重复落账。
  - Pros: 与现有事务/记忆语义一致;幂等点明确;状态可跨进程恢复(演示断点续跑)。
  - Cons: `thread_id` 命名须含 `queue_id`;`SqliteSaver` 库与 memory sqlite 分开管理。
- **B. `thread_id = task_id` 粒度(整任务一个图)** — Cons: 一任务多笔待审 → 单图多 `interrupt`,状态与幂等复杂。

## Decision

采用 **A**。Checkpoint 真实价值如实定位为「人工复核断点持久化 + 恢复幂等」,**非省决策重算**(决策已在 `upload` 完成,子图不含决策节点)。

## Consequences

- 正面:恢复幂等、与 ADR-023/2b-2 写入语义一致、状态跨进程可恢复。
- 负面:`SqliteSaver` 新增一个 sqlite 库(config + conftest 各配一处);`thread_id` 粒度到 `queue_id`;Checkpoint 不覆盖决策重算(文档如实写明,避免夸大其省 token 价值)。
