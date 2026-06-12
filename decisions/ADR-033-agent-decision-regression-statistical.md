# ADR-033: Agent 决策回归测试(统计方法)

- Status: Accepted (2026-06-11)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: tests/test_mvp2b3_decision_regression.py, agents/audit_agent.py(decide_with_llm), core/config.py(decision_regression_runs)

## Context

PRD §3.4 行214-216 / §15.4 行1709:同一输入跑 10 次统计 `decision` 分布(暴露 Prompt 随机性,如 A/B 各半),断言仅检查结构化字段合法。断言不能依赖具体 `decision` 值(真实 LLM 有随机性)。

## Options

- **A. 跑 N 次(默认10)+ 分布统计 + 结构化断言(采纳)** — 对同一异常输入跑 N 次,收集 `decision` 分布;断言只查 `decision ∈ 枚举`、非转人工时 `evidence` 非空、`reason` 非空、`confidence ∈ [0,1]`;fake provider 下确定性(N 次同结果,分布单点)作为回归基线;真实 provider 的随机性分析(分布是否 A/B 各半)留 V1(无 key 时跳过)。
  - Pros: 确定性可测、对齐 PRD、断言不脆弱。
  - Cons: fake 下分布是单点,「随机性暴露」价值要真实 provider 才显现。
- **B. 断言具体 `decision` 值** — Cons: 真实 provider 下脆弱;与「统计方法」本意相悖。

## Decision

采用 **A**。统计分布 + 仅结构化字段断言;N 可配置(默认 10)。

## Consequences

- 正面:回归基线稳定、结构断言不脆弱、对齐 PRD 验收。
- 负面:fake provider 下统计为单点(真实随机性分析留真实 provider / V1)。
