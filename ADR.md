# Stage Real Quality Triage — Architectural Decisions

## Assumptions

- Current branch is `stage-real-quality-triage`; it is not `main`.
- `origin/main` already contains Stage Eval Optimize (`Stage eval optimize (#15)`).
- Existing root `spec.md`, `tasks.md`, and `PR.md` are gitignored leftovers from Stage Eval Optimize and must not be treated as current-stage planning files.
- This stage is driven by the honest gaps recorded in `reports/eval_harness/comparison.md`: real LLM quality, real embedding quality, online adoption, latency, and cost are not yet measured.
- The first current-stage deliverable is this ADR scratchpad. `spec.md` and `tasks.md` must be generated only after these decisions are reviewed.

## ADR-RQT.1: Real quality triage before optimization or runtime default changes

**Slug**: `real-quality-triage-before-optimization`
**Status**: accepted
**Date**: 2026-07-07

### Context

The previous stage produced a clean offline comparison:

- System Eval gates stayed passing.
- RAG improved under `embedding_backend=hash` when using `hybrid_rerank`.
- Agent Eval reached `risk_accuracy=1.0` under `FakeLLMProvider`.

However, the same reports explicitly keep several gaps honest: real DeepSeek quality is not measured, real embedding quality is not part of the combined harness, online human adoption is not measured, and production latency/cost are not measured. Moving directly from fake/hash improvements to production defaults would overstate what the system has proven.

This stage should therefore answer: "Which quality claims are supported by real evidence, which are still fake/hash-only, and what should be optimized next?"

### Options Considered

- Option A: Immediately optimize prompts, retrieval defaults, and production runtime behavior.
  - Pros: May improve visible metrics quickly.
  - Cons: Risks blind tuning without knowing whether the issue comes from real LLM behavior, embedding backend, retrieval mode, or evaluation coverage.
- Option B: Add online adoption, latency, and cost instrumentation first.
  - Pros: Addresses production-readiness gaps.
  - Cons: Requires runtime/schema/API work and still does not answer real model quality for current eval cases.
- Option C: Build a narrow real-quality triage stage before optimization.
  - Pros: Converts known honest gaps into explicit measured / not-run / not-measured findings; preserves the evaluation-driven workflow established by ADR-EH.5 and ADR-EO.1.
  - Cons: This stage may mostly produce reports and diagnosis rather than user-visible product behavior.

### Decision

Choose Option C.

This stage will focus on diagnostic evidence and scope control:

- Keep default CI and default DoD network-free.
- Keep production runtime defaults unchanged unless a later ADR explicitly changes them.
- Measure real RAG quality through opt-in real embedding paths where available.
- Measure real LLM Agent quality through opt-in DeepSeek paths where credentials are available.
- Produce a triage summary that separates measured evidence from environment gaps and deferred online metrics.

### Consequences

- Positive: The project can explain exactly which quality claims are fake/hash-only and which are real-provider or real-embedding backed.
- Positive: Later optimization tasks can be selected from observed misses instead of speculative tuning.
- Negative: The stage will not by itself solve online adoption, latency, or cost gaps.
- Negative: Real-provider and real-embedding evidence may be incomplete on machines without API keys or local model cache.
- Constraint: No report may claim real DeepSeek or real embedding quality unless the corresponding run produced `real_provider_call=true` or an effective non-hash embedding backend in metadata.

## ADR-RQT.2: RAG quality matrix separates CI hash baseline from opt-in real embeddings

**Slug**: `rag-quality-matrix-real-embedding-opt-in`
**Status**: accepted
**Date**: 2026-07-07

### Context

Historical ADRs already define the embedding boundary:

- ADR-083 accepts local real embeddings over hash for semantic quality.
- ADR-088 keeps CI/default tests on hash and makes real embeddings opt-in.
- ADR-089 requires effective backend metadata after fallback.
- ADR-EO.2 keeps mode comparison evidence-driven and forbids hash-specific overfitting.

Current reports cover two partial views:

- `reports/rag_eval_real_vs_hash.md` compares hash, `bge_m3`, and `bge_small` on dense retrieval.
- `reports/rag_eval_mode_comparison.md` compares `dense`, `hybrid`, and `hybrid_rerank` on hash.

The missing view is a backend-by-mode matrix: whether real embeddings plus hybrid/rerank behave better, worse, or differently than hash plus hybrid/rerank.

### Options Considered

- Option A: Switch the combined harness and production default to real embeddings now.
  - Pros: Aligns with semantic retrieval goals.
  - Cons: Violates ADR-088's CI boundary and risks hidden model download/cache dependency in default workflows.
- Option B: Keep only the hash mode comparison from the previous stage.
  - Pros: Simple and deterministic.
  - Cons: Leaves real embedding quality as an old standalone report, not comparable to the selected retrieval mode.
- Option C: Add an opt-in RAG quality matrix across available backends and retrieval modes.
  - Pros: Preserves default hash CI while generating real-embedding evidence when the environment supports it; allows case-level miss analysis before changing defaults.
  - Cons: Matrix generation can be slow and may produce skipped/unavailable rows when models are not cached.

### Decision

Choose Option C.

The RAG triage contract should produce Markdown and JSON reports that include:

- Backend rows for `hash`, `bge_small`, and `bge_m3`.
- Mode columns for `dense`, `hybrid`, and `hybrid_rerank`.
- Effective backend metadata for each run, so fallback to hash is visible.
- Metrics: `hit_at_1`, `recall_at_5`, `mrr`, and `ndcg_at_5`.
- Case-level miss buckets by scenario and error type for the best available real backend/mode.
- Explicit `not_run` / `unavailable` status when dependencies or local model cache are missing.

This report is diagnostic only. It must not silently change production RAG defaults or the default combined harness.

### Consequences

- Positive: The project can compare hash-mode gains against real semantic retrieval instead of treating them as interchangeable.
- Positive: Miss buckets can drive the next optimization stage without relabeling or query tuning during this stage.
- Negative: Running the full matrix may be expensive on CPU, especially for `bge_m3`.
- Negative: If real embeddings are unavailable locally, the stage may only prove that the environment gap still exists.
- Constraint: Eval scripts must keep `min_score=0.0` for ranking-quality measurement, consistent with ADR-086's clarification.

## ADR-RQT.3: Real LLM Agent evaluation is opt-in diagnostic evidence, not the default gate

**Slug**: `real-llm-agent-eval-opt-in-diagnostic`
**Status**: accepted
**Date**: 2026-07-07

### Context

Current Agent Eval is strong for deterministic local regression:

- `FakeLLMProvider` is network-free.
- Safety gates are deterministic.
- Stage Eval Optimize fixed the fake provider high-risk duplicate-booking semantics.

But fake-provider metrics cannot prove real DeepSeek behavior. `scripts/eval_agent.py` already supports `--provider deepseek` and protects fake baseline paths by writing DeepSeek output to separate report paths when defaults are used. There is also a live smoke test guarded by `@pytest.mark.live`.

The gap is not "can the project call DeepSeek at all"; the gap is whether real-provider eval results are reported clearly enough for triage and not confused with fake baseline quality.

### Options Considered

- Option A: Make DeepSeek evaluation part of default DoD.
  - Pros: Ensures real-provider coverage when credentials exist.
  - Cons: Breaks offline development and CI; depends on network, API key, provider availability, and model behavior.
- Option B: Keep only the existing live smoke test.
  - Pros: Minimal and safe.
  - Cons: A JSON smoke response does not evaluate business decision quality, evidence behavior, or safety gates.
- Option C: Keep fake Agent Eval as the default gate and add opt-in real-provider diagnostic reporting.
  - Pros: Preserves deterministic CI while making real LLM behavior visible when credentials are available.
  - Cons: Real-provider diagnosis may be skipped in local environments without `DEEPSEEK_API_KEY`.

### Decision

Choose Option C.

The real Agent triage contract should:

- Preserve fake-provider Agent Eval as the default DoD and baseline.
- Run real-provider Agent Eval only when explicitly requested and credentials are configured.
- Write real-provider output to provider-specific report paths, never overwriting fake baseline reports.
- Record `provider_requested`, `provider_effective`, `model_requested`, `model_effective`, `real_provider_call`, and per-case results.
- Treat provider unavailability as `not_run` in the triage summary, not as a fake pass.
- Keep safety redlines visible: unsafe auto-fix and hard-constraint violation must remain explicit even for diagnostic runs.

This stage may improve report structure and diagnostics, but should not tune prompts or change expected labels based only on one real-provider run.

### Consequences

- Positive: Real LLM quality becomes inspectable without compromising the deterministic test suite.
- Positive: Fake and real-provider claims remain separated in reports.
- Negative: Real LLM output may be non-deterministic, so triage must avoid overclaiming from a tiny sample.
- Negative: A missing API key may leave this part of the stage as an explicit environment gap.
- Constraint: If an evidence-bearing real-provider case falls back or produces no fresh LLM result, the report must mark that run as untrusted / unavailable rather than counting it as quality evidence.

## ADR-RQT.4: Triage summary uses finding taxonomy instead of immediate remediation tasks

**Slug**: `triage-summary-finding-taxonomy`
**Status**: accepted
**Date**: 2026-07-07

### Context

The project now has several evaluation reports, but they answer different questions and use different runtime assumptions. Without a stage-level triage summary, a reviewer can easily confuse:

- default fake/hash regression gates,
- opt-in real embedding reports,
- opt-in real LLM reports,
- online metrics that are not implemented yet.

The next stage should leave a clear artifact that says what is actually known, what was not runnable, what failed, and what should be optimized later.

### Options Considered

- Option A: Produce only raw RAG and Agent reports.
  - Pros: Less code and less documentation.
  - Cons: Reviewers still need to manually infer what matters and which gaps remain.
- Option B: Convert every observed miss into an immediate code fix in the same stage.
  - Pros: Potentially improves numbers quickly.
  - Cons: Mixes diagnosis and remediation; risks overfitting before the root cause is categorized.
- Option C: Produce a structured triage summary and defer remediation to a later stage.
  - Pros: Keeps this stage narrow; makes next-stage planning evidence-based.
  - Cons: Requires one extra artifact and may feel less satisfying because it intentionally defers fixes.

### Decision

Choose Option C.

The stage summary should classify findings into:

- `measured_pass`: measured and acceptable under the stated environment.
- `measured_gap`: measured and below expectation, with case IDs or metric deltas.
- `environment_gap`: not runnable because credentials, model cache, optional dependency, or local resource is missing.
- `deferred_online_metric`: requires online runtime instrumentation or human-review workflow data outside this stage.
- `out_of_scope`: known gap deliberately not handled in this stage.

The summary should point to source reports and recommend, but not implement, the next optimization targets.

### Consequences

- Positive: Review and interview narrative can distinguish "not measured" from "measured and failed."
- Positive: Next stage can choose tasks from concrete findings instead of speculative backlog.
- Negative: This adds reporting work that does not directly change runtime behavior.
- Negative: Some users may expect immediate fixes; the stage must explain why diagnosis comes first.
- Constraint: Any update to `docs/interview/` must be based on real observed findings and remain gitignored.
