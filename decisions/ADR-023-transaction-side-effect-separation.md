# ADR-023: 事务与副作用分离

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: services/reconciliation.py(_write_ledger_entries / _build_write_bundle / _run_side_effect), services/ledger.py, services/queue.py, services/task.py(replace_ai_stats connection), decisions/ADR-014

## Context

reconciliation._write_ledger_entries 原在一个循环里既算逐笔结果,又把核心写入(ledger / queue / task-stats 各自 replace_task_rows)与副作用(agent_log / rag_log / trace JSON)穿插执行:核心三写彼此非原子,副作用抛错会中断主流程。PRD §8.2.1 要求 Post-Hook 纯校验 → 核心事务(必成功) → 副作用(非阻塞,失败不影响主流程)。各 service 的 replace_task_rows 已支持透传 connection 做跨表原子。

## Options

- **A. 核心三写并入单 engine.begin() 透传 connection;副作用后置非阻塞(采纳)** — ledger+queue+ai-stats 同事务原子提交;agent_log/rag_log/trace(及 2b-2 记忆更新)移到提交后,各包 try/except,失败仅 WARNING、不回滚不抛。Pros: 与 PRD 一致、原子、副作用不再拖垮落库、复用既有 connection 透传。Cons: 重排写入顺序、trace 改事务后处理,需回归 e2e。
- **B. 维持现状,仅给副作用加 try/except** — Pros: 改动最小。Cons: 核心三写仍非原子,没解决「事务」本身。

## Decision

采用 A。计算与写入分离:_build_write_bundle 先算齐,再单事务写核心、后置跑副作用。幂等沿用 ADR-014 的 replace_task_rows(按 task 全替换,重跑安全)语义,事务化不改幂等模型。

## Consequences

- 正面:核心写入原子可重跑;副作用与主链路解耦,记忆/日志失败不影响落库正确性。
- 负向:写入顺序与 trace 落盘时机改变;副作用失败由「中断」变「静默 WARNING」,须保日志可观测。
- 落地补遗:_write_ledger_entries 一度复用 task_service._engine 并手调三服务私有 _ensure_initialized(依赖共享同一 engine 隐含假设),TASK-2b1.8 已收敛该耦合。
