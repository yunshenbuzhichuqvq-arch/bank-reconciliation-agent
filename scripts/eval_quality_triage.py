from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HARNESS_COMPARISON = PROJECT_ROOT / "reports/eval_harness/comparison.json"
DEFAULT_RAG_MATRIX = PROJECT_ROOT / "reports/rag_quality_matrix.json"
DEFAULT_AGENT_REAL_JSON = PROJECT_ROOT / "reports/agent_eval_deepseek_flash_metrics.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "reports/real_quality_triage.md"
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "reports/real_quality_triage.json"

FindingCategory = Literal[
    "measured_pass",
    "measured_gap",
    "environment_gap",
    "deferred_online_metric",
    "out_of_scope",
]


def build_triage_summary(
    *,
    harness_comparison: dict[str, Any],
    rag_matrix: dict[str, Any],
    agent_real_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    _add_system_eval_findings(harness_comparison, findings)
    _add_rag_matrix_findings(rag_matrix, findings)
    _add_agent_real_findings(agent_real_report, findings)
    _add_deferred_online_metrics(findings)
    _add_out_of_scope_findings(findings)

    recommendations = _build_recommendations(findings, rag_matrix, agent_real_report)

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_reports": _build_source_reports(harness_comparison, rag_matrix, agent_real_report),
        "findings": findings,
        "next_stage_recommendations": recommendations,
    }


def _add_system_eval_findings(
    harness_comparison: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    after_gates = harness_comparison.get("gates", {}).get("after", {})
    if after_gates:
        all_pass = all(after_gates.values())
        category: FindingCategory = "measured_pass" if all_pass else "measured_gap"
        findings.append({
            "category": category,
            "area": "default_fake_hash_gates",
            "summary": (
                "Default offline safety gates (system + agent) remain passing."
                if all_pass
                else "One or more default offline safety gates failed."
            ),
            "evidence": {
                "gates": after_gates,
                "boundary": "offline, fake-provider, hash embedding",
            },
        })


def _add_rag_matrix_findings(
    rag_matrix: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    rows = rag_matrix.get("rows", {})
    for backend, row in rows.items():
        status = row.get("status")

        if backend == "hash":
            if status == "measured":
                _add_hash_rag_finding(row, findings)
            continue

        if status != "measured":
            findings.append({
                "category": "environment_gap",
                "area": f"rag_{backend}",
                "summary": f"RAG backend {backend} is {status} ({row.get('reason', 'unknown')}).",
                "evidence": {
                    "requested_backend": backend,
                    "effective_backend": row.get("effective_backend"),
                    "status": status,
                    "reason": row.get("reason"),
                },
            })
        else:
            selected_mode = row["selected_mode"]
            gm = row["modes"][selected_mode]["global_metrics"]
            if _below_prd_targets(gm):
                findings.append({
                    "category": "measured_gap",
                    "area": f"rag_{backend}_{selected_mode}",
                    "summary": (
                        f"RAG backend {backend} ({selected_mode}) measured but below "
                        f"PRD targets: Recall@5={gm.get('recall_at_5', 0):.3f}, "
                        f"MRR={gm.get('mrr', 0):.3f}, "
                        f"NDCG@5={gm.get('ndcg_at_5', 0):.3f}"
                    ),
                    "evidence": {
                        "backend": backend,
                        "effective_backend": row.get("effective_backend"),
                        "selected_mode": selected_mode,
                        "metrics": gm,
                    },
                })
            else:
                findings.append({
                    "category": "measured_pass",
                    "area": f"rag_{backend}_{selected_mode}",
                    "summary": (
                        f"RAG backend {backend} ({selected_mode}) meets PRD targets."
                    ),
                    "evidence": {
                        "backend": backend,
                        "effective_backend": row.get("effective_backend"),
                        "selected_mode": selected_mode,
                        "metrics": gm,
                    },
                })


def _add_hash_rag_finding(
    row: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    selected_mode = row["selected_mode"]
    gm = row["modes"][selected_mode]["global_metrics"]
    if _below_prd_targets(gm):
        findings.append({
            "category": "measured_gap",
            "area": "rag_hash",
            "summary": (
                f"RAG hash baseline ({selected_mode}) below PRD targets: "
                f"Recall@5={gm.get('recall_at_5', 0):.3f}, "
                f"MRR={gm.get('mrr', 0):.3f}, "
                f"NDCG@5={gm.get('ndcg_at_5', 0):.3f}"
            ),
            "evidence": {
                "backend": "hash",
                "selected_mode": selected_mode,
                "metrics": gm,
            },
        })
    else:
        findings.append({
            "category": "measured_pass",
            "area": "rag_hash",
            "summary": (
                f"RAG hash baseline ({selected_mode}) meets PRD targets."
            ),
            "evidence": {
                "backend": "hash",
                "selected_mode": selected_mode,
                "metrics": gm,
            },
        })


def _add_agent_real_findings(
    agent_real_report: dict[str, Any] | None,
    findings: list[dict[str, Any]],
) -> None:
    if agent_real_report is None:
        findings.append({
            "category": "environment_gap",
            "area": "real_llm_agent_eval",
            "summary": (
                "DeepSeek Agent Eval report is not present. "
                "Real LLM quality is not measured."
            ),
            "evidence": {
                "report_present": False,
                "hint": (
                    "Run: uv run python -m scripts.eval_agent "
                    "--cases data/agent_eval_cases.json --provider deepseek "
                    "--model deepseek-v4-flash "
                    "--report reports/agent_eval_deepseek_flash.md "
                    "--json-report reports/agent_eval_deepseek_flash_metrics.json"
                ),
            },
        })
        return

    provider_eff = agent_real_report.get("provider_effective", "")
    real_call = agent_real_report.get("real_provider_call", False)
    if provider_eff != "deepseek" or not real_call:
        findings.append({
            "category": "environment_gap",
            "area": "real_llm_agent_eval",
            "summary": (
                "DeepSeek Agent Eval report exists but is not trusted: "
                f"provider_effective={provider_eff}, "
                f"real_provider_call={real_call}."
            ),
            "evidence": {
                "report_present": True,
                "provider_effective": provider_eff,
                "real_provider_call": real_call,
                "trusted": False,
            },
        })
        return

    unsafe = agent_real_report.get("agent_unsafe_auto_fix_rate", 0.0)
    hard = agent_real_report.get("agent_hard_constraint_violation_rate", 0.0)

    gates = agent_real_report.get("gates", {})
    if unsafe > 0 or hard > 0:
        findings.append({
            "category": "measured_gap",
            "area": "real_llm_agent_safety",
            "summary": (
                "DeepSeek Agent Eval has safety violations: "
                f"unsafe_auto_fix_rate={unsafe:.3f}, "
                f"hard_constraint_violation_rate={hard:.3f}"
            ),
            "evidence": {
                "provider_effective": provider_eff,
                "real_provider_call": real_call,
                "unsafe_auto_fix_rate": unsafe,
                "hard_constraint_violation_rate": hard,
                "gates": gates,
            },
        })
    else:
        findings.append({
            "category": "measured_pass",
            "area": "real_llm_agent_eval",
            "summary": (
                "DeepSeek Agent Eval safety gates pass with trusted real provider."
            ),
            "evidence": {
                "provider_effective": provider_eff,
                "real_provider_call": real_call,
                "unsafe_auto_fix_rate": unsafe,
                "hard_constraint_violation_rate": hard,
                "gates": gates,
                "trusted": True,
            },
        })

    case_count = agent_real_report.get("agent_case_count", 0)
    risk_acc = agent_real_report.get("agent_risk_accuracy")
    dec_acc = agent_real_report.get("agent_decision_accuracy")
    if risk_acc is not None and risk_acc < 1.0:
        findings.append({
            "category": "measured_gap",
            "area": "real_llm_agent_quality",
            "summary": (
                f"DeepSeek Agent risk_accuracy={risk_acc:.3f} below 1.0 "
                f"(case_count={case_count})."
            ),
            "evidence": {
                "risk_accuracy": risk_acc,
                "decision_accuracy": dec_acc,
                "case_count": case_count,
            },
        })


def _add_deferred_online_metrics(findings: list[dict[str, Any]]) -> None:
    deferred = [
        {
            "area": "online_adoption",
            "summary": (
                "Online human adoption / override rate is not measured "
                "in offline eval."
            ),
        },
        {
            "area": "production_latency",
            "summary": (
                "Production end-to-end latency and per-agent call latency "
                "are not measured."
            ),
        },
        {
            "area": "production_cost",
            "summary": (
                "Production LLM token usage, embedding compute cost, and "
                "infrastructure cost are not measured."
            ),
        },
    ]
    for item in deferred:
        findings.append({
            "category": "deferred_online_metric",
            **item,
            "evidence": {},
        })


def _add_out_of_scope_findings(findings: list[dict[str, Any]]) -> None:
    findings.append({
        "category": "out_of_scope",
        "area": "llm_as_judge",
        "summary": (
            "LLM-as-Judge evaluation of explanation completeness, reasoning "
            "quality, or natural-language audit judgment is not included."
        ),
        "evidence": {},
    })
    findings.append({
        "category": "out_of_scope",
        "area": "immediate_remediation",
        "summary": (
            "Automatic remediation of observed misses is out of scope in this "
            "triage stage."
        ),
        "evidence": {},
    })


def _build_recommendations(
    findings: list[dict[str, Any]],
    rag_matrix: dict[str, Any],
    agent_real_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    has_rag_gap = any(
        f["area"] == "rag_hash" and f["category"] == "measured_gap"
        for f in findings
    )
    non_hash_env_gaps = [
        f["area"] for f in findings
        if f["area"].startswith("rag_") and f["area"] != "rag_hash"
        and f["category"] == "environment_gap"
    ]
    has_real_agent_env_gap = any(
        f["area"] == "real_llm_agent_eval" and f["category"] == "environment_gap"
        for f in findings
    )
    has_real_agent_safety_gap = any(
        f["area"] == "real_llm_agent_safety" and f["category"] == "measured_gap"
        for f in findings
    )

    if has_rag_gap:
        recommendations.append({
            "target": "rag",
            "reason": (
                "RAG hash baseline is below PRD targets. Consider tuning "
                "chunk structure or retrieval parameters."
            ),
            "scope_hint": (
                "Pick one measured miss bucket; do not relabel eval data to "
                "fit output."
            ),
        })

    if non_hash_env_gaps:
        recommendations.append({
            "target": "rag",
            "reason": (
                "Real embedding backends are not measured. Set up "
                "sentence-transformers and rerun with --real-backend-policy auto."
            ),
            "scope_hint": (
                "Install sentence-transformers, then compare real embedding "
                "quality before changing production defaults."
            ),
        })

    if has_real_agent_env_gap:
        recommendations.append({
            "target": "agent",
            "reason": (
                "Real LLM (DeepSeek) agent quality is not measured. "
                "Run the DeepSeek eval command when credentials are available."
            ),
            "scope_hint": (
                "Do not tune prompts before measuring real DeepSeek behavior "
                "on the existing eval set."
            ),
        })

    if has_real_agent_safety_gap:
        recommendations.append({
            "target": "agent",
            "reason": (
                "DeepSeek agent shows safety violations. "
                "Investigate unsafe auto-fix or hard constraint cases."
            ),
            "scope_hint": (
                "Examine specific failing cases before changing safety logic."
            ),
        })

    if not recommendations:
        recommendations.append({
            "target": "general",
            "reason": (
                "All measurable quality indicators are passing. "
                "Deferred online metrics remain unmeasured."
            ),
            "scope_hint": (
                "Consider adding online adoption / latency / cost instrumentation."
            ),
        })

    return recommendations


def _below_prd_targets(gm: dict[str, Any]) -> bool:
    return (
        gm.get("recall_at_5", 0) < 0.85
        or gm.get("mrr", 0) < 0.70
        or gm.get("ndcg_at_5", 0) < 0.78
    )


def _build_source_reports(
    harness_comparison: dict[str, Any],
    rag_matrix: dict[str, Any],
    agent_real_report: dict[str, Any] | None,
) -> dict[str, str | None]:
    return {
        "harness_comparison": harness_comparison.get(
            "_source_path",
            "reports/eval_harness/comparison.json",
        ),
        "rag_matrix": rag_matrix.get(
            "_source_path",
            "reports/rag_quality_matrix.json",
        ),
        "agent_real_json": (
            agent_real_report.get("_source_path")
            if agent_real_report
            else None
        ),
    }


def write_triage_markdown(summary: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_triage_markdown(summary), encoding="utf-8")


def write_triage_json(summary: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_triage_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Real Quality Triage Summary",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Evaluated At | {summary.get('evaluated_at', 'N/A')} |",
    ]
    source_reports = summary.get("source_reports", {})
    lines.append(
        f"| Harness Comparison | `{source_reports.get('harness_comparison', 'N/A')}` |"
    )
    lines.append(
        f"| RAG Matrix | `{source_reports.get('rag_matrix', 'N/A')}` |"
    )
    agent_src = source_reports.get("agent_real_json") or "(not present)"
    lines.append(f"| Agent Real JSON | `{agent_src}` |")
    lines.append("")

    findings = summary.get("findings", [])
    by_category: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        cat = f.get("category", "unknown")
        by_category.setdefault(cat, []).append(f)

    lines.append("## Findings")
    lines.append("")

    category_order = [
        "measured_pass", "measured_gap", "environment_gap",
        "deferred_online_metric", "out_of_scope",
    ]
    category_labels = {
        "measured_pass": "Measured Pass",
        "measured_gap": "Measured Gap",
        "environment_gap": "Environment Gap",
        "deferred_online_metric": "Deferred Online Metric",
        "out_of_scope": "Out of Scope",
    }

    for cat in category_order:
        items = by_category.get(cat, [])
        if not items:
            continue
        lines.append(f"### {category_labels.get(cat, cat)} ({len(items)})")
        lines.append("")
        for f in items:
            area = f.get("area", "unknown")
            summary_text = f.get("summary", "")
            evidence = f.get("evidence", {})
            lines.append(f"- **{area}**: {summary_text}")
            if evidence:
                lines.append(f"  - Evidence: {json.dumps(evidence, ensure_ascii=False)}")
        lines.append("")

    recommendations = summary.get("next_stage_recommendations", [])
    if recommendations:
        lines.append("## Next Stage Recommendations")
        lines.append("")
        for idx, rec in enumerate(recommendations, 1):
            lines.append(f"{idx}. **{rec.get('target', 'unknown')}**: {rec.get('reason', '')}")
            scope = rec.get("scope_hint", "")
            if scope:
                lines.append(f"   - Scope: {scope}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate real-quality triage summary from existing reports."
    )
    parser.add_argument(
        "--harness-comparison", type=Path, default=DEFAULT_HARNESS_COMPARISON,
    )
    parser.add_argument(
        "--rag-matrix", type=Path, default=DEFAULT_RAG_MATRIX,
    )
    parser.add_argument(
        "--agent-real-json", type=Path, default=None,
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--json-output", type=Path, default=DEFAULT_JSON_OUTPUT,
    )
    args = parser.parse_args(argv)

    harness_comparison = json.loads(
        args.harness_comparison.read_text(encoding="utf-8")
    )
    harness_comparison["_source_path"] = str(args.harness_comparison)

    rag_matrix = json.loads(args.rag_matrix.read_text(encoding="utf-8"))
    rag_matrix["_source_path"] = str(args.rag_matrix)

    agent_real_report: dict[str, Any] | None = None
    agent_real_path: Path | None = args.agent_real_json
    if agent_real_path is not None and agent_real_path.exists():
        try:
            agent_real_report = json.loads(
                agent_real_path.read_text(encoding="utf-8")
            )
            agent_real_report["_source_path"] = str(agent_real_path)
        except (json.JSONDecodeError, OSError):
            pass

    summary = build_triage_summary(
        harness_comparison=harness_comparison,
        rag_matrix=rag_matrix,
        agent_real_report=agent_real_report,
    )

    if args.output:
        write_triage_markdown(summary, args.output)
    if args.json_output:
        write_triage_json(summary, args.json_output)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
