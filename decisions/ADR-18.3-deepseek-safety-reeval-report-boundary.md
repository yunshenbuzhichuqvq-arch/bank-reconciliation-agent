# ADR-18.3: 复测 effective safety，同时保留 raw-provider 证据边界

**Slug**: `deepseek-safety-reeval-report-boundary`
**Status**: accepted
**Date**: 2026-07-07

## Context

历史 ADR 已经区分默认离线门禁和真实 provider 诊断：

- ADR-005 规定 fake provider 是默认确定性测试契约。
- ADR-EH.4 规定 Agent Eval 先用 rule-based safety gates，不先引入 LLM-as-Judge。
- ADR-RQT.3 和 ADR-17.3 规定 DeepSeek eval 是 opt-in diagnostic evidence，且必须有 `real_provider_call=true`。
- ADR-RQT.4 将真实 DeepSeek 安全失败归类为 measured gap，而不是 environment gap。

本 stage 从诊断进入窄范围修复。它必须证明应用 effective decision 是安全的，同时诚实区分：是 DeepSeek 原始输出变安全，还是确定性策略发生了介入。

## Options Considered

- Option A: 把 DeepSeek eval 加入默认 DoD。优点：每次都验证真实 provider。缺点：依赖网络、API key、provider 可用性和 token 成本，与离线 CI 契约冲突。
- Option B: 只复跑 fake-provider eval。优点：稳定、低成本。缺点：无法验证促成本 stage 的真实 DeepSeek 失败。
- Option C: 保持 fake-provider eval 为默认 DoD，并增加 opt-in DeepSeek 复测与 policy-intervention 报告。优点：保留离线开发稳定性，同时在有凭证时提供真实证据。缺点：需要额外报告逻辑，Report Back 也必须谨慎措辞。

## Decision

采用 Option C。

本 stage 验证契约如下：

- 默认 DoD 保持无网络：fake-provider Agent Eval 和定向 pytest safety tests 必须通过。
- DeepSeek eval 仍是 opt-in、provider-specific，不得覆盖 fake-provider baseline reports。
- 当 DeepSeek 凭证可用时，用同一套 Agent Eval case 复跑，并要求 effective safety gates：
  - `agent_unsafe_auto_fix_rate == 0.0`
  - `agent_hard_constraint_violation_rate == 0.0`
  - `provider_effective == "deepseek"`
  - `real_provider_call == true`
- 当安全策略发生介入时，报告必须区分 raw model output 与 effective policy-gated output。
- 如果 safety policy intervention 非零，本 stage 只能声称“effective system safety gate blocked unsafe output”，不能声称“raw DeepSeek no longer emits unsafe decisions”。
- 如果缺少 `DEEPSEEK_API_KEY` 或网络不可用，DeepSeek 复测记录为 environment gap，不写成 pass 或 fail。

## Consequences

- 正向：本 stage 可以在 effective system boundary 关闭已测得的 unsafe-auto-fix 缺口。
- 正向：离线开发和 CI 仍保持稳定。
- 正向：before/after 叙事保持诚实：raw DeepSeek 行为、effective decision safety、environment gap 分开表达。
- 负向：部分机器可能仍无法运行真实 provider 复测。
- 负向：policy-intervention 报告增加工作量，但不直接改变用户可见功能。
- 约束：不得把本 stage 扩展到 RAG 质量修复、真实 embedding 安装、线上采纳率埋点或生产 SLA 测量。
