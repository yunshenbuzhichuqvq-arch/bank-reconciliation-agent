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
from scripts.eval_rag import evaluate_eval_set, load_eval_set
from scripts.eval_system import evaluate_system_batch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports/eval_harness"


def run_harness(
    *,
    seed: int = 20260706,
    normal_rows: int = 1000,
    embedding_backend: str = "hash",
    top_k: int = 5,
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


def write_baseline_markdown(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "baseline.md"
    md_path.write_text(_format_baseline_markdown(report), encoding="utf-8")


def write_baseline_json(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "baseline.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


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
    args = parser.parse_args(argv)

    report = run_harness(
        seed=args.seed,
        normal_rows=args.normal_rows,
        embedding_backend=args.embedding_backend,
        top_k=args.top_k,
    )
    write_baseline_markdown(report, args.output_dir)
    write_baseline_json(report, args.output_dir)
    print(json.dumps(
        {k: report[k] for k in ["metadata", "gates"]},
        ensure_ascii=False, indent=2, default=str,
    ))

    failures = _check_blocking_gates(report["gates"])
    if failures:
        print(f"\nBLOCKING GATE FAILURES: {', '.join(failures)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
