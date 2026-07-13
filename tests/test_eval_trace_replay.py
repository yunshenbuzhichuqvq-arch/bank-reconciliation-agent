"""Tests for the deterministic Trace Replay evidence runner.

Refs: TASK-29.7
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
# Scenario runner tests (each scenario produces valid results)
# ---------------------------------------------------------------------------


def test_scenario_success_generates_valid_trace():
    result = eval_trace_replay.scenario_success()
    assert result["scenario"] == "complete_success"
    assert result["span_count"] > 0
    assert "WORKFLOW" in result["span_sequence"]
    assert result["terminal_type"] == "FINAL"


def test_scenario_tool_failed_generates_valid_trace():
    result = eval_trace_replay.scenario_tool_failed()
    assert result["scenario"] == "tool_failed_fallback"
    assert result["terminal_type"] == "FALLBACK"
    seq = result["span_sequence"]
    assert "TOOL" in seq
    # Tool failed short-circuits — no AGENT or GUARD downstream.
    assert "AGENT" not in seq
    assert "GUARD" not in seq


def test_scenario_agent_repair_failure_generates_valid_trace():
    result = eval_trace_replay.scenario_agent_repair_failure()
    assert result["scenario"] == "agent_repair_failure_fallback"
    assert result["terminal_type"] == "FALLBACK"
    assert "ROUTE" in result["span_sequence"]


def test_scenario_guard_blocked_generates_valid_trace():
    result = eval_trace_replay.scenario_guard_blocked()
    assert result["scenario"] == "guard_blocked_fallback"
    assert "GUARD" in result["span_sequence"]
    assert result["terminal_type"] == "FALLBACK"


def test_cross_tenant_replay_rejection():
    result = eval_trace_replay.scenario_cross_tenant_replay_rejection()
    assert result["trace_persisted"] is True
    assert result["user_a_can_read_own_trace"] is True
    assert result["user_b_can_read_user_a_trace"] is False


def test_trace_write_failure_isolation():
    result = eval_trace_replay.scenario_trace_write_failure_isolation()
    assert result["persist_returned_false"] is True
    assert result["failure_count_incremented"] is True
    assert result["trace_structure_valid"] is True


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
    assert json_1["metrics"]["denominator"] == json_2["metrics"]["denominator"]
    assert json_1["metrics"]["numerator"] == json_2["metrics"]["numerator"]
    assert (
        json_1["metrics"]["trace_completeness_rate"] == json_2["metrics"]["trace_completeness_rate"]
    )

    # Scenario counts are stable.
    assert [s["scenario"] for s in json_1["scenarios"]] == [
        s["scenario"] for s in json_2["scenarios"]
    ]

    # Markdown is generated from JSON, not hand-crafted.
    assert md_1
    assert md_2


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
