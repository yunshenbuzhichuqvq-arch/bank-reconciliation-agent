from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import hashlib
import subprocess
import platform
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

RUNS = 5
DEFAULT_RUNS = RUNS


def _measure_ms(fn) -> float:
    started = time.perf_counter()
    fn()
    return (time.perf_counter() - started) * 1000


def _average(samples: list[float]) -> float:
    return statistics.mean(samples) if samples else 0.0


def _median(samples: list[float]) -> float:
    return statistics.median(samples) if samples else 0.0


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    sorted_samples = sorted(samples)
    idx = int(len(sorted_samples) * 0.95)
    idx = max(0, min(idx, len(sorted_samples) - 1))
    return sorted_samples[idx]


def _minmax(samples: list[float]) -> tuple[float, float]:
    if not samples:
        return (0.0, 0.0)
    return (min(samples), max(samples))


def _latency_stats(samples: list[float]) -> dict[str, Any]:
    s_min, s_max = _minmax(samples)
    return {
        "avg_latency_ms": round(_average(samples), 3),
        "p50_latency_ms": round(_median(samples), 3),
        "p95_latency_ms": round(_p95(samples), 3),
        "min_latency_ms": round(s_min, 3),
        "max_latency_ms": round(s_max, 3),
        "samples_ms": [round(s, 3) for s in samples],
    }


def _stage31_retrieval_mode(settings: Any) -> str:
    if settings.enable_rag_hybrid and settings.enable_rag_reranker:
        return "hybrid_rerank"
    if settings.enable_rag_hybrid:
        return "hybrid"
    return "dense"


def _stage31_canonical_input() -> dict[str, Any]:
    return {
        "version": "stage31-be-r004-v1",
        "scenario_type": "BANK_ENTERPRISE",
        "exception_branch": "BE-R004",
        "error_type": "NARRATIVE_NAME_MISMATCH",
        "source_a_item": {
            "summary": "冲正退款备注待核验",
            "remark": "原流水疑似冲正，需要抽取原始流水号",
            "amount": "100.00",
        },
        "source_b_item": {
            "summary": "REVERSAL",
            "remark": "remark",
        },
        "math_result": {
            "bank_amount": "100.00",
            "clear_amount": "100.00",
            "amount_diff": "0.00",
        },
    }


def _stage31_provider_identity(provider: Any) -> tuple[str, str | None]:
    provider_type = type(provider)
    if (
        provider_type.__module__ == "bank_reconciliation_agent.core.llm.provider"
        and provider_type.__name__ == "DeepSeekProvider"
    ):
        return "deepseek", getattr(provider, "model", None)
    if (
        provider_type.__module__ == "bank_reconciliation_agent.core.llm.provider"
        and provider_type.__name__ == "FakeLLMProvider"
    ):
        return "fake", "fake-llm"
    return "stub", getattr(provider, "model", None)


def _stage31_bench_authorized(
    context: Any,
    *,
    expected_task_id: str | None,
    expected_flow_id: str | None,
) -> bool:
    return bool(
        expected_task_id
        and expected_flow_id
        and getattr(context, "user_id", None) == "bench_user"
        and getattr(context, "task_id", None) == expected_task_id
        and getattr(context, "flow_id", None) == expected_flow_id
        and getattr(context, "scenario_type", None) == "BANK_ENTERPRISE"
        and getattr(context, "exception_branch", None) == "BE-R004"
    )


def _cpu_identity() -> str | None:
    cpu = platform.processor()
    if not cpu or cpu.strip() == "":
        return None
    cpu = cpu.strip()
    for marker in ("/", "\\", "@"):
        if marker in cpu:
            return None
    if len(cpu) > 128:
        return None
    return cpu


def get_git_revision() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT))
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def run_benchmark(
    *,
    runs: int = 5,
    provider_name: str = "fake",
    model: str = "deepseek-v4-flash",
) -> dict[str, Any]:
    from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent
    from bank_reconciliation_agent.core.config import settings
    from bank_reconciliation_agent.core.llm.cost import (
        DEEPSEEK_V4_PRO_INPUT_CACHE_MISS_USD_PER_1M,
        DEEPSEEK_V4_PRO_OUTPUT_USD_PER_1M,
        compute_cost,
    )
    from bank_reconciliation_agent.core.llm.provider import (
        DeepSeekProvider,
        FakeLLMProvider,
        LLMUnavailable,
    )
    from bank_reconciliation_agent.rag.retriever import rule_retriever
    from bank_reconciliation_agent.schemas.rag import RagSearchRequest

    provider_requested = provider_name
    model_requested = model

    if provider_name == "fake":
        provider = FakeLLMProvider()
        provider_effective = "fake"
        model_effective = "fake-llm"
    elif provider_name == "deepseek":
        api_key = settings.deepseek_api_key
        if not api_key:
            raise LLMUnavailable(
                "DEEPSEEK_API_KEY is not configured. "
                "Set the environment variable or use --provider fake."
            )
        provider = DeepSeekProvider(api_key=api_key, model=model)
        provider_effective = "deepseek"
        model_effective = model
    else:
        raise ValueError(f"Unsupported provider: {provider_name}. Use 'fake' or 'deepseek'.")

    extraction_agent = ExtractionAgent(provider=provider)
    extraction_samples: list[float] = []
    rag_samples: list[float] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    rag_request = RagSearchRequest(
        query="银行企业对账 冲正 摘要不一致 规则",
        top_k=3,
        scenario_type="BANK_ENTERPRISE",
    )

    for _ in range(runs):
        extraction_ms = _measure_ms(
            lambda: extraction_agent.extract(
                flow_id="FLOW-BENCH-001",
                summary="冲正退款备注待核验",
                remark="原流水疑似冲正，需要抽取原始流水号",
            )
        )
        extraction_samples.append(extraction_ms)

        if provider_name == "deepseek":
            llm_result = extraction_agent.last_llm_result
            if llm_result is not None:
                total_prompt_tokens += llm_result.prompt_tokens
                total_completion_tokens += llm_result.completion_tokens

        rag_ms = _measure_ms(lambda: rule_retriever.search(rag_request))
        rag_samples.append(rag_ms)

    is_real_provider = provider_effective != "fake"
    token_usage_available = is_real_provider and total_prompt_tokens > 0

    cost_available = False
    estimated_cost_usd: str | None = None
    per_case_estimated_cost_usd: str | None = None
    cost_unavailable_reason: str | None = None
    cost_assumptions: str = "fake provider; no real LLM cost"
    token_unavailable_reason: str | None = None

    if token_usage_available:
        cost_value = compute_cost(total_prompt_tokens, total_completion_tokens)
        estimated_cost_usd = str(cost_value)
        per_case_estimated_cost_usd = str(cost_value / Decimal(runs))
        cost_available = True
        cost_assumptions = (
            f"DeepSeek v4 Pro pricing: "
            f"input ${DEEPSEEK_V4_PRO_INPUT_CACHE_MISS_USD_PER_1M}/1M, "
            f"output ${DEEPSEEK_V4_PRO_OUTPUT_USD_PER_1M}/1M"
        )
    elif is_real_provider and not token_usage_available:
        cost_assumptions = (
            "real provider but no token usage data available; cost cannot be estimated"
        )
        token_unavailable_reason = "token_usage_unavailable"
        cost_unavailable_reason = "token_usage_unavailable"

    status = "measured"
    environment_gap: dict[str, str] | None = None
    trust_reasons: list[str] = []

    if is_real_provider:
        if token_usage_available:
            trust = {
                "trusted": True,
                "real_provider_evidence": True,
                "cost_evidence_available": True,
                "reasons": trust_reasons,
            }
        else:
            status = "environment_gap"
            environment_gap = {
                "reason": "token_usage_unavailable",
                "message": "DeepSeek provider returned no token usage metadata; "
                "cost cannot be estimated from provider response.",
            }
            trust = {
                "trusted": False,
                "real_provider_evidence": True,
                "cost_evidence_available": False,
                "reasons": ["token_usage_unavailable"],
            }
    else:
        trust = {
            "trusted": False,
            "real_provider_evidence": False,
            "cost_evidence_available": False,
            "reasons": ["fake_provider"],
        }

    extraction_latency = _latency_stats(extraction_samples)
    rag_latency = _latency_stats(rag_samples)

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": status,
        "run_count": runs,
        "provider_requested": provider_requested,
        "provider_effective": provider_effective,
        "model_requested": model_requested,
        "model_effective": model_effective,
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": extraction_latency,
            "rag_search": rag_latency,
        },
        "tokens": {
            "token_usage_available": token_usage_available,
            "input_tokens": total_prompt_tokens if token_usage_available else None,
            "output_tokens": total_completion_tokens if token_usage_available else None,
            "total_tokens": (total_prompt_tokens + total_completion_tokens)
            if token_usage_available
            else None,
            "unavailable_reason": token_unavailable_reason,
        },
        "cost": {
            "cost_available": cost_available,
            "estimated_cost_usd": estimated_cost_usd,
            "per_case_estimated_cost_usd": per_case_estimated_cost_usd,
            "assumptions": cost_assumptions,
            "unavailable_reason": cost_unavailable_reason,
        },
        "trust": trust,
        "environment_gap": environment_gap,
    }


def run_stage31_critical_path(
    *,
    provider_name: str,
    model: str,
    embedding_backend: str,
    cold_runs: int,
    warmup_runs: int,
    runs: int,
    artifact_role: str = "baseline",
) -> dict[str, Any]:
    from bank_reconciliation_agent.core.config import settings
    from bank_reconciliation_agent.core.llm.cost import compute_cost
    from bank_reconciliation_agent.services.workflow import run_item
    from bank_reconciliation_agent.services.trace import TraceRecorder, validate_trace_snapshot
    from bank_reconciliation_agent.core.llm.provider import (
        DeepSeekProvider,
        FakeLLMProvider,
    )
    from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent
    from bank_reconciliation_agent.agents.audit_agent import AuditAgent
    from bank_reconciliation_agent.agents.trace_agent import TraceAgent
    from bank_reconciliation_agent.services.tool_adapters import build_default_registry
    from bank_reconciliation_agent.services.tool_executor import ToolExecutor
    from bank_reconciliation_agent.rag.retriever import rule_retriever

    env_gap = None
    trust_reasons = []
    token_usage_unavailable = False
    effective_provider = None
    effective_model = None

    # -- Resolve provider --------------------------------------------------

    requested_provider = provider_name
    requested_model = model

    if provider_name == "deepseek":
        api_key = settings.deepseek_api_key
        if not api_key:
            env_gap = {
                "reason": "missing_deepseek_api_key",
                "message": "DEEPSEEK_API_KEY is not configured.",
            }
        else:
            llm_provider = DeepSeekProvider(
                api_key=api_key,
                model=model,
                base_url=settings.deepseek_base_url,
                timeout=settings.llm_timeout_seconds,
            )
    elif provider_name == "fake":
        llm_provider = FakeLLMProvider()
    else:
        raise ValueError(f"Unsupported provider: {provider_name}. Use 'fake' or 'deepseek'.")

    if not env_gap:
        effective_provider, effective_model = _stage31_provider_identity(llm_provider)

    if not env_gap:
        extraction_agent = ExtractionAgent(provider=llm_provider)
        audit_agent = AuditAgent(provider=llm_provider)
        trace_agent = TraceAgent(provider=llm_provider)

    # -- Resolve embedding backend -----------------------------------------

    requested_backend = embedding_backend
    effective_backend = getattr(rule_retriever.store, "embedding_backend", "unknown")

    effective_retrieval_mode = _stage31_retrieval_mode(settings)

    if requested_backend != effective_backend and not env_gap and effective_provider != "fake":
        env_gap = {
            "reason": "embedding_backend_mismatch",
            "message": (
                f"Requested embedding backend '{requested_backend}' but effective "
                f"backend is '{effective_backend}'. The retriever may have fallen back "
                f"to a different backend."
            ),
        }

    # -- Validate provider identity ----------------------------------------

    if not env_gap and effective_provider != "fake":
        provider_mismatch = effective_provider != requested_provider
        model_mismatch = effective_model != requested_model
        if provider_mismatch or model_mismatch:
            env_gap = {
                "reason": "provider_identity_mismatch",
                "message": (
                    f"Requested provider '{requested_provider}' model "
                    f"'{requested_model}' but effective provider "
                    f"'{effective_provider}' model '{effective_model}'."
                ),
            }

    # -- Bench authorizer --------------------------------------------------

    authorized_context: dict[str, str | None] = {"task_id": None, "flow_id": None}

    def _bench_authorizer(ctx):
        return _stage31_bench_authorized(
            ctx,
            expected_task_id=authorized_context["task_id"],
            expected_flow_id=authorized_context["flow_id"],
        )

    bench_tool_executor = ToolExecutor(
        build_default_registry(),
        _bench_authorizer,
    )

    # -- Canonical input hash ----------------------------------------------

    canonical_input = _stage31_canonical_input()
    input_sha256 = hashlib.sha256(json.dumps(canonical_input, sort_keys=True).encode()).hexdigest()

    # -- Validate CPU identity --------------------------------------------

    cpu = _cpu_identity()
    if cpu is None and not env_gap:
        env_gap = {
            "reason": "cpu_identity_unavailable",
            "message": "Could not determine CPU identity from host platform.",
        }

    # -- Run plan gate -----------------------------------------------------

    if cold_runs < 1 or warmup_runs < 1 or runs < 20:
        if not env_gap:
            env_gap = {
                "reason": "insufficient_run_plan",
                "message": (
                    f"cold_runs={cold_runs} (min 1), warmup_runs={warmup_runs} "
                    f"(min 1), measured_runs={runs} (min 20). "
                ),
            }

    # -- Run samples -------------------------------------------------------

    cold_observations = []
    warm_e2e = []
    warm_extraction = []
    warm_rag = []
    predicted_parallel_e2e = []

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_agent_calls = 0
    total_tool_calls = 0
    total_transport_attempts = 0
    success_count = 0
    failure_count = 0

    trace_completeness = []
    contract_observations = []
    error_distribution: dict[str, int] = {}

    if not env_gap:
        base_time = int(time.time())
        total_runs_count = cold_runs + warmup_runs + runs

        for i in range(total_runs_count):
            is_cold = i < cold_runs
            is_measured = i >= cold_runs + warmup_runs
            flow_id = f"FLOW-BENCH-{base_time}-{i:03d}"
            task_id = f"task-{base_time}-{i:03d}"
            authorized_context.update(task_id=task_id, flow_id=flow_id)

            recorder = TraceRecorder(
                user_id="bench_user",
                task_id=task_id,
                flow_id=flow_id,
            )

            state = {
                "task_id": task_id,
                "user_id": "bench_user",
                "thread_id": "thread-bench",
                "scenario_type": "BANK_ENTERPRISE",
                "current_queue_id": 12345,
                "source_a_item": {
                    "flow_id": flow_id,
                    **canonical_input["source_a_item"],
                },
                "source_b_item": {
                    "flow_id": flow_id,
                    **canonical_input["source_b_item"],
                },
                "error_type": canonical_input["error_type"],
                "exception_branch": canonical_input["exception_branch"],
                "math_result": dict(canonical_input["math_result"]),
                "extraction_result": {},
                "rag_context": [],
                "audit_decision": {},
                "confidence": None,
                "retry_count": 0,
                "fallback_level": 0,
                "next_action": "",
                "error_message": None,
                "agent_logs": [],
                "recorder": recorder,
            }

            started = time.perf_counter()
            final_state = run_item(
                state,
                extraction_agent=extraction_agent,
                audit_agent=audit_agent,
                trace_agent=trace_agent,
                tool_executor=bench_tool_executor,
            )

            recorder.close_root(
                status="SUCCEEDED",
                outcome=final_state.get("next_action") or "PENDING_HUMAN",
            )
            spans = recorder.snapshot()
            validate_trace_snapshot(spans)
            e2e_ms = (time.perf_counter() - started) * 1000

            root_spans = [s for s in spans if s.span_type == "WORKFLOW" and not s.parent_span_id]
            ext_spans = [s for s in spans if s.span_type == "AGENT" and s.name == "ExtractionAgent"]
            rag_spans = [s for s in spans if s.span_type == "TOOL" and s.name == "search_rules"]

            is_complete = False
            trace_failure_reason = "unknown"

            terminal_spans = [
                s
                for s in spans
                if s.span_type in ("FINAL", "FALLBACK") and s.parent_span_id is not None
            ]

            if len(root_spans) != 1:
                trace_failure_reason = "missing_or_duplicate_root"
            elif len(terminal_spans) != 1:
                trace_failure_reason = "missing_or_duplicate_terminal"
            elif len(ext_spans) != 1:
                trace_failure_reason = "missing_or_duplicate_extraction"
            elif len(rag_spans) != 1:
                trace_failure_reason = "missing_or_duplicate_rag"
            else:
                root = root_spans[0]
                terminal = terminal_spans[0]
                ext = ext_spans[0]
                rag = rag_spans[0]

                expected_identity = (root.trace_id, "bench_user", task_id, flow_id)
                if any(
                    (s.trace_id, s.user_id, s.task_id, s.flow_id) != expected_identity
                    for s in spans
                ):
                    trace_failure_reason = "identity_mismatch"
                elif any(
                    s.duration_ms < 0 or s.ended_at < s.started_at
                    for s in (root, terminal, ext, rag)
                ):
                    trace_failure_reason = "invalid_time_or_duration"
                elif any(s.parent_span_id != root.span_id for s in (terminal, ext, rag)):
                    trace_failure_reason = "invalid_required_parent"
                elif (
                    root.status != "SUCCEEDED"
                    or terminal.status != "SUCCEEDED"
                    or ext.status != "SUCCEEDED"
                    or rag.status != "SUCCEEDED"
                ):
                    trace_failure_reason = "non_succeeded_status"
                elif any(
                    s.status != "SUCCEEDED" for s in spans if s.span_type in ("AGENT", "TOOL")
                ):
                    trace_failure_reason = "flow_call_failed"
                elif effective_provider == "fake":
                    trace_failure_reason = "fake_provider"
                else:
                    is_complete = True

            if is_complete:
                agent_spans = [s for s in spans if s.span_type == "AGENT"]
                if effective_provider != "fake" and any(
                    s.model_name != effective_model
                    or s.prompt_tokens is None
                    or s.prompt_tokens <= 0
                    or s.completion_tokens is None
                    or s.completion_tokens < 0
                    or s.attempt < 1
                    for s in agent_spans
                ):
                    token_usage_unavailable = True

            ext_dur = ext_spans[0].duration_ms if ext_spans else 0
            rag_dur = rag_spans[0].duration_ms if rag_spans else 0
            pred_parallel = e2e_ms - ext_dur - rag_dur + max(ext_dur, rag_dur)

            if is_measured:
                if is_complete:
                    success_count += 1
                    # Count all AGENT spans for full-flow token accounting
                    agent_spans = [s for s in spans if s.span_type == "AGENT"]
                    total_agent_calls += len(agent_spans)
                    for ag in agent_spans:
                        if ag.prompt_tokens:
                            total_prompt_tokens += ag.prompt_tokens
                        if ag.completion_tokens:
                            total_completion_tokens += ag.completion_tokens

                    tool_spans = [s for s in spans if s.span_type == "TOOL"]
                    total_tool_calls += len(tool_spans)
                    total_transport_attempts += sum((s.attempt or 0) for s in agent_spans)
                else:
                    failure_count += 1
                    error_distribution[trace_failure_reason] = (
                        error_distribution.get(trace_failure_reason, 0) + 1
                    )

                trace_completeness.append(
                    {
                        "trace_id": root_spans[0].trace_id if root_spans else "unknown",
                        "is_complete": is_complete,
                        "failure_reason": trace_failure_reason if not is_complete else None,
                        "root_span": len(root_spans),
                        "terminal_span": len(terminal_spans),
                        "ext_spans": len(ext_spans),
                        "rag_spans": len(rag_spans),
                        "agent_count": len([s for s in spans if s.span_type == "AGENT"]),
                        "tool_count": len([s for s in spans if s.span_type == "TOOL"]),
                    }
                )

                audit_decision = final_state.get("audit_decision")
                business_decision = (
                    audit_decision.get("decision") if isinstance(audit_decision, dict) else None
                )
                contract_observations.append(
                    {
                        "trace_id": root_spans[0].trace_id if root_spans else "unknown",
                        "business_decision": business_decision,
                        "next_action": final_state.get("next_action") or None,
                        "rag": {
                            "outcome": rag_spans[0].outcome if len(rag_spans) == 1 else None,
                            "result_count": (
                                rag_spans[0].result_count if len(rag_spans) == 1 else None
                            ),
                            "evidence_ids": (
                                sorted(rag_spans[0].evidence_ids) if len(rag_spans) == 1 else []
                            ),
                        },
                        "fallback": {
                            "level": final_state.get("fallback_level"),
                            "path": final_state.get("fallback_path"),
                            "terminal_type": (
                                str(terminal_spans[0].span_type)
                                if len(terminal_spans) == 1
                                else None
                            ),
                            "terminal_outcome": (
                                terminal_spans[0].outcome if len(terminal_spans) == 1 else None
                            ),
                        },
                        "trace_invariants_valid": is_complete,
                        "agent_calls": [s.name for s in spans if s.span_type == "AGENT"],
                        "tool_calls": [s.name for s in spans if s.span_type == "TOOL"],
                    }
                )

                warm_e2e.append(e2e_ms)
                warm_extraction.append(ext_dur)
                warm_rag.append(rag_dur)
                predicted_parallel_e2e.append(pred_parallel)
            elif is_cold:
                cold_observations.append(
                    {
                        "e2e_ms": round(e2e_ms, 3),
                        "extraction_ms": round(ext_dur, 3),
                        "rag_ms": round(rag_dur, 3),
                    }
                )

    complete_count = sum(1 for t in trace_completeness if t["is_complete"])

    if not env_gap and effective_provider != "fake" and token_usage_unavailable:
        env_gap = {
            "reason": "token_usage_unavailable",
            "message": "DeepSeek provider returned no token usage metadata.",
        }
        trust_reasons.append("token_usage_unavailable")

    if env_gap:
        trusted = False
    elif effective_provider == "fake":
        trusted = False
    elif complete_count != runs:
        trusted = False
        trust_reasons.append("incomplete_trace_samples")
    elif total_agent_calls < 2 * success_count:
        trusted = False
        trust_reasons.append("incomplete_agent_accounting")
    else:
        trusted = True

    actual_p95 = round(_p95(warm_e2e), 3)
    pred_p95 = round(_p95(predicted_parallel_e2e), 3)
    theory_pct = 0.0
    if actual_p95 > 0:
        theory_pct = round(((actual_p95 - pred_p95) / actual_p95) * 100, 3)

    # -- Independence gate -------------------------------------------------

    independence_findings = {
        "data_dependency": {
            "finding": "safe",
            "detail": (
                "RAG query is built from scenario_type, error_type, exception_branch, "
                "and amounts via _build_rag_query(); does not read extraction_result. "
                "Static code analysis confirms data independence."
            ),
            "source": "static_code_analysis",
        },
        "shared_state": {
            "finding": "unknown",
            "detail": (
                "In serial runtime there is no concurrent access. For a parallel "
                "candidate, this assessment is conditional on workers receiving "
                "read-only inputs and returning results without modifying shared "
                "ReconciliationState, Trace recorder, SSE emitter, or persistent state. "
                "This has NOT been verified in running code."
            ),
            "source": "static_analysis_unverified",
        },
        "failure_order": {
            "finding": "unsafe",
            "detail": (
                "In serial runtime, Extraction failure causes early return before RAG. "
                "In a parallel candidate, the failure of one side while the other is "
                "in-flight changes the current side-effect order. No candidate exists "
                "to prove fail-closed handling."
            ),
            "source": "static_analysis_unverified",
        },
        "cancellation": {
            "finding": "unbounded",
            "detail": (
                "Synchronous provider/retriever calls may not support hard interrupt. "
                "No candidate demonstrates bounded cancellation or proves that work has "
                "stopped before run_item returns."
            ),
            "source": "static_analysis_unverified",
        },
        "resource_reclamation": {
            "finding": "unknown",
            "detail": (
                "No candidate thread lifecycle exists, so resource reclamation and the "
                "absence of cross-flow background work are not yet proven."
            ),
            "source": "static_analysis_unverified",
        },
    }

    any_unsafe = any(
        f["finding"] in ("unknown", "unsafe", "unbounded") for f in independence_findings.values()
    )

    # -- Gate decision -----------------------------------------------------

    decision = "candidate_allowed"
    closed_reasons = []

    if env_gap:
        decision = "environment_gap"
        closed_reasons.append(env_gap.get("reason", "environment_gap"))
    else:
        if any_unsafe:
            decision = "no_go"
            closed_reasons.append("independence_gate_failed")
        if not trusted:
            decision = "no_go"
            closed_reasons.append("not_trusted")
        if complete_count < runs:
            decision = "no_go"
            closed_reasons.append(f"complete_count_{complete_count}_lt_{runs}")
        if theory_pct < 20.0:
            decision = "no_go"
            closed_reasons.append(f"theory_pct_{theory_pct}_lt_20.0")

    # -- Usage / cost ------------------------------------------------------

    token_usage_available = not token_usage_unavailable and total_prompt_tokens > 0
    cost_value = (
        compute_cost(total_prompt_tokens, total_completion_tokens)
        if token_usage_available
        else Decimal(0)
    )
    per_case_cost = cost_value / Decimal(success_count) if success_count else Decimal(0)

    # -- Report ------------------------------------------------------------

    report = {
        "schema_version": "1.0",
        "stage": "stage-31-trace-guided-performance",
        "artifact_role": artifact_role,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_revision": get_git_revision(),
        "input_sha256": input_sha256,
        "environment": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "cpu": cpu
            if not env_gap or env_gap.get("reason") != "cpu_identity_unavailable"
            else None,
            "python": platform.python_version(),
            "boundary": "offline benchmark; not production SLA",
        },
        "provider": {
            "requested_provider": requested_provider,
            "effective_provider": effective_provider
            if not env_gap or env_gap.get("reason") != "missing_deepseek_api_key"
            else None,
            "requested_model": requested_model,
            "effective_model": effective_model if effective_provider else None,
        },
        "rag": {
            "requested_embedding_backend": requested_backend,
            "effective_embedding_backend": effective_backend,
            "retrieval_mode": effective_retrieval_mode,
        },
        "run_plan": {
            "cold_runs": cold_runs,
            "warmup_runs": warmup_runs,
            "measured_runs": runs,
            "complete_measured_count": complete_count,
        },
        "trust": {
            "trusted": trusted,
            "reasons": trust_reasons,
            "environment_gap": env_gap,
        },
        "trace": {
            "completeness_numerator": complete_count,
            "completeness_denominator": runs,
            "completeness_rate": round(complete_count / runs, 3) if runs else 0,
            "samples": trace_completeness,
        },
        "contract_observations": contract_observations,
        "latency": {
            "cold_observations": cold_observations,
            "end_to_end": _latency_stats(warm_e2e),
            "extraction_agent": _latency_stats(warm_extraction),
            "rag_search": _latency_stats(warm_rag),
        },
        "theory": {
            "per_run_predicted_parallel_e2e_ms": [round(s, 3) for s in predicted_parallel_e2e],
            "actual_warm_p95_ms": actual_p95,
            "predicted_warm_p95_ms": pred_p95,
            "theoretical_p95_improvement_pct": theory_pct,
            "formula": (
                "actual_e2e_ms - extraction_duration_ms - rag_duration_ms "
                "+ max(extraction_duration_ms, rag_duration_ms)"
            ),
        },
        "independence": independence_findings,
        "usage": {
            "logical_agent_calls": total_agent_calls,
            "logical_tool_calls": total_tool_calls,
            "provider_transport_attempts": total_transport_attempts,
            "input_tokens": total_prompt_tokens if token_usage_available else None,
            "output_tokens": total_completion_tokens if token_usage_available else None,
            "total_tokens": (total_prompt_tokens + total_completion_tokens)
            if token_usage_available
            else None,
            "per_successful_run_tokens": (
                (total_prompt_tokens + total_completion_tokens) // success_count
            )
            if success_count and token_usage_available
            else None,
        },
        "cost": {
            "assumptions": (
                "DeepSeek v4 Pro pricing: input $0.89/1M, output $3.45/1M"
                if token_usage_available
                else "unavailable"
            ),
            "total_estimated_usd": str(cost_value) if token_usage_available else None,
            "per_successful_run_estimated_usd": (
                str(per_case_cost) if token_usage_available else None
            ),
            "unavailable_reason": (
                None
                if token_usage_available
                else ("token_usage_unavailable" if token_usage_unavailable else "fake_provider")
            ),
        },
        "reliability": {
            "success_count": success_count,
            "failure_count": failure_count,
            "error_rate": round(failure_count / runs, 3) if runs else 0,
            "error_distribution": error_distribution,
        },
        "decision": decision,
        "closed_reasons": closed_reasons,
    }
    validation_reasons = _stage31_artifact_validation_reasons(
        report,
        expected_role=artifact_role,
    )
    if validation_reasons:
        raise ValueError(f"invalid Stage 31 report: {','.join(validation_reasons)}")
    return report


def _stage31_artifact_validation_reasons(
    data: Any,
    *,
    expected_role: str,
) -> list[str]:
    prefix = expected_role
    if not isinstance(data, dict):
        return [f"{prefix}_artifact_not_object"]

    reasons: list[str] = []
    if data.get("schema_version") != "1.0":
        reasons.append(f"{prefix}_schema_version_invalid")
    if data.get("stage") != "stage-31-trace-guided-performance":
        reasons.append(f"{prefix}_stage_invalid")
    if data.get("artifact_role") != expected_role:
        reasons.append(f"{prefix}_role_invalid")
    if data.get("decision") not in {"candidate_allowed", "no_go", "environment_gap"}:
        reasons.append(f"{prefix}_decision_invalid")

    for key in (
        "environment",
        "provider",
        "rag",
        "run_plan",
        "trust",
        "trace",
        "latency",
        "theory",
        "independence",
        "usage",
        "cost",
        "reliability",
    ):
        if not isinstance(data.get(key), dict):
            reasons.append(f"{prefix}_{key}_invalid")

    if (
        not isinstance(data.get("git_revision"), str)
        or not data.get("git_revision")
        or data.get("git_revision") == "unknown"
    ):
        reasons.append(f"{prefix}_revision_invalid")
    input_sha256 = data.get("input_sha256")
    if not isinstance(input_sha256, str) or len(input_sha256) != 64:
        reasons.append(f"{prefix}_input_sha256_invalid")
    if not isinstance(data.get("closed_reasons"), list) or not all(
        isinstance(reason, str) for reason in data.get("closed_reasons", [])
    ):
        reasons.append(f"{prefix}_closed_reasons_invalid")

    plan = data.get("run_plan")
    trace = data.get("trace")
    reliability = data.get("reliability")
    if isinstance(plan, dict):
        run_values = [
            plan.get("cold_runs"),
            plan.get("warmup_runs"),
            plan.get("measured_runs"),
            plan.get("complete_measured_count"),
        ]
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in run_values
        ):
            reasons.append(f"{prefix}_run_plan_values_invalid")
        elif isinstance(trace, dict):
            if trace.get("completeness_numerator") != plan["complete_measured_count"]:
                reasons.append(f"{prefix}_trace_numerator_invalid")
            if trace.get("completeness_denominator") != plan["measured_runs"]:
                reasons.append(f"{prefix}_trace_denominator_invalid")
            samples = trace.get("samples")
            if not isinstance(samples, list) or (
                data.get("decision") != "environment_gap" and len(samples) != plan["measured_runs"]
            ):
                reasons.append(f"{prefix}_trace_samples_invalid")
        if isinstance(reliability, dict) and data.get("decision") != "environment_gap":
            success_count = reliability.get("success_count")
            failure_count = reliability.get("failure_count")
            if (
                not isinstance(success_count, int)
                or not isinstance(failure_count, int)
                or success_count + failure_count != plan.get("measured_runs")
            ):
                reasons.append(f"{prefix}_reliability_counts_invalid")

    trust = data.get("trust")
    if isinstance(trust, dict):
        if not isinstance(trust.get("trusted"), bool):
            reasons.append(f"{prefix}_trusted_flag_invalid")
        if not isinstance(trust.get("reasons"), list):
            reasons.append(f"{prefix}_trust_reasons_invalid")

    provider = data.get("provider")
    rag = data.get("rag")
    environment = data.get("environment")
    if isinstance(trust, dict) and trust.get("trusted") is True:
        identity_values = []
        if isinstance(provider, dict):
            identity_values.extend(
                provider.get(key)
                for key in (
                    "requested_provider",
                    "effective_provider",
                    "requested_model",
                    "effective_model",
                )
            )
        if isinstance(rag, dict):
            identity_values.extend(
                rag.get(key)
                for key in (
                    "requested_embedding_backend",
                    "effective_embedding_backend",
                    "retrieval_mode",
                )
            )
        if isinstance(environment, dict):
            identity_values.extend(
                environment.get(key) for key in ("os", "architecture", "python", "boundary")
            )
        if not identity_values or any(
            not isinstance(value, str) or not value for value in identity_values
        ):
            reasons.append(f"{prefix}_runtime_identity_invalid")

    independence = data.get("independence")
    required_independence = {
        "data_dependency",
        "shared_state",
        "failure_order",
        "cancellation",
        "resource_reclamation",
    }
    if isinstance(independence, dict):
        if set(independence) != required_independence:
            reasons.append(f"{prefix}_independence_keys_invalid")
        for finding in independence.values():
            if (
                not isinstance(finding, dict)
                or finding.get("finding")
                not in {"safe", "bounded", "unknown", "unsafe", "unbounded"}
                or not isinstance(finding.get("detail"), str)
                or not isinstance(finding.get("source"), str)
            ):
                reasons.append(f"{prefix}_independence_finding_invalid")
                break

    observations = data.get("contract_observations")
    measured_runs = plan.get("measured_runs") if isinstance(plan, dict) else None
    if not isinstance(observations, list) or (
        data.get("decision") != "environment_gap"
        and isinstance(measured_runs, int)
        and len(observations) != measured_runs
    ):
        reasons.append(f"{prefix}_contract_observations_invalid")
    elif isinstance(observations, list):
        for observation in observations:
            rag_observation = observation.get("rag") if isinstance(observation, dict) else None
            fallback_observation = (
                observation.get("fallback") if isinstance(observation, dict) else None
            )
            if (
                not isinstance(observation, dict)
                or not isinstance(observation.get("trace_id"), str)
                or not isinstance(rag_observation, dict)
                or rag_observation.get("outcome") not in {"RESULT", "EMPTY", None}
                or not (
                    isinstance(rag_observation.get("result_count"), int)
                    or rag_observation.get("result_count") is None
                )
                or not isinstance(rag_observation.get("evidence_ids"), list)
                or not all(
                    isinstance(evidence_id, str)
                    for evidence_id in rag_observation.get("evidence_ids", [])
                )
                or not isinstance(fallback_observation, dict)
                or fallback_observation.get("terminal_type") not in {"FINAL", "FALLBACK"}
                or fallback_observation.get("terminal_outcome")
                not in {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}
                or not isinstance(observation.get("trace_invariants_valid"), bool)
                or not isinstance(observation.get("agent_calls"), list)
                or not isinstance(observation.get("tool_calls"), list)
                or not all(isinstance(name, str) for name in observation.get("agent_calls", []))
                or not all(isinstance(name, str) for name in observation.get("tool_calls", []))
            ):
                reasons.append(f"{prefix}_contract_observation_shape_invalid")
                break
            if (
                isinstance(trust, dict)
                and trust.get("trusted") is True
                and (
                    not isinstance(observation.get("business_decision"), str)
                    or not isinstance(observation.get("next_action"), str)
                    or rag_observation.get("outcome") not in {"RESULT", "EMPTY"}
                    or not isinstance(rag_observation.get("result_count"), int)
                    or observation.get("trace_invariants_valid") is not True
                )
            ):
                reasons.append(f"{prefix}_contract_observation_incomplete")
                break

    usage = data.get("usage")
    cost = data.get("cost")
    if isinstance(trust, dict) and trust.get("trusted") is True:
        if isinstance(usage, dict) and any(
            not isinstance(usage.get(key), int) or isinstance(usage.get(key), bool)
            for key in (
                "logical_agent_calls",
                "logical_tool_calls",
                "provider_transport_attempts",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "per_successful_run_tokens",
            )
        ):
            reasons.append(f"{prefix}_usage_values_invalid")
        if isinstance(cost, dict):
            try:
                Decimal(cost["total_estimated_usd"])
                Decimal(cost["per_successful_run_estimated_usd"])
            except (KeyError, TypeError, ValueError):
                reasons.append(f"{prefix}_cost_values_invalid")

        latency = data.get("latency")
        end_to_end = latency.get("end_to_end") if isinstance(latency, dict) else None
        if not isinstance(end_to_end, dict) or not isinstance(
            end_to_end.get("p95_latency_ms"), (int, float)
        ):
            reasons.append(f"{prefix}_latency_values_invalid")
        if not isinstance(trace, dict) or trace.get("completeness_rate") != 1.0:
            reasons.append(f"{prefix}_trace_completeness_invalid")
        if not isinstance(reliability, dict) or (
            not isinstance(reliability.get("error_rate"), (int, float))
            or not isinstance(reliability.get("error_distribution"), dict)
        ):
            reasons.append(f"{prefix}_reliability_values_invalid")

    if data.get("decision") == "candidate_allowed":
        unsafe = isinstance(independence, dict) and any(
            finding.get("finding") in {"unknown", "unsafe", "unbounded"}
            for finding in independence.values()
            if isinstance(finding, dict)
        )
        theory_pct = (
            data.get("theory", {}).get("theoretical_p95_improvement_pct")
            if isinstance(data.get("theory"), dict)
            else None
        )
        if (
            not isinstance(trust, dict)
            or trust.get("trusted") is not True
            or unsafe
            or not isinstance(theory_pct, (int, float))
            or theory_pct < 20.0
        ):
            reasons.append(f"{prefix}_candidate_gate_inconsistent")

    return reasons


def _stage31_normalize_observations(observations: Any) -> list[dict[str, Any]] | None:
    if not isinstance(observations, list):
        return None
    normalized = []
    for observation in observations:
        if not isinstance(observation, dict):
            return None
        normalized.append({key: value for key, value in observation.items() if key != "trace_id"})
    return normalized


def run_stage31_comparison(
    baseline_path: Path | None,
    after_path: Path | None,
    focused_gates_passed: bool,
    stage_gates_passed: bool,
) -> dict[str, Any]:
    if baseline_path is None or after_path is None:
        raise ValueError("stage31-comparison requires --baseline-json and --after-json")
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    with open(after_path, "r", encoding="utf-8") as f:
        after = json.load(f)

    reasons = _stage31_artifact_validation_reasons(
        baseline, expected_role="baseline"
    ) + _stage31_artifact_validation_reasons(after, expected_role="after")

    b_plan = baseline.get("run_plan", {}) if isinstance(baseline, dict) else {}
    a_plan = after.get("run_plan", {}) if isinstance(after, dict) else {}
    b_trace = baseline.get("trace", {}) if isinstance(baseline, dict) else {}
    a_trace = after.get("trace", {}) if isinstance(after, dict) else {}
    b_prov = baseline.get("provider", {}) if isinstance(baseline, dict) else {}
    a_prov = after.get("provider", {}) if isinstance(after, dict) else {}
    b_rag = baseline.get("rag", {}) if isinstance(baseline, dict) else {}
    a_rag = after.get("rag", {}) if isinstance(after, dict) else {}
    b_env = baseline.get("environment", {}) if isinstance(baseline, dict) else {}
    a_env = after.get("environment", {}) if isinstance(after, dict) else {}
    b_usage = baseline.get("usage", {}) if isinstance(baseline, dict) else {}
    a_usage = after.get("usage", {}) if isinstance(after, dict) else {}
    b_rel = baseline.get("reliability", {}) if isinstance(baseline, dict) else {}
    a_rel = after.get("reliability", {}) if isinstance(after, dict) else {}

    baseline_allowed = baseline.get("decision") == "candidate_allowed"
    if not baseline_allowed:
        reasons.append(f"baseline_decision_not_allowed_{baseline.get('decision')}")

    artifacts_trusted = bool(
        baseline.get("trust", {}).get("trusted") is True
        and after.get("trust", {}).get("trusted") is True
    )
    if baseline.get("trust", {}).get("trusted") is not True:
        reasons.append("baseline_not_trusted")
    if after.get("trust", {}).get("trusted") is not True:
        reasons.append("after_not_trusted")

    input_match = bool(
        baseline.get("input_sha256") and baseline.get("input_sha256") == after.get("input_sha256")
    )
    if not input_match:
        reasons.append("input_mismatch")

    runtime_identity_match = bool(
        b_prov.get("requested_provider") == a_prov.get("requested_provider")
        and b_prov.get("effective_provider") == a_prov.get("effective_provider")
        and b_prov.get("requested_model") == a_prov.get("requested_model")
        and b_prov.get("effective_model") == a_prov.get("effective_model")
        and b_rag.get("requested_embedding_backend") == a_rag.get("requested_embedding_backend")
        and b_rag.get("effective_embedding_backend") == a_rag.get("effective_embedding_backend")
        and b_rag.get("retrieval_mode") == a_rag.get("retrieval_mode")
    )
    if not runtime_identity_match:
        reasons.append("runtime_identity_mismatch")
    if b_prov.get("requested_provider") != a_prov.get("requested_provider"):
        reasons.append("provider_mismatch")
    if b_prov.get("effective_provider") != a_prov.get("effective_provider"):
        reasons.append("effective_provider_mismatch")
    if b_prov.get("requested_model") != a_prov.get("requested_model"):
        reasons.append("model_mismatch")
    if b_prov.get("effective_model") != a_prov.get("effective_model"):
        reasons.append("effective_model_mismatch")

    environment_match = bool(
        b_env.get("os") == a_env.get("os")
        and b_env.get("architecture") == a_env.get("architecture")
        and b_env.get("python") == a_env.get("python")
        and b_env.get("boundary") == a_env.get("boundary")
        and isinstance(b_env.get("cpu"), str)
        and bool(b_env.get("cpu", "").strip())
        and isinstance(a_env.get("cpu"), str)
        and bool(a_env.get("cpu", "").strip())
        and b_env.get("cpu") == a_env.get("cpu")
    )
    if not environment_match:
        reasons.append("environment_mismatch")

    # CPU identity must be present, non-empty and match
    b_cpu = b_env.get("cpu")
    a_cpu = a_env.get("cpu")
    if not b_cpu or not isinstance(b_cpu, str) or not b_cpu.strip():
        reasons.append("baseline_cpu_missing_or_empty")
    if not a_cpu or not isinstance(a_cpu, str) or not a_cpu.strip():
        reasons.append("after_cpu_missing_or_empty")
    if b_cpu and a_cpu and b_cpu != a_cpu:
        reasons.append("cpu_mismatch")

    run_plan_match = bool(
        b_plan.get("cold_runs") == a_plan.get("cold_runs")
        and b_plan.get("warmup_runs") == a_plan.get("warmup_runs")
        and b_plan.get("measured_runs") == a_plan.get("measured_runs")
    )
    if not run_plan_match:
        reasons.append("run_plan_mismatch")

    revisions_valid = bool(
        baseline.get("git_revision")
        and after.get("git_revision")
        and baseline.get("git_revision") != after.get("git_revision")
    )
    if not baseline.get("git_revision") or not after.get("git_revision"):
        reasons.append("missing_revision")
    elif baseline.get("git_revision") == after.get("git_revision"):
        reasons.append("same_revision")

    trace_complete = bool(
        isinstance(b_plan.get("complete_measured_count"), int)
        and isinstance(a_plan.get("complete_measured_count"), int)
        and b_plan.get("complete_measured_count") == b_plan.get("measured_runs")
        and a_plan.get("complete_measured_count") == a_plan.get("measured_runs")
        and b_plan.get("complete_measured_count", 0) >= 20
        and a_plan.get("complete_measured_count", 0) >= 20
        and b_trace.get("completeness_rate") == 1.0
        and a_trace.get("completeness_rate") == 1.0
    )
    if not trace_complete:
        reasons.append("trace_completeness_failed")
        if (
            isinstance(b_plan.get("complete_measured_count"), int)
            and b_plan.get("complete_measured_count", 0) < 20
        ):
            reasons.append(
                f"baseline_insufficient_complete_{b_plan.get('complete_measured_count')}"
            )
        if (
            isinstance(a_plan.get("complete_measured_count"), int)
            and a_plan.get("complete_measured_count", 0) < 20
        ):
            reasons.append(f"after_insufficient_complete_{a_plan.get('complete_measured_count')}")

    b_observations = _stage31_normalize_observations(baseline.get("contract_observations"))
    a_observations = _stage31_normalize_observations(after.get("contract_observations"))
    behavior_equivalent = bool(
        b_observations is not None
        and a_observations is not None
        and b_observations == a_observations
    )
    if not behavior_equivalent:
        reasons.append("behavior_contract_mismatch")

    b_p95 = baseline.get("latency", {}).get("end_to_end", {}).get("p95_latency_ms")
    a_p95 = after.get("latency", {}).get("end_to_end", {}).get("p95_latency_ms")
    actual_improvement_pct = 0.0
    if isinstance(b_p95, (int, float)) and isinstance(a_p95, (int, float)) and b_p95 > 0:
        actual_improvement_pct = round(((b_p95 - a_p95) / b_p95) * 100, 3)
    latency_gate = actual_improvement_pct >= 20.0
    if not latency_gate:
        reasons.append(f"actual_improvement_{actual_improvement_pct}_lt_20.0")

    b_agent_calls = b_usage.get("logical_agent_calls")
    a_agent_calls = a_usage.get("logical_agent_calls")
    b_tool_calls = b_usage.get("logical_tool_calls")
    a_tool_calls = a_usage.get("logical_tool_calls")
    call_count_gate = bool(
        isinstance(b_agent_calls, int)
        and isinstance(a_agent_calls, int)
        and isinstance(b_tool_calls, int)
        and isinstance(a_tool_calls, int)
        and a_agent_calls <= b_agent_calls
        and a_tool_calls <= b_tool_calls
    )
    if not call_count_gate:
        reasons.append("agent_or_tool_call_count_increased_or_missing")
        if (
            isinstance(a_agent_calls, int)
            and isinstance(b_agent_calls, int)
            and a_agent_calls > b_agent_calls
        ):
            reasons.append("agent_call_count_increased")
        if (
            isinstance(a_tool_calls, int)
            and isinstance(b_tool_calls, int)
            and a_tool_calls > b_tool_calls
        ):
            reasons.append("tool_call_count_increased")

    b_per_run_tokens = b_usage.get("per_successful_run_tokens")
    a_per_run_tokens = a_usage.get("per_successful_run_tokens")
    token_gate = bool(
        isinstance(b_per_run_tokens, int)
        and isinstance(a_per_run_tokens, int)
        and a_per_run_tokens <= b_per_run_tokens * 1.05
    )
    if not token_gate:
        reasons.append("per_run_tokens_missing_or_increased_gt_105pct")

    try:
        b_cost = Decimal(baseline.get("cost", {})["per_successful_run_estimated_usd"])
        a_cost = Decimal(after.get("cost", {})["per_successful_run_estimated_usd"])
        cost_gate = a_cost <= b_cost * Decimal("1.05")
    except (KeyError, TypeError, ValueError):
        b_cost = Decimal(0)
        a_cost = Decimal(0)
        cost_gate = False
    if not cost_gate:
        reasons.append("per_run_cost_missing_or_increased_gt_105pct")

    b_err = b_rel.get("error_rate")
    a_err = a_rel.get("error_rate")
    error_rate_gate = bool(
        isinstance(b_err, (int, float))
        and isinstance(a_err, (int, float))
        and a_err <= b_err + 0.05
    )
    if not error_rate_gate:
        reasons.append("error_rate_missing_or_increased_gt_5pp")

    b_err_dist = b_rel.get("error_distribution")
    a_err_dist = a_rel.get("error_distribution")
    no_new_error_types = bool(
        isinstance(b_err_dist, dict)
        and isinstance(a_err_dist, dict)
        and not (set(a_err_dist) - set(b_err_dist))
    )
    if not no_new_error_types:
        reasons.append("new_or_invalid_error_types")
        if isinstance(b_err_dist, dict) and isinstance(a_err_dist, dict):
            new_error_types = sorted(set(a_err_dist) - set(b_err_dist))
            if new_error_types:
                reasons.append(f"new_error_types_{new_error_types}")

    def _independence_safe(report: dict[str, Any]) -> bool:
        findings = report.get("independence")
        return bool(
            isinstance(findings, dict)
            and findings
            and all(
                isinstance(finding, dict)
                and finding.get("finding") not in {"unknown", "unsafe", "unbounded"}
                for finding in findings.values()
            )
        )

    independence_safe = _independence_safe(baseline) and _independence_safe(after)
    if not independence_safe:
        reasons.append("independence_gate_failed")

    contract_gates = {
        "artifacts_schema_valid": not any(
            reason.startswith("baseline_") or reason.startswith("after_")
            for reason in reasons
            if reason.endswith("invalid")
            or "_invalid" in reason
            or "_inconsistent" in reason
            or "_artifact_not_object" in reason
        ),
        "baseline_candidate_allowed": baseline_allowed,
        "artifacts_trusted": artifacts_trusted,
        "input_match": input_match,
        "runtime_identity_match": runtime_identity_match,
        "environment_match": environment_match,
        "run_plan_match": run_plan_match,
        "revisions_valid": revisions_valid,
        "trace_complete": trace_complete,
        "behavior_contract_equivalent": behavior_equivalent,
        "call_counts_not_increased": call_count_gate,
        "tokens_within_105_pct": token_gate,
        "cost_within_105_pct": cost_gate,
        "error_rate_within_5pp": error_rate_gate,
        "no_new_error_types": no_new_error_types,
        "independence_safe": independence_safe,
        "warm_p95_improvement_at_least_20_pct": latency_gate,
        "focused_gates_passed": focused_gates_passed,
        "stage_gates_passed": stage_gates_passed,
    }
    if not focused_gates_passed:
        reasons.append("focused_gates_failed")
    if not stage_gates_passed:
        reasons.append("stage_gates_failed")

    reasons = list(dict.fromkeys(reasons))
    success = all(contract_gates.values()) and not reasons
    return {
        "schema_version": "1.0",
        "stage": "stage-31-trace-guided-performance",
        "artifact_role": "comparison",
        "baseline_revision": baseline.get("git_revision", ""),
        "after_revision": after.get("git_revision", ""),
        "input_sha256": baseline.get("input_sha256", ""),
        "success": success,
        "outcome": "optimization_accepted" if success else "optimization_rejected",
        "failure_reasons": reasons,
        "trust": {"trusted": artifacts_trusted and contract_gates["artifacts_schema_valid"]},
        "latency": {
            "actual_improvement_pct": actual_improvement_pct,
            "baseline_warm_p95_ms": b_p95,
            "after_warm_p95_ms": a_p95,
        },
        "usage": {
            "baseline_per_successful_run_tokens": b_per_run_tokens,
            "after_per_successful_run_tokens": a_per_run_tokens,
            "baseline_logical_agent_calls": b_agent_calls,
            "after_logical_agent_calls": a_agent_calls,
            "baseline_logical_tool_calls": b_tool_calls,
            "after_logical_tool_calls": a_tool_calls,
        },
        "cost": {
            "baseline_per_successful_run_estimated_usd": str(b_cost),
            "after_per_successful_run_estimated_usd": str(a_cost),
        },
        "reliability": {
            "baseline_error_rate": b_err,
            "after_error_rate": a_err,
        },
        "contract_gates": contract_gates,
    }


def write_benchmark_markdown(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_benchmark_markdown(report), encoding="utf-8")


def write_benchmark_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_environment_gap_report(
    *,
    provider_requested: str,
    model_requested: str,
    reason: str,
    message: str,
    runs: int,
) -> dict[str, Any]:
    empty_latency = _latency_stats([])
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "environment_gap",
        "run_count": runs,
        "provider_requested": provider_requested,
        "provider_effective": None,
        "model_requested": model_requested,
        "model_effective": None,
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": empty_latency,
            "rag_search": empty_latency,
        },
        "tokens": {
            "token_usage_available": False,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "unavailable_reason": reason,
        },
        "cost": {
            "cost_available": False,
            "estimated_cost_usd": None,
            "per_case_estimated_cost_usd": None,
            "assumptions": "real provider unavailable; cost cannot be estimated",
            "unavailable_reason": reason,
        },
        "trust": {
            "trusted": False,
            "real_provider_evidence": False,
            "cost_evidence_available": False,
            "reasons": [reason],
        },
        "environment_gap": {
            "reason": reason,
            "message": message,
        },
    }


def _format_stage23_markdown(report: dict[str, Any]) -> str:
    """Generate Markdown for Stage 23 legacy reports."""
    lines = ["# Performance & Cost Benchmark", "", "```json"]
    lines.append(json.dumps(report, indent=2))
    lines.append("```")

    lines.append("## Metadata")
    lines.append(f"| Run Count | {report.get('run_count', 0)} |")
    lines.append(f"| Provider Requested | `{report.get('provider_requested', '')}` |")
    lines.append(f"| Provider Effective | `{report.get('provider_effective', '')}` |")
    lines.append(f"| Model Effective | `{report.get('model_effective', 'fake-llm')}` |")
    lines.append("## Claim Boundary")
    lines.append(report.get("boundary", "offline benchmark; not production SLA"))
    if report.get("provider_effective") == "fake":
        lines.append("Not real LLM latency")
        lines.append("No real LLM cost")
    lines.append("## Token Usage")
    tokens = report.get("tokens", {})
    lines.append(f"| Token Usage Available | {tokens.get('token_usage_available', False)} |")
    lines.append("## Cost")
    cost = report.get("cost", {})
    lines.append(f"| Cost Available | {cost.get('cost_available', False)} |")
    if cost.get("estimated_cost_usd") is not None:
        lines.append(f"| Estimated Cost (USD) | {cost['estimated_cost_usd']} |")
    if cost.get("per_case_estimated_cost_usd") is not None:
        lines.append(f"| Per Case Estimated Cost (USD) | {cost['per_case_estimated_cost_usd']} |")
    lines.append("## Environment Gap")
    if report.get("environment_gap"):
        lines.append(report["environment_gap"].get("reason", ""))
    lines.append("## Latency")
    lines.append("## Per-Run Latency")
    lines.append("ExtractionAgent")
    lines.append("RAG Search")

    return "\n".join(lines)


def _format_stage31_markdown(report: dict[str, Any]) -> str:
    """Generate Markdown from Stage 31 JSON data."""
    lines = ["# Stage 31 Trace-Guided Performance Benchmark", ""]
    lines.append("```json")
    lines.append(json.dumps(report, indent=2))
    lines.append("```")
    lines.append("")

    role = report.get("artifact_role", "")
    decision = report.get("decision", "")
    if role in {"baseline", "after"}:
        lines.append(f"## {role.title()} Decision")
        lines.append(f"**Decision**: `{decision}`")
        lines.append(f"**Reasons**: {report.get('closed_reasons', [])}")
        lines.append("")

        lines.append("## Identity")
        lines.append(f"- Schema: `{report.get('schema_version', '')}`")
        lines.append(f"- Stage: `{report.get('stage', '')}`")
        lines.append(f"- Git: `{report.get('git_revision', '')}`")
        lines.append(f"- Input SHA256: `{report.get('input_sha256', '')}`")
        lines.append("")

        lines.append("## Trust")
        trust = report.get("trust", {})
        lines.append(f"- Trusted: `{trust.get('trusted')}`")
        lines.append(f"- Reasons: {trust.get('reasons', [])}")
        env_gap = trust.get("environment_gap")
        if env_gap:
            lines.append(f"- Environment Gap: `{env_gap.get('reason', '')}`")
        lines.append("")

        lines.append("## Run Plan")
        plan = report.get("run_plan", {})
        lines.append(f"- Cold: {plan.get('cold_runs', 0)}")
        lines.append(f"- Warmup: {plan.get('warmup_runs', 0)}")
        lines.append(f"- Measured: {plan.get('measured_runs', 0)}")
        lines.append(f"- Complete: {plan.get('complete_measured_count', 0)}")
        lines.append("")

        lines.append("## Latency")
        lt = report.get("latency", {})
        e2e = lt.get("end_to_end", {})
        lines.append(f"- E2E P95: {e2e.get('p95_latency_ms', 0)} ms")
        lines.append(f"- E2E P50: {e2e.get('p50_latency_ms', 0)} ms")
        lines.append("")

        theory = report.get("theory", {})
        lines.append("## Theory")
        lines.append(f"- Predicted P95: {theory.get('predicted_warm_p95_ms', 0)} ms")
        lines.append(f"- Actual P95: {theory.get('actual_warm_p95_ms', 0)} ms")
        lines.append(f"- Improvement: {theory.get('theoretical_p95_improvement_pct', 0)}%")
        lines.append("")

        usage = report.get("usage", {})
        lines.append("## Usage")
        lines.append(f"- Logical Agent calls: {usage.get('logical_agent_calls', 0)}")
        lines.append(f"- Logical Tool calls: {usage.get('logical_tool_calls', 0)}")
        lines.append(
            f"- Provider transport attempts: {usage.get('provider_transport_attempts', 0)}"
        )
        lines.append(f"- Total tokens: {usage.get('total_tokens')}")
        lines.append("")

        cost = report.get("cost", {})
        lines.append("## Cost")
        lines.append(f"- Total: {cost.get('total_estimated_usd')}")
        lines.append(f"- Per-run: {cost.get('per_successful_run_estimated_usd')}")
        lines.append("")

        rel = report.get("reliability", {})
        lines.append("## Reliability")
        lines.append(f"- Success: {rel.get('success_count', 0)}")
        lines.append(f"- Failure: {rel.get('failure_count', 0)}")
        lines.append(f"- Error Rate: {rel.get('error_rate', 0)}")
        lines.append("")

        ind = report.get("independence", {})
        if isinstance(ind, dict):
            lines.append("## Independence Gate")
            for key, finding in ind.items():
                if isinstance(finding, dict):
                    lines.append(
                        f"- **{key}**: `{finding.get('finding')}` — {finding.get('detail', '')}"
                    )
                else:
                    lines.append(f"- **{key}**: `{finding}`")
            lines.append("")

    elif role == "comparison":
        lines.append("## Comparison Outcome")
        lines.append(f"**Outcome**: `{report.get('outcome', '')}`")
        lines.append(f"**Success**: `{report.get('success')}`")
        lines.append(f"**Reasons**: {report.get('failure_reasons', [])}")
        lines.append("")

        lt = report.get("latency", {})
        lines.append("## Latency")
        lines.append(f"- Improvement: {lt.get('actual_improvement_pct', 0)}%")
        lines.append(f"- Baseline P95: {lt.get('baseline_warm_p95_ms', 0)} ms")
        lines.append(f"- After P95: {lt.get('after_warm_p95_ms', 0)} ms")
        lines.append("")

    return "\n".join(lines)


def _format_benchmark_markdown(report: dict[str, Any]) -> str:
    stage = report.get("stage", "")
    if stage == "stage-31-trace-guided-performance":
        return _format_stage31_markdown(report)
    return _format_stage23_markdown(report)


def _print_stdout_report(
    extraction_avg: float,
    rag_avg: float,
    extraction_samples: list[float],
    rag_samples: list[float],
    *,
    runs: int,
    provider_name: str,
    model_effective: str,
) -> None:
    ratio = extraction_avg / rag_avg if rag_avg > 0 else float("inf")

    print("Agent latency benchmark for ADR-032")
    print(f"runs={runs}")
    print(f"provider={provider_name} model={model_effective}")
    print(f"ExtractionAgent average_ms={extraction_avg:.3f} samples_ms={extraction_samples}")
    print(f"RAG average_ms={rag_avg:.3f} samples_ms={rag_samples}")
    print(f"ratio extraction_over_rag={ratio:.2f}x")
    if provider_name == "fake":
        print(
            "Note: fake provider benchmark; "
            "ExtractionAgent latency here is not representative of a real LLM."
        )
        print(
            "Note: with a real provider, ExtractionAgent is commonly ~1-3s "
            "while local RAG is often <100ms."
        )

    if ratio >= 1.0:
        print(
            "Conclusion: measured ratio shows ExtractionAgent is slower than or equal to RAG, "
            "which supports ADR-032 keeping the workflow serial."
        )
    else:
        print(
            "Conclusion: measured ratio shows ExtractionAgent is faster than RAG in this run; "
            "interpret fake-provider numbers cautiously before revisiting ADR-032."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark ExtractionAgent and RAG latency for performance/cost evidence."
    )
    parser.add_argument("--scenario", default="legacy")
    parser.add_argument("--embedding-backend", default="fake")
    parser.add_argument("--cold-runs", type=int, default=0)
    parser.add_argument("--warmup-runs", type=int, default=0)
    parser.add_argument("--runs", type=int, default=RUNS)
    parser.add_argument("--provider", default="fake")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--baseline-json", type=Path, default=None)
    parser.add_argument("--after-json", type=Path, default=None)
    parser.add_argument("--artifact-role", default="baseline", choices=["baseline", "after"])
    parser.add_argument("--focused-gates-passed", action="store_true")
    parser.add_argument("--stage-gates-passed", action="store_true")
    args = parser.parse_args(argv)

    from bank_reconciliation_agent.core.llm.provider import LLMUnavailable

    report = None
    exit_code = 0

    try:
        if args.scenario == "stage31-critical-path":
            report = run_stage31_critical_path(
                provider_name=args.provider,
                model=args.model,
                embedding_backend=args.embedding_backend,
                cold_runs=args.cold_runs,
                warmup_runs=args.warmup_runs,
                runs=args.runs,
                artifact_role=args.artifact_role,
            )
            if report.get("decision") == "environment_gap":
                exit_code = 1
        elif args.scenario == "stage31-comparison":
            report = run_stage31_comparison(
                args.baseline_json,
                args.after_json,
                args.focused_gates_passed,
                args.stage_gates_passed,
            )
        else:
            report = run_benchmark(runs=args.runs, provider_name=args.provider, model=args.model)
    except LLMUnavailable as exc:
        if args.report is not None or args.json_report is not None:
            reason = (
                "missing_deepseek_api_key"
                if "api_key" in str(exc).lower()
                else "provider_unavailable"
            )
            report = build_environment_gap_report(
                provider_requested=args.provider,
                model_requested=args.model,
                reason=reason,
                message=str(exc),
                runs=args.runs,
            )
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        exit_code = 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if report is not None:
        if report.get("status") == "environment_gap" or report.get("decision") == "environment_gap":
            exit_code = 1

        # Legacy stdout
        if exit_code == 0 and args.scenario == "legacy":
            latency = report["latency"]
            extraction_avg = latency["extraction_agent"]["avg_latency_ms"]
            rag_avg = latency["rag_search"]["avg_latency_ms"]
            extraction_samples = latency["extraction_agent"]["samples_ms"]
            rag_samples = latency["rag_search"]["samples_ms"]

            _print_stdout_report(
                extraction_avg,
                rag_avg,
                extraction_samples,
                rag_samples,
                runs=args.runs,
                provider_name=args.provider,
                model_effective=report["model_effective"],
            )

        if args.report is not None:
            write_benchmark_markdown(report, args.report)
        if args.json_report is not None:
            write_benchmark_json(report, args.json_report)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
