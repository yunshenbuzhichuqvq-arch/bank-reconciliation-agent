from pathlib import Path
import json

from scripts import eval_harness


def test_harness_report_contains_all_three_layers() -> None:
    report = eval_harness.run_harness(normal_rows=10)

    assert "metadata" in report
    assert "system_eval" in report
    assert "rag_eval" in report
    assert "agent_eval" in report
    assert "gates" in report
    assert "honest_gaps" in report

    assert "case_count" in report["system_eval"]
    assert "metrics" in report["system_eval"]
    assert "gates" in report["system_eval"]

    assert "case_count" in report["rag_eval"]
    assert "global_metrics" in report["rag_eval"]

    assert "case_count" in report["agent_eval"]
    assert "metrics" in report["agent_eval"]
    assert "gates" in report["agent_eval"]


def test_harness_metadata_propagates_seed_and_counts() -> None:
    report = eval_harness.run_harness(seed=9999, normal_rows=10)

    meta = report["metadata"]
    assert meta["seed"] == 9999
    assert meta["normal_rows"] == 10
    assert meta["scenario_type"] == "BANK_ENTERPRISE"
    assert meta["embedding_backend"] == "hash"
    assert meta["top_k"] == 5

    assert report["system_eval"]["case_count"] is not None
    assert report["rag_eval"]["case_count"] is not None
    assert report["agent_eval"]["case_count"] is not None


def test_harness_gates_structure() -> None:
    report = eval_harness.run_harness(normal_rows=10)

    gates = report["gates"]
    for key in [
        "system_unsafe_auto_fix_pass",
        "system_hard_constraint_violation_pass",
        "agent_unsafe_auto_fix_pass",
        "agent_hard_constraint_violation_pass",
    ]:
        assert key in gates
        assert isinstance(gates[key], bool)


def test_blocking_gate_detection_all_pass() -> None:
    gates = {
        "system_unsafe_auto_fix_pass": True,
        "system_hard_constraint_violation_pass": True,
        "agent_unsafe_auto_fix_pass": True,
        "agent_hard_constraint_violation_pass": True,
    }
    failures = eval_harness._check_blocking_gates(gates)
    assert failures == []


def test_blocking_gate_detection_with_failures() -> None:
    gates = {
        "system_unsafe_auto_fix_pass": False,
        "system_hard_constraint_violation_pass": True,
        "agent_unsafe_auto_fix_pass": True,
        "agent_hard_constraint_violation_pass": False,
    }
    failures = eval_harness._check_blocking_gates(gates)
    assert "system_unsafe_auto_fix_pass" in failures
    assert "agent_hard_constraint_violation_pass" in failures
    assert len(failures) == 2


def test_baseline_markdown_includes_required_sections(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir)
    content = (output_dir / "baseline.md").read_text(encoding="utf-8")

    assert "Combined Baseline Evaluation Report" in content
    assert "Metadata" in content
    assert "System Eval" in content
    assert "RAG Eval" in content
    assert "Agent Eval" in content
    assert "Combined Gates" in content
    assert "Case Counts" in content
    assert "Baseline Review Gate" in content
    assert "Honest Gaps" in content
    assert "opencode **must stop**" in content
    assert "Codex" in content


def test_baseline_json_includes_all_layers(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir)
    snapshot = json.loads((output_dir / "baseline.json").read_text(encoding="utf-8"))

    for key in ["metadata", "system_eval", "rag_eval", "agent_eval", "gates", "honest_gaps"]:
        assert key in snapshot


def test_baseline_json_gates_are_machine_readable(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir)
    snapshot = json.loads((output_dir / "baseline.json").read_text(encoding="utf-8"))

    gates = snapshot["gates"]
    assert all(isinstance(v, bool) for v in gates.values())


def test_cli_writes_both_baseline_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "eval_harness"

    eval_harness.main([
        "--seed", "20260706",
        "--normal-rows", "10",
        "--embedding-backend", "hash",
        "--top-k", "5",
        "--output-dir", str(output_dir),
    ])

    assert (output_dir / "baseline.md").exists()
    assert (output_dir / "baseline.json").exists()

    snapshot = json.loads((output_dir / "baseline.json").read_text(encoding="utf-8"))
    assert snapshot["metadata"]["seed"] == 20260706


def test_harness_with_agent_gate_failure_triggers_blocking() -> None:
    gates = {
        "system_unsafe_auto_fix_pass": True,
        "system_hard_constraint_violation_pass": True,
        "agent_unsafe_auto_fix_pass": False,
        "agent_hard_constraint_violation_pass": True,
    }
    failures = eval_harness._check_blocking_gates(gates)
    assert "agent_unsafe_auto_fix_pass" in failures
    assert len(failures) == 1


def test_gate_failures_returned_not_raised_in_checker() -> None:
    """_check_blocking_gates returns failure list, does not raise."""
    gates = {
        "system_unsafe_auto_fix_pass": False,
        "system_hard_constraint_violation_pass": False,
        "agent_unsafe_auto_fix_pass": True,
        "agent_hard_constraint_violation_pass": True,
    }
    failures = eval_harness._check_blocking_gates(gates)
    assert len(failures) == 2
    assert "system_unsafe_auto_fix_pass" in failures
    assert "system_hard_constraint_violation_pass" in failures


def test_honest_gaps_includes_all_required_categories() -> None:
    report = eval_harness.run_harness(normal_rows=10)
    gaps = report["honest_gaps"]

    assert len(gaps) >= 6
    gap_text = " ".join(gaps).lower()
    for term in ["real llm", "real embedding", "llm-as-judge", "adoption", "latency", "cost"]:
        assert term in gap_text, f"Expected '{term}' in honest_gaps"


def test_markdown_renders_honest_gaps(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir)
    content = (output_dir / "baseline.md").read_text(encoding="utf-8")

    assert "Honest Gaps / Not Measured" in content
    for term in ["real LLM", "real embedding", "LLM-as-Judge", "latency", "cost"]:
        assert term in content


def test_agent_eval_includes_risk_accuracy() -> None:
    report = eval_harness.run_harness(normal_rows=10)
    agent_metrics = report["agent_eval"]["metrics"]
    assert "risk_accuracy" in agent_metrics


def test_agent_eval_risk_accuracy_in_markdown(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir)
    content = (output_dir / "baseline.md").read_text(encoding="utf-8")

    assert "risk_accuracy" in content.lower()


# ---------------------------------------------------------------------------
# TASK-EO.3: After/comparison reports tests
# ---------------------------------------------------------------------------


def test_run_harness_rag_mode_propagates_to_metadata() -> None:
    report = eval_harness.run_harness(normal_rows=10, rag_mode="hybrid")
    meta = report["metadata"]
    assert meta["rag_mode"] == "hybrid"


def test_run_harness_rag_mode_default_is_dense() -> None:
    report = eval_harness.run_harness(normal_rows=10)
    meta = report["metadata"]
    assert meta["rag_mode"] == "dense"


def test_write_after_markdown_writes_after_md(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir, report_name="after")
    assert (output_dir / "after.md").exists()
    assert (output_dir / "after.json").exists()


def test_write_report_name_baseline_is_default(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir)
    assert (output_dir / "baseline.md").exists()
    assert (output_dir / "baseline.json").exists()


def test_compare_harness_reports_includes_deltas() -> None:
    before = eval_harness.run_harness(normal_rows=10)
    after = eval_harness.run_harness(normal_rows=10, rag_mode="hybrid_rerank")

    comparison = eval_harness.compare_harness_reports(before=before, after=after)

    assert "metadata_comparison" in comparison
    assert "system_eval" in comparison
    assert "rag_eval" in comparison
    assert "agent_eval" in comparison
    assert "gates" in comparison
    assert "honest_gaps" in comparison

    # Deltas present
    assert "deltas" in comparison["system_eval"]
    assert "deltas" in comparison["rag_eval"]
    assert "deltas" in comparison["agent_eval"]


def test_compare_harness_reports_metadata_compatibility() -> None:
    before = eval_harness.run_harness(normal_rows=10, seed=42)
    after = eval_harness.run_harness(normal_rows=10, seed=42)

    comparison = eval_harness.compare_harness_reports(before=before, after=after)
    mc = comparison["metadata_comparison"]
    assert mc["seed_match"] is True
    assert mc["normal_rows_match"] is True
    assert mc["embedding_backend_match"] is True
    assert mc["top_k_match"] is True
    assert "before_rag_mode" in mc
    assert "after_rag_mode" in mc


def test_compare_harness_reports_includes_agent_risk_accuracy_delta() -> None:
    before = eval_harness.run_harness(normal_rows=10)
    after = eval_harness.run_harness(normal_rows=10)

    comparison = eval_harness.compare_harness_reports(before=before, after=after)
    deltas = comparison["agent_eval"]["deltas"]
    assert "risk_accuracy" in deltas
    assert deltas["risk_accuracy"] == 0.0  # Same provider, same cases


def test_compare_harness_reports_gates_structure() -> None:
    before = eval_harness.run_harness(normal_rows=10)
    after = eval_harness.run_harness(normal_rows=10)

    comparison = eval_harness.compare_harness_reports(before=before, after=after)
    gates = comparison["gates"]
    assert "before" in gates
    assert "after" in gates
    assert "changes" in gates


def test_cli_baseline_does_not_overwrite_after_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "eval_harness"

    eval_harness.main([
        "--seed", "20260706",
        "--normal-rows", "10",
        "--embedding-backend", "hash",
        "--top-k", "5",
        "--output-dir", str(output_dir),
        "--report-name", "baseline",
    ])

    assert (output_dir / "baseline.md").exists()
    assert (output_dir / "baseline.json").exists()
    assert not (output_dir / "after.md").exists()
    assert not (output_dir / "after.json").exists()


def test_cli_after_does_not_overwrite_baseline_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "eval_harness"
    # First create a dummy baseline
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "baseline.md").write_text("baseline-md")
    (output_dir / "baseline.json").write_text('{"key":"baseline-json"}')

    eval_harness.main([
        "--seed", "20260706",
        "--normal-rows", "10",
        "--embedding-backend", "hash",
        "--top-k", "5",
        "--output-dir", str(output_dir),
        "--report-name", "after",
    ])

    assert (output_dir / "after.md").exists()
    assert (output_dir / "after.json").exists()
    assert (output_dir / "baseline.md").read_text() == "baseline-md"
    assert (output_dir / "baseline.json").read_text() == '{"key":"baseline-json"}'


def test_cli_compare_with_writes_comparison_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "eval_harness"
    before_path = tmp_path / "before.json"
    comparison_md = tmp_path / "comparison.md"
    comparison_json = tmp_path / "comparison.json"

    # Generate a before baseline first
    before_report = eval_harness.run_harness(normal_rows=10)
    before_path.write_text(json.dumps(before_report, ensure_ascii=False, indent=2, default=str))

    eval_harness.main([
        "--seed", "20260706",
        "--normal-rows", "10",
        "--embedding-backend", "hash",
        "--top-k", "5",
        "--rag-mode", "dense",
        "--output-dir", str(output_dir),
        "--report-name", "after",
        "--compare-with", str(before_path),
        "--comparison-report", str(comparison_md),
        "--comparison-json", str(comparison_json),
    ])

    assert comparison_md.exists()
    assert comparison_json.exists()
    comp = json.loads(comparison_json.read_text(encoding="utf-8"))
    assert "metadata_comparison" in comp
    assert comp["metadata_comparison"]["after_rag_mode"] == "dense"


def test_after_json_includes_rag_mode_in_metadata(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10, rag_mode="hybrid")
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_report(report, output_dir, report_name="after")
    snapshot = json.loads((output_dir / "after.json").read_text(encoding="utf-8"))
    assert snapshot["metadata"]["rag_mode"] == "hybrid"


def test_comparison_json_includes_honest_gaps(tmp_path: Path) -> None:
    before = eval_harness.run_harness(normal_rows=10)
    after = eval_harness.run_harness(normal_rows=10)

    comparison = eval_harness.compare_harness_reports(before=before, after=after)
    gaps = comparison["honest_gaps"]
    assert len(gaps) >= 6
    gap_text = " ".join(gaps).lower()
    for term in ["real llm", "real embedding", "latency", "cost"]:
        assert term in gap_text


# ---------------------------------------------------------------------------
# TASK-EO.4: Comparison structure tests (before_metrics / after_metrics)
# ---------------------------------------------------------------------------


def test_comparison_includes_before_and_after_metrics_for_all_layers() -> None:
    before = eval_harness.run_harness(normal_rows=10)
    after = eval_harness.run_harness(normal_rows=10, rag_mode="hybrid")

    comparison = eval_harness.compare_harness_reports(before=before, after=after)

    for layer in ["system_eval", "rag_eval", "agent_eval"]:
        assert "before_metrics" in comparison[layer], f"{layer} missing before_metrics"
        assert "after_metrics" in comparison[layer], f"{layer} missing after_metrics"
        assert "deltas" in comparison[layer], f"{layer} missing deltas"

    assert isinstance(comparison["system_eval"]["before_metrics"], dict)
    assert isinstance(comparison["system_eval"]["after_metrics"], dict)
    assert isinstance(comparison["rag_eval"]["after_metrics"], dict)
    assert isinstance(comparison["agent_eval"]["after_metrics"], dict)


def test_comparison_deltas_still_present_alongside_metrics() -> None:
    before = eval_harness.run_harness(normal_rows=10)
    after = eval_harness.run_harness(normal_rows=10)

    comparison = eval_harness.compare_harness_reports(before=before, after=after)

    assert "risk_accuracy" in comparison["agent_eval"]["deltas"]
    assert "risk_accuracy" in comparison["agent_eval"]["before_metrics"]
    assert "risk_accuracy" in comparison["agent_eval"]["after_metrics"]
