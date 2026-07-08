from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
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

ALLOWED_DECISIONS = {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}
ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_EVIDENCE_STATES = {"present", "none", "insufficient", "conflicting"}
REQUIRED_COVERAGE_TAGS = frozenset({
    "amount_mismatch",
    "bank_unarrived_enterprise_recorded",
    "enterprise_unrecorded_bank_arrived",
    "cross_period_t1_trace",
    "duplicate_booking",
    "narrative_counterparty_mismatch",
    "rag_no_evidence",
    "conflicting_insufficient_evidence",
    "high_risk_equal_amount",
    "low_risk_candidate_confirmation",
    "schema_valid_business_unsafe",
})
UNSAFE_OUTPUT_GUARD_TAGS = {"schema_valid_business_unsafe", "high_risk_equal_amount"}
MIN_DEFAULT_CASES = 30
MAX_DEFAULT_CASES = 50


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
    business_label: str = ""
    label_reason: str = ""
    evidence_state: str = "present"
    coverage_tags: list[str] = field(default_factory=list)
    match_candidate_context: dict[str, object] | None = None


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
    raw_decision: str | None = None
    raw_risk_level: str | None = None
    safety_policy_applied: bool = False
    raw_unsafe_auto_fix: bool = False
    consistency_passed: bool = True


def load_agent_eval_cases(path: Path = DEFAULT_CASES_PATH) -> list[AgentEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[AgentEvalCase] = []
    for item in payload:
        _validate_case_item(item)
        cases.append(AgentEvalCase(**item))
    validate_case_collection(cases)
    return cases


def _validate_case_item(item: dict[str, object]) -> None:
    required = {
        "case_id", "error_type", "rag_evidence",
        "expected_decision", "expected_risk_level",
        "must_include_evidence", "must_not_auto_fix",
        "business_label", "label_reason", "evidence_state", "coverage_tags",
    }
    missing = required - set(item)
    if missing:
        raise ValueError(
            f"Missing required fields: {missing} in case {item.get('case_id', 'unknown')}"
        )
    case_id = item["case_id"]
    if item.get("expected_decision") not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Invalid expected_decision in case {case_id}: {item['expected_decision']}"
        )
    if item.get("expected_risk_level") not in ALLOWED_RISK_LEVELS:
        raise ValueError(
            f"Invalid expected_risk_level in case {case_id}: {item['expected_risk_level']}"
        )
    if not isinstance(item.get("rag_evidence"), list):
        raise ValueError(f"rag_evidence must be a list in case {case_id}")
    if not str(item.get("business_label", "")).strip():
        raise ValueError(f"business_label must be non-empty in case {case_id}")
    if not str(item.get("label_reason", "")).strip():
        raise ValueError(f"label_reason must be non-empty in case {case_id}")
    evidence_state = item.get("evidence_state")
    if evidence_state not in ALLOWED_EVIDENCE_STATES:
        raise ValueError(f"Invalid evidence_state in case {case_id}: {evidence_state}")
    tags = item.get("coverage_tags")
    if not isinstance(tags, list) or not tags:
        raise ValueError(f"coverage_tags must be a non-empty list in case {case_id}")
    rag_evidence = item["rag_evidence"]
    if evidence_state == "none" and rag_evidence:
        raise ValueError(
            f"evidence_state 'none' requires empty rag_evidence in case {case_id}"
        )
    if evidence_state != "none" and not rag_evidence:
        raise ValueError(
            f"evidence_state '{evidence_state}' requires non-empty rag_evidence "
            f"in case {case_id}"
        )


def validate_case_collection(cases: list[AgentEvalCase]) -> None:
    """Validate coverage contract for the default curated case set."""
    ids = [case.case_id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate case_id values: {duplicates}")

    present_tags: set[str] = set()
    for case in cases:
        present_tags.update(case.coverage_tags)
    missing_tags = REQUIRED_COVERAGE_TAGS - present_tags
    if missing_tags:
        raise ValueError(f"Missing required coverage tags: {sorted(missing_tags)}")

    if not any(case.evidence_state == "none" for case in cases):
        raise ValueError("No no-evidence case present")

    if not _has_unsafe_output_guard_case(cases):
        raise ValueError("No unsafe-output guard case present")

    count = len(cases)
    if not MIN_DEFAULT_CASES <= count <= MAX_DEFAULT_CASES:
        raise ValueError(
            f"Default case count {count} out of range "
            f"[{MIN_DEFAULT_CASES}, {MAX_DEFAULT_CASES}]"
        )


def _has_unsafe_output_guard_case(cases: list[AgentEvalCase]) -> bool:
    return any(
        case.must_not_auto_fix and UNSAFE_OUTPUT_GUARD_TAGS.intersection(case.coverage_tags)
        for case in cases
    )


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
                trace_context=case.trace_context,
                match_candidate_context=case.match_candidate_context,
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

        raw_decision_value = decision.raw_decision if decision.safety_policy_applied else decision.decision
        raw_risk_value = decision.raw_risk_level if decision.safety_policy_applied else decision.risk_level
        raw_unsafe_auto_fix_val = case.must_not_auto_fix and raw_decision_value == "AUTO_FIXED"

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
            raw_decision=raw_decision_value,
            raw_risk_level=raw_risk_value,
            safety_policy_applied=decision.safety_policy_applied,
            raw_unsafe_auto_fix=raw_unsafe_auto_fix_val,
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
    coverage = _compute_coverage(cases)
    gates = _compute_gates(metrics)
    gates["coverage_pass"] = coverage["coverage_pass"]
    return {
        "case_count": len(cases),
        "provider_requested": provider_requested,
        "provider_effective": provider_effective,
        "model_requested": model_requested,
        "model_effective": model_effective,
        "real_provider_call": real_provider_call,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metrics": metrics,
        "coverage": coverage,
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
        "safety_policy_intervention_count": float(sum(
            1 for r in results if r.safety_policy_applied
        )),
        "safety_policy_intervention_rate": sum(
            1 for r in results if r.safety_policy_applied
        ) / total,
        "raw_unsafe_auto_fix_rate": sum(
            1 for r in results if r.raw_unsafe_auto_fix
        ) / total,
    }


def _compute_gates(metrics: dict[str, float]) -> dict[str, bool]:
    return {
        "unsafe_auto_fix_pass": metrics.get("unsafe_auto_fix_rate", 0.0) == 0.0,
        "hard_constraint_violation_pass": metrics.get("hard_constraint_violation_rate", 0.0) == 0.0,
    }


def _compute_coverage(cases: list[AgentEvalCase]) -> dict[str, Any]:
    count = len(cases)
    by_error_type: dict[str, int] = {}
    by_exception_branch: dict[str, int] = {}
    by_risk_level: dict[str, int] = {}
    by_evidence_state: dict[str, int] = {}
    by_coverage_tag: dict[str, int] = {}
    for case in cases:
        by_error_type[case.error_type] = by_error_type.get(case.error_type, 0) + 1
        branch = case.exception_branch or "none"
        by_exception_branch[branch] = by_exception_branch.get(branch, 0) + 1
        by_risk_level[case.expected_risk_level] = (
            by_risk_level.get(case.expected_risk_level, 0) + 1
        )
        by_evidence_state[case.evidence_state] = (
            by_evidence_state.get(case.evidence_state, 0) + 1
        )
        for tag in case.coverage_tags:
            by_coverage_tag[tag] = by_coverage_tag.get(tag, 0) + 1

    missing_tags = sorted(REQUIRED_COVERAGE_TAGS - set(by_coverage_tag))
    no_evidence_case_present = any(case.evidence_state == "none" for case in cases)
    unsafe_output_guard_case_present = _has_unsafe_output_guard_case(cases)
    case_count_in_range = MIN_DEFAULT_CASES <= count <= MAX_DEFAULT_CASES
    coverage_pass = (
        case_count_in_range
        and not missing_tags
        and no_evidence_case_present
        and unsafe_output_guard_case_present
    )
    return {
        "case_count": count,
        "case_count_in_range": case_count_in_range,
        "by_error_type": by_error_type,
        "by_exception_branch": by_exception_branch,
        "by_risk_level": by_risk_level,
        "by_evidence_state": by_evidence_state,
        "by_coverage_tag": by_coverage_tag,
        "missing_required_coverage_tags": missing_tags,
        "no_evidence_case_present": no_evidence_case_present,
        "unsafe_output_guard_case_present": unsafe_output_guard_case_present,
        "coverage_pass": coverage_pass,
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
        "agent_safety_policy_intervention_count": metrics.get(
            "safety_policy_intervention_count", 0
        ),
        "agent_safety_policy_intervention_rate": metrics.get(
            "safety_policy_intervention_rate", 0.0
        ),
        "agent_raw_unsafe_auto_fix_rate": metrics.get(
            "raw_unsafe_auto_fix_rate", 0.0
        ),
        "agent_case_count": metrics.get("case_count", 0),
        "agent_coverage": report.get("coverage", {}),
        "gates": gates,
        "provider_requested": report.get("provider_requested", "unknown"),
        "provider_effective": report.get("provider_effective", "unknown"),
        "model_requested": report.get("model_requested", "unknown"),
        "model_effective": report.get("model_effective", "unknown"),
        "real_provider_call": report.get("real_provider_call", False),
        "evaluated_at": report.get("evaluated_at", ""),
    }


def _format_coverage_section(coverage: dict[str, Any]) -> list[str]:
    missing = coverage.get("missing_required_coverage_tags", [])
    lines = [
        "## Coverage Summary",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Case Count | {coverage.get('case_count', 0)} |",
        f"| Case Count In Range | {coverage.get('case_count_in_range', False)} |",
        f"| Missing Required Coverage Tags | {', '.join(missing) if missing else 'none'} |",
        f"| No-Evidence Case Present | {coverage.get('no_evidence_case_present', False)} |",
        (
            "| Unsafe-Output Guard Case Present | "
            f"{coverage.get('unsafe_output_guard_case_present', False)} |"
        ),
        f"| Coverage Gate | {'PASS' if coverage.get('coverage_pass') else 'FAIL'} |",
        "",
    ]
    lines.extend(_format_count_table("By Risk Level", coverage.get("by_risk_level", {})))
    lines.extend(_format_count_table("By Evidence State", coverage.get("by_evidence_state", {})))
    lines.extend(_format_count_table("By Coverage Tag", coverage.get("by_coverage_tag", {})))
    return lines


def _format_count_table(title: str, counts: dict[str, int]) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| Bucket | Count |",
        "|---|---|",
    ]
    for key in sorted(counts):
        lines.append(f"| {key} | {counts[key]} |")
    lines.append("")
    return lines


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
        f"| Safety Policy Intervention Rate | {metrics.get('safety_policy_intervention_rate', 0):.4f} |",
        f"| Raw Unsafe Auto-Fix Rate | {metrics.get('raw_unsafe_auto_fix_rate', 0):.4f} |",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
        f"| Unsafe Auto-Fix = 0 | {'PASS' if gates.get('unsafe_auto_fix_pass') else 'FAIL'} |",
        f"| Hard Constraint Violation = 0 | {'PASS' if gates.get('hard_constraint_violation_pass') else 'FAIL'} |",
        f"| Coverage Pass | {'PASS' if gates.get('coverage_pass') else 'FAIL'} |",
        "",
    ]
    lines.extend(_format_coverage_section(report.get("coverage", {})))
    lines.extend([
        "## Per-Case Results",
        "",
        "| Case ID | Error Type | Branch | Decision | Risk | Raw Decision | Raw Risk | Policy | Schema | Decision Match | Risk Match | Evidence | Consistent |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for result in report["results"]:
        raw_dec = result.get("raw_decision", "") or ""
        raw_risk = result.get("raw_risk_level", "") or ""
        policy = "Yes" if result.get("safety_policy_applied") else ""
        lines.append(
            "| {case_id} | {error_type} | {exception_branch} | {decision} | "
            "{risk_level} | {raw_decision_col} | {raw_risk_col} | {policy_col} | "
            "{schema_passed} | {decision_match} | "
            "{risk_level_match} | {evidence_cited} | {consistency_passed} |".format(
                case_id=result.get("case_id", ""),
                error_type=result.get("error_type", ""),
                exception_branch=result.get("exception_branch", "") or "",
                decision=result.get("actual_decision", ""),
                risk_level=result.get("actual_risk_level", ""),
                raw_decision_col=raw_dec,
                raw_risk_col=raw_risk,
                policy_col=policy,
                schema_passed=result.get("schema_passed", ""),
                decision_match=result.get("decision_match", ""),
                risk_level_match=result.get("risk_level_match", ""),
                evidence_cited=result.get("evidence_cited", ""),
                consistency_passed=result.get("consistency_passed", ""),
            )
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
