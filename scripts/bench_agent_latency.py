from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
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
        "p95_latency_ms": round(_p95(samples), 3),
        "min_latency_ms": round(s_min, 3),
        "max_latency_ms": round(s_max, 3),
        "samples_ms": [round(s, 3) for s in samples],
    }


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
    cost_assumptions: str = "fake provider; no real LLM cost"

    if token_usage_available:
        cost_value = compute_cost(total_prompt_tokens, total_completion_tokens)
        estimated_cost_usd = str(cost_value)
        cost_available = True
        cost_assumptions = (
            f"DeepSeek v4 Pro pricing: "
            f"input ${DEEPSEEK_V4_PRO_INPUT_CACHE_MISS_USD_PER_1M}/1M, "
            f"output ${DEEPSEEK_V4_PRO_OUTPUT_USD_PER_1M}/1M"
        )
    elif is_real_provider and not token_usage_available:
        cost_assumptions = "real provider but no token usage data available; cost cannot be estimated"

    extraction_latency = _latency_stats(extraction_samples)
    rag_latency = _latency_stats(rag_samples)

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        },
        "cost": {
            "cost_available": cost_available,
            "estimated_cost_usd": estimated_cost_usd,
            "assumptions": cost_assumptions,
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


def _format_benchmark_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Performance & Cost Benchmark",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Run Count | {report['run_count']} |",
        f"| Provider Requested | `{report['provider_requested']}` |",
        f"| Provider Effective | `{report['provider_effective']}` |",
        f"| Model Requested | `{report.get('model_requested', 'unknown')}` |",
        f"| Model Effective | `{report.get('model_effective', 'unknown')}` |",
        f"| Evaluated At | {report.get('evaluated_at', 'N/A')} |",
        "",
        "## Latency",
        "",
    ]

    latency = report.get("latency", {})
    lines.extend(
        [
            "| Component | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Samples (ms) |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for component, label in [
        ("extraction_agent", "ExtractionAgent"),
        ("rag_search", "RAG Search"),
    ]:
        comp_data = latency.get(component, {})
        samples_str = ", ".join(str(s) for s in comp_data.get("samples_ms", []))
        lines.append(
            f"| {label} | {comp_data.get('avg_latency_ms', 0):.3f} | "
            f"{comp_data.get('p95_latency_ms', 0):.3f} | "
            f"{comp_data.get('min_latency_ms', 0):.3f} | "
            f"{comp_data.get('max_latency_ms', 0):.3f} | "
            f"{samples_str} |"
        )
    lines.append("")

    tokens = report.get("tokens", {})
    cost = report.get("cost", {})
    lines.extend(
        [
            "## Token Usage",
            "",
            "| Key | Value |",
            "|---|---|",
            f"| Token Usage Available | {tokens.get('token_usage_available', False)} |",
        ]
    )
    if tokens.get("token_usage_available"):
        lines.append(f"| Input Tokens | {tokens.get('input_tokens', 0)} |")
        lines.append(f"| Output Tokens | {tokens.get('output_tokens', 0)} |")
        lines.append(f"| Total Tokens | {tokens.get('total_tokens', 0)} |")
    lines.append("")
    lines.extend(
        [
            "## Cost",
            "",
            "| Key | Value |",
            "|---|---|",
            f"| Cost Available | {cost.get('cost_available', False)} |",
        ]
    )
    if cost.get("cost_available") and cost.get("estimated_cost_usd") is not None:
        lines.append(f"| Estimated Cost (USD) | {cost['estimated_cost_usd']} |")
    lines.append(f"| Assumptions | {cost.get('assumptions', 'N/A')} |")
    lines.append("")

    lines.extend(
        [
            "## Claim Boundary",
            "",
            f"- {report.get('boundary', 'offline benchmark; not production SLA')}",
        ]
    )
    if report.get("provider_effective") == "fake":
        lines.extend(
            [
                "- **Not real LLM latency**: fake provider; ExtractionAgent latency here does not "
                "represent a real LLM.",
                "- **No real LLM cost**: fake provider; cost data is not available.",
            ]
        )
    lines.append("")

    lines.extend(
        [
            "## Per-Run Latency",
            "",
            "| Run | ExtractionAgent (ms) | RAG Search (ms) |",
            "| ---: | ---: | ---: |",
        ]
    )
    extraction_samples = latency.get("extraction_agent", {}).get("samples_ms", [])
    rag_samples_list = latency.get("rag_search", {}).get("samples_ms", [])
    for i in range(len(extraction_samples)):
        ext_val = extraction_samples[i] if i < len(extraction_samples) else "-"
        rag_val = rag_samples_list[i] if i < len(rag_samples_list) else "-"
        lines.append(f"| {i + 1} | {ext_val} | {rag_val} |")
    lines.append("")

    return "\n".join(lines)


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
    parser.add_argument("--runs", type=int, default=RUNS)
    parser.add_argument("--provider", default="fake")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--json-report", type=Path, default=None)
    args = parser.parse_args(argv)

    from bank_reconciliation_agent.core.llm.provider import LLMUnavailable

    try:
        report = run_benchmark(
            runs=args.runs, provider_name=args.provider, model=args.model
        )
    except (LLMUnavailable, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
