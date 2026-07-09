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

    exit_code = bench_agent_latency.main([
        "--runs", "2",
        "--report", str(md_path),
        "--json-report", str(json_path),
    ])
    assert exit_code == 0
    assert md_path.exists()
    assert json_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["run_count"] == 2
    assert report["provider_effective"] == "fake"


def test_bench_json_has_required_top_level_keys(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main([
        "--runs", "2",
        "--json-report", str(json_path),
    ])
    report = json.loads(json_path.read_text(encoding="utf-8"))

    for key in [
        "evaluated_at", "run_count", "provider_requested",
        "provider_effective", "model_requested", "model_effective", "boundary",
        "latency", "tokens", "cost",
    ]:
        assert key in report, f"Missing key: {key}"


def test_bench_latency_has_full_stats(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main([
        "--runs", "3",
        "--json-report", str(json_path),
    ])
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
    bench_agent_latency.main([
        "--runs", "5",
        "--json-report", str(json_path),
    ])
    report = json.loads(json_path.read_text(encoding="utf-8"))

    for component in ["extraction_agent", "rag_search"]:
        comp = report["latency"][component]
        assert comp["min_latency_ms"] <= comp["avg_latency_ms"] <= comp["max_latency_ms"]
        assert comp["avg_latency_ms"] >= 0.0
        assert comp["p95_latency_ms"] >= comp["avg_latency_ms"]


def test_bench_fake_provider_cost_not_available(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main([
        "--runs", "2",
        "--json-report", str(json_path),
    ])
    report = json.loads(json_path.read_text(encoding="utf-8"))

    assert report["tokens"]["token_usage_available"] is False
    assert report["tokens"]["input_tokens"] is None
    assert report["cost"]["cost_available"] is False
    assert report["cost"]["estimated_cost_usd"] is None


def test_bench_fake_provider_boundary_in_markdown(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    bench_agent_latency.main([
        "--runs", "2",
        "--report", str(md_path),
    ])
    content = md_path.read_text(encoding="utf-8")

    assert "Performance & Cost Benchmark" in content
    assert "Provider Effective | `fake`" in content
    assert "Model Effective | `fake-llm`" in content
    assert "not representative of a real LLM" not in content  # this is in stdout only
    # Markdown should clearly indicate not real LLM
    assert "Not real LLM latency" in content
    assert "not production SLA" in content


def test_bench_markdown_includes_required_sections(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    bench_agent_latency.main([
        "--runs", "3",
        "--report", str(md_path),
    ])
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
    exit_code = bench_agent_latency.main([
        "--runs", "2",
        "--provider", "fake",
        "--json-report", str(json_path),
    ])
    assert exit_code == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["provider_effective"] == "fake"
    assert report["tokens"]["token_usage_available"] is False
    assert report["cost"]["cost_available"] is False


def test_constructed_real_provider_report_cost_is_decimal_string(tmp_path: Path) -> None:
    """Construct a report with real-provider metadata; cost must be a Decimal string."""
    report = {
        "evaluated_at": "2026-07-07T00:00:00Z",
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
        "run_count": 2,
        "provider_requested": "fake",
        "provider_effective": "fake",
        "model_effective": "fake-llm",
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": {
                "avg_latency_ms": 1.0,
                "p95_latency_ms": 1.5,
                "min_latency_ms": 0.8,
                "max_latency_ms": 1.8,
                "samples_ms": [0.8, 1.8],
            },
            "rag_search": {
                "avg_latency_ms": 0.5,
                "p95_latency_ms": 0.6,
                "min_latency_ms": 0.4,
                "max_latency_ms": 0.6,
                "samples_ms": [0.4, 0.6],
            },
        },
        "tokens": {
            "token_usage_available": False,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        },
        "cost": {
            "cost_available": False,
            "estimated_cost_usd": None,
            "assumptions": "fake provider; no real LLM cost",
        },
    }

    md = bench_agent_latency._format_benchmark_markdown(report)
    assert "Provider Effective | `fake`" in md
    assert "Token Usage Available | False" in md
    assert "Cost Available | False" in md
    assert "Not real LLM latency" in md
    assert "No real LLM cost" in md


def test_bench_cli_missing_deepseek_key_fails(monkeypatch) -> None:
    import bank_reconciliation_agent.core.config as _cfg
    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", None)
    exit_code = bench_agent_latency.main([
        "--runs", "1",
        "--provider", "deepseek",
    ])
    assert exit_code == 1


def test_bench_cli_unsupported_provider_fails() -> None:
    exit_code = bench_agent_latency.main([
        "--runs", "1",
        "--provider", "openai",
    ])
    assert exit_code == 1


def test_bench_json_real_backend_boundary(tmp_path: Path) -> None:
    json_path = tmp_path / "bench.json"
    bench_agent_latency.main([
        "--runs", "2",
        "--json-report", str(json_path),
    ])
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["boundary"] == "offline benchmark; not production SLA"


def test_bench_markdown_boundary_claim_present(tmp_path: Path) -> None:
    md_path = tmp_path / "bench.md"
    bench_agent_latency.main([
        "--runs", "2",
        "--report", str(md_path),
    ])
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

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
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
    assert report["model_requested"] == "deepseek-v4-flash"
    assert report["model_effective"] == "deepseek-v4-flash"
    assert report["tokens"]["input_tokens"] == 200
    assert report["tokens"]["output_tokens"] == 40
    assert report["tokens"]["total_tokens"] == 240
    assert report["tokens"]["token_usage_available"] is True
    assert report["cost"]["cost_available"] is True
    Decimal(report["cost"]["estimated_cost_usd"])
    Decimal(report["cost"]["per_case_estimated_cost_usd"])
    assert report["trust"]["trusted"] is True
    assert report["trust"]["real_provider_evidence"] is True
    assert report["trust"]["cost_evidence_available"] is True
    assert report["environment_gap"] is None


def test_deepseek_stub_missing_usage_records_environment_gap(monkeypatch) -> None:
    import bank_reconciliation_agent.core.config as _cfg
    from bank_reconciliation_agent.core.llm import provider as _llm_provider
    from bank_reconciliation_agent.core.llm.provider import LLMResult

    monkeypatch.setattr(_cfg.settings, "deepseek_api_key", "sk-stub")

    class StubDeepSeek:
        def __init__(self, **kwargs):
            pass

        def complete(self, messages, *, temperature=0.0, response_format="json_object"):
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
    assert report["provider_effective"] == "deepseek"
    assert len(report["latency"]["extraction_agent"]["samples_ms"]) > 0
    assert report["tokens"]["token_usage_available"] is False
    assert report["tokens"]["unavailable_reason"] == "token_usage_unavailable"
    assert report["cost"]["cost_available"] is False
    assert report["cost"]["unavailable_reason"] == "token_usage_unavailable"
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
    assert md_path.exists()
    assert json_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["status"] == "environment_gap"
    assert report["provider_requested"] == "deepseek"
    assert report["provider_effective"] is None
    assert report["environment_gap"]["reason"] == "missing_deepseek_api_key"


def test_trusted_markdown_includes_cost_and_per_case_cost() -> None:
    report = {
        "evaluated_at": "2026-07-09T00:00:00Z",
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "measured",
        "run_count": 2,
        "provider_requested": "deepseek",
        "provider_effective": "deepseek",
        "model_requested": "deepseek-v4-flash",
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
            "unavailable_reason": None,
        },
        "cost": {
            "cost_available": True,
            "estimated_cost_usd": str(Decimal("0.0004842")),
            "per_case_estimated_cost_usd": str(Decimal("0.0002421")),
            "assumptions": "DeepSeek v4 Pro pricing",
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

    md = bench_agent_latency._format_benchmark_markdown(report)
    assert "deepseek" in md
    assert "Estimated Cost (USD)" in md
    assert "Per Case Estimated Cost (USD)" in md
    assert "Not real LLM latency" not in md
    assert "No real LLM cost" not in md
    assert "## Environment Gap" not in md


def test_environment_gap_markdown_excludes_fake_cost_wording() -> None:
    report = {
        "evaluated_at": "2026-07-09T00:00:00Z",
        "stage": "stage-23-real-provider-cost-benchmark",
        "status": "environment_gap",
        "run_count": 1,
        "provider_requested": "deepseek",
        "provider_effective": "deepseek",
        "model_requested": "deepseek-v4-flash",
        "model_effective": "deepseek-v4-flash",
        "boundary": "offline benchmark; not production SLA",
        "latency": {
            "extraction_agent": {
                "avg_latency_ms": 1200.0,
                "p95_latency_ms": 1200.0,
                "min_latency_ms": 1200.0,
                "max_latency_ms": 1200.0,
                "samples_ms": [1200.0],
            },
            "rag_search": {
                "avg_latency_ms": 50.0,
                "p95_latency_ms": 50.0,
                "min_latency_ms": 50.0,
                "max_latency_ms": 50.0,
                "samples_ms": [50.0],
            },
        },
        "tokens": {
            "token_usage_available": False,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "unavailable_reason": "token_usage_unavailable",
        },
        "cost": {
            "cost_available": False,
            "estimated_cost_usd": None,
            "per_case_estimated_cost_usd": None,
            "assumptions": "real provider but no token usage data available",
            "unavailable_reason": "token_usage_unavailable",
        },
        "trust": {
            "trusted": False,
            "real_provider_evidence": True,
            "cost_evidence_available": False,
            "reasons": ["token_usage_unavailable"],
        },
        "environment_gap": {
            "reason": "token_usage_unavailable",
            "message": "DeepSeek provider returned no token usage metadata.",
        },
    }

    md = bench_agent_latency._format_benchmark_markdown(report)
    assert "## Environment Gap" in md
    assert "token_usage_unavailable" in md
    assert "Not real LLM latency" not in md
    assert "No real LLM cost" not in md
