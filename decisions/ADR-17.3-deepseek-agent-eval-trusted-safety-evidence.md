# ADR-17.3: DeepSeek Agent Eval is trusted only with real-provider metadata and safety redlines

**Slug**: `deepseek-agent-eval-trusted-safety-evidence`
**Status**: accepted
**Date**: 2026-07-07

## Context

当前 fake-provider Agent Eval 能证明 deterministic baseline 和安全门禁，但不能证明真实 DeepSeek 行为。用户本阶段需要的数据是“真实 LLM 下是否仍守住金融安全红线”，重点指标包括：

- `decision_accuracy`
- `risk_accuracy`
- `evidence_citation_rate`
- `unsafe_auto_fix_rate`
- `hard_constraint_violation_rate`

ADR-RQT.3 已规定真实 LLM Agent Eval 是 opt-in diagnostic evidence，不能变成默认 DoD。

## Options Considered

- Option A: 把 DeepSeek Eval 加入默认 DoD。Pros: 每次都覆盖真实模型。Cons: 依赖网络、API key、模型可用性和费用；不适合 CI，也会让本地开发不稳定。
- Option B: 继续只跑 fake provider，然后在简历中泛称 Agent Eval。Pros: 稳定、成本低。Cons: 不能支持“真实 DeepSeek 下”的结论，容易被面试追问击穿。
- Option C: 保留 fake baseline，同时增加 provider-specific DeepSeek report，并只信任带 `real_provider_call=true` 的结果（采纳）。Pros: 可证明真实调用；不污染 fake baseline；没有 API key 时能诚实记录 environment gap。Cons: 真实 LLM 输出有非确定性，case 数小的时候不能过度泛化。

## Decision

采用 Option C。

DeepSeek benchmark contract：

- 默认 fake-provider Agent Eval 继续作为离线 safety baseline。
- DeepSeek 运行必须显式使用 provider-specific 输出路径，例如 `reports/agent_eval_deepseek_flash.md` 和 `reports/agent_eval_deepseek_flash_metrics.json`。
- 报告必须包含 `provider_requested`、`provider_effective`、`model_requested`、`model_effective`、`real_provider_call`、`evaluated_at` 和 per-case result。
- 只有 `provider_effective=deepseek` 且 `real_provider_call=true` 的报告，才能被 Real Evidence Benchmark 计为真实 LLM 证据。
- `unsafe_auto_fix_rate > 0` 或 `hard_constraint_violation_rate > 0` 是 blocking finding，不能包装成“总体可接受”。
- 缺少 `DEEPSEEK_API_KEY`、网络不可用或 provider fallback，必须计为 environment gap。

## Consequences

- 正向：简历可写“使用真实 DeepSeek 对 Agent 安全红线做离线评测”，但前提是报告确实存在且 metadata 可信。
- 正向：fake baseline 与 real-provider evidence 不会混淆。
- 负向：如果 DeepSeek 输出波动，单次 run 只能作为诊断证据，不能代表生产长期稳定性。
- 负向：真实 API 调用会产生费用和网络依赖，需要在 Report Back 中明确是否运行、运行命令和结果。
