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
    }]))

    with pytest.raises(ValueError, match="Invalid expected_decision"):
        eval_agent.load_agent_eval_cases(cases_path)


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
    monkeypatch.setattr(eval_agent.settings, "deepseek_api_key", "sk-test")
    md_path = tmp_path / "agent_eval.md"
    json_path = tmp_path / "agent_eval_metrics.json"

    fake_md_def = tmp_path / "fake_default.md"
    fake_json_def = tmp_path / "fake_default_metrics.json"
    monkeypatch.setattr(eval_agent, "DEFAULT_REPORT_PATH", fake_md_def)
    monkeypatch.setattr(eval_agent, "DEFAULT_JSON_REPORT_PATH", fake_json_def)
    monkeypatch.setattr(
        eval_agent, "DEEPSEEK_FLASH_REPORT_PATH", tmp_path / "agent_eval_deepseek_flash.md"
    )
    monkeypatch.setattr(
        eval_agent, "DEEPSEEK_FLASH_JSON_PATH", tmp_path / "agent_eval_deepseek_flash_metrics.json"
    )

    with pytest.raises(SystemExit):
        eval_agent.main([
            "--cases", str(PROJECT_ROOT / "data/agent_eval_cases.json"),
            "--provider", "deepseek",
            "--model", "deepseek-v4-flash",
            "--report", str(md_path),
            "--json-report", str(json_path),
        ])

    assert not md_path.exists()
    assert not json_path.exists()


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
