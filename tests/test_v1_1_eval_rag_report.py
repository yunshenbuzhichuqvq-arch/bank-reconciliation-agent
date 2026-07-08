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
