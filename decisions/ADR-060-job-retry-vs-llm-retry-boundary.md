# ADR-060: Job 重试 vs 现有 LLM 有界重试 / Fallback 的边界

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/worker.py(max_tries), src/bank_reconciliation_agent/services/reconciliation.py(run_reconciliation_job 异常分类), decisions/ADR-007(三级 Fallback), decisions/ADR-023(核心事务 vs 事务后副作用), decisions/ADR-059(幂等)

## Context

ARQ 自带 job 级重试。现有链路已有两层失败处理:AuditAgent 结构化输出的有界重试(Schema 校验失败重试)+ 三级 Fallback(ADR-007,RAG 无命中/LLM 失败转人工)。若 ARQ job 对同一任务整体重试,会把"已落库的部分副作用 + LLM 调用"整条重放,与既有重试/fallback 叠加放大失败、重复烧 token、并可能违反 ADR-023 事务边界与幂等。

## Options Considered

- **A. Job 重试仅覆盖基础设施瞬时错误(采纳)** — ARQ `max_tries` 仅对 Redis(`ConnectionError`)/DB(`OperationalError`)类瞬时故障重抛重试;业务/LLM 失败由现有 AuditAgent 有界重试 + 三级 Fallback 处理,失败任务翻 `FAILED`,**不**由 job 层重放整条对账。
  - Pros:不与既有重试/fallback 叠加;不重复烧 token;副作用幂等边界清晰。Cons:需在 worker 内区分"瞬时基础设施错误"与"业务失败"两类异常。
- **B. Job 整体重试** — 失败即整任务重跑。
  - Pros:实现简单。Cons:重复 LLM 调用与副作用、与既有 fallback 叠加、幂等风险高。
- **C. 关闭 job 重试** — `max_tries=1`,任何失败即 FAILED。
  - Pros:最简、零叠加。Cons:Redis/DB 抖动这类真瞬时错误也不重试,鲁棒性弱。

## Decision

采用 **A**:job 重试只兜底基础设施瞬时错误(`RedisConnectionError` / `OperationalError` 重抛交 ARQ `max_tries=3`);LLM/业务失败沿用现有有界重试 + 三级 Fallback,捕获后翻 `FAILED` 不重抛。worker 重入幂等:复用 task_id 内容寻址 + 落库前终态复查跳过。落库为 replace 覆盖 + 单事务(ADR-023/014),故重试重跑安全。

## Consequences

- 正面:失败处理职责单一、不叠加放大;token 不被重复消耗;与 ADR-007/023 一致。
- 负面:worker 需显式分类异常(瞬时 vs 业务),增实现复杂度;"瞬时错误"判定边界需明确,否则易误分类。
- Follow-up(收尾 review 登记):瞬时错误重试耗尽时 task 停在 `RUNNING`(只重抛不翻状态),且 RUNNING+force→409 无恢复路径 → 应由 ARQ `on_job_failure` 兜底翻 `FAILED`。
