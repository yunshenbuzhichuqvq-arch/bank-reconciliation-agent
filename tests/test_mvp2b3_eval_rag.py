from collections import Counter
import json
from pathlib import Path
import re

import pytest

from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from scripts import eval_rag


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _item(chunk_id: str) -> RagSearchItem:
    return RagSearchItem(
        chunk_id=chunk_id,
        source=f"source#{chunk_id}",
        source_name="test source",
        source_url="https://example.com/rule",
        source_file="data/rag/raw_sources/test.md",
        section_title="section",
        element_type="paragraph",
        business_tags=["test"],
        score=1.0,
        content=f"content for {chunk_id}",
    )


class StubRetriever:
    def __init__(self, responses: dict[str, list[str]]) -> None:
        self.responses = responses
        self.requests = []

    def search(self, request) -> RagSearchResponse:
        self.requests.append(request)
        return RagSearchResponse(items=[_item(chunk_id) for chunk_id in self.responses[request.query]])


def test_evaluate_eval_set_computes_recall_mrr_and_ndcg() -> None:
    cases = [
        eval_rag.EvalCase(
            id="case-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1", "c2"],
        ),
        eval_rag.EvalCase(
            id="case-2",
            scenario_type="BANK_ENTERPRISE",
            error_type="SINGLE_SIDE_MISSING",
            query="q2",
            expected_chunk_ids=["c3"],
        ),
    ]

    retriever = StubRetriever(
        {
            "q1": ["c1", "x", "c2"],
            "q2": ["x", "c3"],
        }
    )

    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)

    assert report["case_count"] == 2
    assert report["summaries"] == [
        pytest.approx(
            {
                "scenario_type": "BANK_ENTERPRISE",
                "case_count": 2,
                "hit_at_1": 0.5,
                "recall_at_5": 1.0,
                "mrr": 0.75,
                "ndcg_at_5": 0.7753252713598225,
            }
        )
    ]
    assert [request.enable_hybrid for request in retriever.requests] == [False, False]
    # New: global metrics are present
    assert "global_metrics" in report
    assert report["global_metrics"] == pytest.approx({
        "hit_at_1": 0.5,
        "recall_at_5": 1.0,
        "mrr": 0.75,
        "ndcg_at_5": 0.7753252713598225,
    })
    # New: metadata keys are present
    assert "embedding_backend" in report
    assert "top_k" in report
    assert "evaluated_at" in report


def test_eval_rag_cli_prints_metric_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eval_set_path = tmp_path / "rag_eval_set.json"
    eval_set_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "scenario_type": "BANK_ENTERPRISE",
                    "error_type": "AMOUNT_MISMATCH",
                    "query": "金额差异 对账不平",
                    "expected_chunk_ids": ["unionpay_reconciliation_faq_001"],
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    eval_rag.main(
        [
            "--eval-set",
            str(eval_set_path),
            "--chroma",
            str(tmp_path / "chroma"),
            "--report",
            str(tmp_path / "rag_eval.md"),
            "--embedding-backend",
            "hash",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["case_count"] == 1
    assert payload["summaries"][0]["scenario_type"] == "BANK_ENTERPRISE"
    assert "hit_at_1" in payload["summaries"][0]
    assert "recall_at_5" in payload["summaries"][0]
    assert "mrr" in payload["summaries"][0]
    assert "ndcg_at_5" in payload["summaries"][0]
    assert "Recall@5 is evaluated" in payload["notes"][0]


def test_eval_set_queries_are_semantic_questions_without_error_code_stuffing() -> None:
    cases = eval_rag.load_eval_set(PROJECT_ROOT / "data/rag_eval_set.json")

    assert len(cases) >= 120
    assert all("?" not in case.query for case in cases)
    assert not any(re.search(r"\b[A-Z_]{4,}\b", case.query) for case in cases)

    grouped: dict[tuple[str, str], set[str]] = {}
    for case in cases:
        key = (case.scenario_type, case.error_type)
        grouped.setdefault(key, set()).add(case.query[:8])

    assert all(len(prefixes) >= 4 for prefixes in grouped.values())


def test_bank_enterprise_eval_set_has_no_single_chunk_stuffing() -> None:
    cases = eval_rag.load_eval_set(PROJECT_ROOT / "data/rag_eval_set.json")

    sole_expected_counts = Counter(
        case.expected_chunk_ids[0]
        for case in cases
        if case.scenario_type == "BANK_ENTERPRISE" and len(case.expected_chunk_ids) == 1
    )

    assert all(count <= 3 for count in sole_expected_counts.values())


# ---------------------------------------------------------------------------
# TASK-EH.2: New tests for grouped reporting, metadata, snapshot compat
# ---------------------------------------------------------------------------


def test_error_type_summaries_present_and_grouped() -> None:
    """Report has at least one grouping by (scenario_type, error_type)."""
    cases = [
        eval_rag.EvalCase(
            id="et-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
        eval_rag.EvalCase(
            id="et-2",
            scenario_type="BANK_ENTERPRISE",
            error_type="SINGLE_SIDE_MISSING",
            query="q2",
            expected_chunk_ids=["c2"],
        ),
        eval_rag.EvalCase(
            id="et-3",
            scenario_type="BANK_CLEARING",
            error_type="AMOUNT_MISMATCH",
            query="q3",
            expected_chunk_ids=["c3"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"], "q2": ["x", "c2"], "q3": ["c3"]})
    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)

    assert "error_type_summaries" in report
    error_summaries = report["error_type_summaries"]
    assert len(error_summaries) >= 2  # at least 2 groups
    # Each summary has scenario_type and error_type
    for summary in error_summaries:
        assert "scenario_type" in summary
        assert "error_type" in summary
        assert "hit_at_1" in summary
        assert "recall_at_5" in summary
        assert "mrr" in summary
        assert "ndcg_at_5" in summary


def test_error_type_summary_metric_math() -> None:
    """Verify per-error-type metrics are computed correctly, not hardcoded."""
    cases = [
        eval_rag.EvalCase(
            id="math-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
        eval_rag.EvalCase(
            id="math-2",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q2",
            expected_chunk_ids=["c1"],
        ),
    ]
    # q1 hits c1 at position 1 (hit@1=1), q2 does not hit (hit@1=0)
    retriever = StubRetriever({"q1": ["c1", "x"], "q2": ["x", "y"]})
    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)

    amt_group = [
        s for s in report["error_type_summaries"]
        if s["error_type"] == "AMOUNT_MISMATCH"
    ]
    assert len(amt_group) == 1
    assert amt_group[0]["case_count"] == 2
    assert amt_group[0]["hit_at_1"] == pytest.approx(0.5)  # 1 hit / 2 cases


def test_json_snapshot_backward_compatible_keys() -> None:
    """JSON snapshot must retain rag_recall_at5, rag_mrr, evaluated_at."""
    cases = [
        eval_rag.EvalCase(
            id="compat-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})
    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)
    snapshot = eval_rag._to_metrics_snapshot(report)

    # Required backward-compatible keys
    assert "rag_recall_at5" in snapshot
    assert "rag_mrr" in snapshot
    assert "evaluated_at" in snapshot
    # Richer keys also present
    assert "rag_hit_at1" in snapshot
    assert "rag_ndcg_at5" in snapshot
    assert "embedding_backend" in snapshot
    assert "top_k" in snapshot
    assert "case_count" in snapshot


def test_json_snapshot_preserves_numeric_values() -> None:
    """JSON snapshot numeric values come from global metrics, not hardcoded."""
    cases = [
        eval_rag.EvalCase(
            id="num-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})
    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)
    snapshot = eval_rag._to_metrics_snapshot(report)

    assert snapshot["rag_recall_at5"] == pytest.approx(1.0)
    assert snapshot["rag_mrr"] == pytest.approx(1.0)
    assert snapshot["rag_hit_at1"] == pytest.approx(1.0)
    assert snapshot["rag_ndcg_at5"] == pytest.approx(1.0)


def test_metadata_records_embedding_backend_and_top_k() -> None:
    """embedding_backend and top_k are recorded in report and snapshot."""
    cases = [
        eval_rag.EvalCase(
            id="meta-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})
    report = eval_rag.evaluate_eval_set(
        cases, retriever=retriever, embedding_backend="hash", top_k=5,
    )
    assert report["embedding_backend"] == "hash"
    assert report["top_k"] == 5

    snapshot = eval_rag._to_metrics_snapshot(report)
    assert snapshot["embedding_backend"] == "hash"
    assert snapshot["top_k"] == 5


def test_saturation_note_when_recall_at_5_is_one() -> None:
    """Recall@5 saturation risk is explicitly noted when Recall@5 = 1.0."""
    cases = [
        eval_rag.EvalCase(
            id="sat-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})  # Recall@5 = 1.0
    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)

    saturation_notes = [n for n in report["notes"] if "saturation" in n.lower()]
    assert len(saturation_notes) >= 1, "Expected at least one saturation note"


def test_no_saturation_note_when_recall_below_one() -> None:
    """No saturation note when Recall@5 < 1.0."""
    cases = [
        eval_rag.EvalCase(
            id="nosat-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1", "c2"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})  # Recall@5 = 0.5
    report = eval_rag.evaluate_eval_set(cases, retriever=retriever)

    saturation_notes = [n for n in report["notes"] if "saturation" in n.lower()]
    assert len(saturation_notes) == 0


def test_markdown_report_includes_all_sections(tmp_path: Path) -> None:
    """Markdown report includes Hit@1, Recall@5, MRR, NDCG@5 and groupings."""
    cases = [
        eval_rag.EvalCase(
            id="md-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
        eval_rag.EvalCase(
            id="md-2",
            scenario_type="BANK_CLEARING",
            error_type="CUTOFF_CROSS_DAY",
            query="q2",
            expected_chunk_ids=["c2"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"], "q2": ["x"]})
    report = eval_rag.evaluate_eval_set(
        cases, retriever=retriever, embedding_backend="hash", top_k=5,
    )
    md_path = tmp_path / "rag_eval.md"
    eval_rag.write_markdown_report(report, md_path)
    content = md_path.read_text(encoding="utf-8")

    assert "Hit@1" in content
    assert "Recall@5" in content
    assert "MRR" in content
    assert "NDCG@5" in content
    assert "Global Metrics" in content
    assert "By Scenario" in content
    assert "Error Type" in content
    assert "hash" in content  # embedding_backend
    assert "Notes" in content


def test_evalcase_input_format_unchanged() -> None:
    """EvalCase dataclass must keep the same fields."""
    case = eval_rag.EvalCase(
        id="compat",
        scenario_type="BANK_ENTERPRISE",
        error_type="AMOUNT_MISMATCH",
        query="test query",
        expected_chunk_ids=["chunk-1"],
    )
    assert case.id == "compat"
    assert case.scenario_type == "BANK_ENTERPRISE"
    assert case.error_type == "AMOUNT_MISMATCH"
    assert case.query == "test query"
    assert case.expected_chunk_ids == ["chunk-1"]


# ---------------------------------------------------------------------------
# TASK-EO.1: RAG mode flags and mode comparison tests
# ---------------------------------------------------------------------------


def test_request_for_eval_mode_dense_disables_hybrid_and_reranker() -> None:
    case = eval_rag.EvalCase(
        id="case-1",
        scenario_type="BANK_ENTERPRISE",
        error_type="AMOUNT_MISMATCH",
        query="q1",
        expected_chunk_ids=["c1"],
    )
    request = eval_rag.request_for_eval_mode(case, mode="dense", top_k=5)
    assert request.enable_hybrid is False
    assert request.enable_reranker is False
    assert request.query == "q1"
    assert request.scenario_type == "BANK_ENTERPRISE"
    assert request.top_k == 5


def test_request_for_eval_mode_hybrid_enables_hybrid_only() -> None:
    case = eval_rag.EvalCase(
        id="case-1",
        scenario_type="BANK_CLEARING",
        error_type="AMOUNT_MISMATCH",
        query="q1",
        expected_chunk_ids=["c1"],
    )
    request = eval_rag.request_for_eval_mode(case, mode="hybrid", top_k=3)
    assert request.enable_hybrid is True
    assert request.enable_reranker is False
    assert request.scenario_type == "BANK_CLEARING"


def test_request_for_eval_mode_hybrid_rerank_enables_both() -> None:
    case = eval_rag.EvalCase(
        id="case-1",
        scenario_type="BANK_ENTERPRISE",
        error_type="SINGLE_SIDE_MISSING",
        query="q1",
        expected_chunk_ids=["c1"],
    )
    request = eval_rag.request_for_eval_mode(case, mode="hybrid_rerank", top_k=5)
    assert request.enable_hybrid is True
    assert request.enable_reranker is True


def test_evaluate_eval_set_dense_mode_disables_hybrid_flags() -> None:
    cases = [
        eval_rag.EvalCase(
            id="d-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
        eval_rag.EvalCase(
            id="d-2",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q2",
            expected_chunk_ids=["c2"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"], "q2": ["c2"]})
    eval_rag.evaluate_eval_set(cases, retriever=retriever, mode="dense")
    assert [r.enable_hybrid for r in retriever.requests] == [False, False]
    assert [r.enable_reranker for r in retriever.requests] == [False, False]


def test_evaluate_eval_set_hybrid_mode_enables_hybrid_only() -> None:
    cases = [
        eval_rag.EvalCase(
            id="h-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})
    eval_rag.evaluate_eval_set(cases, retriever=retriever, mode="hybrid")
    assert [r.enable_hybrid for r in retriever.requests] == [True]
    assert [r.enable_reranker for r in retriever.requests] == [False]


def test_evaluate_eval_set_hybrid_rerank_mode_enables_both() -> None:
    cases = [
        eval_rag.EvalCase(
            id="hr-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})
    eval_rag.evaluate_eval_set(cases, retriever=retriever, mode="hybrid_rerank")
    assert [r.enable_hybrid for r in retriever.requests] == [True]
    assert [r.enable_reranker for r in retriever.requests] == [True]


def test_evaluate_mode_comparison_includes_all_modes_and_deltas() -> None:
    cases = [
        eval_rag.EvalCase(
            id="cmp-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"]})
    report = eval_rag.evaluate_mode_comparison(
        cases,
        retriever=retriever,
        modes=["dense", "hybrid", "hybrid_rerank"],
        top_k=5,
        embedding_backend="hash",
    )
    assert report["baseline_mode"] == "dense"
    assert "selected_mode" in report
    assert "selection_reason" in report
    assert set(report["modes"]) == {"dense", "hybrid", "hybrid_rerank"}
    for mode in ["dense", "hybrid", "hybrid_rerank"]:
        assert "global_metrics" in report["modes"][mode]
        gm = report["modes"][mode]["global_metrics"]
        assert "hit_at_1" in gm
        assert "mrr" in gm
        assert "ndcg_at_5" in gm
    assert set(report["deltas_vs_dense"]) == {"hybrid", "hybrid_rerank"}
    for mode in ["hybrid", "hybrid_rerank"]:
        for key in ["hit_at_1", "mrr", "ndcg_at_5"]:
            assert key in report["deltas_vs_dense"][mode]


def test_mode_comparison_no_improvement_keeps_dense() -> None:
    cases = [
        eval_rag.EvalCase(
            id="ni-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
        eval_rag.EvalCase(
            id="ni-2",
            scenario_type="BANK_ENTERPRISE",
            error_type="SINGLE_SIDE_MISSING",
            query="q2",
            expected_chunk_ids=["c2"],
        ),
    ]
    retriever = StubRetriever({"q1": ["c1"], "q2": ["x"]})
    report = eval_rag.evaluate_mode_comparison(
        cases,
        retriever=retriever,
        modes=["dense", "hybrid", "hybrid_rerank"],
        top_k=5,
        embedding_backend="hash",
    )
    assert report["selected_mode"] == "dense"
    assert "improve" in report["selection_reason"].lower() or "no" in report["selection_reason"].lower()


def test_mode_comparison_selects_better_mode() -> None:
    cases = [
        eval_rag.EvalCase(
            id="best-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
        eval_rag.EvalCase(
            id="best-2",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q2",
            expected_chunk_ids=["c1"],
        ),
    ]
    # dense: q1=["x"] (0 hits), q2=["c1"] (1 hit) → hit@1=0.5, mrr=0.5, ndcg>0
    # hybrid: q1=["c1"] (1 hit), q2=["c1"] (1 hit) → hit@1=1.0, mrr=1.0, ndcg=1.0
    class ModeAwareRetriever:
        def __init__(self) -> None:
            self.requests: list = []

        def search(self, request):
            self.requests.append(request)
            if request.enable_hybrid and not request.enable_reranker:
                ids = ["c1", "c1"]
            elif request.enable_hybrid and request.enable_reranker:
                ids = ["x", "c1"]
            else:
                ids = ["x", "c1"]
            q_idx = 0 if request.query == "q1" else 1
            return RagSearchResponse(items=[_item(ids[q_idx])])

    retriever = ModeAwareRetriever()
    report = eval_rag.evaluate_mode_comparison(
        cases,
        retriever=retriever,
        modes=["dense", "hybrid", "hybrid_rerank"],
        top_k=5,
        embedding_backend="hash",
    )
    assert report["selected_mode"] == "hybrid"
    deltas = report["deltas_vs_dense"]["hybrid"]
    assert deltas["hit_at_1"] > 0


# ---------------------------------------------------------------------------
# TASK-EO.4: Stricter RAG selection tests
# ---------------------------------------------------------------------------


def test_mode_with_negative_delta_is_rejected() -> None:
    """A mode with positive delta but any negative ranking metric is NOT eligible."""
    modes = ["dense", "hybrid"]
    deltas = {
        "hybrid": {"hit_at_1": 0.1, "mrr": -0.05, "ndcg_at_5": 0.0},
    }
    mode_reports = {
        "dense": {"global_metrics": {"hit_at_1": 0.5, "mrr": 0.5, "ndcg_at_5": 0.5}},
        "hybrid": {"global_metrics": {"hit_at_1": 0.6, "mrr": 0.45, "ndcg_at_5": 0.5}},
    }
    selected, _ = eval_rag._select_best_mode(modes, deltas, mode_reports)
    assert selected == "dense"


# ---------------------------------------------------------------------------
# TASK-17.1: RAG backend-by-mode matrix tests
# ---------------------------------------------------------------------------

class _StubStore:
    def __init__(self, embedding_backend: str) -> None:
        self.embedding_backend = embedding_backend


class _StubRetrieverWithStore(StubRetriever):
    def __init__(self, responses: dict[str, list[str]], embedding_backend: str = "hash") -> None:
        super().__init__(responses)
        self.store = _StubStore(embedding_backend)


def test_matrix_real_backend_policy_skip_marks_not_run() -> None:
    cases = [
        eval_rag.EvalCase(
            id="skip-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    def factory(backend: str) -> _StubRetrieverWithStore:
        return _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend=backend)

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small", "bge_m3"],
        modes=["dense"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )

    assert report["real_backend_policy"] == "skip"
    assert report["requested_backends"] == ["hash", "bge_small", "bge_m3"]

    assert report["rows"]["hash"]["status"] == "measured"

    bge_small = report["rows"]["bge_small"]
    assert bge_small["status"] == "not_run"
    assert bge_small["effective_backend"] is None
    assert bge_small["reason"] == "real backend policy is skip"

    bge_m3 = report["rows"]["bge_m3"]
    assert bge_m3["status"] == "not_run"
    assert bge_m3["effective_backend"] is None
    assert bge_m3["reason"] == "real backend policy is skip"


def test_matrix_unavailable_when_effective_backend_differs() -> None:
    cases = [
        eval_rag.EvalCase(
            id="unav-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    def factory(backend: str) -> _StubRetrieverWithStore:
        return _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend="hash")

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    assert report["rows"]["hash"]["status"] == "measured"
    assert report["rows"]["bge_small"]["status"] == "unavailable"
    assert report["rows"]["bge_small"]["effective_backend"] == "hash"
    assert "not bge_small" in report["rows"]["bge_small"]["reason"]


def test_matrix_measured_row_has_required_fields() -> None:
    cases = [
        eval_rag.EvalCase(
            id="req-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    def factory(backend: str) -> _StubRetrieverWithStore:
        return _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend=backend)

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash"],
        modes=["dense", "hybrid"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    row = report["rows"]["hash"]
    assert row["requested_backend"] == "hash"
    assert row["effective_backend"] == "hash"
    assert row["status"] == "measured"
    assert row["selected_mode"] in ("dense", "hybrid")
    assert row["selection_reason"] is not None
    assert row["modes"] is not None
    assert row["deltas_vs_dense"] is not None

    for mode_name in ["dense", "hybrid"]:
        gm = row["modes"][mode_name]["global_metrics"]
        assert "hit_at_1" in gm
        assert "recall_at_5" in gm
        assert "mrr" in gm
        assert "ndcg_at_5" in gm


def test_matrix_markdown_shows_per_backend_mode_metrics() -> None:
    cases = [
        eval_rag.EvalCase(
            id="md-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    def factory(backend: str) -> _StubRetrieverWithStore:
        return _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend=backend)

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    md = eval_rag._format_matrix_markdown(report)

    assert "RAG Quality Matrix Report" in md
    assert "hash" in md
    assert "measured" in md
    assert "Hit@1" in md
    assert "Recall@5" in md
    assert "MRR" in md
    assert "NDCG@5" in md
    assert "Global Metrics" in md


def test_matrix_json_has_required_structure() -> None:
    cases = [
        eval_rag.EvalCase(
            id="json-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    def factory(backend: str) -> _StubRetrieverWithStore:
        return _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend=backend)

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense", "hybrid", "hybrid_rerank"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )

    assert report["case_count"] == 1
    assert report["top_k"] == 5
    assert report["requested_backends"] == ["hash", "bge_small"]
    assert report["modes"] == ["dense", "hybrid", "hybrid_rerank"]
    assert "evaluated_at" in report
    assert "rows" in report
    assert report["real_backend_policy"] == "skip"

    bge_row = report["rows"]["bge_small"]
    assert "modes" not in bge_row
    assert "deltas_vs_dense" not in bge_row
    assert "selected_mode" not in bge_row

    hash_row = report["rows"]["hash"]
    assert "modes" in hash_row
    assert "deltas_vs_dense" in hash_row


def test_evaluate_eval_set_uses_min_score_zero_for_matrix() -> None:
    cases = [
        eval_rag.EvalCase(
            id="ms-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    retrievers_captured: list[_StubRetrieverWithStore] = []

    def factory(backend: str) -> _StubRetrieverWithStore:
        r = _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend=backend)
        retrievers_captured.append(r)
        return r

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash"],
        modes=["dense"],
        real_backend_policy="auto",
        retriever_factory=factory,
    )

    assert report["rows"]["hash"]["status"] == "measured"

    for r in retrievers_captured:
        for request in r.requests:
            assert request.min_score == 0.0


def test_matrix_not_run_row_does_not_count_as_measured() -> None:
    cases = [
        eval_rag.EvalCase(
            id="nr-1",
            scenario_type="BANK_ENTERPRISE",
            error_type="AMOUNT_MISMATCH",
            query="q1",
            expected_chunk_ids=["c1"],
        ),
    ]

    def factory(backend: str) -> _StubRetrieverWithStore:
        return _StubRetrieverWithStore({"q1": ["c1"]}, embedding_backend=backend)

    report = eval_rag.evaluate_backend_mode_matrix(
        cases,
        requested_backends=["hash", "bge_small"],
        modes=["dense"],
        real_backend_policy="skip",
        retriever_factory=factory,
    )

    assert report["best_real_backend"] is None
    assert len(report["miss_buckets"]) == 0


def test_mode_with_all_non_negative_deltas_remains_eligible() -> None:
    modes = ["dense", "hybrid"]
    deltas = {
        "hybrid": {"hit_at_1": 0.0, "mrr": 0.1, "ndcg_at_5": 0.15},
    }
    mode_reports = {
        "dense": {"global_metrics": {"hit_at_1": 0.2, "mrr": 0.2, "ndcg_at_5": 0.2}},
        "hybrid": {"global_metrics": {"hit_at_1": 0.2, "mrr": 0.3, "ndcg_at_5": 0.35}},
    }
    selected, _ = eval_rag._select_best_mode(modes, deltas, mode_reports)
    assert selected == "hybrid"


def test_mode_with_zero_only_deltas_keeps_dense() -> None:
    modes = ["dense", "hybrid", "hybrid_rerank"]
    deltas = {
        "hybrid": {"hit_at_1": 0.0, "mrr": 0.0, "ndcg_at_5": 0.0},
        "hybrid_rerank": {"hit_at_1": 0.0, "mrr": 0.0, "ndcg_at_5": 0.0},
    }
    mode_reports = {
        "dense": {"global_metrics": {"hit_at_1": 0.5, "mrr": 0.5, "ndcg_at_5": 0.5}},
        "hybrid": {"global_metrics": {"hit_at_1": 0.5, "mrr": 0.5, "ndcg_at_5": 0.5}},
        "hybrid_rerank": {"global_metrics": {"hit_at_1": 0.5, "mrr": 0.5, "ndcg_at_5": 0.5}},
    }
    selected, _ = eval_rag._select_best_mode(modes, deltas, mode_reports)
    assert selected == "dense"
