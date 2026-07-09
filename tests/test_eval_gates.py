import json
from pathlib import Path
from typing import Any

from scripts import eval_gates


REQUIRED_CHECK_IDS = {
    "ci_default_fake_hash_harness_gates",
    "ci_agent_schema_conformance",
    "manual_deepseek_agent_eval",
    "manual_real_embedding_rag_matrix",
    "manual_real_provider_performance_cost",
    "release_effective_unsafe_auto_fix_zero",
    "release_effective_hard_constraint_violation_zero",
    "release_real_provider_trust_visible",
    "release_real_embedding_trust_visible",
    "release_performance_cost_trust_visible",
}


def _passing_harness_comparison() -> dict[str, Any]:
    return {
        "gates": {
            "before": {
                "system_unsafe_auto_fix_pass": True,
                "system_hard_constraint_violation_pass": True,
                "agent_unsafe_auto_fix_pass": True,
                "agent_hard_constraint_violation_pass": True,
            },
            "after": {
                "system_unsafe_auto_fix_pass": True,
                "system_hard_constraint_violation_pass": True,
                "agent_unsafe_auto_fix_pass": True,
                "agent_hard_constraint_violation_pass": True,
            },
            "changes": [],
        },
    }


def _failing_harness_comparison() -> dict[str, Any]:
    return {
        "gates": {
            "before": {
                "system_unsafe_auto_fix_pass": True,
                "system_hard_constraint_violation_pass": True,
                "agent_unsafe_auto_fix_pass": True,
                "agent_hard_constraint_violation_pass": True,
            },
            "after": {
                "system_unsafe_auto_fix_pass": True,
                "system_hard_constraint_violation_pass": True,
                "agent_unsafe_auto_fix_pass": False,
                "agent_hard_constraint_violation_pass": True,
            },
            "changes": [],
        },
    }


def _schema_conformance_pass() -> dict[str, Any]:
    return {
        "schema_conformance_rate": 1.0,
        "evaluated_at": "2026-07-09T09:09:24.948080Z",
    }


def _schema_conformance_fail(schema_conformance_rate: float = 0.99) -> dict[str, Any]:
    return {
        "schema_conformance_rate": schema_conformance_rate,
        "evaluated_at": "2026-07-09T09:09:24.948080Z",
    }


def _trusted_deepseek_agent_report() -> dict[str, Any]:
    return {
        "agent_schema_pass_rate": 1.0,
        "agent_decision_accuracy": 1.0,
        "agent_risk_accuracy": 1.0,
        "agent_hard_constraint_violation_rate": 0.0,
        "agent_unsafe_auto_fix_rate": 0.0,
        "agent_case_count": 6.0,
        "gates": {
            "unsafe_auto_fix_pass": True,
            "hard_constraint_violation_pass": True,
        },
        "provider_requested": "deepseek",
        "provider_effective": "deepseek",
        "model_requested": "deepseek-v4-flash",
        "model_effective": "deepseek-v4-flash",
        "real_provider_call": True,
        "evaluated_at": "2026-07-08T06:19:49.229497Z",
    }


def _untrusted_fake_agent_report() -> dict[str, Any]:
    return {
        "agent_hard_constraint_violation_rate": 0.0,
        "agent_unsafe_auto_fix_rate": 0.0,
        "gates": {
            "unsafe_auto_fix_pass": True,
            "hard_constraint_violation_pass": True,
        },
        "provider_requested": "deepseek",
        "provider_effective": "fake",
        "model_effective": "fake-model",
        "real_provider_call": False,
        "evaluated_at": "2026-07-08T06:19:49.229497Z",
    }


def _trusted_real_rag_matrix() -> dict[str, Any]:
    return {
        "case_count": 120,
        "top_k": 5,
        "real_backend_policy": "auto",
        "rows": {
            "hash": {
                "requested_backend": "hash",
                "effective_backend": "hash",
                "status": "measured",
                "selected_mode": "hybrid_rerank",
                "modes": {
                    "hybrid_rerank": {
                        "global_metrics": {
                            "hit_at_1": 0.53,
                            "recall_at_5": 0.70,
                            "mrr": 0.64,
                            "ndcg_at_5": 0.62,
                        }
                    }
                },
            },
            "bge_small": {
                "requested_backend": "bge_small",
                "effective_backend": "bge_small",
                "status": "measured",
                "selected_mode": "dense",
                "modes": {
                    "dense": {
                        "global_metrics": {
                            "hit_at_1": 0.59,
                            "recall_at_5": 0.79,
                            "mrr": 0.71,
                            "ndcg_at_5": 0.69,
                        }
                    }
                },
            },
        },
        "real_backend_requirement": {
            "required_backend": "bge_small",
            "satisfied": True,
            "measured_real_backends": ["bge_small"],
            "unavailable_real_backends": [],
            "not_run_real_backends": [],
            "reason": "bge_small measured with trusted effective backend",
        },
    }


def _fallback_real_rag_matrix() -> dict[str, Any]:
    return {
        "case_count": 120,
        "top_k": 5,
        "real_backend_policy": "auto",
        "rows": {
            "hash": {
                "requested_backend": "hash",
                "effective_backend": "hash",
                "status": "measured",
                "selected_mode": "hybrid_rerank",
                "modes": {
                    "hybrid_rerank": {
                        "global_metrics": {
                            "hit_at_1": 0.53,
                            "recall_at_5": 0.70,
                            "mrr": 0.64,
                            "ndcg_at_5": 0.62,
                        }
                    }
                },
            },
            "bge_small": {
                "requested_backend": "bge_small",
                "effective_backend": "hash",
                "status": "unavailable",
                "reason": "sentence-transformers not installed; fell back to hash",
            },
        },
        "real_backend_requirement": {
            "required_backend": "bge_small",
            "satisfied": False,
            "measured_real_backends": [],
            "unavailable_real_backends": ["bge_small"],
            "not_run_real_backends": [],
            "reason": "bge_small unavailable; fell back to hash",
        },
    }


def _trusted_performance_cost_report() -> dict[str, Any]:
    return {
        "evaluated_at": "2026-07-09T07:45:52.133525Z",
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "measured",
        "run_count": 5,
        "provider_requested": "deepseek",
        "provider_effective": "deepseek",
        "model_requested": "deepseek-v4-flash",
        "model_effective": "deepseek-v4-flash",
        "latency": {
            "extraction_agent": {"avg_latency_ms": 3312.742, "p95_latency_ms": 4661.419},
            "rag_search": {"avg_latency_ms": 1308.533, "p95_latency_ms": 6278.735},
        },
        "tokens": {
            "token_usage_available": True,
            "input_tokens": 1115,
            "output_tokens": 1105,
            "total_tokens": 2220,
            "unavailable_reason": None,
        },
        "cost": {
            "cost_available": True,
            "estimated_cost_usd": "0.001446375",
            "per_case_estimated_cost_usd": "0.000289275",
            "unavailable_reason": None,
        },
        "trust": {
            "trusted": True,
            "real_provider_evidence": True,
            "cost_evidence_available": True,
            "reasons": [],
        },
        "environment_gap": None,
    }


def _fake_performance_cost_report() -> dict[str, Any]:
    return {
        "evaluated_at": "2026-07-09T07:45:52.133525Z",
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "measured",
        "run_count": 5,
        "provider_requested": "deepseek",
        "provider_effective": "fake",
        "model_effective": "fake-model",
        "latency": {
            "extraction_agent": {"avg_latency_ms": 12.0, "p95_latency_ms": 20.0},
            "rag_search": {"avg_latency_ms": 5.0, "p95_latency_ms": 9.0},
        },
        "tokens": {
            "token_usage_available": False,
            "unavailable_reason": "fake provider does not report token usage",
        },
        "cost": {
            "cost_available": False,
            "unavailable_reason": "no token usage",
        },
        "trust": {
            "trusted": False,
            "real_provider_evidence": False,
            "cost_evidence_available": False,
            "reasons": ["fake provider"],
        },
        "environment_gap": None,
    }


def _all_checks_by_id(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    for layer in summary["layers"].values():
        for check in layer["checks"]:
            checks[check["id"]] = check
    return checks


def _all_check_ids(summary: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for layer in summary["layers"].values():
        for check in layer["checks"]:
            ids.append(check["id"])
    return ids


def test_build_eval_gate_summary_all_layers_pass() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_passing_harness_comparison(),
        schema_conformance=_schema_conformance_pass(),
        agent_real_report=_trusted_deepseek_agent_report(),
        rag_matrix=_trusted_real_rag_matrix(),
        performance_cost_report=_trusted_performance_cost_report(),
    )

    assert summary["stage"] == "stage-24-eval-gate-layering"
    assert summary["overall_status"] == "pass"
    assert summary["layers"]["ci"]["status"] == "pass"
    assert summary["layers"]["manual_diagnostic"]["status"] == "pass"
    assert summary["layers"]["release"]["status"] == "pass"
    assert summary["layers"]["manual_diagnostic"]["required_for_default_ci"] is False

    ids = _all_check_ids(summary)
    assert set(ids) == REQUIRED_CHECK_IDS
    assert len(ids) == len(REQUIRED_CHECK_IDS)


def test_ci_gate_failure_blocks_ci_and_release() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_failing_harness_comparison(),
        schema_conformance=_schema_conformance_pass(),
        agent_real_report=_trusted_deepseek_agent_report(),
        rag_matrix=_trusted_real_rag_matrix(),
        performance_cost_report=_trusted_performance_cost_report(),
    )

    checks = _all_checks_by_id(summary)
    harness = checks["ci_default_fake_hash_harness_gates"]
    assert harness["status"] == "fail"
    assert harness["blocks_ci"] is True
    assert harness["blocks_release"] is True

    assert summary["layers"]["ci"]["status"] == "fail"
    assert summary["overall_status"] == "blocked"


def test_schema_conformance_below_one_fails_ci() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_passing_harness_comparison(),
        schema_conformance=_schema_conformance_fail(schema_conformance_rate=0.99),
        agent_real_report=_trusted_deepseek_agent_report(),
        rag_matrix=_trusted_real_rag_matrix(),
        performance_cost_report=_trusted_performance_cost_report(),
    )

    check = _all_checks_by_id(summary)["ci_agent_schema_conformance"]
    assert check["status"] == "fail"
    assert check["evidence"]["schema_conformance_rate"] == 0.99


def test_missing_deepseek_report_is_manual_gap_and_release_block() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_passing_harness_comparison(),
        schema_conformance=_schema_conformance_pass(),
        agent_real_report=None,
        rag_matrix=_trusted_real_rag_matrix(),
        performance_cost_report=_trusted_performance_cost_report(),
    )

    checks = _all_checks_by_id(summary)
    manual = checks["manual_deepseek_agent_eval"]
    assert manual["status"] == "environment_gap"
    assert manual["blocks_ci"] is False

    unsafe = checks["release_effective_unsafe_auto_fix_zero"]
    hard = checks["release_effective_hard_constraint_violation_zero"]
    assert unsafe["status"] == "environment_gap"
    assert hard["status"] == "environment_gap"
    assert unsafe["blocks_release"] is True
    assert hard["blocks_release"] is True


def test_untrusted_deepseek_report_does_not_satisfy_release_safety() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_passing_harness_comparison(),
        schema_conformance=_schema_conformance_pass(),
        agent_real_report=_untrusted_fake_agent_report(),
        rag_matrix=_trusted_real_rag_matrix(),
        performance_cost_report=_trusted_performance_cost_report(),
    )

    checks = _all_checks_by_id(summary)
    assert checks["manual_deepseek_agent_eval"]["status"] == "environment_gap"
    assert checks["release_real_provider_trust_visible"]["status"] == "environment_gap"


def test_real_embedding_fallback_does_not_count_as_release_pass() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_passing_harness_comparison(),
        schema_conformance=_schema_conformance_pass(),
        agent_real_report=_trusted_deepseek_agent_report(),
        rag_matrix=_fallback_real_rag_matrix(),
        performance_cost_report=_trusted_performance_cost_report(),
    )

    checks = _all_checks_by_id(summary)
    assert checks["manual_real_embedding_rag_matrix"]["status"] == "environment_gap"
    assert checks["release_real_embedding_trust_visible"]["status"] == "environment_gap"


def test_fake_performance_cost_is_visible_diagnostic_gap() -> None:
    summary = eval_gates.build_eval_gate_summary(
        harness_comparison=_passing_harness_comparison(),
        schema_conformance=_schema_conformance_pass(),
        agent_real_report=_trusted_deepseek_agent_report(),
        rag_matrix=_trusted_real_rag_matrix(),
        performance_cost_report=_fake_performance_cost_report(),
    )

    checks = _all_checks_by_id(summary)
    manual = checks["manual_real_provider_performance_cost"]
    assert manual["status"] == "environment_gap"
    assert manual["blocks_ci"] is False

    release = checks["release_performance_cost_trust_visible"]
    assert release["status"] != "pass"
    assert release["evidence"].get("provider_effective") == "fake"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


REQUIRED_MARKDOWN_HEADINGS = [
    "# Evaluation Gate Summary",
    "## Source Reports",
    "## CI Layer",
    "## Manual Diagnostic Layer",
    "## Release Layer",
    "## Claim Boundary",
    "## Exit Semantics",
]


def test_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    harness = tmp_path / "comparison.json"
    schema = tmp_path / "schema.json"
    agent = tmp_path / "agent.json"
    rag = tmp_path / "rag.json"
    perf = tmp_path / "perf.json"
    _write_json(harness, _passing_harness_comparison())
    _write_json(schema, _schema_conformance_pass())
    _write_json(agent, _trusted_deepseek_agent_report())
    _write_json(rag, _trusted_real_rag_matrix())
    _write_json(perf, _trusted_performance_cost_report())

    md_output = tmp_path / "eval_gate_summary.md"
    json_output = tmp_path / "eval_gate_summary.json"

    exit_code = eval_gates.main([
        "--harness-comparison", str(harness),
        "--schema-conformance", str(schema),
        "--agent-real-json", str(agent),
        "--rag-matrix", str(rag),
        "--performance-cost-json", str(perf),
        "--output", str(md_output),
        "--json-output", str(json_output),
    ])

    assert exit_code == 0
    assert json_output.exists()
    assert md_output.exists()

    data = json.loads(json_output.read_text(encoding="utf-8"))
    assert "layers" in data

    md_text = md_output.read_text(encoding="utf-8")
    for heading in REQUIRED_MARKDOWN_HEADINGS:
        assert heading in md_text


def test_cli_writes_outputs_before_release_block_exit(tmp_path: Path) -> None:
    harness = tmp_path / "comparison.json"
    schema = tmp_path / "schema.json"
    rag = tmp_path / "rag.json"
    perf = tmp_path / "perf.json"
    _write_json(harness, _passing_harness_comparison())
    _write_json(schema, _schema_conformance_pass())
    _write_json(rag, _trusted_real_rag_matrix())
    _write_json(perf, _trusted_performance_cost_report())

    md_output = tmp_path / "eval_gate_summary.md"
    json_output = tmp_path / "eval_gate_summary.json"

    exit_code = eval_gates.main([
        "--harness-comparison", str(harness),
        "--schema-conformance", str(schema),
        "--agent-real-json", str(tmp_path / "missing_agent.json"),
        "--rag-matrix", str(rag),
        "--performance-cost-json", str(perf),
        "--output", str(md_output),
        "--json-output", str(json_output),
        "--fail-on-release-block",
    ])

    assert exit_code == 2
    assert json_output.exists()
    assert md_output.exists()


def test_cli_ci_failure_returns_one(tmp_path: Path) -> None:
    harness = tmp_path / "comparison.json"
    schema = tmp_path / "schema.json"
    _write_json(harness, _failing_harness_comparison())
    _write_json(schema, _schema_conformance_pass())

    exit_code = eval_gates.main([
        "--harness-comparison", str(harness),
        "--schema-conformance", str(schema),
        "--agent-real-json", str(tmp_path / "missing_agent.json"),
        "--rag-matrix", str(tmp_path / "missing_rag.json"),
        "--performance-cost-json", str(tmp_path / "missing_perf.json"),
        "--output", str(tmp_path / "out.md"),
        "--json-output", str(tmp_path / "out.json"),
    ])

    assert exit_code == 1


def test_cli_default_does_not_fail_on_release_block(tmp_path: Path) -> None:
    harness = tmp_path / "comparison.json"
    schema = tmp_path / "schema.json"
    _write_json(harness, _passing_harness_comparison())
    _write_json(schema, _schema_conformance_pass())

    exit_code = eval_gates.main([
        "--harness-comparison", str(harness),
        "--schema-conformance", str(schema),
        "--agent-real-json", str(tmp_path / "missing_agent.json"),
        "--rag-matrix", str(tmp_path / "missing_rag.json"),
        "--performance-cost-json", str(tmp_path / "missing_perf.json"),
        "--output", str(tmp_path / "out.md"),
        "--json-output", str(tmp_path / "out.json"),
    ])

    assert exit_code == 0
