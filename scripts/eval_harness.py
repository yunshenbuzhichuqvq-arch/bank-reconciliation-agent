"""Combined baseline eval harness: System + RAG + Agent.

Produces `reports/eval_harness/baseline.md` and `baseline.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.rag.retriever import ChromaRuleStore, RuleRetriever, rule_retriever
from scripts.eval_agent import evaluate_agent_cases, load_agent_eval_cases
from scripts.eval_rag import RagEvalMode, evaluate_eval_set, load_eval_set
from scripts.eval_system import evaluate_system_batch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports/eval_harness"

HONEST_GAPS = [
    "Real LLM provider quality: Agent Eval uses FakeLLMProvider; decision quality under a real LLM (e.g. DeepSeek) is not measured by this baseline.",
    "Real embedding quality: RAG Eval uses embedding_backend=hash; real embedding (e.g. bge-m3, bge-small) retrieval quality is not measured here.",
    "LLM-as-Judge: No LLM-based evaluation of explanation completeness, reasoning quality, or natural-language audit judgment is included.",
    "Online human adoption/override rate: This offline eval does not measure how often human reviewers accept, override, or escalate system decisions in production.",
    "Production latency: End-to-end system latency and per-agent call latency are not measured in this offline eval.",
    "Production cost: LLM token usage, embedding compute cost, and infrastructure cost are not measured in this offline eval.",
]


def run_harness(
    *,
    seed: int = 20260706,
    normal_rows: int = 1000,
    embedding_backend: str = "hash",
    top_k: int = 5,
    rag_mode: RagEvalMode = "dense",
) -> dict[str, Any]:
    scenario_type = "BANK_ENTERPRISE"

    # -- System Eval ----------------------------------------------------------
    system_result = evaluate_system_batch(
        scenario_type=scenario_type,
        normal_rows=normal_rows,
        seed=seed,
    )

    # -- RAG Eval -------------------------------------------------------------
    rag_retriever = (
        rule_retriever
        if embedding_backend == settings.embedding_backend
        else RuleRetriever(
            store=ChromaRuleStore(embedding_backend=embedding_backend),
        )
    )
    rag_cases = load_eval_set()
    rag_result = evaluate_eval_set(
        rag_cases,
        retriever=rag_retriever,
        top_k=top_k,
        embedding_backend=embedding_backend,
        mode=rag_mode,
    )

    # -- Agent Eval -----------------------------------------------------------
    agent_cases = load_agent_eval_cases()
    agent_result = evaluate_agent_cases(agent_cases, provider="fake")

    # -- Combined output -------------------------------------------------------
    system_gates = system_result.get("gates", {})
    agent_gates = agent_result.get("gates", {})
    gates = _combine_gates(system_gates, agent_gates)

    return {
        "metadata": {
            "seed": seed,
            "scenario_type": scenario_type,
            "normal_rows": normal_rows,
            "embedding_backend": embedding_backend,
            "top_k": top_k,
            "rag_mode": rag_mode,
            "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "system_eval": {
            "case_count": system_result.get("case_count"),
            "metrics": system_result.get("metrics"),
            "gates": system_gates,
        },
        "rag_eval": {
            "case_count": rag_result.get("case_count"),
            "global_metrics": rag_result.get("global_metrics"),
        },
        "agent_eval": {
            "case_count": agent_result.get("case_count"),
            "metrics": agent_result.get("metrics"),
            "gates": agent_gates,
        },
        "gates": gates,
        "honest_gaps": HONEST_GAPS,
    }


def _combine_gates(
    system_gates: dict[str, object],
    agent_gates: dict[str, object],
) -> dict[str, bool]:
    sys_unsafe = system_gates.get("unsafe_auto_fix_rate", {})
    sys_violation = system_gates.get("hard_constraint_violation_rate", {})
    return {
        "system_unsafe_auto_fix_pass": (
            sys_unsafe.get("pass", True) if isinstance(sys_unsafe, dict) else True
        ),
        "system_hard_constraint_violation_pass": (
            sys_violation.get("pass", True) if isinstance(sys_violation, dict) else True
        ),
        "agent_unsafe_auto_fix_pass": agent_gates.get("unsafe_auto_fix_pass", True),
        "agent_hard_constraint_violation_pass": agent_gates.get(
            "hard_constraint_violation_pass", True
        ),
    }


def compare_harness_reports(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_meta = before["metadata"]
    after_meta = after["metadata"]

    metadata_comparison = {
        "seed_match": before_meta.get("seed") == after_meta.get("seed"),
        "normal_rows_match": before_meta.get("normal_rows") == after_meta.get("normal_rows"),
        "embedding_backend_match": before_meta.get("embedding_backend") == after_meta.get("embedding_backend"),
        "top_k_match": before_meta.get("top_k") == after_meta.get("top_k"),
        "before_rag_mode": before_meta.get("rag_mode", "dense"),
        "after_rag_mode": after_meta.get("rag_mode", "dense"),
    }

    system_deltas = _compute_metric_deltas(
        before["system_eval"].get("metrics", {}),
        after["system_eval"].get("metrics", {}),
    )
    rag_deltas = _compute_metric_deltas(
        before["rag_eval"].get("global_metrics", {}),
        after["rag_eval"].get("global_metrics", {}),
    )
    agent_deltas = _compute_metric_deltas(
        before["agent_eval"].get("metrics", {}),
        after["agent_eval"].get("metrics", {}),
    )

    before_gates = before.get("gates", {})
    after_gates = after.get("gates", {})
    gate_changes = [
        name for name in before_gates
        if before_gates.get(name) != after_gates.get(name)
    ]

    return {
        "metadata_comparison": metadata_comparison,
        "system_eval": {
            "before_summary": {
                "case_count": before["system_eval"].get("case_count"),
            },
            "after_summary": {
                "case_count": after["system_eval"].get("case_count"),
            },
            "deltas": system_deltas,
        },
        "rag_eval": {
            "before_summary": {
                "case_count": before["rag_eval"].get("case_count"),
            },
            "after_summary": {
                "case_count": after["rag_eval"].get("case_count"),
            },
            "deltas": rag_deltas,
        },
        "agent_eval": {
            "before_summary": {
                "case_count": before["agent_eval"].get("case_count"),
            },
            "after_summary": {
                "case_count": after["agent_eval"].get("case_count"),
            },
            "deltas": agent_deltas,
        },
        "gates": {
            "before": before_gates,
            "after": after_gates,
            "changes": gate_changes,
        },
        "honest_gaps": after.get("honest_gaps", []),
    }


def _compute_metric_deltas(
    before_metrics: dict[str, Any],
    after_metrics: dict[str, Any],
) -> dict[str, float | None]:
    deltas: dict[str, float | None] = {}
    all_keys = set(before_metrics) | set(after_metrics)
    for key in sorted(all_keys):
        before_val = before_metrics.get(key)
        after_val = after_metrics.get(key)
        if isinstance(before_val, (int, float)) and isinstance(after_val, (int, float)):
            deltas[key] = after_val - before_val
        else:
            deltas[key] = 0.0 if (after_val == before_val) else None
    return deltas


def write_report(
    report: dict[str, Any],
    output_dir: Path,
    *,
    report_name: str = "baseline",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{report_name}.md"
    json_path = output_dir / f"{report_name}.json"

    if report_name == "after":
        md_path.write_text(_format_after_markdown(report), encoding="utf-8")
    else:
        md_path.write_text(_format_baseline_markdown(report), encoding="utf-8")

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def write_comparison_markdown(
    comparison: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_comparison_markdown(comparison), encoding="utf-8")


def write_comparison_json(
    comparison: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _format_after_markdown(report: dict[str, Any]) -> str:
    meta = report.get("metadata", {})
    sys_eval = report.get("system_eval", {})
    rag_eval = report.get("rag_eval", {})
    agent_eval = report.get("agent_eval", {})
    gates = report.get("gates", {})

    lines = [
        "# Combined After-Run Evaluation Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Seed | `{meta.get('seed')}` |",
        f"| Scenario | `{meta.get('scenario_type')}` |",
        f"| Normal Rows | {meta.get('normal_rows')} |",
        f"| Embedding Backend | `{meta.get('embedding_backend')}` |",
        f"| Top K | {meta.get('top_k')} |",
        f"| RAG Mode | `{meta.get('rag_mode')}` |",
        f"| Evaluated At | {meta.get('evaluated_at')} |",
        "",
        "## System Eval",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    sys_metrics = sys_eval.get("metrics", {})
    for key, value in sys_metrics.items():
        lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        "## RAG Eval",
        "",
        "| Metric | Value |",
        "|---|---|",
    ])
    rag_metrics = rag_eval.get("global_metrics", {})
    for key, value in rag_metrics.items():
        lines.append(f"| {key} | {value:.4f} |")
    lines.extend([
        "",
        "## Agent Eval",
        "",
        "| Metric | Value |",
        "|---|---|",
    ])
    ag_metrics = agent_eval.get("metrics", {})
    for key, value in ag_metrics.items():
        if isinstance(value, float):
            lines.append(f"| {key} | {value:.4f} |")
        else:
            lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        "## Combined Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ])
    for gate_name, passed in gates.items():
        lines.append(f"| {gate_name} | {'PASS' if passed else 'FAIL'} |")

    lines.extend([
        "",
        "## Case Counts",
        "",
        f"- System Eval: {sys_eval.get('case_count', 'N/A')}",
        f"- RAG Eval: {rag_eval.get('case_count', 'N/A')}",
        f"- Agent Eval: {agent_eval.get('case_count', 'N/A')}",
        "",
        "## Honest Gaps / Not Measured",
        "",
    ])
    for gap in report.get("honest_gaps", []):
        lines.append(f"- {gap}")

    return "\n".join(lines)


def _format_comparison_markdown(comparison: dict[str, Any]) -> str:
    meta_comp = comparison.get("metadata_comparison", {})
    sys_comp = comparison.get("system_eval", {})
    rag_comp = comparison.get("rag_eval", {})
    agent_comp = comparison.get("agent_eval", {})
    gates_comp = comparison.get("gates", {})

    lines = [
        "# Combined Harness Comparison Report",
        "",
        "## Metadata Compatibility",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Seed Match | {meta_comp.get('seed_match')} |",
        f"| Normal Rows Match | {meta_comp.get('normal_rows_match')} |",
        f"| Embedding Backend Match | {meta_comp.get('embedding_backend_match')} |",
        f"| Top K Match | {meta_comp.get('top_k_match')} |",
        f"| Before RAG Mode | `{meta_comp.get('before_rag_mode')}` |",
        f"| After RAG Mode | `{meta_comp.get('after_rag_mode')}` |",
        "",
        "## System Eval Deltas",
        "",
        "| Metric | Δ Value |",
        "|---|---|",
    ]
    for key, delta in sys_comp.get("deltas", {}).items():
        if delta is not None:
            sign = "+" if delta > 0 else ""
            lines.append(f"| {key} | {sign}{delta:.6f} |")
    lines.extend([
        "",
        "## RAG Eval Deltas",
        "",
        "| Metric | Δ Value |",
        "|---|---|",
    ])
    for key, delta in rag_comp.get("deltas", {}).items():
        if delta is not None:
            sign = "+" if delta > 0 else ""
            lines.append(f"| {key} | {sign}{delta:.6f} |")
    lines.extend([
        "",
        "## Agent Eval Deltas",
        "",
        "| Metric | Δ Value |",
        "|---|---|",
    ])
    for key, delta in agent_comp.get("deltas", {}).items():
        if delta is not None:
            sign = "+" if delta > 0 else ""
            lines.append(f"| {key} | {sign}{delta:.6f} |")

    before_gates = gates_comp.get("before", {})
    after_gates = gates_comp.get("after", {})
    changes = gates_comp.get("changes", [])
    lines.extend([
        "",
        "## Combined Gates",
        "",
        "| Gate | Before | After |",
        "|---|---|---|",
    ])
    for gate_name in sorted(set(before_gates) | set(after_gates)):
        bv = before_gates.get(gate_name, "N/A")
        av = after_gates.get(gate_name, "N/A")
        lines.append(f"| {gate_name} | {bv} | {av} |")
    if changes:
        lines.append(f"\n⚠️ Gate changes detected: {', '.join(changes)}")
    else:
        lines.append("\nAll gates unchanged.")

    lines.extend([
        "",
        "## Honest Gaps / Not Measured",
        "",
    ])
    for gap in comparison.get("honest_gaps", []):
        lines.append(f"- {gap}")

    return "\n".join(lines)


def _format_baseline_markdown(report: dict[str, Any]) -> str:
    meta = report.get("metadata", {})
    sys_eval = report.get("system_eval", {})
    rag_eval = report.get("rag_eval", {})
    agent_eval = report.get("agent_eval", {})
    gates = report.get("gates", {})

    lines = [
        "# Combined Baseline Evaluation Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Seed | `{meta.get('seed')}` |",
        f"| Scenario | `{meta.get('scenario_type')}` |",
        f"| Normal Rows | {meta.get('normal_rows')} |",
        f"| Embedding Backend | `{meta.get('embedding_backend')}` |",
        f"| Top K | {meta.get('top_k')} |",
        f"| Evaluated At | {meta.get('evaluated_at')} |",
        "",
        "## System Eval",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    sys_metrics = sys_eval.get("metrics", {})
    for key, value in sys_metrics.items():
        lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        "## RAG Eval",
        "",
        "| Metric | Value |",
        "|---|---|",
    ])
    rag_metrics = rag_eval.get("global_metrics", {})
    for key, value in rag_metrics.items():
        lines.append(f"| {key} | {value:.4f} |")
    lines.extend([
        "",
        "## Agent Eval",
        "",
        "| Metric | Value |",
        "|---|---|",
    ])
    ag_metrics = agent_eval.get("metrics", {})
    for key, value in ag_metrics.items():
        if isinstance(value, float):
            lines.append(f"| {key} | {value:.4f} |")
        else:
            lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        "## Combined Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ])
    for gate_name, passed in gates.items():
        lines.append(f"| {gate_name} | {'PASS' if passed else 'FAIL'} |")

    lines.extend([
        "",
        "## Case Counts",
        "",
        f"- System Eval: {sys_eval.get('case_count', 'N/A')}",
        f"- RAG Eval: {rag_eval.get('case_count', 'N/A')}",
        f"- Agent Eval: {agent_eval.get('case_count', 'N/A')}",
        "",
        "## Honest Gaps / Not Measured",
        "",
        "> This offline stage does not measure everything. The following metrics are",
        "> explicitly not covered by this baseline:",
        "",
    ])
    for gap in report.get("honest_gaps", []):
        lines.append(f"- {gap}")
    lines.extend([
        "",
        "## Baseline Review Gate",
        "",
        "> This is the baseline report. opencode **must stop** after generating this report",
        "> and wait for Codex to review the metrics and update `tasks.md` with at most 1-2",
        "> optimization tasks per ADR-EH.5. No optimization may be implemented before this",
        "> review gate is passed.",
        "",
    ])
    return "\n".join(lines)


def _check_blocking_gates(gates: dict[str, bool]) -> list[str]:
    failures: list[str] = []
    if not gates.get("system_unsafe_auto_fix_pass", True):
        failures.append("system_unsafe_auto_fix_pass")
    if not gates.get("system_hard_constraint_violation_pass", True):
        failures.append("system_hard_constraint_violation_pass")
    if not gates.get("agent_unsafe_auto_fix_pass", True):
        failures.append("agent_unsafe_auto_fix_pass")
    if not gates.get("agent_hard_constraint_violation_pass", True):
        failures.append("agent_hard_constraint_violation_pass")
    return failures


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run combined three-layer baseline eval harness."
    )
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--normal-rows", type=int, default=1000)
    parser.add_argument("--embedding-backend", default="hash")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rag-mode", choices=["dense", "hybrid", "hybrid_rerank"], default="dense")
    parser.add_argument("--report-name", default="baseline")
    parser.add_argument("--compare-with", type=Path, default=None)
    parser.add_argument("--comparison-report", type=Path, default=DEFAULT_OUTPUT_DIR / "comparison.md")
    parser.add_argument("--comparison-json", type=Path, default=DEFAULT_OUTPUT_DIR / "comparison.json")
    args = parser.parse_args(argv)

    report = run_harness(
        seed=args.seed,
        normal_rows=args.normal_rows,
        embedding_backend=args.embedding_backend,
        top_k=args.top_k,
        rag_mode=args.rag_mode,
    )

    write_report(report, args.output_dir, report_name=args.report_name)
    print(json.dumps(
        {k: report[k] for k in ["metadata", "gates"]},
        ensure_ascii=False, indent=2, default=str,
    ))

    failures = _check_blocking_gates(report["gates"])
    if failures:
        print(f"\nBLOCKING GATE FAILURES: {', '.join(failures)}", file=sys.stderr)
        raise SystemExit(1)

    if args.compare_with is not None:
        before = json.loads(args.compare_with.read_text(encoding="utf-8"))
        comparison = compare_harness_reports(before=before, after=report)
        if args.comparison_report:
            write_comparison_markdown(comparison, args.comparison_report)
        if args.comparison_json:
            write_comparison_json(comparison, args.comparison_json)
        print(json.dumps({
            "comparison_summary": {
                "before_rag_mode": comparison["metadata_comparison"]["before_rag_mode"],
                "after_rag_mode": comparison["metadata_comparison"]["after_rag_mode"],
                "agent_risk_accuracy_delta": comparison["agent_eval"]["deltas"].get("risk_accuracy"),
            }
        }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
