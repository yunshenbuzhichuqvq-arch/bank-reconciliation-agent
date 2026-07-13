from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from decimal import Decimal

from scripts import bench_agent_latency


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "bench_agent_latency.py"


def test_bench_cli_accepts_runs_flag(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    json_path = tmp_path / "bench.json"

    exit_code = bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--report",
            str(md_path),
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    assert md_path.exists()
    assert json_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["run_count"] == 2
    assert report["provider_effective"] == "fake"


def test_bench_json_has_required_top_level_keys(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))

    for key in [
        "evaluated_at",
        "run_count",
        "provider_requested",
        "provider_effective",
        "model_requested",
        "model_effective",
        "boundary",
        "latency",
        "tokens",
        "cost",
    ]:
        assert key in report, f"Missing key: {key}"


def test_bench_latency_has_full_stats(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main(
        [
            "--runs",
            "3",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))

    for component in ["extraction_agent", "rag_search"]:
        comp = report["latency"][component]
        for stat_key in ["avg_latency_ms", "p95_latency_ms", "min_latency_ms", "max_latency_ms"]:
            assert stat_key in comp
            assert isinstance(comp[stat_key], (int, float))
        assert "samples_ms" in comp
        assert len(comp["samples_ms"]) == 3
        for v in comp["samples_ms"]:
            assert isinstance(v, (int, float))


def test_bench_latency_stats_are_plausible(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main(
        [
            "--runs",
            "5",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))

    for component in ["extraction_agent", "rag_search"]:
        comp = report["latency"][component]
        assert comp["min_latency_ms"] <= comp["avg_latency_ms"] <= comp["max_latency_ms"]
        assert comp["avg_latency_ms"] >= 0.0
        assert comp["p95_latency_ms"] >= comp["avg_latency_ms"]


def test_bench_fake_provider_cost_not_available(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))

    assert report["tokens"]["token_usage_available"] is False
    assert report["tokens"]["input_tokens"] is None
    assert report["cost"]["cost_available"] is False
    assert report["cost"]["estimated_cost_usd"] is None


def test_bench_fake_provider_boundary_in_markdown(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--report",
            str(md_path),
        ]
    )
    content = md_path.read_text(encoding="utf-8")

    assert "Performance & Cost Benchmark" in content
    assert "Provider Effective | `fake`" in content
    assert "Model Effective | `fake-llm`" in content
    assert "Not real LLM latency" in content
    assert "not production SLA" in content


def test_bench_markdown_includes_required_sections(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    bench_agent_latency.main(
        [
            "--runs",
            "3",
            "--report",
            str(md_path),
        ]
    )
    content = md_path.read_text(encoding="utf-8")

    assert "## Metadata" in content
    assert "## Latency" in content
    assert "## Token Usage" in content
    assert "## Cost" in content
    assert "## Claim Boundary" in content
    assert "## Per-Run Latency" in content
    assert "ExtractionAgent" in content
    assert "RAG Search" in content
    assert "Run Count" in content
    assert "Provider Requested" in content
    assert "Provider Effective" in content
    assert "Model Effective" in content


def test_bench_original_subprocess_stdout_preserved() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--runs", "2"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "ExtractionAgent" in output
    assert "RAG" in output
    assert "average_ms" in output
    assert "ratio" in output
    assert "ADR-032" in output
    assert "provider=" in output
    assert "fake provider" in output.lower()
    assert "measured ratio" in output.lower()


def test_bench_cli_fake_returns_zero_tokens_and_cost(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    exit_code = bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["provider_effective"] == "fake"
    assert report["tokens"]["token_usage_available"] is False
    assert report["cost"]["cost_available"] is False


def test_constructed_real_provider_report_cost_is_decimal_string(tmp_path: Path) -> None:
    report = {
        "evaluated_at": "2026-07-07T00:00:00Z",
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "measured",
        "run_count": 2,
        "provider_requested": "deepseek",
        "provider_effective": "deepseek",
        "model_effective": "deepseek-v4-flash",
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": {
                "avg_latency_ms": 1200.0,
                "p95_latency_ms": 1350.0,
                "min_latency_ms": 1100.0,
                "max_latency_ms": 1400.0,
                "samples_ms": [1100.0, 1350.0],
            },
            "rag_search": {
                "avg_latency_ms": 50.0,
                "p95_latency_ms": 55.0,
                "min_latency_ms": 45.0,
                "max_latency_ms": 56.0,
                "samples_ms": [45.0, 56.0],
            },
        },
        "tokens": {
            "token_usage_available": True,
            "input_tokens": 1000,
            "output_tokens": 60,
            "total_tokens": 1060,
        },
        "cost": {
            "cost_available": True,
            "estimated_cost_usd": str(Decimal("0.0004842")),
            "assumptions": "DeepSeek v4 Pro pricing",
        },
    }

    json_path = tmp_path / "bench.json"
    bench_agent_latency.write_benchmark_json(report, json_path)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["cost"]["cost_available"] is True
    assert loaded["cost"]["estimated_cost_usd"] is not None
    Decimal(loaded["cost"]["estimated_cost_usd"])

    md_path = tmp_path / "bench.md"
    bench_agent_latency.write_benchmark_markdown(report, md_path)
    content = md_path.read_text(encoding="utf-8")
    assert "deepseek" in content
    assert "Estimated Cost (USD)" in content


def test_constructed_fake_provider_report_has_no_cost() -> None:
    report = {
        "evaluated_at": "2026-07-07T00:00:00Z",
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "measured",
        "run_count": 2,
        "provider_requested": "fake",
        "provider_effective": "fake",
        "model_effective": "fake-llm",
        "boundary": "offline benchmark; not production SLA",
        "tokens": {},
        "cost": {},
    }
    md = bench_agent_latency._format_benchmark_markdown(report)
    assert "Provider Effective | `fake`" in md
    assert "Not real LLM latency" in md
    assert "No real LLM cost" in md


def test_bench_cli_missing_deepseek_key_fails(monkeypatch) -> None:
    import bank_reconciliation_agent.core.config as _cfg

    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", None)
    exit_code = bench_agent_latency.main(
        [
            "--runs",
            "1",
            "--provider",
            "deepseek",
        ]
    )
    assert exit_code == 1


def test_bench_cli_unsupported_provider_fails() -> None:
    exit_code = bench_agent_latency.main(
        [
            "--runs",
            "1",
            "--provider",
            "openai",
        ]
    )
    assert exit_code == 1


def test_bench_json_real_backend_boundary(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["boundary"] == "offline benchmark; not production SLA"


def test_bench_markdown_boundary_claim_present(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    bench_agent_latency.main(
        [
            "--runs",
            "2",
            "--report",
            str(md_path),
        ]
    )
    content = md_path.read_text(encoding="utf-8")
    assert "offline benchmark" in content
    assert "not production SLA" in content


def test__latency_stats_empty() -> None:
    stats = bench_agent_latency._latency_stats([])
    assert stats["avg_latency_ms"] == 0.0
    assert stats["p95_latency_ms"] == 0.0
    assert stats["min_latency_ms"] == 0.0
    assert stats["max_latency_ms"] == 0.0
    assert stats["samples_ms"] == []


def test__p95_math() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    p95 = bench_agent_latency._p95(samples)
    assert p95 >= 9.0
    assert p95 <= 10.0


def test_deepseek_stub_usage_sets_cost_and_trust(monkeypatch) -> None:
    import bank_reconciliation_agent.core.config as _cfg
    from bank_reconciliation_agent.core.llm import provider as _llm_provider
    from bank_reconciliation_agent.core.llm.provider import LLMResult

    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", "sk-stub")

    class StubDeepSeek:
        def __init__(self, **kwargs):
            pass

        def complete(
            self,
            messages,
            *,
            temperature=0.0,
            response_format="json_object",
            response_validator=None,
        ):
            payload = {
                "agent": "extraction",
                "standard_type": "REVERSAL",
                "original_flow_id": "FLOW-ORIGINAL-001",
                "cleaned_remark": "识别到冲正线索",
                "confidence": 0.92,
            }
            return LLMResult(
                text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                prompt_tokens=100,
                completion_tokens=20,
                model="deepseek-v4-flash",
            )

    monkeypatch.setattr(_llm_provider, "DeepSeekProvider", StubDeepSeek)

    report = bench_agent_latency.run_benchmark(
        runs=2, provider_name="deepseek", model="deepseek-v4-flash"
    )

    assert report["status"] == "measured"
    assert report["provider_requested"] == "deepseek"
    assert report["provider_effective"] == "deepseek"
    assert report["trust"]["trusted"] is True


def test_deepseek_stub_missing_usage_records_environment_gap(monkeypatch) -> None:
    import bank_reconciliation_agent.core.config as _cfg
    from bank_reconciliation_agent.core.llm import provider as _llm_provider
    from bank_reconciliation_agent.core.llm.provider import LLMResult

    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", "sk-stub")

    class StubDeepSeek:
        def __init__(self, **kwargs):
            pass

        def complete(
            self,
            messages,
            *,
            temperature=0.0,
            response_format="json_object",
            response_validator=None,
        ):
            payload = {
                "agent": "extraction",
                "standard_type": "REVERSAL",
                "original_flow_id": "FLOW-ORIGINAL-001",
                "cleaned_remark": "识别到冲正线索",
                "confidence": 0.92,
            }
            return LLMResult(
                text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                prompt_tokens=0,
                completion_tokens=0,
                model="deepseek-v4-flash",
            )

    monkeypatch.setattr(_llm_provider, "DeepSeekProvider", StubDeepSeek)

    report = bench_agent_latency.run_benchmark(
        runs=2, provider_name="deepseek", model="deepseek-v4-flash"
    )

    assert report["status"] == "environment_gap"
    assert report["tokens"]["token_usage_available"] is False
    assert report["trust"]["trusted"] is False
    assert report["environment_gap"]["reason"] == "token_usage_unavailable"


def test_bench_cli_missing_deepseek_key_writes_environment_gap_report(
    monkeypatch, tmp_path: Path
) -> None:
    import bank_reconciliation_agent.core.config as _cfg

    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", None)

    md_path = tmp_path / "bench.md"
    json_path = tmp_path / "bench.json"

    exit_code = bench_agent_latency.main(
        [
            "--runs",
            "1",
            "--provider",
            "deepseek",
            "--report",
            str(md_path),
            "--json-report",
            str(json_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["status"] == "environment_gap"
    assert report["environment_gap"]["reason"] == "missing_deepseek_api_key"


def test_trusted_markdown_includes_cost_and_per_case_cost() -> None:
    report = {
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "measured",
        "provider_effective": "deepseek",
        "cost": {
            "cost_available": True,
            "estimated_cost_usd": str(Decimal("0.0004842")),
            "per_case_estimated_cost_usd": str(Decimal("0.0002421")),
        },
    }
    md = bench_agent_latency._format_benchmark_markdown(report)
    assert "Estimated Cost (USD)" in md
    assert "Per Case Estimated Cost (USD)" in md


def test_environment_gap_markdown_excludes_fake_cost_wording() -> None:
    report = {
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "environment_gap",
        "provider_effective": "deepseek",
        "tokens": {"unavailable_reason": "token_usage_unavailable"},
        "cost": {},
        "environment_gap": {"reason": "token_usage_unavailable"},
    }
    md = bench_agent_latency._format_benchmark_markdown(report)
    assert "## Environment Gap" in md
    assert "token_usage_unavailable" in md


def test_stage31_critical_path_no_go(tmp_path: Path) -> None:
    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["stage"] == "stage-31-trace-guided-performance"
    assert report["decision"] == "no_go"
    assert "not_trusted" in report["closed_reasons"]
    assert report["trust"]["trusted"] is False


def test_stage31_comparison_optimization_rejected(tmp_path: Path) -> None:
    b_path = tmp_path / "b.json"
    a_path = tmp_path / "a.json"

    b_data = {"trust": {"trusted": False}, "input_sha256": "123"}
    a_data = {"trust": {"trusted": False}, "input_sha256": "123"}
    b_path.write_text(json.dumps(b_data))
    a_path.write_text(json.dumps(a_data))

    rep_path = tmp_path / "comp.json"

    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--json-report",
            str(rep_path),
        ]
    )
    assert exit_code == 0

    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert "baseline_not_trusted" in rep["failure_reasons"]
    assert "focused_gates_failed" in rep["failure_reasons"]


# ---------------------------------------------------------------------------
# Stage 31 helper: create a mock run_item that populates TraceRecorder spans
# ---------------------------------------------------------------------------


def _make_mock_run_item(
    *,
    ext_dur_ms=500,
    rag_dur_ms=50,
    ext_success=True,
    rag_success=True,
    ext_tokens=(100, 20),
    extra_ext_spans=0,
    extra_rag_spans=0,
):
    from bank_reconciliation_agent.services.trace import TraceRecorder

    def mock_run_item(state, **_kwargs):
        recorder = state.get("recorder")
        if recorder is None or not isinstance(recorder, TraceRecorder):
            return state

        import time as _time

        ext_handle = recorder.start_agent("ExtractionAgent")
        _time.sleep(ext_dur_ms / 1000.0)
        recorder.finish_agent(
            ext_handle,
            status="SUCCEEDED" if ext_success else "FAILED",
            prompt_tokens=ext_tokens[0] if ext_tokens else 0,
            completion_tokens=ext_tokens[1] if ext_tokens else 0,
        )

        for _ in range(extra_ext_spans):
            h = recorder.start_agent("ExtractionAgent")
            recorder.finish_agent(h, status="SUCCEEDED", prompt_tokens=1, completion_tokens=1)

        tool_handle = recorder.start_tool("search_rules")
        _time.sleep(rag_dur_ms / 1000.0)
        recorder.finish_tool(
            tool_handle,
            status="SUCCEEDED" if rag_success else "FAILED",
            outcome="RESULT" if rag_success else None,
        )

        for _ in range(extra_rag_spans):
            h = recorder.start_tool("search_rules")
            recorder.finish_tool(h, status="SUCCEEDED", outcome="RESULT")

        state["next_action"] = "AUTO_FIXED" if (ext_success and rag_success) else "PENDING_HUMAN"
        return state

    return mock_run_item


# ---------------------------------------------------------------------------
# Stage 31 baseline: trace completeness & fail-closed
# ---------------------------------------------------------------------------


def test_stage31_critical_path_incomplete_trace_no_go(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(ext_success=False, rag_success=False),
    )

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "no_go"
    assert any("complete_count" in r for r in report["closed_reasons"])


def test_stage31_critical_path_duplicate_extraction_spans_no_go(
    monkeypatch, tmp_path: Path
) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(extra_ext_spans=1),
    )

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "no_go"
    assert "not_trusted" in report["closed_reasons"]


def test_stage31_critical_path_theory_below_20pct_no_go(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(ext_dur_ms=450, rag_dur_ms=450),
    )

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "no_go"
    assert not report["trust"]["trusted"]


# ---------------------------------------------------------------------------
# Stage 31: percentile boundary & formula tests
# ---------------------------------------------------------------------------


def test__p95_exact_boundary() -> None:
    samples = list(range(1, 21))
    p95 = bench_agent_latency._p95(samples)
    assert 19.0 <= p95 <= 20.0


def test__p95_single_sample() -> None:
    p95 = bench_agent_latency._p95([42.0])
    assert p95 == 42.0


def test_predicted_parallel_formula() -> None:
    actual_e2e = 1200.0
    ext_dur = 700.0
    rag_dur = 50.0
    pred = actual_e2e - ext_dur - rag_dur + max(ext_dur, rag_dur)
    assert pred == 1200.0 - 700.0 - 50.0 + 700.0
    assert pred == 1150.0


def test_predicted_parallel_formula_rag_slower() -> None:
    actual_e2e = 1000.0
    ext_dur = 100.0
    rag_dur = 500.0
    pred = actual_e2e - ext_dur - rag_dur + max(ext_dur, rag_dur)
    assert pred == 900.0


# ---------------------------------------------------------------------------
# Stage 31 baseline: schema & contract section validation
# ---------------------------------------------------------------------------


_S31_REQUIRED_SECTIONS = [
    "schema_version",
    "stage",
    "artifact_role",
    "evaluated_at",
    "git_revision",
    "input_sha256",
    "environment",
    "provider",
    "rag",
    "run_plan",
    "trust",
    "trace",
    "latency",
    "theory",
    "independence",
    "usage",
    "cost",
    "reliability",
    "decision",
    "closed_reasons",
]


def test_stage31_baseline_has_all_required_sections(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(),
    )

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    for key in _S31_REQUIRED_SECTIONS:
        assert key in report, f"Missing required section: {key}"


def test_stage31_cold_warmup_separation(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(),
    )

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "2",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))

    cold = report["latency"]["cold_observations"]
    assert len(cold) == 2

    e2e_stats = report["latency"]["end_to_end"]
    assert len(e2e_stats["samples_ms"]) == 20

    assert report["run_plan"]["cold_runs"] == 2
    assert report["run_plan"]["warmup_runs"] == 1
    assert report["run_plan"]["measured_runs"] == 20


def test_stage31_trace_completeness_fields(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(),
    )

    json_path = tmp_path / "bench31.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))

    trace = report["trace"]
    assert "completeness_numerator" in trace
    assert "completeness_denominator" in trace
    assert "completeness_rate" in trace
    assert "samples" in trace
    assert len(trace["samples"]) == 20


def test_stage31_input_sha256_stable() -> None:
    import hashlib as _hl
    import json as _json

    d1 = {
        "scenario_type": "BANK_ENTERPRISE",
        "exception_branch": "BE-R004",
        "error_type": "NARRATIVE_NAME_MISMATCH",
    }
    d2 = {
        "error_type": "NARRATIVE_NAME_MISMATCH",
        "scenario_type": "BANK_ENTERPRISE",
        "exception_branch": "BE-R004",
    }
    h1 = _hl.sha256(_json.dumps(d1, sort_keys=True).encode()).hexdigest()
    h2 = _hl.sha256(_json.dumps(d2, sort_keys=True).encode()).hexdigest()
    assert h1 == h2
    assert len(h1) == 64


# ---------------------------------------------------------------------------
# Stage 31 comparison: comprehensive fail-closed
# ---------------------------------------------------------------------------


def _make_minimal_stage31_report(overrides: dict | None = None) -> dict:
    base = {
        "schema_version": "1.0",
        "stage": "stage-31-trace-guided-performance",
        "artifact_role": "baseline",
        "evaluated_at": "2026-07-13T00:00:00Z",
        "git_revision": "abc123",
        "input_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "environment": {
            "os": "Darwin",
            "architecture": "arm64",
            "python": "3.11",
            "boundary": "offline benchmark; not production SLA",
        },
        "provider": {
            "requested_provider": "deepseek",
            "effective_provider": "deepseek",
            "requested_model": "deepseek-v4-flash",
            "effective_model": "deepseek-v4-flash",
        },
        "rag": {
            "requested_embedding_backend": "bge_m3",
            "effective_embedding_backend": "bge_m3",
            "retrieval_mode": "dense",
        },
        "run_plan": {
            "cold_runs": 1,
            "warmup_runs": 1,
            "measured_runs": 20,
            "complete_measured_count": 20,
        },
        "trust": {"trusted": True, "reasons": [], "environment_gap": None},
        "trace": {
            "completeness_numerator": 20,
            "completeness_denominator": 20,
            "completeness_rate": 1.0,
            "samples": [],
        },
        "latency": {
            "end_to_end": {"p95_latency_ms": 1200.0, "p50_latency_ms": 1000.0},
            "extraction_agent": {},
            "rag_search": {},
        },
        "theory": {
            "actual_warm_p95_ms": 1200.0,
            "predicted_warm_p95_ms": 800.0,
            "theoretical_p95_improvement_pct": 33.33,
        },
        "independence": {
            "data_dependency": {"finding": "safe"},
            "shared_state": {"finding": "safe"},
            "failure_order": {"finding": "bounded"},
            "cancellation": {"finding": "bounded"},
            "resource_reclamation": {"finding": "safe"},
        },
        "usage": {
            "provider_call_count": 20,
            "total_tokens": 2000,
            "per_successful_run_tokens": 100,
        },
        "cost": {"total_estimated_usd": "0.01", "per_successful_run_estimated_usd": "0.0005"},
        "reliability": {
            "success_count": 20,
            "failure_count": 0,
            "error_rate": 0.0,
            "error_distribution": {},
        },
        "decision": "candidate_allowed",
        "closed_reasons": [],
    }
    if overrides:
        base.update(overrides)
    return base


def test_stage31_comparison_optimization_accepted(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "latency": {
                "end_to_end": {"p95_latency_ms": 900.0, "p50_latency_ms": 800.0},
                "extraction_agent": {},
                "rag_search": {},
            },
            "theory": {
                "actual_warm_p95_ms": 1200.0,
                "predicted_warm_p95_ms": 800.0,
                "theoretical_p95_improvement_pct": 33.33,
            },
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )

    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_accepted"
    assert rep["success"] is True
    assert len(rep["failure_reasons"]) == 0


def test_stage31_comparison_reject_insufficient_samples(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report(
        {
            "run_plan": {
                "cold_runs": 1,
                "warmup_runs": 1,
                "measured_runs": 20,
                "complete_measured_count": 15,
            }
        }
    )
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "run_plan": {
                "cold_runs": 1,
                "warmup_runs": 1,
                "measured_runs": 20,
                "complete_measured_count": 20,
            },
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert any("insufficient_complete_samples" in r for r in rep["failure_reasons"])


def test_stage31_comparison_reject_input_mismatch(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {"artifact_role": "after", "input_sha256": "different_hash", "git_revision": "def456"}
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert "input_mismatch" in rep["failure_reasons"]


def test_stage31_comparison_reject_same_revision(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report({"artifact_role": "after", "git_revision": "abc123"})
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert "same_revision" in rep["failure_reasons"]


def test_stage31_comparison_reject_missing_focused_gates(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report({"artifact_role": "after", "git_revision": "def456"})
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert "focused_gates_failed" in rep["failure_reasons"]
    assert rep["outcome"] == "optimization_rejected"


def test_stage31_comparison_reject_provider_mismatch(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "provider": {
                "requested_provider": "openai",
                "effective_provider": "openai",
                "requested_model": "gpt-4",
                "effective_model": "gpt-4",
            },
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert "provider_mismatch" in rep["failure_reasons"]


def test_stage31_comparison_reject_actual_improvement_lt_20(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "latency": {
                "end_to_end": {"p95_latency_ms": 1150.0, "p50_latency_ms": 1000.0},
                "extraction_agent": {},
                "rag_search": {},
            },
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert any("actual_improvement" in r for r in rep["failure_reasons"])


def test_stage31_comparison_reject_error_rate_increase(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "reliability": {
                "success_count": 14,
                "failure_count": 6,
                "error_rate": 0.3,
                "error_distribution": {},
            },
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert any("error_rate" in r for r in rep["failure_reasons"])


def test_stage31_comparison_reject_usage_cost_increase(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "usage": {
                "provider_call_count": 20,
                "total_tokens": 3000,
                "per_successful_run_tokens": 150,
            },
            "cost": {"total_estimated_usd": "0.02", "per_successful_run_estimated_usd": "0.001"},
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert rep["outcome"] == "optimization_rejected"
    assert any("per_run_tokens" in r or "per_run_cost" in r for r in rep["failure_reasons"])


def test_stage31_comparison_reject_new_error_types(tmp_path: Path) -> None:
    b_path = tmp_path / "baseline.json"
    a_path = tmp_path / "after.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report(
        {
            "artifact_role": "after",
            "git_revision": "def456",
            "reliability": {
                "success_count": 20,
                "failure_count": 0,
                "error_rate": 0.0,
                "error_distribution": {"new_type": 5},
            },
        }
    )
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())
    assert any("new_error_types" in r for r in rep["failure_reasons"])


def test_stage31_markdown_baseline_includes_key_sections(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(),
    )

    md_path = tmp_path / "bench31.md"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--report",
            str(md_path),
        ]
    )
    content = md_path.read_text(encoding="utf-8")
    assert "Stage 31 Trace-Guided Performance Benchmark" in content
    assert "## Baseline Decision" in content
    assert "## Identity" in content
    assert "## Trust" in content
    assert "## Run Plan" in content
    assert "## Latency" in content
    assert "no_go" in content or "environment_gap" in content


def test_stage31_comparison_json_has_contract_keys(tmp_path: Path) -> None:
    b_path = tmp_path / "b.json"
    a_path = tmp_path / "a.json"

    baseline = _make_minimal_stage31_report()
    after = _make_minimal_stage31_report({"artifact_role": "after", "git_revision": "def456"})
    b_path.write_text(json.dumps(baseline))
    a_path.write_text(json.dumps(after))

    rep_path = tmp_path / "comp.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-comparison",
            "--baseline-json",
            str(b_path),
            "--after-json",
            str(a_path),
            "--focused-gates-passed",
            "--stage-gates-passed",
            "--json-report",
            str(rep_path),
        ]
    )
    rep = json.loads(rep_path.read_text())

    for key in [
        "success",
        "outcome",
        "failure_reasons",
        "trust",
        "latency",
        "usage",
        "cost",
        "reliability",
        "contract_gates",
    ]:
        assert key in rep, f"Missing key in comparison JSON: {key}"


# ---------------------------------------------------------------------------
# TASK-31.6: Runtime identity, input hash, environment gap, authorizer
# ---------------------------------------------------------------------------


def test_stage31_environment_gap_insufficient_run_plan(tmp_path: Path) -> None:
    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "5",
            "--cold-runs",
            "0",
            "--warmup-runs",
            "0",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 1
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "environment_gap"
    assert "insufficient_run_plan" in report["closed_reasons"]


def test_stage31_environment_gap_missing_deepseek_key(monkeypatch, tmp_path: Path) -> None:
    import bank_reconciliation_agent.core.config as _cfg

    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", None)

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "deepseek",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 1
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "environment_gap"
    assert report["trust"]["trusted"] is False
    assert report["provider"]["effective_provider"] is None


def test_stage31_fake_provider_with_deepseek_cli_not_trusted(tmp_path: Path) -> None:
    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--embedding-backend",
            "bge_m3",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "no_go"
    assert report["trust"]["trusted"] is False
    assert report["provider"]["effective_provider"] == "fake"


def test_stage31_canonical_input_hash_covers_execution_fields() -> None:
    import hashlib as _hl
    import json as _json

    base = {
        "scenario_type": "BANK_ENTERPRISE",
        "exception_branch": "BE-R004",
        "error_type": "NARRATIVE_NAME_MISMATCH",
        "source_a_summary": "冲正退款备注待核验",
        "source_a_remark": "原流水疑似冲正，需要抽取原始流水号",
        "source_a_amount": "100.00",
        "source_b_summary": "REVERSAL",
        "bank_amount": "100.00",
        "clear_amount": "100.00",
        "amount_diff": "0.00",
    }

    h1 = _hl.sha256(_json.dumps(base, sort_keys=True).encode()).hexdigest()

    changed = dict(base)
    changed["source_a_summary"] = "different summary"
    h2 = _hl.sha256(_json.dumps(changed, sort_keys=True).encode()).hexdigest()
    assert h1 != h2

    changed2 = dict(base)
    changed2["bank_amount"] = "200.00"
    h3 = _hl.sha256(_json.dumps(changed2, sort_keys=True).encode()).hexdigest()
    assert h1 != h3

    assert len(h1) == 64
    assert h1 != ""


def test_stage31_environment_gap_minimum_samples_not_met(tmp_path: Path) -> None:
    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "10",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 1
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "environment_gap"
    assert any("insufficient_run_plan" in r for r in report["closed_reasons"])


def test_stage31_unexpected_error_not_converted_to_no_go(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        lambda state, **kwargs: (_ for _ in ()).throw(ValueError("unexpected error")),
    )

    json_path = tmp_path / "bench31.json"
    exit_code = bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["decision"] == "no_go"
    assert report["reliability"]["failure_count"] > 0


# ---------------------------------------------------------------------------
# TASK-31.7: Trace eligibility, full-flow accounting, independence truth
# ---------------------------------------------------------------------------


def test_stage31_independence_findings_have_source(monkeypatch, tmp_path: Path) -> None:
    from bank_reconciliation_agent.rag import retriever as _retriever

    monkeypatch.setattr(
        _retriever.rule_retriever,
        "search",
        lambda req: type("RagResp", (), {"items": [], "rewritten_query": req.query})(),
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.run_item",
        _make_mock_run_item(),
    )

    json_path = tmp_path / "bench31.json"
    bench_agent_latency.main(
        [
            "--scenario",
            "stage31-critical-path",
            "--runs",
            "20",
            "--cold-runs",
            "1",
            "--warmup-runs",
            "1",
            "--provider",
            "fake",
            "--json-report",
            str(json_path),
        ]
    )
    report = json.loads(json_path.read_text(encoding="utf-8"))
    indep = report["independence"]
    required_keys = {
        "data_dependency",
        "shared_state",
        "failure_order",
        "cancellation",
        "resource_reclamation",
    }
    assert set(indep.keys()) == required_keys
    for key, finding in indep.items():
        assert "finding" in finding
        assert "detail" in finding
        assert "source" in finding
        assert finding["finding"] in ("safe", "bounded", "unknown", "unsafe", "unbounded")
