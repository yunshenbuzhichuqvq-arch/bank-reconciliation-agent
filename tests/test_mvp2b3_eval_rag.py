import json
from pathlib import Path

import pytest

from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from scripts import eval_rag


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
