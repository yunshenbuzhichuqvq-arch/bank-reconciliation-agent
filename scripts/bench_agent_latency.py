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
) -> dict[str, Any]:
    from bank_reconciliation_agent.core.config import settings
    from bank_reconciliation_agent.core.llm.cost import compute_cost
    from bank_reconciliation_agent.services.workflow import run_item
    from bank_reconciliation_agent.services.trace import TraceRecorder
    from bank_reconciliation_agent.core.llm.provider import LLMUnavailable

    is_real_provider = provider_name == "deepseek"
    is_real_backend = embedding_backend == "bge_m3"
    is_real_env = is_real_provider and is_real_backend

    trust_reasons = []
    env_gap = None
    token_usage_unavailable = False

    if provider_name == "deepseek" and not settings.deepseek_api_key:
        raise LLMUnavailable("DEEPSEEK_API_KEY is not configured.")

    if not is_real_provider:
        trust_reasons.append("fake_provider")
    if not is_real_backend:
        trust_reasons.append("fake_embedding_backend")

    input_data = {
        "scenario_type": "BANK_ENTERPRISE",
        "exception_branch": "BE-R004",
        "error_type": "NARRATIVE_NAME_MISMATCH",
    }
    input_sha256 = hashlib.sha256(json.dumps(input_data, sort_keys=True).encode()).hexdigest()

    cold_observations = []
    warm_e2e = []
    warm_extraction = []
    warm_rag = []
    predicted_parallel_e2e = []

    total_prompt_tokens = 0
    total_completion_tokens = 0
    success_count = 0
    failure_count = 0

    trace_completeness = []
    error_distribution: dict[str, int] = {}

    base_time = int(time.time())
    total_runs_count = cold_runs + warmup_runs + runs

    for i in range(total_runs_count):
        is_cold = i < cold_runs
        is_measured = i >= cold_runs + warmup_runs
        flow_id = f"FLOW-BENCH-{base_time}-{i:03d}"

        recorder = TraceRecorder(
            user_id="bench_user",
            task_id=f"task-{base_time}-{i:03d}",
            flow_id=flow_id,
        )

        state = {
            "task_id": f"task-{base_time}-{i:03d}",
            "user_id": "bench_user",
            "thread_id": "thread-bench",
            "scenario_type": "BANK_ENTERPRISE",
            "current_queue_id": 12345,
            "source_a_item": {
                "flow_id": flow_id,
                "summary": "冲正退款备注待核验",
                "remark": "原流水疑似冲正，需要抽取原始流水号",
                "amount": "100.00",
            },
            "source_b_item": {
                "flow_id": flow_id,
                "summary": "REVERSAL",
                "remark": "remark",
            },
            "error_type": "NARRATIVE_NAME_MISMATCH",
            "exception_branch": "BE-R004",
            "math_result": {
                "bank_amount": "100.00",
                "clear_amount": "100.00",
                "amount_diff": "0.00",
            },
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
        try:
            final_state = run_item(state)
            root_status = "SUCCEEDED"
        except Exception:
            root_status = "FAILED"
            final_state = state

        recorder.close_root(
            status=root_status,
            outcome=final_state.get("next_action") or "PENDING_HUMAN",
        )
        spans = recorder.snapshot()
        e2e_ms = (time.perf_counter() - started) * 1000

        root_spans = [s for s in spans if s.span_type == "WORKFLOW" and not s.parent_span_id]
        ext_spans = [s for s in spans if s.span_type == "AGENT" and s.name == "ExtractionAgent"]
        rag_spans = [s for s in spans if s.span_type == "TOOL" and s.name == "search_rules"]

        is_complete = False
        if len(root_spans) == 1 and len(ext_spans) == 1 and len(rag_spans) == 1:
            if (
                root_spans[0].status == "SUCCEEDED"
                and ext_spans[0].status == "SUCCEEDED"
                and rag_spans[0].status == "SUCCEEDED"
            ):
                is_complete = True
                if is_real_env and (
                    ext_spans[0].prompt_tokens is None or ext_spans[0].prompt_tokens == 0
                ):
                    token_usage_unavailable = True

        ext_dur = ext_spans[0].duration_ms if ext_spans else 0
        rag_dur = rag_spans[0].duration_ms if rag_spans else 0
        pred_parallel = e2e_ms - ext_dur - rag_dur + max(ext_dur, rag_dur)

        if is_measured:
            if is_complete:
                success_count += 1
                if ext_spans[0].prompt_tokens:
                    total_prompt_tokens += ext_spans[0].prompt_tokens
                if ext_spans[0].completion_tokens:
                    total_completion_tokens += ext_spans[0].completion_tokens
            else:
                failure_count += 1
                err_key = "incomplete_trace"
                if len(root_spans) != 1:
                    err_key = "missing_or_duplicate_root"
                elif len(ext_spans) != 1:
                    err_key = "missing_or_duplicate_extraction"
                elif len(rag_spans) != 1:
                    err_key = "missing_or_duplicate_rag"
                error_distribution[err_key] = error_distribution.get(err_key, 0) + 1

            trace_completeness.append(
                {
                    "trace_id": root_spans[0].trace_id if root_spans else "unknown",
                    "is_complete": is_complete,
                    "ext_spans": len(ext_spans),
                    "rag_spans": len(rag_spans),
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

    if is_real_env and token_usage_unavailable:
        trust_reasons.append("token_usage_unavailable")
        env_gap = {
            "reason": "token_usage_unavailable",
            "message": "DeepSeek provider returned no token usage metadata.",
        }

    trusted = is_real_env and not env_gap

    actual_p95 = round(_p95(warm_e2e), 3)
    pred_p95 = round(_p95(predicted_parallel_e2e), 3)
    theory_pct = 0.0
    if actual_p95 > 0:
        theory_pct = round(((actual_p95 - pred_p95) / actual_p95) * 100, 3)

    independence_findings = {
        "data_dependency": {
            "finding": "safe",
            "detail": (
                "RAG query is built from scenario_type, error_type, exception_branch, and "
                "amounts; does not read extraction_result. Extraction and RAG are data-independent."
            ),
        },
        "shared_state": {
            "finding": "safe",
            "detail": (
                "In serial runtime there is no concurrent access. For a parallel candidate, "
                "workers must receive read-only inputs and return results without modifying "
                "ReconciliationState, Trace recorder, SSE emitter, or persistent state."
            ),
        },
        "failure_order": {
            "finding": "bounded",
            "detail": (
                "In serial runtime, Extraction failure causes early return before RAG. "
                "In a parallel candidate, the failure of one side while the other is in-flight "
                "requires explicit fail-closed handling: both must be complete, and any failure "
                "must prevent automatic audit."
            ),
        },
        "cancellation": {
            "finding": "bounded",
            "detail": (
                "Synchronous provider/retriever calls may not support hard interrupt. "
                "A thread pool must use bounded timeouts and guarantee no background state "
                "mutation after timeout."
            ),
        },
        "resource_reclamation": {
            "finding": "safe",
            "detail": (
                "Thread pool resources are released via context manager. No persistent "
                "background threads or shared buffers."
            ),
        },
    }

    any_unsafe = any(
        f["finding"] in ("unknown", "unsafe", "unbounded") for f in independence_findings.values()
    )

    decision = "candidate_allowed"
    closed_reasons = []

    if env_gap:
        decision = "environment_gap"
        closed_reasons.append("environment_gap")
    elif any_unsafe:
        decision = "no_go"
        closed_reasons.append("independence_gate_failed")
    else:
        if not trusted:
            decision = "no_go"
            closed_reasons.append("not_trusted")
        if complete_count < runs:
            decision = "no_go"
            closed_reasons.append(f"complete_count_{complete_count}_lt_{runs}")
        if theory_pct < 20.0:
            decision = "no_go"
            closed_reasons.append(f"theory_pct_{theory_pct}_lt_20.0")

    token_usage_available = not token_usage_unavailable and total_prompt_tokens > 0
    cost_value = (
        compute_cost(total_prompt_tokens, total_completion_tokens)
        if token_usage_available
        else Decimal(0)
    )
    per_case_cost = cost_value / Decimal(success_count) if success_count else Decimal(0)

    return {
        "schema_version": "1.0",
        "stage": "stage-31-trace-guided-performance",
        "artifact_role": "baseline",
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_revision": get_git_revision(),
        "input_sha256": input_sha256,
        "environment": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "boundary": "offline benchmark; not production SLA",
        },
        "provider": {
            "requested_provider": provider_name,
            "effective_provider": provider_name if is_real_env else "fake",
            "requested_model": model,
            "effective_model": model if is_real_env else "fake-llm",
        },
        "rag": {
            "requested_embedding_backend": embedding_backend,
            "effective_embedding_backend": embedding_backend if is_real_backend else "fake",
            "retrieval_mode": "dense",
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
            "provider_call_count": success_count,
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


def run_stage31_comparison(
    baseline_path: Path,
    after_path: Path,
    focused_gates_passed: bool,
    stage_gates_passed: bool,
) -> dict[str, Any]:
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    with open(after_path, "r", encoding="utf-8") as f:
        after = json.load(f)

    reasons: list[str] = []

    # Artifact role validation
    if baseline.get("artifact_role") != "baseline":
        reasons.append("baseline_role_invalid")
    if after.get("artifact_role") != "after":
        reasons.append("after_role_invalid")

    # Trust validation
    if not baseline.get("trust", {}).get("trusted"):
        reasons.append("baseline_not_trusted")
    if not after.get("trust", {}).get("trusted"):
        reasons.append("after_not_trusted")

    # Input identity match
    if baseline.get("input_sha256") != after.get("input_sha256"):
        reasons.append("input_mismatch")

    # Provider/model/backend match
    b_prov = baseline.get("provider", {})
    a_prov = after.get("provider", {})
    if b_prov.get("requested_provider") != a_prov.get("requested_provider"):
        reasons.append("provider_mismatch")
    if b_prov.get("effective_provider") != a_prov.get("effective_provider"):
        reasons.append("effective_provider_mismatch")
    if b_prov.get("requested_model") != a_prov.get("requested_model"):
        reasons.append("model_mismatch")

    b_rag = baseline.get("rag", {})
    a_rag = after.get("rag", {})
    if b_rag.get("requested_embedding_backend") != a_rag.get("requested_embedding_backend"):
        reasons.append("embedding_backend_mismatch")

    # Environment consistency
    b_env = baseline.get("environment", {})
    a_env = after.get("environment", {})
    if b_env.get("os") != a_env.get("os") or b_env.get("architecture") != a_env.get("architecture"):
        reasons.append("environment_mismatch")

    # Run plan match
    b_plan = baseline.get("run_plan", {})
    a_plan = after.get("run_plan", {})
    if b_plan.get("measured_runs") != a_plan.get("measured_runs"):
        reasons.append("run_plan_mismatch")
    if b_plan.get("cold_runs") != a_plan.get("cold_runs"):
        reasons.append("cold_runs_mismatch")
    if b_plan.get("warmup_runs") != a_plan.get("warmup_runs"):
        reasons.append("warmup_runs_mismatch")

    # Git revision must be different (after should be a candidate revision)
    if baseline.get("git_revision") == after.get("git_revision"):
        reasons.append("same_revision")

    # Complete count requirements
    b_complete = b_plan.get("complete_measured_count", 0)
    a_complete = a_plan.get("complete_measured_count", 0)
    if b_complete < 20:
        reasons.append(f"baseline_insufficient_complete_samples_{b_complete}")
    if a_complete < 20:
        reasons.append(f"after_insufficient_complete_samples_{a_complete}")

    # Trace completeness
    b_trace = baseline.get("trace", {})
    a_trace = after.get("trace", {})
    if b_trace.get("completeness_rate", 0) != 1.0:
        reasons.append("baseline_trace_incomplete")
    if a_trace.get("completeness_rate", 0) != 1.0:
        reasons.append("after_trace_incomplete")

    # Focused and stage gates
    if not focused_gates_passed:
        reasons.append("focused_gates_failed")
    if not stage_gates_passed:
        reasons.append("stage_gates_failed")

    # Latency comparison
    b_p95 = baseline.get("latency", {}).get("end_to_end", {}).get("p95_latency_ms", 0)
    a_p95 = after.get("latency", {}).get("end_to_end", {}).get("p95_latency_ms", 0)
    actual_improvement_pct = 0.0
    if b_p95 > 0:
        actual_improvement_pct = round(((b_p95 - a_p95) / b_p95) * 100, 3)

    if actual_improvement_pct < 20.0:
        reasons.append(f"actual_improvement_{actual_improvement_pct}_lt_20.0")

    # Usage comparison
    b_usage = baseline.get("usage", {})
    a_usage = after.get("usage", {})
    b_per_run_tokens = b_usage.get("per_successful_run_tokens") or 0
    a_per_run_tokens = a_usage.get("per_successful_run_tokens") or 0
    if b_per_run_tokens > 0 and a_per_run_tokens > b_per_run_tokens * 1.05:
        reasons.append("per_run_tokens_increased_gt_105pct")

    # Provider call count comparison
    b_calls = b_usage.get("provider_call_count", 0)
    a_calls = a_usage.get("provider_call_count", 0)
    if a_calls > b_calls:
        reasons.append("provider_call_count_increased")

    # Cost comparison
    b_cost_str = baseline.get("cost", {}).get("per_successful_run_estimated_usd")
    a_cost_str = after.get("cost", {}).get("per_successful_run_estimated_usd")
    b_cost = Decimal(b_cost_str) if b_cost_str else Decimal(0)
    a_cost = Decimal(a_cost_str) if a_cost_str else Decimal(0)
    if b_cost > 0 and a_cost > b_cost * Decimal("1.05"):
        reasons.append("per_run_cost_increased_gt_105pct")

    # Error rate comparison
    b_err = baseline.get("reliability", {}).get("error_rate", 0)
    a_err = after.get("reliability", {}).get("error_rate", 0)
    if a_err > b_err + 0.05:
        reasons.append(f"error_rate_increased_{a_err}_gt_{b_err}_plus_5pp")

    # Error distribution check
    a_err_dist = after.get("reliability", {}).get("error_distribution", {})
    b_err_dist = baseline.get("reliability", {}).get("error_distribution", {})
    new_error_types = set(a_err_dist.keys()) - set(b_err_dist.keys())
    if new_error_types:
        reasons.append(f"new_error_types_{sorted(new_error_types)}")

    # Independence gate — comparison must have passed
    b_ind = baseline.get("independence", {})
    b_unsafe = any(
        f.get("finding", "") in ("unknown", "unsafe", "unbounded")
        for f in (b_ind.values() if isinstance(b_ind, dict) else [])
    )
    if b_unsafe:
        reasons.append("baseline_independence_failed")

    success = len(reasons) == 0
    return {
        "success": success,
        "outcome": "optimization_accepted" if success else "optimization_rejected",
        "failure_reasons": reasons,
        "trust": {
            "trusted": (
                baseline.get("trust", {}).get("trusted", False)
                and after.get("trust", {}).get("trusted", False)
            ),
        },
        "latency": {
            "actual_improvement_pct": actual_improvement_pct,
            "baseline_warm_p95_ms": b_p95,
            "after_warm_p95_ms": a_p95,
        },
        "usage": {
            "baseline_per_successful_run_tokens": b_per_run_tokens,
            "after_per_successful_run_tokens": a_per_run_tokens,
            "baseline_provider_call_count": b_calls,
            "after_provider_call_count": a_calls,
        },
        "cost": {
            "baseline_per_successful_run_estimated_usd": str(b_cost),
            "after_per_successful_run_estimated_usd": str(a_cost),
        },
        "reliability": {
            "baseline_error_rate": b_err,
            "after_error_rate": a_err,
        },
        "contract_gates": {
            "focused_gates_passed": focused_gates_passed,
            "stage_gates_passed": stage_gates_passed,
        },
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
    if role == "baseline":
        lines.append("## Baseline Decision")
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
        lines.append(f"- Provider calls: {usage.get('provider_call_count', 0)}")
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
