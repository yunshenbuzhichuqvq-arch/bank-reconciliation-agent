"""Tests for the deterministic Trace Replay evidence runner.

Refs: TASK-29.7
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import eval_trace_replay


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"


# ---------------------------------------------------------------------------
# Algorithm and unit-level tests
# ---------------------------------------------------------------------------


def test_p50_algorithm():
    assert eval_trace_replay._p50([1, 2, 3, 4, 5]) == 3
    assert eval_trace_replay._p50([1, 2, 3, 4]) == 2
    assert eval_trace_replay._p50([5]) == 5
    assert eval_trace_replay._p50([]) == 0


def test_p95_algorithm():
    assert eval_trace_replay._p95(list(range(1, 101))) >= 95
    assert eval_trace_replay._p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == 10
    assert eval_trace_replay._p95([]) == 0


def test_empty_duration_returns_zero():
    metrics = eval_trace_replay._compute_metrics([])
    assert metrics["trace_completeness_rate"] == 0.0
    assert metrics["numerator"] == 0
    assert metrics["denominator"] == 0


# ---------------------------------------------------------------------------
# Scenario runner tests (each scenario meets its own expectation)
# ---------------------------------------------------------------------------


def test_scenario_success_generates_valid_trace():
    result = eval_trace_replay.scenario_success()
    assert result["scenario"] == "complete_success"
    assert result["scenario_passed"] is True
    assert result["eligible_execution"] is True
    assert result["trace_persisted"] is True
    assert result["span_count"] > 0
    assert "WORKFLOW" in result["span_sequence"]
    assert result["terminal_type"] == "FINAL"


def test_scenario_tool_failed_generates_valid_trace():
    result = eval_trace_replay.scenario_tool_failed()
    assert result["scenario"] == "tool_failed_fallback"
    assert result["scenario_passed"] is True
    assert result["terminal_type"] == "FALLBACK"
    seq = result["span_sequence"]
    assert "TOOL" in seq
    # Tool failed short-circuits — no AGENT or GUARD downstream.
    assert "AGENT" not in seq
    assert "GUARD" not in seq


def test_scenario_agent_repair_failure_generates_valid_trace():
    result = eval_trace_replay.scenario_agent_repair_failure()
    assert result["scenario"] == "agent_repair_failure_fallback"
    assert result["scenario_passed"] is True
    assert result["terminal_type"] == "FALLBACK"
    assert "ROUTE" in result["span_sequence"]
    facts = result["facts"]
    assert facts["failed_agent_spans"] >= 1
    assert facts["structured_repair_attempted"] is True
    assert facts["non_cached_agent_tokens"] > 0
    assert facts["error_type"] == "schema_invalid"


def test_scenario_guard_blocked_generates_valid_trace():
    result = eval_trace_replay.scenario_guard_blocked()
    assert result["scenario"] == "guard_blocked_fallback"
    assert result["scenario_passed"] is True
    assert "GUARD" in result["span_sequence"]
    assert result["terminal_type"] == "FALLBACK"
    assert result["facts"]["guard_outcome"] == "BLOCKED"


def test_cross_tenant_replay_rejection_via_http():
    result = eval_trace_replay.scenario_cross_tenant_replay_rejection()
    assert result["scenario"] == "cross_tenant_replay_rejection"
    assert result["scenario_passed"] is True
    assert result["trace_persisted"] is True
    facts = result["facts"]
    assert facts["owner_http_status"] == 200
    assert facts["owner_replay_status"] == "AVAILABLE"
    assert facts["non_owner_http_status"] == 404
    assert facts["non_owner_error_code"] == "TASK_NOT_FOUND"
    assert facts["non_owner_payload_leaked"] is False
    assert facts["storage_empty_read"] is True


def test_trace_write_failure_isolation():
    result = eval_trace_replay.scenario_trace_write_failure_isolation()
    assert result["scenario"] == "trace_write_failure_isolation"
    assert result["scenario_passed"] is True
    assert result["eligible_execution"] is True
    assert result["trace_persisted"] is False
    assert result["expected_persistence"] is False
    facts = result["facts"]
    assert facts["business_call_succeeded"] is True
    assert facts["ledger_committed"] is True
    assert facts["queue_committed"] is True
    assert facts["task_stats_committed"] is True
    assert facts["final_decision"] == "PENDING_HUMAN"
    assert facts["trace_rows"] == 0
    assert facts["failure_counter_incremented"] is True


# ---------------------------------------------------------------------------
# Completeness must be an honest 5/6 (not 4/4 = 100%)
# ---------------------------------------------------------------------------


def test_completeness_is_five_over_six(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(eval_trace_replay, "REPORTS_DIR", tmp_path)
    assert eval_trace_replay.main() == 0
    report = json.loads((tmp_path / "trace_replay_evidence.json").read_text("utf-8"))
    assert report["metrics"]["denominator"] == 6
    assert report["metrics"]["numerator"] == 5
    assert abs(report["metrics"]["trace_completeness_rate"] - 5 / 6) < 1e-9
    assert report["scenario_pass_count"] == 6
    assert report["scenario_total"] == 6
    assert all(s["scenario_passed"] for s in report["scenarios"])


# ---------------------------------------------------------------------------
# Determinism: consecutive runner execution yields stable results
# ---------------------------------------------------------------------------


def test_runner_deterministic_across_consecutive_runs(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(eval_trace_replay, "REPORTS_DIR", tmp_path)

    old_argv = sys.argv
    try:
        sys.argv = ["eval_trace_replay.py"]
        exit_code_1 = eval_trace_replay.main()
    finally:
        sys.argv = old_argv

    assert exit_code_1 == 0

    json_1 = json.loads((tmp_path / "trace_replay_evidence.json").read_text("utf-8"))
    md_1 = (tmp_path / "trace_replay_evidence.md").read_text("utf-8")

    # Second run — structural keys must be identical; only timestamps may differ.
    try:
        sys.argv = ["eval_trace_replay.py"]
        exit_code_2 = eval_trace_replay.main()
    finally:
        sys.argv = old_argv

    assert exit_code_2 == 0
    json_2 = json.loads((tmp_path / "trace_replay_evidence.json").read_text("utf-8"))
    md_2 = (tmp_path / "trace_replay_evidence.md").read_text("utf-8")

    # Schema-level keys must be stable across runs.
    assert json_1["environment"] == json_2["environment"]
    assert json_1["provider"] == json_2["provider"]
    assert json_1["embedding"] == json_2["embedding"]
    assert json_1["claim"] == json_2["claim"]
    assert json_1["scenario_pass_count"] == json_2["scenario_pass_count"] == 6
    assert json_1["metrics"]["denominator"] == json_2["metrics"]["denominator"] == 6
    assert json_1["metrics"]["numerator"] == json_2["metrics"]["numerator"] == 5
    assert (
        json_1["metrics"]["trace_completeness_rate"] == json_2["metrics"]["trace_completeness_rate"]
    )

    # Distributions and token aggregates are stable (durations/counters excluded).
    assert json_1["metrics"]["error_distribution"] == json_2["metrics"]["error_distribution"]
    assert json_1["metrics"]["fallback_distribution"] == json_2["metrics"]["fallback_distribution"]
    assert json_1["metrics"]["token_by_agent"] == json_2["metrics"]["token_by_agent"]

    # Scenario set, order and per-scenario pass verdicts are stable.
    assert [s["scenario"] for s in json_1["scenarios"]] == [
        s["scenario"] for s in json_2["scenarios"]
    ]
    assert [s["scenario_passed"] for s in json_1["scenarios"]] == [
        s["scenario_passed"] for s in json_2["scenarios"]
    ]

    # Markdown is generated from JSON, not hand-crafted.
    assert md_1
    assert md_2


# ---------------------------------------------------------------------------
# Atomic report writing: never overwrite half of a paired report
# ---------------------------------------------------------------------------


def _seed_old_reports(reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "trace_replay_evidence.json"
    md_path = reports_dir / "trace_replay_evidence.md"
    json_path.write_text("OLD-JSON-CONTENT", encoding="utf-8")
    md_path.write_text("OLD-MD-CONTENT", encoding="utf-8")
    return json_path, md_path


def test_main_leaves_reports_untouched_when_markdown_render_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(eval_trace_replay, "REPORTS_DIR", tmp_path)
    json_path, md_path = _seed_old_reports(tmp_path)

    def _boom(report):
        raise RuntimeError("markdown boom")

    monkeypatch.setattr(eval_trace_replay, "_build_markdown", _boom)

    assert eval_trace_replay.main() != 0
    assert json_path.read_text("utf-8") == "OLD-JSON-CONTENT"
    assert md_path.read_text("utf-8") == "OLD-MD-CONTENT"


def test_main_leaves_reports_untouched_on_cross_field_inconsistency(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(eval_trace_replay, "REPORTS_DIR", tmp_path)
    json_path, md_path = _seed_old_reports(tmp_path)

    real_compute = eval_trace_replay._compute_metrics

    def _tampered(scenarios):
        metrics = real_compute(scenarios)
        metrics["numerator"] = 4  # inconsistent with the 5 persisted scenarios
        return metrics

    monkeypatch.setattr(eval_trace_replay, "_compute_metrics", _tampered)

    assert eval_trace_replay.main() != 0
    assert json_path.read_text("utf-8") == "OLD-JSON-CONTENT"
    assert md_path.read_text("utf-8") == "OLD-MD-CONTENT"


def test_main_markdown_is_consistent_with_json(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(eval_trace_replay, "REPORTS_DIR", tmp_path)
    assert eval_trace_replay.main() == 0

    report = json.loads((tmp_path / "trace_replay_evidence.json").read_text("utf-8"))
    md = (tmp_path / "trace_replay_evidence.md").read_text("utf-8")

    assert report["metrics"]["numerator"] == 5
    assert report["metrics"]["denominator"] == 6
    assert report["scenario_pass_count"] == 6
    assert (
        f"Scenario pass count**: {report['scenario_pass_count']}/{report['scenario_total']}" in md
    )
    assert "Numerator (eligible flows persisted)**: 5" in md
    assert "Denominator (eligible flows executed)**: 6" in md


# ---------------------------------------------------------------------------
# Environment lock: refuse non-offline configurations before importing services
# ---------------------------------------------------------------------------


def _run_runner_subprocess(env_overrides: dict[str, str], reports_dir: Path):
    env = {**os.environ, "TRACE_REPLAY_REPORTS_DIR": str(reports_dir)}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "scripts.eval_trace_replay"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_runner_refuses_non_sqlite_dsn(tmp_path: Path):
    reports = tmp_path / "reports"
    json_path, md_path = _seed_old_reports(reports)
    proc = _run_runner_subprocess(
        {"MYSQL_DSN": "mysql+pymysql://user:pass@localhost:3306/db"}, reports
    )
    assert proc.returncode != 0
    # Fail-fast happened before any report write.
    assert json_path.read_text("utf-8") == "OLD-JSON-CONTENT"
    assert md_path.read_text("utf-8") == "OLD-MD-CONTENT"


def test_runner_refuses_non_hash_embedding(tmp_path: Path):
    reports = tmp_path / "reports"
    json_path, md_path = _seed_old_reports(reports)
    proc = _run_runner_subprocess(
        {
            "MYSQL_DSN": f"sqlite:///{tmp_path / 'eval.sqlite'}",
            "EMBEDDING_BACKEND": "bge_small",
        },
        reports,
    )
    assert proc.returncode != 0
    # Failed before loading any embedding model or writing reports.
    assert json_path.read_text("utf-8") == "OLD-JSON-CONTENT"
    assert md_path.read_text("utf-8") == "OLD-MD-CONTENT"


@pytest.mark.parametrize("truthy_value", ["1", "yes", "on"])
def test_runner_refuses_truthy_rag_flags(tmp_path: Path, truthy_value: str):
    reports = tmp_path / "reports"
    json_path, md_path = _seed_old_reports(reports)
    proc = _run_runner_subprocess(
        {
            "MYSQL_DSN": f"sqlite:///{tmp_path / 'eval.sqlite'}",
            "EMBEDDING_BACKEND": "hash",
            "ENABLE_RAG_HYBRID": truthy_value,
        },
        reports,
    )
    assert proc.returncode != 0
    assert json_path.read_text("utf-8") == "OLD-JSON-CONTENT"
    assert md_path.read_text("utf-8") == "OLD-MD-CONTENT"


def test_runner_accepts_valid_sqlite_hash_env(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    proc = _run_runner_subprocess(
        {
            "MYSQL_DSN": f"sqlite:///{tmp_path / 'eval.sqlite'}",
            "EMBEDDING_BACKEND": "hash",
        },
        reports,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads((reports / "trace_replay_evidence.json").read_text("utf-8"))
    assert report["metrics"]["numerator"] == 5
    assert report["metrics"]["denominator"] == 6
    assert report["scenario_pass_count"] == 6


# ---------------------------------------------------------------------------
# Sensitive-data scan
# ---------------------------------------------------------------------------


def test_report_excludes_sensitive_data():
    """JSON and Markdown reports must not contain sensitive markers."""
    json_path = REPORTS_DIR / "trace_replay_evidence.json"
    md_path = REPORTS_DIR / "trace_replay_evidence.md"

    if not json_path.exists() or not md_path.exists():
        # Run the runner once to generate reports for scanning.
        eval_trace_replay.main()

    json_text = json_path.read_text("utf-8")
    md_text = md_path.read_text("utf-8")

    forbidden = [
        "api_key",
        "password",
        "secret",
        "DEEPSEEK",
        "mysql+pymysql",
        "DB_PASSWORD",
        "JAEGER",
    ]
    for text in (json_text, md_text):
        lower = text.lower()
        for token in forbidden:
            assert token.lower() not in lower, f"Forbidden token '{token}' found in report"
