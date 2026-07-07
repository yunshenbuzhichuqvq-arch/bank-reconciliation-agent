# ADR-EO.3: Agent 风险修复聚焦确定性高风险语义

**Slug**: `agent-risk-high-risk-semantics`
**Status**: accepted
**Date**: 2026-07-07

### Context

Agent Eval 有 1 个明确的 risk mismatch：

- Case：`agent-high-risk-001`
- Error type：`DUPLICATE_BOOKING`
- Branch：`BE-R008`
- Expected risk：`HIGH`
- Baseline actual risk：`MEDIUM`

`AuditAgent.decide()` 已经在 `BRANCH_PROFILE` 中把 `BE-R008` 映射为 `HIGH`，
但 fake LLM 路径返回了通用 `MEDIUM` risk。由于默认 Agent Eval 使用
`FakeLLMProvider`，这个 miss 是确定性 test-provider 语义缺口，而不是真实
DeepSeek 风险模型结果的证据。

### Options Considered

- Option A：把该 eval case 的期望值改成 `MEDIUM`。
  - 优点：最快让 `risk_accuracy=1.0`。
  - 缺点：隐藏真实的高风险业务预期，并与 duplicate-booking branch profile
    冲突。
- Option B：在 Agent Eval 结果后处理阶段覆盖该 case 的 risk level。
  - 优点：改动局限在 eval script。
  - 缺点：让 evaluator 替 provider 行为兜底，可能夸大 runtime quality。
- Option C：让 deterministic fake provider 或 deterministic fallback path 尊重
  已知高风险 branch / error semantics，然后重新运行 Agent Eval。
  - 优点：保持 case label 诚实，并让 fake baseline 对齐既有 branch risk
    contract。
  - 缺点：可能需要更新那些假设 fake provider 永远返回 `MEDIUM` 的测试；
    真实 DeepSeek 质量仍然未被测量。

### Decision

采用 Option C。

Agent optimization task 应让 deterministic local evaluation 将 `BE-R008` /
`DUPLICATE_BOOKING` 识别为 `HIGH` risk，同时不得削弱既有 safety gates：

- `unsafe_auto_fix_rate` 必须保持 `0.0`。
- `hard_constraint_violation_rate` 必须保持 `0.0`。
- `decision_accuracy` 不得回退。
- Fake provider 必须保持 network-free，且不能声称代表真实 DeepSeek quality。

Real provider behavior 仍为 opt-in，不能从 fake-provider metrics 推断。

### Consequences

- 正向：Agent Eval 可以在保留高风险标签的同时，针对已知 deterministic miss
  达到 `risk_accuracy=1.0`。
- 正向：该修复强化 fake baseline，而不是为了适配当前输出去修改 evaluation
  labels。
- 负向：结果仍不能证明真实 LLM risk accuracy。
- 约束：不得为了提升指标而放松 `must_not_auto_fix`、evidence 或 hard-constraint
  rules。
