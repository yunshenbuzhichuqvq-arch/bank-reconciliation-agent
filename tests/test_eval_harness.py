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
    eval_harness.write_baseline_markdown(report, output_dir)
    content = (output_dir / "baseline.md").read_text(encoding="utf-8")

    assert "Combined Baseline Evaluation Report" in content
    assert "Metadata" in content
    assert "System Eval" in content
    assert "RAG Eval" in content
    assert "Agent Eval" in content
    assert "Combined Gates" in content
    assert "Case Counts" in content
    assert "Baseline Review Gate" in content
    assert "opencode **must stop**" in content
    assert "Codex" in content


def test_baseline_json_includes_all_layers(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_baseline_json(report, output_dir)
    snapshot = json.loads((output_dir / "baseline.json").read_text(encoding="utf-8"))

    for key in ["metadata", "system_eval", "rag_eval", "agent_eval", "gates"]:
        assert key in snapshot


def test_baseline_json_gates_are_machine_readable(tmp_path: Path) -> None:
    report = eval_harness.run_harness(normal_rows=10)
    output_dir = tmp_path / "eval_harness"
    eval_harness.write_baseline_json(report, output_dir)
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
