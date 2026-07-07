import json
from pathlib import Path

from scripts import eval_quality_triage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _harness_comparison() -> dict:
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


def _rag_matrix_skip() -> dict:
    return {
        "case_count": 120,
        "top_k": 5,
        "requested_backends": ["hash", "bge_small", "bge_m3"],
        "modes": ["dense", "hybrid", "hybrid_rerank"],
        "real_backend_policy": "skip",
        "rows": {
            "hash": {
                "requested_backend": "hash",
                "effective_backend": "hash",
                "status": "measured",
                "selected_mode": "hybrid_rerank",
                "selection_reason": "...",
                "modes": {
                    "hybrid_rerank": {
                        "global_metrics": {
                            "hit_at_1": 0.43,
                            "recall_at_5": 0.66,
                            "mrr": 0.57,
                            "ndcg_at_5": 0.55,
                        }
                    }
                },
                "deltas_vs_dense": {},
            },
            "bge_small": {
                "requested_backend": "bge_small",
                "effective_backend": None,
                "status": "not_run",
                "reason": "real backend policy is skip",
            },
            "bge_m3": {
                "requested_backend": "bge_m3",
                "effective_backend": None,
                "status": "not_run",
                "reason": "real backend policy is skip",
            },
        },
        "best_real_backend": None,
        "miss_buckets": [],
    }


def _rag_matrix_with_measured_real() -> dict:
    return {
        "case_count": 120,
        "top_k": 5,
        "requested_backends": ["hash", "bge_small"],
        "modes": ["dense", "hybrid", "hybrid_rerank"],
        "real_backend_policy": "auto",
        "rows": {
            "hash": {
                "requested_backend": "hash",
                "effective_backend": "hash",
                "status": "measured",
                "selected_mode": "hybrid_rerank",
                "selection_reason": "...",
                "modes": {
                    "hybrid_rerank": {
                        "global_metrics": {
                            "hit_at_1": 0.43,
                            "recall_at_5": 0.66,
                            "mrr": 0.57,
                            "ndcg_at_5": 0.55,
                        }
                    }
                },
                "deltas_vs_dense": {},
            },
            "bge_small": {
                "requested_backend": "bge_small",
                "effective_backend": "bge_small",
                "status": "measured",
                "selected_mode": "hybrid_rerank",
                "selection_reason": "...",
                "modes": {
                    "hybrid_rerank": {
                        "global_metrics": {
                            "hit_at_1": 0.85,
                            "recall_at_5": 0.90,
                            "mrr": 0.85,
                            "ndcg_at_5": 0.88,
                        }
                    }
                },
                "deltas_vs_dense": {},
            },
        },
        "best_real_backend": "bge_small",
        "miss_buckets": [],
    }


def _trusted_deepseek_report() -> dict:
    return {
        "provider_effective": "deepseek",
        "real_provider_call": True,
        "agent_unsafe_auto_fix_rate": 0.0,
        "agent_hard_constraint_violation_rate": 0.0,
        "agent_risk_accuracy": 1.0,
        "agent_decision_accuracy": 1.0,
        "agent_case_count": 6,
        "gates": {
            "unsafe_auto_fix_pass": True,
            "hard_constraint_violation_pass": True,
        },
    }


def _untrusted_deepseek_report() -> dict:
    return {
        "provider_effective": "fake",
        "real_provider_call": False,
        "agent_unsafe_auto_fix_rate": 0.0,
        "agent_hard_constraint_violation_rate": 0.0,
        "agent_risk_accuracy": 1.0,
        "agent_case_count": 6,
        "gates": {},
    }


def _risky_deepseek_report() -> dict:
    return {
        "provider_effective": "deepseek",
        "real_provider_call": True,
        "agent_unsafe_auto_fix_rate": 0.2,
        "agent_hard_constraint_violation_rate": 0.1,
        "agent_risk_accuracy": 0.8,
        "agent_decision_accuracy": 0.9,
        "agent_case_count": 6,
        "gates": {
            "unsafe_auto_fix_pass": False,
            "hard_constraint_violation_pass": False,
        },
    }


class TestBuildTriageSummary:
    def test_missing_deepseek_becomes_environment_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        findings = summary["findings"]
        agent_findings = [
            f for f in findings if f["area"] == "real_llm_agent_eval"
        ]
        assert len(agent_findings) == 1
        assert agent_findings[0]["category"] == "environment_gap"
        assert "not present" in agent_findings[0]["summary"]

    def test_untrusted_deepseek_report_is_environment_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_untrusted_deepseek_report(),
        )

        agent_findings = [
            f for f in summary["findings"]
            if f["area"] == "real_llm_agent_eval"
        ]
        assert len(agent_findings) == 1
        assert agent_findings[0]["category"] == "environment_gap"
        assert "not trusted" in agent_findings[0]["summary"]

    def test_trusted_deepseek_is_measured_pass(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_trusted_deepseek_report(),
        )

        agent_findings = [
            f for f in summary["findings"]
            if f["area"] == "real_llm_agent_eval"
        ]
        assert len(agent_findings) == 1
        assert agent_findings[0]["category"] == "measured_pass"
        assert agent_findings[0]["evidence"]["trusted"] is True

    def test_trusted_deepseek_with_safety_violations_is_measured_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_risky_deepseek_report(),
        )

        safety_findings = [
            f for f in summary["findings"]
            if f["area"] == "real_llm_agent_safety"
        ]
        assert len(safety_findings) == 1
        assert safety_findings[0]["category"] == "measured_gap"

        quality_findings = [
            f for f in summary["findings"]
            if f["area"] == "real_llm_agent_quality"
        ]
        assert len(quality_findings) == 1
        assert quality_findings[0]["category"] == "measured_gap"

    def test_non_hash_rag_not_run_is_environment_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        bge_findings = [
            f for f in summary["findings"]
            if f["area"].startswith("rag_bge_")
        ]
        assert len(bge_findings) == 2
        for f in bge_findings:
            assert f["category"] == "environment_gap"

    def test_measured_rag_below_prd_is_measured_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        hash_findings = [
            f for f in summary["findings"]
            if f["area"] == "rag_hash"
        ]
        assert len(hash_findings) == 1
        assert hash_findings[0]["category"] == "measured_gap"

    def test_measured_rag_above_prd_is_measured_pass(self) -> None:
        matrix = _rag_matrix_skip()
        gm = matrix["rows"]["hash"]["modes"]["hybrid_rerank"]["global_metrics"]
        gm["recall_at_5"] = 0.90
        gm["mrr"] = 0.80
        gm["ndcg_at_5"] = 0.82

        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=matrix,
            agent_real_report=None,
        )

        hash_findings = [
            f for f in summary["findings"]
            if f["area"] == "rag_hash"
        ]
        assert hash_findings[0]["category"] == "measured_pass"

    def test_measured_real_rag_below_prd_is_measured_gap(self) -> None:
        matrix = _rag_matrix_with_measured_real()
        gm = matrix["rows"]["bge_small"]["modes"]["hybrid_rerank"]["global_metrics"]
        gm["recall_at_5"] = 0.80

        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=matrix,
            agent_real_report=None,
        )

        bge_findings = [
            f for f in summary["findings"]
            if f["area"] == "rag_bge_small_hybrid_rerank"
        ]
        assert len(bge_findings) == 1
        assert bge_findings[0]["category"] == "measured_gap"

    def test_deferred_online_metrics_always_present(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        deferred = [
            f for f in summary["findings"]
            if f["category"] == "deferred_online_metric"
        ]
        areas = {f["area"] for f in deferred}
        assert "online_adoption" in areas
        assert "production_latency" in areas
        assert "production_cost" in areas

    def test_out_of_scope_always_present(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        oos = [
            f for f in summary["findings"]
            if f["category"] == "out_of_scope"
        ]
        areas = {f["area"] for f in oos}
        assert "llm_as_judge" in areas
        assert "immediate_remediation" in areas

    def test_fake_hash_gates_measured_pass(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        gate_findings = [
            f for f in summary["findings"]
            if f["area"] == "default_fake_hash_gates"
        ]
        assert len(gate_findings) == 1
        assert gate_findings[0]["category"] == "measured_pass"
        assert "offline" in str(gate_findings[0]["evidence"])

    def test_failing_gate_is_measured_gap(self) -> None:
        harness = _harness_comparison()
        harness["gates"]["after"]["system_unsafe_auto_fix_pass"] = False

        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=harness,
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        gate_findings = [
            f for f in summary["findings"]
            if f["area"] == "default_fake_hash_gates"
        ]
        assert gate_findings[0]["category"] == "measured_gap"

    def test_finding_categories_are_valid(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        valid = {
            "measured_pass", "measured_gap", "environment_gap",
            "deferred_online_metric", "out_of_scope",
        }
        cats = {f["category"] for f in summary["findings"]}
        assert cats <= valid

    def test_source_reports_point_to_correct_files(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        src = summary["source_reports"]
        assert src["agent_real_json"] is None
        assert src["harness_comparison"] is not None
        assert src["rag_matrix"] is not None

    def test_source_reports_with_agent_path(self) -> None:
        report = _trusted_deepseek_report()
        report["_source_path"] = "reports/agent_eval_deepseek_flash_metrics.json"
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=report,
        )

        src = summary["source_reports"]
        assert src["agent_real_json"] == "reports/agent_eval_deepseek_flash_metrics.json"

    def test_triage_summary_has_required_top_level_keys(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        required = {"evaluated_at", "source_reports", "findings", "next_stage_recommendations"}
        assert required <= set(summary)

    def test_trusted_deepseek_passes_when_all_safe(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_trusted_deepseek_report(),
        )

        safety_gaps = [
            f for f in summary["findings"]
            if f["area"] == "real_llm_agent_safety"
            and f["category"] == "measured_gap"
        ]
        assert len(safety_gaps) == 0

    def test_rag_not_run_is_not_counted_as_measured_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
        )

        bge_pass = [
            f for f in summary["findings"]
            if f["area"].startswith("rag_bge_")
            and f["category"] in ("measured_pass", "measured_gap")
        ]
        assert len(bge_pass) == 0

    def test_cli_with_agent_real_json_missing_does_not_fail(self, tmp_path: Path) -> None:
        harness_path = tmp_path / "comparison.json"
        harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
        rag_path = tmp_path / "rag_matrix.json"
        rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))
        missing_path = tmp_path / "nonexistent.json"

        eval_quality_triage.main([
            "--harness-comparison", str(harness_path),
            "--rag-matrix", str(rag_path),
            "--agent-real-json", str(missing_path),
            "--output", str(tmp_path / "triage.md"),
            "--json-output", str(tmp_path / "triage.json"),
        ])

        output = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
        agent_findings = [
            f for f in output["findings"]
            if f["area"] == "real_llm_agent_eval"
        ]
        assert len(agent_findings) == 1
        assert agent_findings[0]["category"] == "environment_gap"

    def test_cli_writes_both_formats(self, tmp_path: Path) -> None:
        harness_path = tmp_path / "comparison.json"
        harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
        rag_path = tmp_path / "rag_matrix.json"
        rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))

        eval_quality_triage.main([
            "--harness-comparison", str(harness_path),
            "--rag-matrix", str(rag_path),
            "--output", str(tmp_path / "triage.md"),
            "--json-output", str(tmp_path / "triage.json"),
        ])

        md = (tmp_path / "triage.md").read_text(encoding="utf-8")
        assert "# Real Quality Triage Summary" in md
        assert "## Findings" in md
        assert "Measured Pass" in md or "measured_pass" in md
        assert "Measured Gap" in md or "measured_gap" in md

        js = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
        assert "findings" in js
        assert "source_reports" in js
        assert "next_stage_recommendations" in js

    def test_markdown_includes_source_report_paths(self, tmp_path: Path) -> None:
        harness_path = tmp_path / "comparison.json"
        harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
        rag_path = tmp_path / "rag_matrix.json"
        rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))

        eval_quality_triage.main([
            "--harness-comparison", str(harness_path),
            "--rag-matrix", str(rag_path),
            "--output", str(tmp_path / "triage.md"),
            "--json-output", str(tmp_path / "triage.json"),
        ])

        md = (tmp_path / "triage.md").read_text(encoding="utf-8")
        assert "comparison.json" in md
        assert "rag_matrix.json" in md
        assert "(not present)" in md.lower() or "not present" in md
        js = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
        assert js["source_reports"]["agent_real_json"] is None


def test_missing_agent_real_json_path_preserved_in_source_reports(
    tmp_path: Path,
) -> None:
    harness_path = tmp_path / "comparison.json"
    harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
    rag_path = tmp_path / "rag_matrix.json"
    rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))
    missing_path = tmp_path / "nonexistent.json"

    eval_quality_triage.main([
        "--harness-comparison", str(harness_path),
        "--rag-matrix", str(rag_path),
        "--agent-real-json", str(missing_path),
        "--output", str(tmp_path / "triage.md"),
        "--json-output", str(tmp_path / "triage.json"),
    ])

    js = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
    assert js["source_reports"]["agent_real_json"] == str(missing_path)

    md = (tmp_path / "triage.md").read_text(encoding="utf-8")
    assert "nonexistent.json" in md


def test_missing_agent_real_json_is_environment_gap(
    tmp_path: Path,
) -> None:
    harness_path = tmp_path / "comparison.json"
    harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
    rag_path = tmp_path / "rag_matrix.json"
    rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))
    missing_path = tmp_path / "nonexistent.json"

    eval_quality_triage.main([
        "--harness-comparison", str(harness_path),
        "--rag-matrix", str(rag_path),
        "--agent-real-json", str(missing_path),
        "--output", str(tmp_path / "triage.md"),
        "--json-output", str(tmp_path / "triage.json"),
    ])

    js = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
    agent_findings = [
        f for f in js["findings"]
        if f["area"] == "real_llm_agent_eval"
    ]
    assert len(agent_findings) == 1
    assert agent_findings[0]["category"] == "environment_gap"
    assert "not present" in agent_findings[0]["summary"]


# ---------------------------------------------------------------------------
# TASK-17.4: Real Evidence Summary tests
# ---------------------------------------------------------------------------


def _performance_cost_fake() -> dict:
    return {
        "run_count": 5,
        "provider_effective": "fake",
        "model_effective": "fake-llm",
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": {
                "avg_latency_ms": 0.06, "p95_latency_ms": 0.10,
                "min_latency_ms": 0.03, "max_latency_ms": 0.12,
                "samples_ms": [0.06, 0.10, 0.05, 0.04, 0.03],
            },
            "rag_search": {
                "avg_latency_ms": 42.0, "p95_latency_ms": 206.0,
                "min_latency_ms": 0.7, "max_latency_ms": 206.0,
                "samples_ms": [206.0, 0.9, 0.8, 0.7, 0.7],
            },
        },
        "tokens": {
            "token_usage_available": False,
            "input_tokens": None, "output_tokens": None, "total_tokens": None,
        },
        "cost": {
            "cost_available": False,
            "estimated_cost_usd": None,
            "assumptions": "fake provider; no real LLM cost",
        },
    }


def _performance_cost_real() -> dict:
    return {
        "run_count": 2,
        "provider_effective": "deepseek",
        "model_effective": "deepseek-v4-flash",
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": {
                "avg_latency_ms": 1200.0, "p95_latency_ms": 1350.0,
                "min_latency_ms": 1100.0, "max_latency_ms": 1400.0,
                "samples_ms": [1100.0, 1350.0],
            },
            "rag_search": {
                "avg_latency_ms": 50.0, "p95_latency_ms": 55.0,
                "min_latency_ms": 45.0, "max_latency_ms": 56.0,
                "samples_ms": [45.0, 56.0],
            },
        },
        "tokens": {
            "token_usage_available": True,
            "input_tokens": 1000, "output_tokens": 60, "total_tokens": 1060,
        },
        "cost": {
            "cost_available": True,
            "estimated_cost_usd": "0.0004842",
            "assumptions": "DeepSeek v4 Pro pricing",
        },
    }


class TestBuildTriageSummaryExtended:
    def test_performance_cost_optional_missing_is_not_error(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=None,
        )
        perf_findings = [
            f for f in summary["findings"]
            if f["area"] == "performance_cost"
        ]
        assert len(perf_findings) == 1
        assert perf_findings[0]["category"] == "environment_gap"

    def test_source_reports_includes_performance_cost(self) -> None:
        pc = _performance_cost_fake()
        pc["_source_path"] = "reports/performance_cost_benchmark.json"
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=pc,
        )
        assert summary["source_reports"]["performance_cost_json"] == "reports/performance_cost_benchmark.json"

    def test_source_reports_with_performance_cost_path(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=None,
            performance_cost_path="reports/pc_bench.json",
        )
        assert summary["source_reports"]["performance_cost_json"] == "reports/pc_bench.json"

    def test_resume_safe_facts_present(self) -> None:
        pc = _performance_cost_fake()
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=pc,
        )
        assert "resume_safe_facts" in summary
        assert len(summary["resume_safe_facts"]) >= 1

    def test_resume_safe_facts_each_has_source_and_boundary(self) -> None:
        pc = _performance_cost_fake()
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=pc,
        )
        for fact in summary["resume_safe_facts"]:
            assert "area" in fact
            assert "fact" in fact
            assert "source_report" in fact
            assert "boundary" in fact

    def test_resume_safe_facts_no_deepseek_when_not_trusted(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_untrusted_deepseek_report(),
            performance_cost_report=_performance_cost_fake(),
        )
        agent_facts = [f for f in summary["resume_safe_facts"] if f["area"] == "agent"]
        assert len(agent_facts) == 0

    def test_resume_safe_facts_has_deepseek_when_trusted(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_trusted_deepseek_report(),
            performance_cost_report=_performance_cost_fake(),
        )
        agent_facts = [f for f in summary["resume_safe_facts"] if f["area"] == "agent"]
        assert len(agent_facts) == 1

    def test_bullet_draft_no_cost_when_fake(self) -> None:
        pc = _performance_cost_fake()
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=pc,
        )
        cost_facts_in_safe = [f for f in summary["resume_safe_facts"] if f["area"] == "cost"]
        assert len(cost_facts_in_safe) == 0

    def test_bullet_draft_no_cost_number_when_not_available(self) -> None:
        pc = _performance_cost_real()
        pc["cost"]["cost_available"] = False
        pc["cost"]["estimated_cost_usd"] = None
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=pc,
        )
        cost_facts = [f for f in summary["resume_safe_facts"] if f["area"] == "cost"]
        assert len(cost_facts) == 0

    def test_cost_fact_when_real_and_available(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_real(),
        )
        cost_facts = [f for f in summary["resume_safe_facts"] if f["area"] == "cost"]
        assert len(cost_facts) == 1

    def test_claim_boundary_present(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_fake(),
        )
        assert "claim_boundary" in summary
        boundaries = summary["claim_boundary"]
        assert any("offline benchmark" in b for b in boundaries)
        assert any("production SLA" in b for b in boundaries)

    def test_claim_boundary_notes_deepseek_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=None,
        )
        boundaries = summary["claim_boundary"]
        assert any("DeepSeek" in b for b in boundaries)
        assert any("not run" in b for b in boundaries)

    def test_claim_boundary_notes_fake_perf(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_fake(),
        )
        boundaries = summary["claim_boundary"]
        assert any("fake provider" in b for b in boundaries)

    def test_resume_bullet_draft_present(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_fake(),
        )
        assert "resume_bullet_draft" in summary
        assert len(summary["resume_bullet_draft"]) >= 1

    def test_triage_summary_has_all_required_top_level_keys(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_fake(),
        )
        required = {
            "evaluated_at", "source_reports", "findings",
            "resume_safe_facts", "resume_bullet_draft",
            "claim_boundary", "next_stage_recommendations",
        }
        assert required <= set(summary)

    def test_performance_cost_fake_is_deferred_for_real(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_fake(),
        )
        perf_deferred = [
            f for f in summary["findings"]
            if f["area"] == "performance_cost_real"
        ]
        assert len(perf_deferred) == 1
        assert perf_deferred[0]["category"] == "deferred_online_metric"

    def test_risky_deepseek_unsafe_rate_enters_measured_gap(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_risky_deepseek_report(),
            performance_cost_report=None,
        )
        safety_findings = [
            f for f in summary["findings"]
            if f["area"] == "real_llm_agent_safety"
        ]
        assert len(safety_findings) == 1
        assert safety_findings[0]["category"] == "measured_gap"
        assert safety_findings[0]["evidence"]["unsafe_auto_fix_rate"] > 0

    def test_bullet_draft_does_not_write_deepseek_measured_when_not_trusted(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=_untrusted_deepseek_report(),
            performance_cost_report=None,
        )
        for bullet in summary["resume_bullet_draft"]:
            assert "deepseek" not in bullet.lower()

    def test_bullet_draft_does_not_write_cost_number_when_not_available(self) -> None:
        summary = eval_quality_triage.build_triage_summary(
            harness_comparison=_harness_comparison(),
            rag_matrix=_rag_matrix_skip(),
            agent_real_report=None,
            performance_cost_report=_performance_cost_fake(),
        )
        bullets_text = " ".join(summary["resume_bullet_draft"])
        assert "USD" not in bullets_text or "cost" not in bullets_text.lower()

    def test_markdown_includes_resume_sections(self, tmp_path: Path) -> None:
        harness_path = tmp_path / "comparison.json"
        harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
        rag_path = tmp_path / "rag_matrix.json"
        rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))
        pc_path = tmp_path / "perf.json"
        pc_path.write_text(json.dumps(_performance_cost_fake(), ensure_ascii=False))

        eval_quality_triage.main([
            "--harness-comparison", str(harness_path),
            "--rag-matrix", str(rag_path),
            "--performance-cost-json", str(pc_path),
            "--output", str(tmp_path / "triage.md"),
            "--json-output", str(tmp_path / "triage.json"),
        ])

        md = (tmp_path / "triage.md").read_text(encoding="utf-8")
        assert "Resume-Safe Facts" in md
        assert "Resume Bullet Draft" in md
        assert "Claim Boundary" in md

    def test_cli_performance_cost_json_optional_missing(self, tmp_path: Path) -> None:
        harness_path = tmp_path / "comparison.json"
        harness_path.write_text(json.dumps(_harness_comparison(), ensure_ascii=False))
        rag_path = tmp_path / "rag_matrix.json"
        rag_path.write_text(json.dumps(_rag_matrix_skip(), ensure_ascii=False))
        missing_path = tmp_path / "nonexistent_perf.json"

        eval_quality_triage.main([
            "--harness-comparison", str(harness_path),
            "--rag-matrix", str(rag_path),
            "--performance-cost-json", str(missing_path),
            "--output", str(tmp_path / "triage.md"),
            "--json-output", str(tmp_path / "triage.json"),
        ])

        js = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
        assert js["source_reports"]["performance_cost_json"] == str(missing_path)
        perf_findings = [
            f for f in js["findings"]
            if f["area"] == "performance_cost"
        ]
        assert len(perf_findings) == 1
        assert perf_findings[0]["category"] == "environment_gap"
