"""System-level offline evaluation: deterministic batch + ground truth manifest + metrics."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent
from bank_reconciliation_agent.agents.trace_agent import TraceAgent
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from scripts.generate_mock_excel import build_batch


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def _build_manifest(
    bank_df: pd.DataFrame,
    clear_df: pd.DataFrame,
    expected_branches: dict[str, tuple[str | None, str | None, str]],
    *,
    scenario_type: str,
) -> list[dict[str, object]]:
    """Build a ground truth manifest case for every flow_id in the batch."""
    all_flow_ids = sorted(set(bank_df["flow_id"].tolist()) | set(clear_df["flow_id"].tolist()))
    manifest: list[dict[str, object]] = []
    for flow_id in all_flow_ids:
        if flow_id in expected_branches:
            error_type, branch, status = expected_branches[flow_id]
            manifest.append({
                "case_id": flow_id,
                "flow_id": flow_id,
                "scenario_type": scenario_type,
                "scenario_name": _scenario_name(error_type, status),
                "expected_status": status,
                "expected_error_type": error_type,
                "expected_exception_branch": branch,
                "should_auto_fix": status == "AUTO_FIXED",
                "should_require_human": status == "PENDING_HUMAN",
                "risk_label": "LOW" if status == "AUTO_FIXED" else "MEDIUM",
                "source_rule": _source_rule(error_type),
                "notes": f"anomaly case: {error_type or 'sentinel'}",
            })
        else:
            manifest.append({
                "case_id": flow_id,
                "flow_id": flow_id,
                "scenario_type": scenario_type,
                "scenario_name": "normal_auto_fixed",
                "expected_status": "AUTO_FIXED",
                "expected_error_type": None,
                "expected_exception_branch": None,
                "should_auto_fix": True,
                "should_require_human": False,
                "risk_label": "LOW",
                "source_rule": "generated_normal_pair",
                "notes": "deterministic generated normal pair",
            })
    return manifest


def _scenario_name(error_type: str | None, status: str) -> str:
    if error_type is None and status == "AUTO_FIXED":
        return "normal_auto_fixed"
    if error_type is None:
        return "sentinel_auto_fixed"
    return f"anomaly_{error_type.lower()}"


def _source_rule(error_type: str | None) -> str:
    if error_type is None:
        return "generated_sentinel_pair"
    return f"anomaly_{error_type.lower()}"


# ---------------------------------------------------------------------------
# Public API: build_system_eval_batch
# ---------------------------------------------------------------------------


def build_system_eval_batch(
    *,
    scenario_type: str = "BANK_ENTERPRISE",
    normal_rows: int = 1000,
    seed: int = 20260706,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    """Build a deterministic batch and ground truth manifest.

    Returns (bank_df, clear_df, manifest).
    """
    scenario_key = {
        "BANK_ENTERPRISE": "bank_enterprise",
        "BANK_CLEARING": "bank_clearing",
    }.get(scenario_type)
    if scenario_key is None:
        raise ValueError(f"unsupported scenario_type: {scenario_type}")

    bank_df, clear_df, expected_branches = build_batch(
        scenario=scenario_key,
        n_normal=normal_rows,
        seed=seed,
    )
    manifest = _build_manifest(
        bank_df, clear_df, expected_branches,
        scenario_type=scenario_type,
    )
    return bank_df, clear_df, manifest


# ---------------------------------------------------------------------------
# Workflow runner for non-auto cases
# ---------------------------------------------------------------------------

def _make_eval_state(
    *,
    result: ReconciliationMatchResult,
    scenario_type: str,
    bank_row_dict: dict[str, Any],
    clear_row_dict: dict[str, Any],
) -> ReconciliationState:
    """Build a ReconciliationState for running the workflow in eval mode."""
    def _opt_str(val: Decimal | None) -> str | None:
        return str(val) if val is not None else None

    return {
        "task_id": "eval-system",
        "user_id": "demo_user",
        "thread_id": "eval-system",
        "scenario_type": scenario_type,
        "current_queue_id": None,
        "source_a_item": bank_row_dict,
        "source_b_item": clear_row_dict,
        "error_type": result.error_type,
        "exception_branch": result.exception_branch,
        "math_result": {
            "bank_amount": _opt_str(result.bank_amount),
            "clear_amount": _opt_str(result.clear_amount),
            "amount_diff": _opt_str(result.amount_diff),
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
        "rag_query": f"{result.error_type or ''} reconciliation eval query",
        "t1_candidate": result.t1_candidate,
        "fuzzy_candidate": result.fuzzy_candidate,
    }


def _run_workflow_for_anomaly(
    result: ReconciliationMatchResult,
    *,
    scenario_type: str,
    bank_df: pd.DataFrame,
    clear_df: pd.DataFrame,
) -> ReconciliationState:
    """Run the workflow for a non-auto case using FakeLLMProvider."""
    fake = FakeLLMProvider()
    bank_rows = bank_df[bank_df["flow_id"] == result.flow_id]
    clear_rows = clear_df[clear_df["flow_id"] == result.flow_id]
    bank_row_dict = bank_rows.iloc[0].to_dict() if not bank_rows.empty else {"flow_id": result.flow_id}
    clear_row_dict = (
        clear_rows.iloc[0].to_dict() if not clear_rows.empty else {"flow_id": result.flow_id}
    )

    state = _make_eval_state(
        result=result,
        scenario_type=scenario_type,
        bank_row_dict=bank_row_dict,
        clear_row_dict=clear_row_dict,
    )
    return run_item(
        state,
        extraction_agent=ExtractionAgent(provider=fake),
        trace_agent=TraceAgent(provider=fake),
        audit_agent=AuditAgent(provider=fake),
    )


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _compute_metrics(
    manifest: list[dict[str, object]],
    results: list[ReconciliationMatchResult],
    workflow_states: dict[str, ReconciliationState],
) -> dict[str, object]:
    """Compute system eval metrics from manifest expectations and actual results."""
    results_by_flow = {r.flow_id: r for r in results}
    case_count = len(manifest)

    # Classification accuracy: fraction of cases where actual status matches expected
    classification_correct = 0
    # Branch accuracy: fraction of anomaly cases where error_type and branch match
    branch_total = 0
    branch_correct = 0
    auto_fix_count = 0
    pending_human_count = 0
    unsafe_auto_fix_count = 0
    hard_constraint_violations = 0

    for case in manifest:
        flow_id = case["flow_id"]
        result = results_by_flow.get(flow_id)
        if result is None:
            continue

        actual_status = result.status
        expected_status = case["expected_status"]

        if actual_status == expected_status:
            classification_correct += 1

        if actual_status == "AUTO_FIXED":
            auto_fix_count += 1

        if actual_status == "PENDING_HUMAN":
            pending_human_count += 1

        # Branch accuracy: only for cases with expected error_type
        if case["expected_error_type"] is not None:
            branch_total += 1
            if (
                result.error_type == case["expected_error_type"]
                and result.exception_branch == case["expected_exception_branch"]
            ):
                branch_correct += 1

        # Safety: auto-fix on a case that should require human
        if case["should_require_human"] and actual_status == "AUTO_FIXED":
            unsafe_auto_fix_count += 1

        # Hard constraint: non-human decision without evidence for anomaly case
        if case["expected_error_type"] is not None and actual_status == "AUTO_FIXED":
            hard_constraint_violations += 1

    # Fallback trigger rate: fraction of workflow-processed cases that triggered fallback
    fallback_trigger_count = 0
    workflow_case_count = len(workflow_states)
    for _flow_id, ws in workflow_states.items():
        fallback_path = ws.get("fallback_path", "")
        if fallback_path and fallback_path != "L1":
            fallback_trigger_count += 1

    classification_accuracy = (
        classification_correct / case_count if case_count > 0 else 0.0
    )
    branch_accuracy = (
        branch_correct / branch_total if branch_total > 0 else 0.0
    )
    auto_fix_rate = auto_fix_count / case_count if case_count > 0 else 0.0
    pending_human_rate = pending_human_count / case_count if case_count > 0 else 0.0
    fallback_trigger_rate = (
        fallback_trigger_count / workflow_case_count if workflow_case_count > 0 else 0.0
    )
    unsafe_auto_fix_rate = (
        unsafe_auto_fix_count / case_count if case_count > 0 else 0.0
    )
    hard_constraint_violation_rate = (
        hard_constraint_violations / case_count if case_count > 0 else 0.0
    )

    return {
        "case_count": case_count,
        "auto_fix_rate": round(auto_fix_rate, 6),
        "classification_accuracy": round(classification_accuracy, 6),
        "branch_accuracy": round(branch_accuracy, 6),
        "pending_human_rate": round(pending_human_rate, 6),
        "fallback_trigger_rate": round(fallback_trigger_rate, 6),
        "unsafe_auto_fix_rate": round(unsafe_auto_fix_rate, 6),
        "hard_constraint_violation_rate": round(hard_constraint_violation_rate, 6),
    }


def _compute_gates(metrics: dict[str, object]) -> dict[str, object]:
    """Return gate pass/fail for blocking metrics."""
    return {
        "unsafe_auto_fix_rate": {
            "value": metrics["unsafe_auto_fix_rate"],
            "threshold": 0,
            "pass": metrics["unsafe_auto_fix_rate"] == 0,
        },
        "hard_constraint_violation_rate": {
            "value": metrics["hard_constraint_violation_rate"],
            "threshold": 0,
            "pass": metrics["hard_constraint_violation_rate"] == 0,
        },
    }


# ---------------------------------------------------------------------------
# Public API: evaluate_system_batch
# ---------------------------------------------------------------------------


def evaluate_system_batch(
    *,
    scenario_type: str = "BANK_ENTERPRISE",
    normal_rows: int = 1000,
    seed: int = 20260706,
) -> dict[str, object]:
    """Run the full system evaluation and return structured results.

    Returns a dict with keys: seed, scenario_type, normal_rows, case_count,
    manifest, metrics, gates, evaluated_at.
    """
    bank_df, clear_df, manifest = build_system_eval_batch(
        scenario_type=scenario_type,
        normal_rows=normal_rows,
        seed=seed,
    )

    # Step 1: Classify all rows
    svc = ReconciliationService()
    results = svc._build_match_results(bank_df, clear_df, scenario_type=scenario_type)

    # Step 2: Run workflow only for non-AUTO_FIXED cases
    workflow_states: dict[str, ReconciliationState] = {}
    for result in results:
        if result.status != "AUTO_FIXED":
            try:
                ws = _run_workflow_for_anomaly(
                    result,
                    scenario_type=scenario_type,
                    bank_df=bank_df,
                    clear_df=clear_df,
                )
                workflow_states[result.flow_id] = ws
            except Exception:
                # If workflow fails, still record the case with a fallback state
                workflow_states[result.flow_id] = {
                    "fallback_path": "AI_ERROR->HUMAN",
                }

    # Step 3: Compute metrics
    metrics = _compute_metrics(manifest, results, workflow_states)
    gates = _compute_gates(metrics)

    return {
        "seed": seed,
        "scenario_type": scenario_type,
        "normal_rows": normal_rows,
        "case_count": metrics["case_count"],
        "manifest": manifest,
        "metrics": metrics,
        "gates": gates,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def write_markdown_report(result: dict[str, object], output_path: str | Path) -> None:
    """Write a Markdown report summarizing the system evaluation."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    metrics = result["metrics"]
    gates = result["gates"]
    manifest = result["manifest"]

    normal_count = sum(1 for c in manifest if c["expected_status"] == "AUTO_FIXED")
    anomaly_count = sum(1 for c in manifest if c["expected_status"] != "AUTO_FIXED")

    lines = [
        "# System Evaluation Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Seed | `{result['seed']}` |",
        f"| Scenario | `{result['scenario_type']}` |",
        f"| Normal Rows | {result['normal_rows']} |",
        f"| Total Cases | {result['case_count']} |",
        f"| Normal Cases | {normal_count} |",
        f"| Anomaly Cases | {anomaly_count} |",
        f"| Evaluated At | {result['evaluated_at']} |",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key, value in metrics.items():
        lines.append(f"| {key} | {value} |")

    lines.extend([
        "",
        "## Gates",
        "",
        "| Gate | Value | Threshold | Pass |",
        "|---|---|---|---|",
    ])
    for gate_name, gate_info in gates.items():
        pass_str = "✅" if gate_info["pass"] else "❌"
        lines.append(
            f"| {gate_name} | {gate_info['value']} | {gate_info['threshold']} | {pass_str} |"
        )

    lines.extend([
        "",
        "## Anomaly Distribution",
        "",
        "| Error Type | Count |",
        "|---|---|",
    ])
    error_dist: dict[str, int] = {}
    for case in manifest:
        et = case.get("expected_error_type")
        if et is not None:
            error_dist[et] = error_dist.get(et, 0) + 1
    for et, count in sorted(error_dist.items()):
        lines.append(f"| {et} | {count} |")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json_report(result: dict[str, object], output_path: str | Path) -> None:
    """Write a JSON report containing seed, scenario, metrics, gates, and manifest."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Use a serializable subset (exclude heavy manifest from top level if needed)
    output = {
        "seed": result["seed"],
        "scenario_type": result["scenario_type"],
        "normal_rows": result["normal_rows"],
        "case_count": result["case_count"],
        "manifest": result["manifest"],
        "metrics": result["metrics"],
        "gates": result["gates"],
        "evaluated_at": result["evaluated_at"],
    }
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="System-level offline evaluation")
    parser.add_argument(
        "--scenario-type", default="BANK_ENTERPRISE",
        help="Scenario type (default: BANK_ENTERPRISE)",
    )
    parser.add_argument(
        "--normal-rows", type=int, default=1000,
        help="Number of normal rows to generate (default: 1000)",
    )
    parser.add_argument(
        "--seed", type=int, default=20260706,
        help="Random seed for deterministic generation (default: 20260706)",
    )
    parser.add_argument(
        "--report", default="reports/system_eval.md",
        help="Path for Markdown report output",
    )
    parser.add_argument(
        "--json-report", default="reports/system_eval_metrics.json",
        help="Path for JSON report output",
    )
    args = parser.parse_args(argv)

    print(f"Running system eval: scenario={args.scenario_type}, "
          f"normal_rows={args.normal_rows}, seed={args.seed}")

    result = evaluate_system_batch(
        scenario_type=args.scenario_type,
        normal_rows=args.normal_rows,
        seed=args.seed,
    )

    metrics = result["metrics"]
    gates = result["gates"]

    print(f"\nResults ({result['case_count']} cases):")
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    print("\nGates:")
    all_pass = True
    for gate_name, gate_info in gates.items():
        status = "PASS" if gate_info["pass"] else "FAIL"
        print(f"  {gate_name}: {gate_info['value']} (threshold={gate_info['threshold']}) [{status}]")
        if not gate_info["pass"]:
            all_pass = False

    write_markdown_report(result, args.report)
    print(f"\nMarkdown report written to {args.report}")

    write_json_report(result, args.json_report)
    print(f"JSON report written to {args.json_report}")

    if not all_pass:
        print("\n⚠️  One or more gates FAILED.")
        sys.exit(1)
    else:
        print("\n✅ All gates passed.")


if __name__ == "__main__":
    main()
