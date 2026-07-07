# ADR-RQT.3: Real LLM Agent evaluation is opt-in diagnostic evidence, not the default gate

**Slug**: `real-llm-agent-eval-opt-in-diagnostic`
**Status**: accepted
**Date**: 2026-07-07

## Context

Current Agent Eval is strong for deterministic local regression:

- `FakeLLMProvider` is network-free.
- Safety gates are deterministic.
- Stage Eval Optimize fixed the fake provider high-risk duplicate-booking semantics.

But fake-provider metrics cannot prove real DeepSeek behavior. `scripts/eval_agent.py` already supports `--provider deepseek` and protects fake baseline paths by writing DeepSeek output to separate report paths when defaults are used. There is also a live smoke test guarded by `@pytest.mark.live`.

The gap is not "can the project call DeepSeek at all"; the gap is whether real-provider eval results are reported clearly enough for triage and not confused with fake baseline quality.

## Options Considered

- Option A: Make DeepSeek evaluation part of default DoD.
  - Pros: Ensures real-provider coverage when credentials exist.
  - Cons: Breaks offline development and CI; depends on network, API key, provider availability, and model behavior.
- Option B: Keep only the existing live smoke test.
  - Pros: Minimal and safe.
  - Cons: A JSON smoke response does not evaluate business decision quality, evidence behavior, or safety gates.
- Option C: Keep fake Agent Eval as the default gate and add opt-in real-provider diagnostic reporting.
  - Pros: Preserves deterministic CI while making real LLM behavior visible when credentials are available.
  - Cons: Real-provider diagnosis may be skipped in local environments without `DEEPSEEK_API_KEY`.

## Decision

Choose Option C.

The real Agent triage contract should:

- Preserve fake-provider Agent Eval as the default DoD and baseline.
- Run real-provider Agent Eval only when explicitly requested and credentials are configured.
- Write real-provider output to provider-specific report paths, never overwriting fake baseline reports.
- Record `provider_requested`, `provider_effective`, `model_requested`, `model_effective`, `real_provider_call`, and per-case results.
- Treat provider unavailability as `not_run` in the triage summary, not as a fake pass.
- Keep safety redlines visible: unsafe auto-fix and hard-constraint violation must remain explicit even for diagnostic runs.

This stage may improve report structure and diagnostics, but should not tune prompts or change expected labels based only on one real-provider run.

## Consequences

- Positive: Real LLM quality becomes inspectable without compromising the deterministic test suite.
- Positive: Fake and real-provider claims remain separated in reports.
- Negative: Real LLM output may be non-deterministic, so triage must avoid overclaiming from a tiny sample.
- Negative: A missing API key may leave this part of the stage as an explicit environment gap.
- Constraint: If an evidence-bearing real-provider case falls back or produces no fresh LLM result, the report must mark that run as untrusted / unavailable rather than counting it as quality evidence.
