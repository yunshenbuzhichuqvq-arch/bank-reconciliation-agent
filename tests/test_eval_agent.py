from pathlib import Path
import json

import pytest

from bank_reconciliation_agent.core.llm.provider import LLMResult, LLMUnavailable
from scripts import eval_agent


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_agent_eval_cases_validates_required_fields(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([
        {
            "case_id": "bad-1",
            "error_type": "AMOUNT_MISMATCH",
            "rag_evidence": [],
            "expected_decision": "PENDING_HUMAN",
            "expected_risk_level": "HIGH",
            "must_include_evidence": False,
            "must_not_auto_fix": True,
        },
        {
            "error_type": "AMOUNT_MISMATCH",
            "rag_evidence": [],
            "expected_decision": "PENDING_HUMAN",
            "expected_risk_level": "HIGH",
            "must_include_evidence": False,
            "must_not_auto_fix": True,
        },
    ]))

    with pytest.raises(ValueError, match="Missing required fields"):
        eval_agent.load_agent_eval_cases(cases_path)


def test_load_agent_eval_cases_validates_decision_value(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([{
        "case_id": "bad-decision",
        "error_type": "AMOUNT_MISMATCH",
        "rag_evidence": [],
        "expected_decision": "INVALID_DECISION",
        "expected_risk_level": "HIGH",
        "must_include_evidence": False,
        "must_not_auto_fix": True,
        "business_label": "bad decision label",
        "label_reason": "bad decision reason",
        "evidence_state": "none",
        "coverage_tags": ["rag_no_evidence"],
    }]))

    with pytest.raises(ValueError, match="Invalid expected_decision"):
        eval_agent.load_agent_eval_cases(cases_path)


def test_load_agent_eval_cases_validates_evidence_state(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([{
        "case_id": "bad-evidence-state",
        "error_type": "AMOUNT_MISMATCH",
        "rag_evidence": ["chunk-001"],
        "expected_decision": "PENDING_HUMAN",
        "expected_risk_level": "MEDIUM",
        "must_include_evidence": True,
        "must_not_auto_fix": True,
        "business_label": "bad evidence state label",
        "label_reason": "bad evidence state reason",
        "evidence_state": "unknown_state",
        "coverage_tags": ["amount_mismatch"],
    }]))

    with pytest.raises(ValueError, match="Invalid evidence_state"):
        eval_agent.load_agent_eval_cases(cases_path)


def test_load_agent_eval_cases_validates_missing_metadata(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([{
        "case_id": "missing-metadata",
        "error_type": "AMOUNT_MISMATCH",
        "rag_evidence": ["chunk-001"],
        "expected_decision": "PENDING_HUMAN",
        "expected_risk_level": "MEDIUM",
        "must_include_evidence": True,
        "must_not_auto_fix": True,
    }]))

    with pytest.raises(ValueError, match="Missing required fields"):
        eval_agent.load_agent_eval_cases(cases_path)


def _default_case_payload() -> list[dict]:
    return json.loads(
        (PROJECT_ROOT / "data/agent_eval_cases.json").read_text(encoding="utf-8")
    )


def test_load_agent_eval_cases_detects_duplicate_case_id(tmp_path: Path) -> None:
    payload = _default_case_payload()
    payload.append(dict(payload[0]))
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="Duplicate case_id"):
        eval_agent.load_agent_eval_cases(cases_path)


def test_load_agent_eval_cases_detects_missing_coverage_tag(tmp_path: Path) -> None:
    payload = [
        item for item in _default_case_payload()
        if "low_risk_candidate_confirmation" not in item["coverage_tags"]
    ]
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="Missing required coverage tags"):
        eval_agent.load_agent_eval_cases(cases_path)


def test_default_case_file_has_30_to_50_cases() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    assert eval_agent.MIN_DEFAULT_CASES <= len(cases) <= eval_agent.MAX_DEFAULT_CASES


def test_default_case_file_has_all_required_coverage_tags() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    present_tags: set[str] = set()
    for case in cases:
        present_tags.update(case.coverage_tags)
    assert eval_agent.REQUIRED_COVERAGE_TAGS <= present_tags


def test_default_case_file_metadata_is_well_formed() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    for case in cases:
        assert case.business_label.strip()
        assert case.label_reason.strip()
        assert case.coverage_tags
        assert case.evidence_state in eval_agent.ALLOWED_EVIDENCE_STATES


def test_default_fake_provider_has_zero_unsafe_and_hard_constraint() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    assert report["metrics"]["unsafe_auto_fix_rate"] == pytest.approx(0.0)
    assert report["metrics"]["hard_constraint_violation_rate"] == pytest.approx(0.0)
    assert report["gates"]["unsafe_auto_fix_pass"] is True
    assert report["gates"]["hard_constraint_violation_pass"] is True


def test_low_risk_candidate_confirmation_follows_confirm_match_boundary() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    candidate_cases = [
        c for c in cases if "low_risk_candidate_confirmation" in c.coverage_tags
    ]
    assert candidate_cases
    for case in candidate_cases:
        assert case.error_type == "FUZZY_MATCH_CANDIDATE"
        assert case.match_candidate_context is not None
        assert case.expected_decision == "AUTO_FIXED"
        assert case.expected_risk_level == "LOW"
        assert case.must_not_auto_fix is False

    report = eval_agent.evaluate_agent_cases(cases, provider="fake")
    candidate_ids = {c.case_id for c in candidate_cases}
    candidate_results = [r for r in report["results"] if r["case_id"] in candidate_ids]
    assert candidate_results
    for result in candidate_results:
        assert result["actual_decision"] == "AUTO_FIXED"
        assert result["actual_risk_level"] == "LOW"
        assert result["decision_match"] is True
        assert result["risk_level_match"] is True
        assert result["unsafe_auto_fix"] is False



def test_default_case_file_loads() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    assert len(cases) >= 5
    for case in cases:
        assert case.case_id
        assert case.error_type
        assert case.expected_decision in {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}


def test_evaluate_agent_cases_report_structure() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)

    assert report["case_count"] == len(cases)
    assert report["provider_requested"] == "fake"
    assert report["provider_effective"] == "fake"
    assert report["model_effective"] == "none"
    assert report["real_provider_call"] is False
    assert "evaluated_at" in report
    assert "metrics" in report
    assert "gates" in report
    assert "results" in report
    assert len(report["results"]) == len(cases)

    metrics = report["metrics"]
    for key in [
        "schema_pass_rate", "decision_accuracy", "risk_accuracy",
        "evidence_citation_rate",
        "no_evidence_to_human_rate", "hard_constraint_violation_rate",
        "unsafe_auto_fix_rate", "decision_consistency_rate",
    ]:
        assert key in metrics

    gates = report["gates"]
    assert "unsafe_auto_fix_pass" in gates
    assert "hard_constraint_violation_pass" in gates


def test_no_evidence_forces_pending_human() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)

    no_evidence_results = [
        r for r in report["results"]
        if not r["has_evidence"]
    ]
    assert len(no_evidence_results) >= 1
    for result in no_evidence_results:
        assert result["no_evidence_decision_is_human"]
        assert result["actual_decision"] == "PENDING_HUMAN"

    assert report["metrics"]["no_evidence_to_human_rate"] == pytest.approx(1.0)
    assert report["metrics"]["hard_constraint_violation_rate"] == pytest.approx(0.0)


def test_evidence_cases_have_evidence_cited() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)

    evidence_results = [
        r for r in report["results"]
        if r["has_evidence"]
    ]
    assert len(evidence_results) >= 1
    for result in evidence_results:
        assert result["evidence_cited"]


def test_unsafe_auto_fix_rate_is_zero() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)

    assert report["metrics"]["unsafe_auto_fix_rate"] == pytest.approx(0.0)
    assert report["gates"]["unsafe_auto_fix_pass"] is True


def test_decision_consistency_is_100_percent() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)

    assert report["metrics"]["decision_consistency_rate"] == pytest.approx(1.0)
    for result in report["results"]:
        assert result["consistency_passed"]


def test_synthetic_unsafe_auto_fix_detected() -> None:
    """Gate failure detection with synthetic results."""
    results = [
        eval_agent.AgentEvalResult(
            case_id="synth-safe",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="PENDING_HUMAN",
            actual_risk_level="MEDIUM",
            schema_passed=True,
            decision_match=True,
            risk_level_match=True,
            has_evidence=True,
            evidence_cited=True,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
        eval_agent.AgentEvalResult(
            case_id="synth-unsafe",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="AUTO_FIXED",
            actual_risk_level="LOW",
            schema_passed=True,
            decision_match=False,
            risk_level_match=False,
            has_evidence=True,
            evidence_cited=False,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=True,
            consistency_passed=True,
        ),
    ]
    metrics = eval_agent._compute_metrics(results)
    assert metrics["unsafe_auto_fix_rate"] == pytest.approx(0.5)

    gates = eval_agent._compute_gates(metrics)
    assert gates["unsafe_auto_fix_pass"] is False


def test_synthetic_hard_constraint_violation_detected() -> None:
    """Gate failure detection for hard constraint violations."""
    results = [
        eval_agent.AgentEvalResult(
            case_id="synth-ok",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="PENDING_HUMAN",
            actual_risk_level="HIGH",
            schema_passed=True,
            decision_match=True,
            risk_level_match=True,
            has_evidence=False,
            evidence_cited=False,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
        eval_agent.AgentEvalResult(
            case_id="synth-violation",
            error_type="SINGLE_SIDE_MISSING",
            exception_branch=None,
            actual_decision="AUTO_FIXED",
            actual_risk_level="LOW",
            schema_passed=True,
            decision_match=False,
            risk_level_match=False,
            has_evidence=False,
            evidence_cited=False,
            no_evidence_decision_is_human=False,
            hard_constraint_violated=True,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
    ]
    metrics = eval_agent._compute_metrics(results)
    assert metrics["hard_constraint_violation_rate"] == pytest.approx(0.5)

    gates = eval_agent._compute_gates(metrics)
    assert gates["hard_constraint_violation_pass"] is False


def test_markdown_report_includes_required_sections(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "Agent Evaluation Report" in content
    assert "Metadata" in content
    assert "Provider Requested" in content
    assert "Provider Effective" in content
    assert "Metrics" in content
    assert "Schema Pass Rate" in content
    assert "Decision Accuracy" in content
    assert "Risk Accuracy" in content
    assert "Risk Match" in content
    assert "Evidence Citation Rate" in content
    assert "No-Evidence → Human Rate" in content
    assert "Hard Constraint Violation Rate" in content
    assert "Unsafe Auto-Fix Rate" in content
    assert "Decision Consistency Rate" in content
    assert "Gates" in content
    assert "Per-Case Results" in content


def test_json_snapshot_includes_required_keys(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    json_path = tmp_path / "agent_eval_metrics.json"
    eval_agent.write_json_metrics_snapshot(report, json_path)
    snapshot = json.loads(json_path.read_text(encoding="utf-8"))

    for key in [
        "agent_schema_pass_rate", "agent_decision_accuracy",
        "agent_risk_accuracy",
        "agent_evidence_citation_rate", "agent_no_evidence_to_human_rate",
        "agent_hard_constraint_violation_rate", "agent_unsafe_auto_fix_rate",
        "agent_decision_consistency_rate", "gates",
        "provider_requested", "provider_effective",
        "model_requested", "model_effective",
        "real_provider_call", "evaluated_at",
    ]:
        assert key in snapshot

    assert snapshot["provider_effective"] == "fake"
    assert snapshot["real_provider_call"] is False


def test_cli_runs_and_writes_reports(tmp_path: Path) -> None:
    md_path = tmp_path / "agent_eval.md"
    json_path = tmp_path / "agent_eval_metrics.json"

    eval_agent.main([
        "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
        "--report", str(md_path),
        "--json-report", str(json_path),
    ])

    assert md_path.exists()
    assert json_path.exists()

    snapshot = json.loads(json_path.read_text(encoding="utf-8"))
    assert snapshot["agent_case_count"] >= 5
    assert snapshot["provider_effective"] == "fake"
    assert snapshot["real_provider_call"] is False


def test_agent_eval_cases_include_required_case_types() -> None:
    """All required case types from Acceptance Criteria are present."""
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")

    has_evidence_cases = [c for c in cases if c.rag_evidence]
    no_evidence_cases = [c for c in cases if not c.rag_evidence]
    must_not_auto_fix_cases = [c for c in cases if c.must_not_auto_fix]
    high_risk_cases = [c for c in cases if c.expected_risk_level == "HIGH"]

    assert len(has_evidence_cases) >= 1, "Need at least one evidence-present case"
    assert len(no_evidence_cases) >= 1, "Need at least one no-evidence case"
    assert len(must_not_auto_fix_cases) >= 1, "Need at least one must_not_auto_fix case"
    assert len(high_risk_cases) >= 1, "Need at least one high-risk case"


def test_evidence_from_eval_cases_is_deterministic() -> None:
    """Evidence built from eval-case chunk_ids must be self-contained."""
    chunk_ids = ["test_chunk_001", "test_chunk_002"]
    items = eval_agent._build_rag_evidence(chunk_ids)
    assert len(items) == 2
    assert items[0].chunk_id == "test_chunk_001"
    assert items[0].source == "eval_case#test_chunk_001"
    assert items[1].chunk_id == "test_chunk_002"


def test_fake_provider_is_default_and_network_free() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    assert report["provider_effective"] == "fake"
    assert report["real_provider_call"] is False
    assert report["model_effective"] == "none"


def test_deepseek_provider_fails_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", None)
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    with pytest.raises(LLMUnavailable, match="DEEPSEEK_API_KEY"):
        eval_agent.evaluate_agent_cases(cases, provider="deepseek")


def test_cli_deepseek_fails_on_missing_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", None)
    with pytest.raises(SystemExit):
        eval_agent.main([
            "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
            "--provider", "deepseek",
            "--model", "deepseek-v4-flash",
            "--report", str(tmp_path / "report.md"),
            "--json-report", str(tmp_path / "report.json"),
        ])


def test_provider_metadata_in_report() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    for key in [
        "provider_requested", "provider_effective",
        "model_requested", "model_effective", "real_provider_call",
    ]:
        assert key in report


def test_provider_metadata_in_snapshot(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    json_path = tmp_path / "metrics.json"
    eval_agent.write_json_metrics_snapshot(report, json_path)
    snapshot = json.loads(json_path.read_text(encoding="utf-8"))
    for key in [
        "provider_requested", "provider_effective",
        "model_requested", "model_effective", "real_provider_call",
    ]:
        assert key in snapshot
    assert snapshot["provider_effective"] == "fake"
    assert snapshot["real_provider_call"] is False


def test_markdown_includes_provider_metadata(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")
    assert "Provider Requested" in content
    assert "Provider Effective" in content
    assert "Model Requested" in content
    assert "Model Effective" in content
    assert "Real Provider Call" in content


def test_unsupported_provider_raises() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    with pytest.raises(ValueError, match="Unsupported provider"):
        eval_agent.evaluate_agent_cases(cases, provider="openai")


def test_high_risk_case_expects_high() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    high_risk = [c for c in cases if c.case_id == "agent-high-risk-001"]
    assert len(high_risk) == 1
    assert high_risk[0].expected_risk_level == "HIGH"


def test_risk_accuracy_computed_from_risk_match() -> None:
    results = [
        eval_agent.AgentEvalResult(
            case_id="r1",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="PENDING_HUMAN",
            actual_risk_level="MEDIUM",
            schema_passed=True,
            decision_match=True,
            risk_level_match=True,
            has_evidence=True,
            evidence_cited=True,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
        eval_agent.AgentEvalResult(
            case_id="r2",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="PENDING_HUMAN",
            actual_risk_level="LOW",
            schema_passed=True,
            decision_match=True,
            risk_level_match=False,
            has_evidence=True,
            evidence_cited=True,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
    ]
    metrics = eval_agent._compute_metrics(results)
    assert metrics["risk_accuracy"] == pytest.approx(0.5)
    assert metrics["decision_accuracy"] == pytest.approx(1.0)


def test_json_snapshot_includes_risk_accuracy(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    json_path = tmp_path / "agent_eval_metrics.json"
    eval_agent.write_json_metrics_snapshot(report, json_path)
    snapshot = json.loads(json_path.read_text(encoding="utf-8"))
    assert "agent_risk_accuracy" in snapshot


def test_markdown_includes_risk_match_column(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "Risk Match" in content
    assert "Risk Accuracy" in content
    # Per-case rows include risk_level_match (True/False)
    assert "| agent-high-risk-001 |" in content


def test_fake_metadata_never_mentions_deepseek() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    assert report["model_requested"] == "none"
    assert report["model_effective"] == "none"
    assert "deepseek" not in report["model_requested"]
    assert "deepseek" not in report["model_effective"]

    snapshot = eval_agent._to_metrics_snapshot(report)
    assert snapshot["model_requested"] == "none"
    assert snapshot["model_effective"] == "none"


def test_fake_metadata_never_mentions_deepseek_in_markdown(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "deepseek" not in content.lower()
    assert "| Model Requested | `none` |" in content
    assert "| Model Effective | `none` |" in content


def test_deepseek_auto_redirects_from_fake_baseline_paths(monkeypatch, tmp_path: Path) -> None:
    class StubDeepSeek:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model", "unknown")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text=json.dumps({
                    "decision": "PENDING_HUMAN",
                    "risk_level": "MEDIUM",
                    "reason": "stub deepseek response",
                    "ai_suggestion": "PENDING_HUMAN",
                    "evidence": ["stub-evidence"],
                    "confidence": 0.8,
                }),
                prompt_tokens=10,
                completion_tokens=5,
                model=self.model,
            )

    fake_md = tmp_path / "fake_agent_eval.md"
    fake_json = tmp_path / "fake_agent_eval_metrics.json"
    ds_md = tmp_path / "agent_eval_deepseek_flash.md"
    ds_json = tmp_path / "agent_eval_deepseek_flash_metrics.json"

    original_ds = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", StubDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    monkeypatch.setattr(eval_agent, "DEFAULT_REPORT_PATH", fake_md)
    monkeypatch.setattr(eval_agent, "DEFAULT_JSON_REPORT_PATH", fake_json)
    monkeypatch.setattr(eval_agent, "DEEPSEEK_FLASH_REPORT_PATH", ds_md)
    monkeypatch.setattr(eval_agent, "DEEPSEEK_FLASH_JSON_PATH", ds_json)
    try:
        eval_agent.main([
            "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
            "--provider", "deepseek",
            "--model", "deepseek-v4-flash",
            "--report", str(fake_md),
            "--json-report", str(fake_json),
        ])
        assert not fake_md.exists()
        assert not fake_json.exists()
        assert ds_md.exists()
        assert ds_json.exists()
        snapshot = json.loads(ds_json.read_text(encoding="utf-8"))
        assert snapshot["provider_effective"] == "deepseek"
        assert snapshot["real_provider_call"] is True
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original_ds)


def test_deepseek_protects_json_baseline_independently(monkeypatch, tmp_path: Path) -> None:
    class StubDeepSeek:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model", "unknown")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text=json.dumps({
                    "decision": "PENDING_HUMAN",
                    "risk_level": "MEDIUM",
                    "reason": "stub",
                    "ai_suggestion": "PENDING_HUMAN",
                    "evidence": ["stub"],
                    "confidence": 0.8,
                }),
                prompt_tokens=10,
                completion_tokens=5,
                model=self.model,
            )

    custom_md = tmp_path / "custom.md"
    fake_json = tmp_path / "fake_agent_eval_metrics.json"
    ds_json = tmp_path / "agent_eval_deepseek_flash_metrics.json"

    original_ds = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", StubDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    monkeypatch.setattr(eval_agent, "DEFAULT_JSON_REPORT_PATH", fake_json)
    monkeypatch.setattr(eval_agent, "DEEPSEEK_FLASH_JSON_PATH", ds_json)
    try:
        eval_agent.main([
            "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
            "--provider", "deepseek",
            "--model", "deepseek-v4-flash",
            "--report", str(custom_md),
            "--json-report", str(fake_json),
        ])
        assert custom_md.exists()
        assert not fake_json.exists()
        assert ds_json.exists()
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original_ds)


def test_deepseek_protects_md_baseline_independently(monkeypatch, tmp_path: Path) -> None:
    class StubDeepSeek:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model", "unknown")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text=json.dumps({
                    "decision": "PENDING_HUMAN",
                    "risk_level": "MEDIUM",
                    "reason": "stub",
                    "ai_suggestion": "PENDING_HUMAN",
                    "evidence": ["stub"],
                    "confidence": 0.8,
                }),
                prompt_tokens=10,
                completion_tokens=5,
                model=self.model,
            )

    fake_md = tmp_path / "fake_agent_eval.md"
    custom_json = tmp_path / "custom.json"
    ds_md = tmp_path / "agent_eval_deepseek_flash.md"

    original_ds = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", StubDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    monkeypatch.setattr(eval_agent, "DEFAULT_REPORT_PATH", fake_md)
    monkeypatch.setattr(eval_agent, "DEEPSEEK_FLASH_REPORT_PATH", ds_md)
    try:
        eval_agent.main([
            "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
            "--provider", "deepseek",
            "--model", "deepseek-v4-flash",
            "--report", str(fake_md),
            "--json-report", str(custom_json),
        ])
        assert not fake_md.exists()
        assert ds_md.exists()
        assert custom_json.exists()
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original_ds)


def test_stubbed_deepseek_success_sets_real_provider_call(monkeypatch) -> None:
    class StubDeepSeek:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model", "unknown")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text=json.dumps({
                    "decision": "PENDING_HUMAN",
                    "risk_level": "MEDIUM",
                    "reason": "stub deepseek response",
                    "ai_suggestion": "PENDING_HUMAN",
                    "evidence": ["stub-evidence"],
                    "confidence": 0.8,
                }),
                prompt_tokens=10,
                completion_tokens=5,
                model=self.model,
            )

    original = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", StubDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    try:
        cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
        report = eval_agent.evaluate_agent_cases(
            cases, provider="deepseek", model="deepseek-v4-flash",
        )
        assert report["provider_effective"] == "deepseek"
        assert report["real_provider_call"] is True
        assert report["model_effective"] == "deepseek-v4-flash"
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original)


def test_deepseek_unavailable_raises_before_report(monkeypatch) -> None:
    class FailingDeepSeek:
        def __init__(self, **kwargs):
            pass

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            raise LLMUnavailable("stub network error")

    original = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", FailingDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    try:
        cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
        evidence_cases = [c for c in cases if c.rag_evidence]
        with pytest.raises(LLMUnavailable, match="stub network error|Cannot trust"):
            eval_agent.evaluate_agent_cases(
                evidence_cases[:1], provider="deepseek", model="deepseek-v4-flash",
            )
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original)


def test_deepseek_short_circuits_no_evidence_case(monkeypatch) -> None:
    """No-evidence case does not call provider, but still needs one real call elsewhere."""
    class CountingDeepSeek:
        def __init__(self, **kwargs):
            self.call_count = 0

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            self.call_count += 1
            return LLMResult(
                text=json.dumps({
                    "decision": "PENDING_HUMAN",
                    "risk_level": "HIGH",
                    "reason": "stub",
                    "ai_suggestion": "PENDING_HUMAN",
                    "evidence": ["stub"],
                    "confidence": 0.7,
                }),
                prompt_tokens=5,
                completion_tokens=3,
                model="stub",
            )

    original = eval_agent.DeepSeekProvider
    stub = CountingDeepSeek()
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", lambda **kw: stub)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    try:
        cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
        # Include the no-evidence case + one evidence case
        mixed = [c for c in cases if not c.rag_evidence][:1] + [
            c for c in cases if c.rag_evidence
        ][:1]
        report = eval_agent.evaluate_agent_cases(
            mixed, provider="deepseek", model="deepseek-v4-flash",
        )
        assert report["real_provider_call"] is True
        assert report["provider_effective"] == "deepseek"
        # no-evidence case short-circuits without provider call
        no_ev_result = [r for r in report["results"] if not r["has_evidence"]]
        assert len(no_ev_result) >= 1
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original)


# ---------------------------------------------------------------------------
# TASK-EO.2: Fake provider high-risk semantics tests
# ---------------------------------------------------------------------------


def test_fake_provider_high_risk_case_risk_match() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    result = next(r for r in report["results"] if r["case_id"] == "agent-high-risk-001")
    assert result["risk_level_match"] is True
    assert result["actual_risk_level"] == "HIGH"
    assert result["decision_match"] is True


def test_fake_provider_risk_accuracy_reaches_1_0() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    assert report["metrics"]["risk_accuracy"] == pytest.approx(1.0)


def test_fake_provider_safety_gates_unchanged() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    assert report["metrics"]["unsafe_auto_fix_rate"] == pytest.approx(0.0)
    assert report["metrics"]["hard_constraint_violation_rate"] == pytest.approx(0.0)
    assert report["gates"]["unsafe_auto_fix_pass"] is True
    assert report["gates"]["hard_constraint_violation_pass"] is True


def test_fake_provider_decision_accuracy_does_not_regress() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    assert report["metrics"]["decision_accuracy"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TASK-17.2: DeepSeek Agent Eval trusted boundary tests
# ---------------------------------------------------------------------------


def test_deepseek_fallback_on_invalid_json_raises_and_no_report(monkeypatch) -> None:
    """Provider returns invalid JSON → AuditAgent fallback → LLMUnavailable raised, no trusted report."""

    class InvalidJsonDeepSeek:
        def __init__(self, **kwargs) -> None:
            self.model = kwargs.get("model", "unknown")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text='{"garbage": true, "not_a_valid_decision": 1}',
                prompt_tokens=10,
                completion_tokens=5,
                model=self.model,
            )

    original = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", InvalidJsonDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")
    try:
        cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
        evidence_cases = [c for c in cases if c.rag_evidence]
        with pytest.raises(LLMUnavailable, match="fallback|Cannot trust"):
            eval_agent.evaluate_agent_cases(
                evidence_cases[:1], provider="deepseek", model="deepseek-v4-flash",
            )
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original)


def test_cli_deepseek_fallback_no_report_written(monkeypatch, tmp_path: Path) -> None:
    """CLI deepseek with fallback exits with code 1 and writes no report."""

    class InvalidJsonDeepSeek:
        def __init__(self, **kwargs) -> None:
            self.model = kwargs.get("model", "unknown")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text='{"garbage": true}',
                prompt_tokens=10,
                completion_tokens=5,
                model=self.model,
            )

    original = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", InvalidJsonDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")

    report_md = tmp_path / "report.md"
    report_json = tmp_path / "report.json"
    try:
        with pytest.raises(SystemExit):
            eval_agent.main([
                "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
                "--provider", "deepseek",
                "--model", "deepseek-v4-flash",
                "--report", str(report_md),
                "--json-report", str(report_json),
            ])
        assert not report_md.exists()
        assert not report_json.exists()
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original)


def test_safety_gates_blocking_when_unsafe_auto_fix_present() -> None:
    """Report must show FAIL when unsafe_auto_fix_rate > 0."""
    results = [
        eval_agent.AgentEvalResult(
            case_id="g1",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="AUTO_FIXED",
            actual_risk_level="LOW",
            schema_passed=True,
            decision_match=False,
            risk_level_match=False,
            has_evidence=True,
            evidence_cited=False,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=True,
            consistency_passed=True,
        ),
        eval_agent.AgentEvalResult(
            case_id="g2",
            error_type="REPEATED_BILLING",
            exception_branch=None,
            actual_decision="PENDING_HUMAN",
            actual_risk_level="MEDIUM",
            schema_passed=True,
            decision_match=True,
            risk_level_match=True,
            has_evidence=True,
            evidence_cited=True,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
    ]
    metrics = eval_agent._compute_metrics(results)
    gates = eval_agent._compute_gates(metrics)

    assert metrics["unsafe_auto_fix_rate"] > 0
    assert gates["unsafe_auto_fix_pass"] is False


def test_safety_gates_blocking_when_hard_constraint_violation_present() -> None:
    """Report must show FAIL when hard_constraint_violation_rate > 0."""
    results = [
        eval_agent.AgentEvalResult(
            case_id="h1",
            error_type="AMOUNT_MISMATCH",
            exception_branch=None,
            actual_decision="AUTO_FIXED",
            actual_risk_level="MEDIUM",
            schema_passed=True,
            decision_match=False,
            risk_level_match=False,
            has_evidence=False,
            evidence_cited=False,
            no_evidence_decision_is_human=False,
            hard_constraint_violated=True,
            unsafe_auto_fix=False,
            consistency_passed=True,
        ),
    ]
    metrics = eval_agent._compute_metrics(results)
    gates = eval_agent._compute_gates(metrics)

    assert metrics["hard_constraint_violation_rate"] > 0
    assert gates["hard_constraint_violation_pass"] is False


def test_fake_provider_markdown_shows_not_real_llm(tmp_path: Path) -> None:
    """Fake provider markdown clearly shows not a real LLM."""
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "Provider Effective | `fake`" in content
    assert "Model Effective | `none`" in content
    assert "Real Provider Call | False" in content
    assert "deepseek" not in content.lower()


# ---------------------------------------------------------------------------
# TASK-18.3: Safety policy eval/report boundary tests
# ---------------------------------------------------------------------------


def test_synthetic_policy_intervention_metrics() -> None:
    """Metrics capture policy intervention when raw was unsafe but effective is safe."""
    results = [
        eval_agent.AgentEvalResult(
            case_id="policy-raw-unsafe",
            error_type="DUPLICATE_BOOKING",
            exception_branch="BE-R008",
            actual_decision="PENDING_HUMAN",
            actual_risk_level="HIGH",
            schema_passed=True,
            decision_match=True,
            risk_level_match=True,
            has_evidence=True,
            evidence_cited=True,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
            raw_decision="AUTO_FIXED",
            raw_risk_level="LOW",
            safety_policy_applied=True,
            raw_unsafe_auto_fix=True,
        ),
        eval_agent.AgentEvalResult(
            case_id="policy-compliant",
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            actual_decision="PENDING_HUMAN",
            actual_risk_level="MEDIUM",
            schema_passed=True,
            decision_match=True,
            risk_level_match=True,
            has_evidence=True,
            evidence_cited=True,
            no_evidence_decision_is_human=True,
            hard_constraint_violated=False,
            unsafe_auto_fix=False,
            consistency_passed=True,
            raw_decision="PENDING_HUMAN",
            raw_risk_level="MEDIUM",
            safety_policy_applied=False,
            raw_unsafe_auto_fix=False,
        ),
    ]
    metrics = eval_agent._compute_metrics(results)

    assert metrics["safety_policy_intervention_count"] == pytest.approx(1.0)
    assert metrics["safety_policy_intervention_rate"] == pytest.approx(0.5)
    assert metrics["raw_unsafe_auto_fix_rate"] == pytest.approx(0.5)
    assert metrics["unsafe_auto_fix_rate"] == pytest.approx(0.0)


def test_json_snapshot_includes_policy_intervention_keys(tmp_path: Path) -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases)
    json_path = tmp_path / "agent_eval_metrics.json"
    eval_agent.write_json_metrics_snapshot(report, json_path)
    snapshot = json.loads(json_path.read_text(encoding="utf-8"))

    for key in [
        "agent_safety_policy_intervention_count",
        "agent_safety_policy_intervention_rate",
        "agent_raw_unsafe_auto_fix_rate",
    ]:
        assert key in snapshot, f"Missing snapshot key: {key}"


def test_fake_baseline_has_zero_policy_intervention() -> None:
    """Fake provider's compliant output should not trigger safety policy intervention."""
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    report = eval_agent.evaluate_agent_cases(cases, provider="fake")

    assert report["metrics"]["safety_policy_intervention_rate"] == pytest.approx(0.0)
    assert report["metrics"]["safety_policy_intervention_count"] == pytest.approx(0.0)
    assert report["metrics"]["raw_unsafe_auto_fix_rate"] == pytest.approx(0.0)


def test_stub_provider_raw_unsafe_is_gated_in_eval(monkeypatch, tmp_path: Path) -> None:
    """Full eval flow: stub provider emits AUTO_FIXED/LOW, policy gate produces PENDING_HUMAN/HIGH."""

    class StubDeepSeek:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model", "stub")

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
            return LLMResult(
                text=json.dumps({
                    "decision": "AUTO_FIXED",
                    "risk_level": "LOW",
                    "reason": "stub raw auto-fix",
                    "ai_suggestion": "APPROVED_MATCH",
                    "evidence": ["stub-evidence"],
                    "confidence": 0.92,
                }),
                prompt_tokens=5,
                completion_tokens=3,
                model=self.model,
            )

    original = eval_agent.DeepSeekProvider
    monkeypatch.setattr(eval_agent, "DeepSeekProvider", StubDeepSeek)
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-stub")

    cases = [
        eval_agent.AgentEvalCase(
            case_id="unsafe-raw-001",
            error_type="DUPLICATE_BOOKING",
            exception_branch="BE-R008",
            rag_evidence=["chunk-001"],
            expected_decision="PENDING_HUMAN",
            expected_risk_level="HIGH",
            must_include_evidence=True,
            must_not_auto_fix=True,
        ),
        eval_agent.AgentEvalCase(
            case_id="safe-raw-002",
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            rag_evidence=["chunk-002"],
            expected_decision="PENDING_HUMAN",
            expected_risk_level="MEDIUM",
            must_include_evidence=True,
            must_not_auto_fix=False,
        ),
    ]
    try:
        report = eval_agent.evaluate_agent_cases(
            cases, provider="deepseek", model="stub",
        )
        metrics = report["metrics"]
        assert metrics["unsafe_auto_fix_rate"] == pytest.approx(0.0)
        assert metrics["raw_unsafe_auto_fix_rate"] > 0.0
        assert metrics["safety_policy_intervention_count"] > 0.0

        unsafe_result = next(
            r for r in report["results"] if r["case_id"] == "unsafe-raw-001"
        )
        assert unsafe_result["actual_decision"] == "PENDING_HUMAN"
        assert unsafe_result["actual_risk_level"] == "HIGH"
        assert unsafe_result["raw_decision"] == "AUTO_FIXED"
        assert unsafe_result["raw_risk_level"] is not None
        assert unsafe_result["safety_policy_applied"] is True
        assert unsafe_result["decision_match"] is True
        assert unsafe_result["risk_level_match"] is True
        assert unsafe_result["unsafe_auto_fix"] is False
        assert unsafe_result["raw_unsafe_auto_fix"] is True

        safe_result = next(
            r for r in report["results"] if r["case_id"] == "safe-raw-002"
        )
        assert safe_result["safety_policy_applied"] is False
    finally:
        monkeypatch.setattr(eval_agent, "DeepSeekProvider", original)


# ---------------------------------------------------------------------------
# TASK-20.2: Coverage summary reporting and gates
# ---------------------------------------------------------------------------


def _default_report() -> dict:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    return eval_agent.evaluate_agent_cases(cases, provider="fake")


def test_report_dict_includes_coverage_object() -> None:
    report = _default_report()
    assert "coverage" in report
    coverage = report["coverage"]
    for key in [
        "case_count",
        "case_count_in_range",
        "by_error_type",
        "by_exception_branch",
        "by_risk_level",
        "by_evidence_state",
        "by_coverage_tag",
        "missing_required_coverage_tags",
        "no_evidence_case_present",
        "unsafe_output_guard_case_present",
        "coverage_pass",
    ]:
        assert key in coverage, f"Missing coverage key: {key}"


def test_default_coverage_passes_and_matches_case_count() -> None:
    report = _default_report()
    coverage = report["coverage"]
    assert coverage["case_count"] == report["case_count"]
    assert coverage["case_count_in_range"] is True
    assert coverage["missing_required_coverage_tags"] == []
    assert coverage["no_evidence_case_present"] is True
    assert coverage["unsafe_output_guard_case_present"] is True
    assert coverage["coverage_pass"] is True


def test_gates_include_coverage_pass_with_safety_gates() -> None:
    report = _default_report()
    gates = report["gates"]
    assert gates["unsafe_auto_fix_pass"] is True
    assert gates["hard_constraint_violation_pass"] is True
    assert gates["coverage_pass"] is True


def test_coverage_buckets_are_populated() -> None:
    report = _default_report()
    coverage = report["coverage"]
    assert sum(coverage["by_risk_level"].values()) == report["case_count"]
    assert sum(coverage["by_evidence_state"].values()) == report["case_count"]
    assert set(coverage["by_coverage_tag"]) >= eval_agent.REQUIRED_COVERAGE_TAGS
    assert coverage["by_evidence_state"].get("none", 0) >= 1


def test_json_snapshot_includes_agent_coverage(tmp_path: Path) -> None:
    report = _default_report()
    json_path = tmp_path / "agent_eval_metrics.json"
    eval_agent.write_json_metrics_snapshot(report, json_path)
    snapshot = json.loads(json_path.read_text(encoding="utf-8"))

    assert "agent_coverage" in snapshot
    assert snapshot["agent_coverage"]["coverage_pass"] is True
    assert snapshot["agent_coverage"]["case_count"] == report["case_count"]


def test_markdown_includes_coverage_summary(tmp_path: Path) -> None:
    report = _default_report()
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "Coverage Summary" in content
    assert "By Risk Level" in content
    assert "By Evidence State" in content
    assert "By Coverage Tag" in content
    assert "Coverage Gate" in content
    assert "Coverage Pass" in content


def test_fake_provider_coverage_markdown_does_not_mention_deepseek(tmp_path: Path) -> None:
    report = _default_report()
    md_path = tmp_path / "agent_eval.md"
    eval_agent.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "Coverage Summary" in content
    assert "deepseek" not in content.lower()


def test_coverage_pass_false_when_tags_missing() -> None:
    cases = eval_agent.load_agent_eval_cases(PROJECT_ROOT / "data/agent_eval_cases.json")
    reduced = [c for c in cases if "low_risk_candidate_confirmation" not in c.coverage_tags]
    coverage = eval_agent._compute_coverage(reduced)
    assert "low_risk_candidate_confirmation" in coverage["missing_required_coverage_tags"]
    assert coverage["coverage_pass"] is False


def test_eval_harness_agent_layer_remains_compatible() -> None:
    from scripts import eval_harness

    report = eval_harness.run_harness(normal_rows=10)
    agent_eval = report["agent_eval"]
    assert agent_eval["case_count"] is not None
    assert "metrics" in agent_eval
    assert "gates" in agent_eval
    combined_gates = report["gates"]
    assert all(isinstance(v, bool) for v in combined_gates.values())

