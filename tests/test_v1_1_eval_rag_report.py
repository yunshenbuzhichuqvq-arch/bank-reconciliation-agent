import json
from pathlib import Path

from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from scripts import eval_rag


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeStore:
    def __init__(self, embedding_backend: str) -> None:
        self.embedding_backend = embedding_backend


class _FakeRetriever:
    def __init__(self, embedding_backend: str) -> None:
        self.store = _FakeStore(embedding_backend)

    def search(self, request) -> RagSearchResponse:
        scenario = request.scenario_type
        item = RagSearchItem(
            chunk_id=f"{scenario}_chunk_1",
            source=f"{scenario}#test",
            source_name="test",
            source_url="",
            source_file="test.md",
            section_title="test",
            element_type="paragraph",
            business_tags=["amount_mismatch"],
            score=0.9,
            content="mock content",
        )
        return RagSearchResponse(items=[item])


def test_eval_rag_cli_writes_markdown_report_for_both_scenarios(
    tmp_path: Path,
    capsys,
) -> None:
    report_path = tmp_path / "rag_eval.md"
    json_report_path = tmp_path / "rag_eval_metrics.json"

    eval_rag.main(
        [
            "--eval-set",
            str(PROJECT_ROOT / "data/rag_eval_set.json"),
            "--chroma",
            str(tmp_path / "chroma"),
            "--report",
            str(report_path),
            "--json-report",
            str(json_report_path),
            "--embedding-backend",
            "hash",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    summaries = {summary["scenario_type"]: summary for summary in payload["summaries"]}
    assert payload["case_count"] >= 120
    assert set(summaries) == {"BANK_CLEARING", "BANK_ENTERPRISE"}

    for scenario_type, summary in summaries.items():
        assert summary["case_count"] >= 60
        assert "hit_at_1" in summary
        assert "recall_at_5" in summary
        assert "mrr" in summary
        assert "ndcg_at_5" in summary
        assert summary["recall_at_5"] < 1.0 or summary["hit_at_1"] < summary["recall_at_5"], (
            scenario_type,
            summary,
        )

    markdown = report_path.read_text(encoding="utf-8")
    assert "# RAG Evaluation Report" in markdown
    assert "| Scenario | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |" in markdown
    assert "| BANK_CLEARING |" in markdown
    assert "| BANK_ENTERPRISE |" in markdown

    snapshot = json.loads(json_report_path.read_text(encoding="utf-8"))
    assert {"rag_recall_at5", "rag_mrr", "evaluated_at"}.issubset(set(snapshot))
    assert 0.0 <= snapshot["rag_recall_at5"] <= 1.0
    assert 0.0 <= snapshot["rag_mrr"] <= 1.0
    assert snapshot["evaluated_at"]


def test_matrix_skip_policy_marks_non_hash_as_not_run() -> None:
    def factory(_backend: str) -> _FakeRetriever:
        return _FakeRetriever("hash")

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small", "bge_m3"],
        modes=["dense"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )

    rows = report["rows"]
    assert rows["hash"]["status"] == "measured"
    assert rows["bge_small"]["status"] == "not_run"
    assert rows["bge_small"]["reason"] == "real backend policy is skip"
    assert rows["bge_m3"]["status"] == "not_run"
    assert rows["bge_m3"]["reason"] == "real backend policy is skip"
    assert report["best_real_backend"] is None
    assert report["miss_buckets"] == []


def test_matrix_backend_mismatch_marks_unavailable() -> None:
    def factory(backend: str) -> _FakeRetriever:
        return _FakeRetriever("hash")

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    rows = report["rows"]
    assert rows["hash"]["status"] == "measured"
    assert rows["bge_small"]["status"] == "unavailable"
    assert rows["bge_small"]["effective_backend"] == "hash"
    assert "effective backend is hash" in rows["bge_small"]["reason"]
    assert report["best_real_backend"] is None


def test_matrix_best_real_backend_populated() -> None:
    def factory(backend: str) -> _FakeRetriever:
        return _FakeRetriever(backend)

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    rows = report["rows"]
    assert rows["bge_small"]["status"] == "measured"
    assert rows["bge_small"]["effective_backend"] == "bge_small"
    assert report["best_real_backend"] == "bge_small"


def test_matrix_miss_buckets_empty_when_no_real_backend() -> None:
    def factory(_backend: str) -> _FakeRetriever:
        return _FakeRetriever("hash")

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )
    assert report["miss_buckets"] == []


def test_matrix_miss_buckets_populated_for_measured_real_backend() -> None:
    def factory(backend: str) -> _FakeRetriever:
        return _FakeRetriever(backend)

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    assert len(report["miss_buckets"]) >= 1
    bucket = report["miss_buckets"][0]
    assert "scenario_type" in bucket
    assert "error_type" in bucket
    assert "miss_count" in bucket
    assert "hit_at_1" in bucket
    assert "recall_at_5" in bucket
    assert "mrr" in bucket
    assert "ndcg_at_5" in bucket
    assert "miss_cases" in bucket


def test_matrix_json_structure_has_required_keys() -> None:
    def factory(_backend: str) -> _FakeRetriever:
        return _FakeRetriever("hash")

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small", "bge_m3"],
        modes=["dense", "hybrid", "hybrid_rerank"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )

    required_top = {
        "case_count", "top_k", "requested_backends", "modes",
        "real_backend_policy", "rows", "best_real_backend", "best_real_mode",
        "real_backend_requirement", "miss_buckets",
    }
    assert required_top.issubset(set(report))

    rows = report["rows"]
    assert rows["hash"]["status"] == "measured"
    assert "bge_small" in rows
    assert "bge_m3" in rows


def test_matrix_cli_writes_reports(tmp_path: Path) -> None:
    matrix_report_path = tmp_path / "rag_quality_matrix.md"
    matrix_json_path = tmp_path / "rag_quality_matrix.json"

    eval_rag.main(
        [
            "--eval-set",
            str(PROJECT_ROOT / "data/rag_eval_set.json"),
            "--chroma",
            str(tmp_path / "chroma"),
            "--top-k",
            "5",
            "--matrix-backends",
            "hash,bge_small,bge_m3",
            "--matrix-modes",
            "dense,hybrid,hybrid_rerank",
            "--real-backend-policy",
            "skip",
            "--matrix-report",
            str(matrix_report_path),
            "--matrix-json",
            str(matrix_json_path),
        ]
    )

    payload = json.loads(matrix_json_path.read_text(encoding="utf-8"))
    assert payload["real_backend_policy"] == "skip"
    assert payload["rows"]["hash"]["status"] == "measured"
    assert payload["rows"]["bge_small"]["status"] == "not_run"
    assert payload["rows"]["bge_m3"]["status"] == "not_run"
    assert "case_count" in payload
    assert "requested_backends" in payload
    assert "modes" in payload
    assert "best_real_backend" in payload
    assert "best_real_mode" in payload
    assert "real_backend_requirement" in payload
    assert "miss_buckets" in payload

    md = matrix_report_path.read_text(encoding="utf-8")
    assert "# RAG Quality Matrix Report" in md
    assert "| Backend | Eff Backend | Status |" in md


def test_matrix_skip_policy_produces_no_real_embedding_fallback_warning(
    tmp_path: Path,
) -> None:
    import os
    import subprocess
    import sys

    env = {**os.environ, "EMBEDDING_BACKEND": "bge_m3"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.eval_rag",
            "--top-k",
            "5",
            "--matrix-backends",
            "hash,bge_small,bge_m3",
            "--matrix-modes",
            "dense,hybrid,hybrid_rerank",
            "--real-backend-policy",
            "skip",
            "--matrix-report",
            str(tmp_path / "rag_quality_matrix.md"),
            "--matrix-json",
            str(tmp_path / "rag_quality_matrix.json"),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr

    combined = (result.stdout + result.stderr).lower()
    assert "rag_embedding_backend_fallback" not in combined, (
        f"should not contain rag_embedding_backend_fallback: {result.stderr}"
    )
    assert "sentence_transformers" not in combined, (
        f"should not contain sentence_transformers: {result.stderr}"
    )

    data = json.loads((tmp_path / "rag_quality_matrix.json").read_text(encoding="utf-8"))
    assert data["rows"]["hash"]["status"] == "measured"
    assert data["rows"]["bge_small"]["status"] == "not_run"
    assert data["rows"]["bge_m3"]["status"] == "not_run"


def test_real_backend_requirement_skip_policy_not_satisfied() -> None:
    def factory(_backend: str) -> _FakeRetriever:
        return _FakeRetriever("hash")

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )

    req = report["real_backend_requirement"]
    assert req["required_backend"] == "bge_small"
    assert req["satisfied"] is False
    assert "reason" in req
    assert "measured_real_backends" in req
    assert "unavailable_real_backends" in req
    assert "not_run_real_backends" in req


def test_real_backend_requirement_bge_small_fallback_unavailable() -> None:
    def factory(backend: str) -> _FakeRetriever:
        return _FakeRetriever("hash")

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    rows = report["rows"]
    assert rows["bge_small"]["status"] == "unavailable"
    assert rows["bge_small"]["effective_backend"] == "hash"
    req = report["real_backend_requirement"]
    assert req["satisfied"] is False


def test_real_backend_requirement_bge_small_measured_satisfied() -> None:
    def factory(backend: str) -> _FakeRetriever:
        if backend == "bge_m3":
            return _FakeRetriever("hash")
        return _FakeRetriever(backend)

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["chunk-1"],
        )
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small", "bge_m3"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    rows = report["rows"]
    assert rows["bge_small"]["status"] == "measured"
    assert rows["bge_small"]["effective_backend"] == "bge_small"
    assert rows["bge_m3"]["status"] == "unavailable"
    assert rows["bge_m3"]["effective_backend"] == "hash"
    req = report["real_backend_requirement"]
    assert req["satisfied"] is True
    assert req["required_backend"] == "bge_small"
    assert "bge_small" in req["measured_real_backends"]
    assert "bge_m3" in req["unavailable_real_backends"]


def test_matrix_markdown_contains_real_backend_requirement_section() -> None:
    from scripts.eval_rag import _format_matrix_markdown

    report = {
        "case_count": 1,
        "top_k": 5,
        "requested_backends": ["hash", "bge_small"],
        "modes": ["dense"],
        "real_backend_policy": "skip",
        "evaluated_at": "2025-01-01T00:00:00Z",
        "rows": {
            "hash": {
                "requested_backend": "hash",
                "effective_backend": "hash",
                "status": "measured",
                "selected_mode": "dense",
                "selection_reason": "test",
                "modes": {"dense": {"global_metrics": {"hit_at_1": 1.0, "recall_at_5": 1.0, "mrr": 1.0, "ndcg_at_5": 1.0}}},
                "deltas_vs_dense": {},
            },
            "bge_small": {
                "requested_backend": "bge_small",
                "effective_backend": None,
                "status": "not_run",
                "reason": "real backend policy is skip",
            },
        },
        "best_real_backend": None,
        "best_real_mode": None,
        "real_backend_requirement": {
            "required_backend": "bge_small",
            "satisfied": False,
            "measured_real_backends": [],
            "unavailable_real_backends": [],
            "not_run_real_backends": ["bge_small"],
            "reason": "bge_small is not a trusted measured backend",
        },
        "miss_buckets": [],
    }
    md = _format_matrix_markdown(report)
    assert "Real Backend Requirement" in md
    assert "`bge_small`" in md


def test_matrix_miss_buckets_contain_miss_cases_with_case_details() -> None:
    def factory(backend: str) -> _FakeRetriever:
        return _FakeRetriever(backend)

    cases = [
        eval_rag.EvalCase(
            id="c1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="query one",
            expected_chunk_ids=["BANK_ENTERPRISE_chunk_1"],
        ),
        eval_rag.EvalCase(
            id="c2",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="query two",
            expected_chunk_ids=["wrong_chunk"],
        ),
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    buckets = report["miss_buckets"]
    assert len(buckets) >= 1
    bucket = buckets[0]
    assert bucket["scenario_type"] == "BANK_ENTERPRISE"
    assert bucket["error_type"] == "AMOUNT_MISMATCH"
    assert bucket["case_count"] == 2
    assert bucket["miss_count"] >= 1
    assert "miss_cases" in bucket
    assert len(bucket["miss_cases"]) == bucket["miss_count"]

    miss_case = bucket["miss_cases"][0]
    assert miss_case["id"] == "c2"
    assert miss_case["query"] == "query two"
    assert miss_case["expected_chunk_ids"] == ["wrong_chunk"]
    assert miss_case["retrieved_chunk_ids"] == ["BANK_ENTERPRISE_chunk_1"]
    assert miss_case["hit_at_1"] == 0.0
    assert miss_case["recall_at_5"] == 0.0


def test_matrix_miss_buckets_miss_cases_capped() -> None:
    def factory(backend: str) -> _FakeRetriever:
        return _FakeRetriever(backend)

    cases = [
        eval_rag.EvalCase(
            id=f"c{i}",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query=f"q{i}",
            expected_chunk_ids=["wrong_chunk"],
        )
        for i in range(1, 8)
    ]
    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    buckets = report["miss_buckets"]
    assert len(buckets) >= 1
    bucket = buckets[0]
    assert bucket["miss_count"] == 7
    assert len(bucket["miss_cases"]) == 5


def test_matrix_markdown_miss_buckets_show_miss_sample_ids() -> None:
    from scripts.eval_rag import _format_matrix_markdown

    report = {
        "case_count": 2,
        "top_k": 5,
        "requested_backends": ["hash", "bge_small"],
        "modes": ["dense"],
        "real_backend_policy": "auto",
        "evaluated_at": "2025-01-01T00:00:00Z",
        "rows": {
            "hash": {
                "requested_backend": "hash",
                "effective_backend": "hash",
                "status": "measured",
                "selected_mode": "dense",
                "selection_reason": "test",
                "modes": {"dense": {"global_metrics": {"hit_at_1": 1.0, "recall_at_5": 1.0, "mrr": 1.0, "ndcg_at_5": 1.0}}},
                "deltas_vs_dense": {},
            },
            "bge_small": {
                "requested_backend": "bge_small",
                "effective_backend": "bge_small",
                "status": "measured",
                "selected_mode": "dense",
                "selection_reason": "test",
                "modes": {"dense": {"global_metrics": {"hit_at_1": 0.5, "recall_at_5": 0.5, "mrr": 0.5, "ndcg_at_5": 0.5}}},
                "deltas_vs_dense": {},
            },
        },
        "best_real_backend": "bge_small",
        "best_real_mode": "dense",
        "real_backend_requirement": {
            "required_backend": "bge_small",
            "satisfied": True,
            "measured_real_backends": ["bge_small"],
            "unavailable_real_backends": [],
            "not_run_real_backends": [],
            "reason": "bge_small measured with trusted effective backend",
        },
        "miss_buckets": [
            {
                "scenario_type": "BANK_ENTERPRISE",
                "error_type": "AMOUNT_MISMATCH",
                "case_count": 2,
                "miss_count": 1,
                "hit_at_1": 0.5,
                "recall_at_5": 0.5,
                "mrr": 0.5,
                "ndcg_at_5": 0.5,
                "miss_cases": [
                    {
                        "id": "c2",
                        "query": "query two",
                        "expected_chunk_ids": ["chunk-x"],
                        "retrieved_chunk_ids": ["BANK_ENTERPRISE_chunk_1"],
                        "hit_at_1": 0.0,
                        "recall_at_5": 0.0,
                    }
                ],
            }
        ],
    }
    md = _format_matrix_markdown(report)
    assert "Miss Samples" in md
    assert "c2" in md
    assert "chunk-x" in md
    assert "BANK_ENTERPRISE_chunk_1" in md


def _make_matrix(
    *,
    case_count: int = 120,
    top_k: int = 5,
    real_backend_policy: str = "auto",
    best_real_backend: str | None = "bge_m3",
    best_real_mode: str | None = "hybrid",
    backend: str = "bge_m3",
    mode: str = "hybrid",
    status: str = "measured",
    effective_backend: str = "bge_m3",
    global_hit1: float = 0.55,
    global_recall: float = 0.75,
    global_mrr: float = 0.66,
    global_ndcg: float = 0.65,
    clearing_single_side_recall: float = 0.40,
    clearing_single_side_miss_count: int = 7,
    bucket_metrics: list[dict] | None = None,
    extra_buckets: list[dict] | None = None,
    selected_mode: str | None = None,
) -> dict:
    selected = selected_mode or mode
    if bucket_metrics is None:
        bucket_metrics = [
            {
                "scenario_type": "BANK_ENTERPRISE",
                "error_type": "AMOUNT_MISMATCH",
                "case_count": 70,
                "miss_count": 5,
                "hit_at_1": 0.60,
                "recall_at_5": 0.80,
                "mrr": 0.72,
                "ndcg_at_5": 0.70,
            },
            {
                "scenario_type": "BANK_ENTERPRISE",
                "error_type": "TIMING_DIFFERENCE",
                "case_count": 40,
                "miss_count": 4,
                "hit_at_1": 0.50,
                "recall_at_5": 0.70,
                "mrr": 0.62,
                "ndcg_at_5": 0.60,
            },
            {
                "scenario_type": "BANK_CLEARING",
                "error_type": "SINGLE_SIDE_MISSING",
                "case_count": 10,
                "miss_count": clearing_single_side_miss_count,
                "hit_at_1": 0.20,
                "recall_at_5": clearing_single_side_recall,
                "mrr": 0.30,
                "ndcg_at_5": 0.30,
            },
        ]
        if extra_buckets:
            bucket_metrics.extend(extra_buckets)

    return {
        "case_count": case_count,
        "top_k": top_k,
        "real_backend_policy": real_backend_policy,
        "requested_backends": ["hash", "bge_small", "bge_m3"],
        "modes": ["dense", "hybrid", "hybrid_rerank"],
        "best_real_backend": best_real_backend,
        "best_real_mode": best_real_mode,
        "rows": {
            "bge_m3": {
                "requested_backend": backend,
                "effective_backend": effective_backend,
                "status": status,
                "selected_mode": selected,
                "selection_reason": "test",
                "modes": {
                    mode: {
                        "global_metrics": {
                            "hit_at_1": global_hit1,
                            "recall_at_5": global_recall,
                            "mrr": global_mrr,
                            "ndcg_at_5": global_ndcg,
                        },
                        "bucket_metrics": bucket_metrics,
                    }
                },
                "deltas_vs_dense": {},
            }
        },
        "real_backend_requirement": {
            "required_backend": "bge_small",
            "satisfied": status == "measured" and effective_backend == backend,
        },
        "miss_buckets": bucket_metrics,
    }


def test_build_optimization_comparison_target_improved() -> None:
    baseline = _make_matrix(clearing_single_side_recall=0.40, clearing_single_side_miss_count=7)
    after = _make_matrix(clearing_single_side_recall=0.60, clearing_single_side_miss_count=4)

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["target_bucket"]["improved"] is True
    assert report["target_bucket"]["before"]["recall_at_5"] == 0.40
    assert report["target_bucket"]["after"]["recall_at_5"] == 0.60
    assert report["target_bucket"]["before"]["miss_count"] == 7
    assert report["target_bucket"]["after"]["miss_count"] == 4


def test_build_optimization_comparison_success_true_when_target_improves_and_global_within_limit() -> None:
    baseline = _make_matrix(
        clearing_single_side_recall=0.40, clearing_single_side_miss_count=7,
        global_mrr=0.66, global_ndcg=0.65,
    )
    after = _make_matrix(
        clearing_single_side_recall=0.60, clearing_single_side_miss_count=4,
        global_mrr=0.67, global_ndcg=0.66,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["success"] is True
    assert report["global"]["within_regression_limit"] is True


def test_build_optimization_comparison_success_false_when_after_effective_backend_is_hash() -> None:
    baseline = _make_matrix()
    after = _make_matrix(
        effective_backend="hash",
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["success"] is False
    assert report["trust"]["trusted"] is False
    assert "after effective backend" in " ".join(report["failure_reasons"]).lower() or any("hash" in r.lower() for r in report["failure_reasons"])


def test_build_optimization_comparison_success_false_when_recall_up_but_miss_count_not_down() -> None:
    baseline = _make_matrix(clearing_single_side_recall=0.40, clearing_single_side_miss_count=7)
    after = _make_matrix(clearing_single_side_recall=0.50, clearing_single_side_miss_count=7)

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["success"] is False
    assert report["target_bucket"]["improved"] is False
    assert "miss_count" in " ".join(report["failure_reasons"]).lower()


def test_build_optimization_comparison_success_false_when_global_ndcg_regresses() -> None:
    baseline = _make_matrix(
        clearing_single_side_recall=0.40, clearing_single_side_miss_count=7,
        global_mrr=0.66, global_ndcg=0.65,
    )
    after = _make_matrix(
        clearing_single_side_recall=0.60, clearing_single_side_miss_count=4,
        global_mrr=0.60, global_ndcg=0.60,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )
    assert report["success"] is False
    assert report["global"]["within_regression_limit"] is False


def test_build_optimization_comparison_side_effect_buckets_capped_and_sorted() -> None:
    baseline = _make_matrix()
    baseline["miss_buckets"].append({
        "scenario_type": "BANK_CLEARING",
        "error_type": "EXTRA_BUCKET",
        "case_count": 5,
        "miss_count": 3,
        "hit_at_1": 0.10,
        "recall_at_5": 0.30,
        "mrr": 0.20,
        "ndcg_at_5": 0.20,
    })
    baseline["miss_buckets"].append({
        "scenario_type": "BANK_ENTERPRISE",
        "error_type": "EXTRA_BUCKET_2",
        "case_count": 5,
        "miss_count": 3,
        "hit_at_1": 0.10,
        "recall_at_5": 0.30,
        "mrr": 0.20,
        "ndcg_at_5": 0.20,
    })
    baseline["miss_buckets"].append({
        "scenario_type": "BANK_CLEARING",
        "error_type": "EXTRA_BUCKET_3",
        "case_count": 5,
        "miss_count": 3,
        "hit_at_1": 0.10,
        "recall_at_5": 0.30,
        "mrr": 0.20,
        "ndcg_at_5": 0.20,
    })
    baseline["miss_buckets"].append({
        "scenario_type": "BANK_ENTERPRISE",
        "error_type": "EXTRA_BUCKET_4",
        "case_count": 5,
        "miss_count": 3,
        "hit_at_1": 0.10,
        "recall_at_5": 0.30,
        "mrr": 0.20,
        "ndcg_at_5": 0.20,
    })

    after = _make_matrix(clearing_single_side_recall=0.60, clearing_single_side_miss_count=4)
    after["miss_buckets"].append({
        "scenario_type": "BANK_CLEARING",
        "error_type": "EXTRA_BUCKET",
        "case_count": 5,
        "miss_count": 2,
        "hit_at_1": 0.80,
        "recall_at_5": 0.90,
        "mrr": 0.85,
        "ndcg_at_5": 0.85,
    })
    after["miss_buckets"].append({
        "scenario_type": "BANK_ENTERPRISE",
        "error_type": "EXTRA_BUCKET_2",
        "case_count": 5,
        "miss_count": 3,
        "hit_at_1": 0.05,
        "recall_at_5": 0.10,
        "mrr": 0.05,
        "ndcg_at_5": 0.05,
    })
    after["miss_buckets"].append({
        "scenario_type": "BANK_CLEARING",
        "error_type": "EXTRA_BUCKET_3",
        "case_count": 5,
        "miss_count": 3,
        "hit_at_1": 0.90,
        "recall_at_5": 1.00,
        "mrr": 0.95,
        "ndcg_at_5": 0.95,
    })
    after["miss_buckets"].append({
        "scenario_type": "BANK_ENTERPRISE",
        "error_type": "EXTRA_BUCKET_4",
        "case_count": 5,
        "miss_count": 4,
        "hit_at_1": 0.01,
        "recall_at_5": 0.05,
        "mrr": 0.02,
        "ndcg_at_5": 0.02,
    })

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    se = report["side_effect_buckets"]
    assert len(se["largest_regressions"]) <= 3
    assert len(se["largest_improvements"]) <= 3

    if len(se["largest_regressions"]) > 1:
        for i in range(len(se["largest_regressions"]) - 1):
            assert se["largest_regressions"][i]["delta"]["ndcg_at_5"] <= se["largest_regressions"][i + 1]["delta"]["ndcg_at_5"]

    if len(se["largest_improvements"]) > 1:
        for i in range(len(se["largest_improvements"]) - 1):
            assert se["largest_improvements"][i]["delta"]["ndcg_at_5"] >= se["largest_improvements"][i + 1]["delta"]["ndcg_at_5"]


def test_build_optimization_comparison_uses_requested_mode_not_selected_mode() -> None:
    dense_target = {
        "scenario_type": "BANK_CLEARING",
        "error_type": "SINGLE_SIDE_MISSING",
        "case_count": 10,
        "miss_count": 8,
        "hit_at_1": 0.10,
        "recall_at_5": 0.20,
        "mrr": 0.15,
        "ndcg_at_5": 0.15,
    }

    baseline = _make_matrix(
        selected_mode="hybrid",
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    baseline["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"] = [
        b for b in baseline["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"]
        if b["error_type"] == "SINGLE_SIDE_MISSING"
    ]

    after = _make_matrix(
        selected_mode="dense",
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )
    after["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"] = [
        b for b in after["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"]
        if b["error_type"] == "SINGLE_SIDE_MISSING"
    ]
    after["rows"]["bge_m3"]["modes"]["dense"] = {
        "global_metrics": {"hit_at_1": 0.50, "recall_at_5": 0.70, "mrr": 0.60, "ndcg_at_5": 0.55},
        "bucket_metrics": [dict(dense_target)],
    }

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
        backend="bge_m3",
        mode="hybrid",
    )

    assert report["trust"]["trusted"] is True
    assert report["target_bucket"]["before"]["recall_at_5"] == 0.40
    assert report["target_bucket"]["after"]["recall_at_5"] == 0.60


def test_build_optimization_comparison_trust_fails_when_bucket_metrics_missing() -> None:
    baseline = _make_matrix(
        selected_mode="dense",
        best_real_mode="dense",
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    del baseline["rows"]["bge_m3"]["modes"]["hybrid"]
    baseline["rows"]["bge_m3"]["modes"]["dense"] = {
        "global_metrics": {"hit_at_1": 0.50, "recall_at_5": 0.70, "mrr": 0.60, "ndcg_at_5": 0.55},
        "bucket_metrics": [],
    }

    after = _make_matrix()

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
        backend="bge_m3",
        mode="hybrid",
    )

    assert report["trust"]["trusted"] is False
    assert any("bucket_metrics" in r for r in report["trust"]["reasons"])


def test_optimization_cli_rejects_missing_args() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.eval_rag",
            "--optimization-baseline-json", "/tmp/nonexistent.json",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "both be provided" in result.stderr


def test_build_optimization_comparison_trusted_legacy_baseline() -> None:
    baseline = _make_matrix(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    del baseline["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"]

    after = _make_matrix(
        clearing_single_side_recall=0.35,
        clearing_single_side_miss_count=8,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
        backend="bge_m3",
        mode="hybrid",
    )

    assert report["trust"]["trusted"] is True
    assert "bucket_metric_sources" in report["trust"]
    assert report["target_bucket"]["before"]["recall_at_5"] == 0.40
    assert report["target_bucket"]["before"]["miss_count"] == 7
    assert report["target_bucket"]["after"]["recall_at_5"] == 0.35


def test_build_optimization_comparison_rejects_legacy_mode_mismatch() -> None:
    baseline = {
        "case_count": 120,
        "top_k": 5,
        "real_backend_policy": "auto",
        "requested_backends": ["hash", "bge_m3"],
        "best_real_backend": "bge_m3",
        "best_real_mode": "dense",
        "rows": {
            "bge_m3": {
                "requested_backend": "bge_m3",
                "effective_backend": "bge_m3",
                "status": "measured",
                "selected_mode": "dense",
                "selection_reason": "test",
                "modes": {},
                "deltas_vs_dense": {},
            }
        },
        "real_backend_requirement": {"satisfied": True},
        "miss_buckets": [
            {
                "scenario_type": "BANK_CLEARING",
                "error_type": "SINGLE_SIDE_MISSING",
                "case_count": 10,
                "miss_count": 7,
                "hit_at_1": 0.20,
                "recall_at_5": 0.40,
                "mrr": 0.30,
                "ndcg_at_5": 0.30,
            }
        ],
    }

    after = _make_matrix(clearing_single_side_recall=0.35, clearing_single_side_miss_count=8)

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
        backend="bge_m3",
        mode="hybrid",
    )

    assert report["trust"]["trusted"] is False
    reasons_text = " ".join(report["trust"]["reasons"])
    assert "lacks" in reasons_text.lower() or "missing" in reasons_text.lower()


# ---------------------------------------------------------------------------
# TASK-30.1: Stage 30 new-format trust contract and full side-effect reporting
# ---------------------------------------------------------------------------


def _make_stage30_matrix(
    role: str,
    *,
    eval_set_sha256: str | None = "eval-hash-abc",
    chunk_corpus_sha256: str | None = "chunk-hash-xyz",
    git_revision: str | None = "role-rev",
    query_enrichment: dict | None = None,
    **kwargs,
) -> dict:
    matrix = _make_matrix(**kwargs)
    matrix["eval_set_sha256"] = eval_set_sha256
    matrix["chunk_corpus_sha256"] = chunk_corpus_sha256
    matrix["git_revision"] = git_revision
    if query_enrichment is None:
        if role == "baseline":
            query_enrichment = {"enabled": False, "profile": None}
        else:
            query_enrichment = {
                "enabled": True,
                "profile": "bank-clearing-single-side-missing",
                "profile_sha256": "profile-hash",
                "latency_ms": {
                    "count": matrix["case_count"],
                    "p50": 0.1,
                    "p95": 0.2,
                    "max": 0.3,
                },
            }
    matrix["query_enrichment"] = query_enrichment
    return matrix


def _stage30_baseline(**kwargs) -> dict:
    return _make_stage30_matrix("baseline", **kwargs)


def _stage30_after(**kwargs) -> dict:
    return _make_stage30_matrix("after", **kwargs)


def test_stage30_comparison_trusted_when_hashes_match() -> None:
    baseline = _stage30_baseline(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
        global_mrr=0.66,
        global_ndcg=0.65,
    )
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
        global_mrr=0.67,
        global_ndcg=0.66,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is True
    assert report["success"] is True


def test_stage30_comparison_trust_fails_when_eval_set_hash_mismatch() -> None:
    baseline = _stage30_baseline(eval_set_sha256="hash-a")
    after = _stage30_after(
        eval_set_sha256="hash-b",
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert "eval_set_sha256" in " ".join(report["trust"]["reasons"])


def test_stage30_comparison_trust_fails_when_chunk_corpus_hash_mismatch() -> None:
    baseline = _stage30_baseline(chunk_corpus_sha256="chunk-a")
    after = _stage30_after(
        chunk_corpus_sha256="chunk-b",
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert "chunk_corpus_sha256" in " ".join(report["trust"]["reasons"])


def test_stage30_comparison_trust_fails_when_hash_missing() -> None:
    baseline = _stage30_baseline(eval_set_sha256=None)
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False


def test_stage30_comparison_does_not_use_legacy_bucket_fallback() -> None:
    baseline = _stage30_baseline(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    del baseline["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"]

    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
        backend="bge_m3",
        mode="hybrid",
    )

    assert report["trust"]["trusted"] is False
    assert any("bucket_metrics" in r for r in report["trust"]["reasons"])


def test_build_optimization_comparison_success_false_when_global_mrr_regresses() -> None:
    baseline = _make_matrix(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
        global_mrr=0.66,
        global_ndcg=0.65,
    )
    after = _make_matrix(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
        global_mrr=0.60,
        global_ndcg=0.65,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["success"] is False
    assert report["global"]["within_regression_limit"] is False
    assert "mrr" in " ".join(report["failure_reasons"]).lower()


def test_comparison_json_includes_all_non_target_buckets() -> None:
    baseline = _stage30_baseline(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    se = report["side_effect_buckets"]
    assert "all_non_target" in se
    keys = {(d["scenario_type"], d["error_type"]) for d in se["all_non_target"]}
    assert ("BANK_ENTERPRISE", "AMOUNT_MISMATCH") in keys
    assert ("BANK_ENTERPRISE", "TIMING_DIFFERENCE") in keys
    assert ("BANK_CLEARING", "SINGLE_SIDE_MISSING") not in keys
    for d in se["all_non_target"]:
        assert "before" in d
        assert "after" in d
        assert "delta" in d


def test_comparison_markdown_shows_full_side_effect_data() -> None:
    baseline = _stage30_baseline(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    md = eval_rag._format_optimization_comparison_markdown(report)
    assert "TIMING_DIFFERENCE" in md
    assert "AMOUNT_MISMATCH" in md


# ---------------------------------------------------------------------------
# TASK-30.7: artifact role and enrichment metadata fail-closed
# ---------------------------------------------------------------------------


def test_stage30_role_gate_fails_when_after_missing_query_enrichment() -> None:
    baseline = _stage30_baseline()
    after = _make_matrix(clearing_single_side_recall=0.60, clearing_single_side_miss_count=4)
    after["eval_set_sha256"] = "eval-hash-abc"
    after["chunk_corpus_sha256"] = "chunk-hash-xyz"
    after["git_revision"] = "candidate-rev"
    # deliberately no query_enrichment key on after

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("query_enrichment" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_after_disabled() -> None:
    baseline = _stage30_baseline()
    after = _stage30_after(
        query_enrichment={"enabled": False, "profile": None},
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("after query_enrichment must be enabled" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_baseline_enabled() -> None:
    baseline = _stage30_baseline(
        query_enrichment={
            "enabled": True,
            "profile": "bank-clearing-single-side-missing",
            "profile_sha256": "x",
            "latency_ms": {"count": 120, "p50": 0.1, "p95": 0.2, "max": 0.3},
        },
    )
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any(
        "baseline query_enrichment must be disabled" in r for r in report["trust"]["reasons"]
    )


def test_stage30_role_gate_fails_when_after_profile_hash_missing() -> None:
    baseline = _stage30_baseline()
    after = _stage30_after(
        query_enrichment={
            "enabled": True,
            "profile": "bank-clearing-single-side-missing",
            "profile_sha256": "",
            "latency_ms": {"count": 120, "p50": 0.1, "p95": 0.2, "max": 0.3},
        },
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("profile_sha256" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_git_revision_missing() -> None:
    baseline = _stage30_baseline(git_revision=None)
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("git_revision" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_after_latency_missing() -> None:
    baseline = _stage30_baseline()
    after = _stage30_after(
        query_enrichment={
            "enabled": True,
            "profile": "bank-clearing-single-side-missing",
            "profile_sha256": "x",
        },
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("latency" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_latency_count_mismatch() -> None:
    baseline = _stage30_baseline()
    after = _stage30_after(
        query_enrichment={
            "enabled": True,
            "profile": "bank-clearing-single-side-missing",
            "profile_sha256": "x",
            "latency_ms": {"count": 5, "p50": 0.1, "p95": 0.2, "max": 0.3},
        },
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("latency count" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_latency_order_invalid() -> None:
    baseline = _stage30_baseline()
    after = _stage30_after(
        query_enrichment={
            "enabled": True,
            "profile": "bank-clearing-single-side-missing",
            "profile_sha256": "x",
            "latency_ms": {"count": 120, "p50": 0.5, "p95": 0.2, "max": 0.3},
        },
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("ordering invalid" in r for r in report["trust"]["reasons"])


def test_stage30_role_gate_fails_when_only_after_is_stage30() -> None:
    baseline = _make_matrix(clearing_single_side_recall=0.40, clearing_single_side_miss_count=7)
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("baseline lacks Stage 30" in r for r in report["trust"]["reasons"])


def test_stage30_comparison_markdown_shows_enrichment_role_and_revision() -> None:
    baseline = _stage30_baseline(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
    )
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
    )

    report = eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )

    md = eval_rag._format_optimization_comparison_markdown(report)
    assert "git_revision" in md
    assert "query_enrichment.enabled" in md
    assert "bank-clearing-single-side-missing" in md
    assert "latency_ms" in md


# ---------------------------------------------------------------------------
# TASK-30.8: bucket set, uniqueness and case count fail-closed
# ---------------------------------------------------------------------------


def _stage30_pair(**kwargs):
    baseline = _stage30_baseline(
        clearing_single_side_recall=0.40,
        clearing_single_side_miss_count=7,
        **kwargs,
    )
    after = _stage30_after(
        clearing_single_side_recall=0.60,
        clearing_single_side_miss_count=4,
        **kwargs,
    )
    return baseline, after


def _mode_buckets(matrix):
    return matrix["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"]


def _run_stage30(baseline, after):
    return eval_rag.build_optimization_comparison_report(
        baseline,
        after,
        target_scenario_type="BANK_CLEARING",
        target_error_type="SINGLE_SIDE_MISSING",
    )


def test_stage30_bucket_gate_fails_when_after_missing_non_target_bucket() -> None:
    baseline, after = _stage30_pair()
    after_buckets = _mode_buckets(after)
    after["rows"]["bge_m3"]["modes"]["hybrid"]["bucket_metrics"] = [
        b for b in after_buckets if b["error_type"] != "TIMING_DIFFERENCE"
    ]

    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("missing baseline buckets" in r for r in report["trust"]["reasons"])


def test_stage30_bucket_gate_fails_when_after_has_extra_bucket() -> None:
    baseline, after = _stage30_pair()
    _mode_buckets(after).append(
        {
            "scenario_type": "BANK_ENTERPRISE",
            "error_type": "EXTRA_BUCKET",
            "case_count": 0,
            "miss_count": 0,
            "hit_at_1": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "ndcg_at_5": 0.0,
        }
    )

    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("extra buckets" in r for r in report["trust"]["reasons"])


def test_stage30_bucket_gate_fails_when_duplicate_bucket() -> None:
    baseline, after = _stage30_pair()
    dup = dict(_mode_buckets(after)[0])
    _mode_buckets(after).append(dup)

    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("duplicate bucket keys" in r for r in report["trust"]["reasons"])


def test_stage30_bucket_gate_fails_when_case_count_differs() -> None:
    baseline, after = _stage30_pair()
    _mode_buckets(after)[0]["case_count"] += 1

    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("case_count mismatch" in r for r in report["trust"]["reasons"])


def test_stage30_bucket_gate_fails_when_case_count_sum_mismatch() -> None:
    baseline, after = _stage30_pair()
    for matrix in (baseline, after):
        _mode_buckets(matrix)[0]["case_count"] += 5

    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("case_count sum" in r for r in report["trust"]["reasons"])


def test_stage30_bucket_gate_fails_when_required_metric_field_missing() -> None:
    baseline, after = _stage30_pair()
    del _mode_buckets(after)[0]["ndcg_at_5"]

    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is False
    assert report["success"] is False
    assert any("ndcg_at_5" in r and "non-numeric" in r for r in report["trust"]["reasons"])


def test_stage30_all_non_target_equals_total_buckets_minus_one() -> None:
    baseline, after = _stage30_pair()
    report = _run_stage30(baseline, after)
    assert report["trust"]["trusted"] is True
    total_buckets = len(_mode_buckets(baseline))
    assert len(report["side_effect_buckets"]["all_non_target"]) == total_buckets - 1
