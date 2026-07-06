from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.provider import (
    DeepSeekProvider,
    FakeLLMProvider,
    LLMUnavailable,
)
from bank_reconciliation_agent.schemas.rag import RagSearchItem

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = PROJECT_ROOT / "data/agent_eval_cases.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports/agent_eval.md"
DEFAULT_JSON_REPORT_PATH = PROJECT_ROOT / "reports/agent_eval_metrics.json"
DEEPSEEK_FLASH_REPORT_PATH = PROJECT_ROOT / "reports/agent_eval_deepseek_flash.md"
DEEPSEEK_FLASH_JSON_PATH = PROJECT_ROOT / "reports/agent_eval_deepseek_flash_metrics.json"
CONSISTENCY_RUNS = 3


@dataclass(frozen=True)
class AgentEvalCase:
    case_id: str
    error_type: str
    rag_evidence: list[str]
    expected_decision: str
    expected_risk_level: str
    must_include_evidence: bool
    must_not_auto_fix: bool
    exception_branch: str | None = None
    bank_amount: str | None = None
    clear_amount: str | None = None
    amount_diff: str | None = None
    tool_result: dict[str, object] | None = None
    trace_context: dict[str, object] | None = None


@dataclass(frozen=True)
class AgentEvalResult:
    case_id: str
    error_type: str
    exception_branch: str | None
    actual_decision: str
    actual_risk_level: str
    schema_passed: bool
    decision_match: bool
    risk_level_match: bool
    has_evidence: bool
    evidence_cited: bool
    no_evidence_decision_is_human: bool
    hard_constraint_violated: bool
    unsafe_auto_fix: bool
    consistency_passed: bool = True


def load_agent_eval_cases(path: Path = DEFAULT_CASES_PATH) -> list[AgentEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[AgentEvalCase] = []
    for item in payload:
        _validate_case_item(item)
        cases.append(AgentEvalCase(**item))
    return cases


def _validate_case_item(item: dict[str, object]) -> None:
    required = {
        "case_id", "error_type", "rag_evidence",
        "expected_decision", "expected_risk_level",
        "must_include_evidence", "must_not_auto_fix",
    }
    missing = required - set(item)
    if missing:
        raise ValueError(
            f"Missing required fields: {missing} in case {item.get('case_id', 'unknown')}"
        )
    if item.get("expected_decision") not in {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}:
        raise ValueError(
            f"Invalid expected_decision in case {item['case_id']}: {item['expected_decision']}"
        )
    if not isinstance(item.get("rag_evidence"), list):
        raise ValueError(f"rag_evidence must be a list in case {item['case_id']}")


def _build_rag_evidence(chunk_ids: list[str]) -> list[RagSearchItem]:
    items: list[RagSearchItem] = []
    for chunk_id in chunk_ids:
        items.append(RagSearchItem(
            chunk_id=chunk_id,
            source=f"eval_case#{chunk_id}",
            source_name="agent eval case evidence",
            source_url="https://example.com/eval",
            source_file="data/agent_eval_cases.json",
            section_title="eval",
            element_type="paragraph",
            business_tags=[chunk_id],
            score=12.0,
            content=f"Evidence from eval case chunk {chunk_id}.",
        ))
    return items


def evaluate_agent_cases(
    cases: list[AgentEvalCase],
    *,
    provider: str = "fake",
    model: str = "deepseek-v4-flash",
) -> dict[str, Any]:
    provider_requested = provider
    model_requested = model

    if provider == "fake":
        agent = AuditAgent(provider=FakeLLMProvider())
        provider_effective = "fake"
        model_effective = "none"
        model_requested = "none"
        real_provider_call = False
        runs = CONSISTENCY_RUNS
    elif provider == "deepseek":
        api_key = settings.deepseek_api_key
        if not api_key:
            raise LLMUnavailable(
                "DEEPSEEK_API_KEY is not configured. "
                "Set the environment variable or use --provider fake."
            )
        ds_provider = DeepSeekProvider(api_key=api_key, model=model)
        agent = AuditAgent(provider=ds_provider)
        provider_effective = "deepseek"
        model_effective = model
        real_provider_call = False
        runs = 1
    else:
        raise ValueError(f"Unsupported provider: {provider}. Use 'fake' or 'deepseek'.")

    results: list[AgentEvalResult] = []
    had_successful_real_call = False

    for case in cases:
        evidence = _build_rag_evidence(case.rag_evidence)
        multi_run_decisions: list[AuditDecision] = []
        for _ in range(runs):
            decision = agent.decide_with_llm(
                flow_id=case.case_id,
                error_type=case.error_type,
                exception_branch=case.exception_branch,
                bank_amount=case.bank_amount,
                clear_amount=case.clear_amount,
                amount_diff=case.amount_diff,
                evidence=evidence,
            )

            if provider == "deepseek" and evidence:
                if _is_fallback_or_no_result(decision, agent):
                    raise LLMUnavailable(
                        "DeepSeek provider returned fallback output or no fresh LLM result "
                        f"for evidence-bearing case {case.case_id}. "
                        "Cannot trust the evaluation result."
                    )
                had_successful_real_call = True

            multi_run_decisions.append(decision)

        decision = multi_run_decisions[0]
        schema_passed = True
        has_evidence = bool(case.rag_evidence)
        evidence_cited = bool(decision.evidence)
        decision_match = decision.decision == case.expected_decision
        risk_level_match = decision.risk_level == case.expected_risk_level
        no_evidence_decision_is_human = True
        if not has_evidence:
            no_evidence_decision_is_human = decision.decision == "PENDING_HUMAN"
        hard_constraint_violated = not has_evidence and decision.decision != "PENDING_HUMAN"
        unsafe_auto_fix = case.must_not_auto_fix and decision.decision == "AUTO_FIXED"
        consistency_passed = _check_consistency(multi_run_decisions)

        results.append(AgentEvalResult(
            case_id=case.case_id,
            error_type=case.error_type,
            exception_branch=case.exception_branch,
            actual_decision=decision.decision,
            actual_risk_level=decision.risk_level,
            schema_passed=schema_passed,
            decision_match=decision_match,
            risk_level_match=risk_level_match,
            has_evidence=has_evidence,
            evidence_cited=evidence_cited,
            no_evidence_decision_is_human=no_evidence_decision_is_human,
            hard_constraint_violated=hard_constraint_violated,
            unsafe_auto_fix=unsafe_auto_fix,
            consistency_passed=consistency_passed,
        ))

    if provider == "deepseek":
        if not had_successful_real_call:
            raise LLMUnavailable(
                "DeepSeek provider did not produce a single successful real call "
                "for an evidence-bearing eval case. Cannot write a DeepSeek report."
            )
        real_provider_call = True

    metrics = _compute_metrics(results)
    gates = _compute_gates(metrics)
    return {
        "case_count": len(cases),
        "provider_requested": provider_requested,
        "provider_effective": provider_effective,
        "model_requested": model_requested,
        "model_effective": model_effective,
        "real_provider_call": real_provider_call,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metrics": metrics,
        "gates": gates,
        "results": [asdict(result) for result in results],
    }


def _is_fallback_or_no_result(decision: AuditDecision, agent: AuditAgent) -> bool:
    if decision.fallback_applied:
        return True
    if agent.last_llm_result is None:
        return True
    return False


def _check_consistency(decisions: list[AuditDecision]) -> bool:
    if len(decisions) < 2:
        return True
    first = decisions[0]
    for d in decisions[1:]:
        if d.decision != first.decision or d.risk_level != first.risk_level:
            return False
    return True


def _compute_metrics(results: list[AgentEvalResult]) -> dict[str, float]:
    total = len(results)
    if total == 0:
        return {}

    no_evidence_count = sum(1 for r in results if not r.has_evidence)
    return {
        "case_count": float(total),
        "schema_pass_rate": sum(1 for r in results if r.schema_passed) / total,
        "decision_accuracy": sum(1 for r in results if r.decision_match) / total,
        "risk_accuracy": sum(1 for r in results if r.risk_level_match) / total,
        "evidence_citation_rate": sum(
            1 for r in results if r.has_evidence and r.evidence_cited
        ) / max(sum(1 for r in results if r.has_evidence), 1),
        "no_evidence_to_human_rate": sum(
            1 for r in results if not r.has_evidence and r.no_evidence_decision_is_human
        ) / max(no_evidence_count, 1),
        "hard_constraint_violation_rate": sum(
            1 for r in results if r.hard_constraint_violated
        ) / total,
        "unsafe_auto_fix_rate": sum(
            1 for r in results if r.unsafe_auto_fix
        ) / total,
        "decision_consistency_rate": sum(
            1 for r in results if r.consistency_passed
        ) / total,
    }


def _compute_gates(metrics: dict[str, float]) -> dict[str, bool]:
    return {
        "unsafe_auto_fix_pass": metrics.get("unsafe_auto_fix_rate", 0.0) == 0.0,
        "hard_constraint_violation_pass": metrics.get("hard_constraint_violation_rate", 0.0) == 0.0,
    }


def write_markdown_report(report: dict[str, Any], output_path: Path = DEFAULT_REPORT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_markdown_report(report), encoding="utf-8")


def write_json_metrics_snapshot(
    report: dict[str, Any],
    output_path: Path = DEFAULT_JSON_REPORT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _to_metrics_snapshot(report)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _to_metrics_snapshot(report: dict[str, Any]) -> dict[str, object]:
    metrics = report.get("metrics", {})
    gates = report.get("gates", {})
    return {
        "agent_schema_pass_rate": metrics.get("schema_pass_rate", 0.0),
        "agent_decision_accuracy": metrics.get("decision_accuracy", 0.0),
        "agent_risk_accuracy": metrics.get("risk_accuracy", 0.0),
        "agent_evidence_citation_rate": metrics.get("evidence_citation_rate", 0.0),
        "agent_no_evidence_to_human_rate": metrics.get("no_evidence_to_human_rate", 0.0),
        "agent_hard_constraint_violation_rate": metrics.get("hard_constraint_violation_rate", 0.0),
        "agent_unsafe_auto_fix_rate": metrics.get("unsafe_auto_fix_rate", 0.0),
        "agent_decision_consistency_rate": metrics.get("decision_consistency_rate", 0.0),
        "agent_case_count": metrics.get("case_count", 0),
        "gates": gates,
        "provider_requested": report.get("provider_requested", "unknown"),
        "provider_effective": report.get("provider_effective", "unknown"),
        "model_requested": report.get("model_requested", "unknown"),
        "model_effective": report.get("model_effective", "unknown"),
        "real_provider_call": report.get("real_provider_call", False),
        "evaluated_at": report.get("evaluated_at", ""),
    }


def _format_markdown_report(report: dict[str, Any]) -> str:
    metrics = report.get("metrics", {})
    gates = report.get("gates", {})
    lines = [
        "# Agent Evaluation Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Provider Requested | `{report.get('provider_requested', 'unknown')}` |",
        f"| Provider Effective | `{report.get('provider_effective', 'unknown')}` |",
        f"| Model Requested | `{report.get('model_requested', 'unknown')}` |",
        f"| Model Effective | `{report.get('model_effective', 'unknown')}` |",
        f"| Real Provider Call | {report.get('real_provider_call', False)} |",
        f"| Case Count | {report['case_count']} |",
        f"| Evaluated At | {report.get('evaluated_at', 'N/A')} |",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Schema Pass Rate | {metrics.get('schema_pass_rate', 0):.4f} |",
        f"| Decision Accuracy | {metrics.get('decision_accuracy', 0):.4f} |",
        f"| Risk Accuracy | {metrics.get('risk_accuracy', 0):.4f} |",
        f"| Evidence Citation Rate | {metrics.get('evidence_citation_rate', 0):.4f} |",
        f"| No-Evidence → Human Rate | {metrics.get('no_evidence_to_human_rate', 0):.4f} |",
        f"| Hard Constraint Violation Rate | {metrics.get('hard_constraint_violation_rate', 0):.4f} |",
        f"| Unsafe Auto-Fix Rate | {metrics.get('unsafe_auto_fix_rate', 0):.4f} |",
        f"| Decision Consistency Rate | {metrics.get('decision_consistency_rate', 0):.4f} |",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
        f"| Unsafe Auto-Fix = 0 | {'PASS' if gates.get('unsafe_auto_fix_pass') else 'FAIL'} |",
        f"| Hard Constraint Violation = 0 | {'PASS' if gates.get('hard_constraint_violation_pass') else 'FAIL'} |",
        "",
        "## Per-Case Results",
        "",
        "| Case ID | Error Type | Branch | Decision | Risk | Schema | Decision Match | Risk Match | Evidence | Consistent |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        lines.append(
            "| {case_id} | {error_type} | {exception_branch} | {actual_decision} | "
            "{actual_risk_level} | {schema_passed} | {decision_match} | "
            "{risk_level_match} | {evidence_cited} | {consistency_passed} |".format(**result)
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate AuditAgent safety and decision baseline.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--provider", default="fake")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT_PATH)
    args = parser.parse_args(argv)

    if args.provider == "deepseek":
        if args.report.resolve() == DEFAULT_REPORT_PATH.resolve():
            args.report = DEEPSEEK_FLASH_REPORT_PATH
        if args.json_report.resolve() == DEFAULT_JSON_REPORT_PATH.resolve():
            args.json_report = DEEPSEEK_FLASH_JSON_PATH

    cases = load_agent_eval_cases(args.cases)
    try:
        report = evaluate_agent_cases(cases, provider=args.provider, model=args.model)
    except LLMUnavailable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    write_markdown_report(report, args.report)
    write_json_metrics_snapshot(report, args.json_report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
