from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import eval_tools


PROJECT_ROOT = Path(__file__).resolve().parents[1]


_FORBIDDEN_KEYS = {
    "args",
    "query",
    "content",
    "result",
    "exception",
    "traceback",
    "sql",
    "dsn",
    "token",
    "user_id",
    "ai_audit_opinion",
    "amount",
}
_FORBIDDEN_VALUES = {
    eval_tools.SENSITIVE_QUERY_MARKER,
    eval_tools.SENSITIVE_RULE_MARKER,
    eval_tools.SENSITIVE_OPINION_MARKER,
}


@pytest.fixture(scope="module")
def summary() -> dict:
    return eval_tools.build_report()


def _assert_no_sensitive(node: object) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in _FORBIDDEN_KEYS, f"forbidden key leaked: {key}"
            _assert_no_sensitive(value)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            _assert_no_sensitive(item)
    elif isinstance(node, str):
        for secret in _FORBIDDEN_VALUES:
            assert secret not in node, f"sensitive value leaked: {node!r}"


def test_default_paths_are_under_reports() -> None:
    assert eval_tools.DEFAULT_JSON_REPORT_PATH.name == "tool_executor_evidence.json"
    assert eval_tools.DEFAULT_REPORT_PATH.name == "tool_executor_evidence.md"
    assert eval_tools.DEFAULT_JSON_REPORT_PATH.parent.name == "reports"


def test_report_declares_stage_and_claim_boundary(summary: dict) -> None:
    assert summary["stage"] == "stage-28-readonly-tool-executor"
    assert "evaluated_at" in summary
    env = summary["environment"]
    assert env["embedding_backend"] == "hash"
    assert env["database"] == "sqlite"
    boundary = summary["claim_boundary"]
    assert boundary["local_only"] is True
    assert boundary["external_credentials"] is False
    assert boundary["production_sla"] is False


def test_each_tool_has_real_adapter_succeeded_and_empty(summary: dict) -> None:
    cases = summary["cases"]
    for tool in ("search_rules", "load_confirmed_cases", "lookup_t1_context"):
        real_cases = [
            c for c in cases if c["tool_name"] == tool and c["source"] == "real_adapter"
        ]
        statuses = {c["status"] for c in real_cases}
        assert "SUCCEEDED" in statuses, f"{tool} missing real SUCCEEDED"
        assert "EMPTY" in statuses, f"{tool} missing real EMPTY"


def test_matrix_covers_all_required_failure_modes(summary: dict) -> None:
    cases = summary["cases"]
    error_types = {c["error_type"] for c in cases if c["status"] == "FAILED"}
    assert "VALIDATION_ERROR" in error_types
    assert "PERMISSION_DENIED" in error_types
    assert "TIMEOUT" in error_types
    assert "CIRCUIT_OPEN" in error_types
    assert any(c["retry_recovered"] for c in cases)


def test_permission_denied_missing_and_cross_user_are_identical(summary: dict) -> None:
    denied = [
        c
        for c in cases_by_label(summary, "permission")
    ]
    assert len(denied) >= 2
    external = {
        (c["status"], c["error_type"], c["fallback_reason"], c["result_count"])
        for c in denied
    }
    assert len(external) == 1


def test_timeout_case_has_two_physical_attempts(summary: dict) -> None:
    timeout_cases = [c for c in summary["cases"] if c["error_type"] == "TIMEOUT"]
    assert timeout_cases
    assert all(c["attempt"] == 2 for c in timeout_cases)


def test_retry_recovered_case_keeps_two_attempts_and_success(summary: dict) -> None:
    recovered = [c for c in summary["cases"] if c["retry_recovered"]]
    assert recovered
    for c in recovered:
        assert c["status"] in ("SUCCEEDED", "EMPTY")
        assert c["attempt"] == 2


def test_circuit_open_is_failed_not_empty(summary: dict) -> None:
    circuit = [c for c in summary["cases"] if c["error_type"] == "CIRCUIT_OPEN"]
    assert circuit
    assert all(c["status"] == "FAILED" for c in circuit)


def test_outcome_counts_recomputable_from_cases(summary: dict) -> None:
    cases = summary["cases"]
    for tool, stats in summary["tools"].items():
        tool_cases = [c for c in cases if c["tool_name"] == tool]
        expected_outcomes: dict[str, int] = {}
        expected_errors: dict[str, int] = {}
        retry_count = 0
        for c in tool_cases:
            expected_outcomes[c["status"]] = expected_outcomes.get(c["status"], 0) + 1
            if c["error_type"]:
                expected_errors[c["error_type"]] = expected_errors.get(c["error_type"], 0) + 1
            if c["retry_recovered"]:
                retry_count += 1
        assert stats["outcomes"] == expected_outcomes
        assert stats["errors"] == expected_errors
        assert stats["retry_recovered"] == retry_count


def test_percentile_uses_nearest_rank() -> None:
    samples = [1.0, 2.0, 3.0, 4.0]
    assert eval_tools.percentile(samples, 0.5) == 2.0
    assert eval_tools.percentile(samples, 0.95) == 4.0
    assert eval_tools.percentile([5.0], 0.5) == 5.0
    assert eval_tools.percentile([], 0.5) == 0.0


def test_latency_stats_present_and_non_negative(summary: dict) -> None:
    for tool, stats in summary["tools"].items():
        latency = stats["latency_ms"]
        assert latency["sample_count"] >= 1
        assert latency["p50"] >= 0.0
        assert latency["p95"] >= 0.0


def test_json_and_markdown_share_counts(tmp_path: Path) -> None:
    json_path = tmp_path / "evidence.json"
    report_path = tmp_path / "evidence.md"
    summary = eval_tools.run(json_report=json_path, report=report_path)

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["case_count"] == len(summary["cases"])

    markdown = report_path.read_text(encoding="utf-8")
    assert "stage-28-readonly-tool-executor" in markdown
    assert str(summary["case_count"]) in markdown
    for tool, stats in summary["tools"].items():
        assert tool in markdown
        assert str(stats["outcomes"].get("SUCCEEDED", 0)) in markdown
    assert "latency" in markdown.lower()


def test_default_run_writes_default_paths(tmp_path: Path, monkeypatch) -> None:
    json_path = tmp_path / "d.json"
    report_path = tmp_path / "d.md"
    monkeypatch.setattr(eval_tools, "DEFAULT_JSON_REPORT_PATH", json_path)
    monkeypatch.setattr(eval_tools, "DEFAULT_REPORT_PATH", report_path)

    eval_tools.run()

    assert json_path.exists()
    assert report_path.exists()


def test_cases_contain_no_sensitive_fields(summary: dict) -> None:
    _assert_no_sensitive(summary["cases"])


def test_full_summary_contains_no_sensitive_values(summary: dict) -> None:
    _assert_no_sensitive(summary)


def cases_by_label(summary: dict, label: str) -> list[dict]:
    return [c for c in summary["cases"] if label in c["label"]]


def test_eval_tools_forces_hash_offline_despite_external_bge_m3(tmp_path: Path) -> None:
    fake_pkg_dir = tmp_path / "fake_site"
    st_dir = fake_pkg_dir / "sentence_transformers"
    st_dir.mkdir(parents=True)
    sentinel = tmp_path / "sentence_transformers_imported.flag"
    (st_dir / "__init__.py").write_text(
        "import pathlib\n"
        f"pathlib.Path({str(sentinel)!r}).write_text('imported')\n"
        "raise AssertionError('sentence_transformers must not be imported in eval_tools')\n",
        encoding="utf-8",
    )

    json_path = tmp_path / "evidence.json"
    report_path = tmp_path / "evidence.md"

    env = {**os.environ, "EMBEDDING_BACKEND": "bge_m3"}
    env["PYTHONPATH"] = os.pathsep.join(
        [str(fake_pkg_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env.pop("HF_TOKEN", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.eval_tools",
            "--json-report",
            str(json_path),
            "--report",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists(), "eval_tools imported sentence_transformers"
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert "loading weights" not in combined
    assert "huggingface" not in combined
    assert "hf_token" not in combined
    assert "unauthenticated" not in combined

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["environment"]["embedding_backend"] == "hash"
    assert written["claim_boundary"]["hash_embedding"] is True
    assert written["claim_boundary"]["network_access"] is False
