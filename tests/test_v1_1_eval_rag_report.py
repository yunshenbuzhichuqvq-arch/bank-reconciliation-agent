import json
from pathlib import Path

from scripts import eval_rag


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    assert set(snapshot) == {"rag_recall_at5", "rag_mrr", "evaluated_at"}
    assert 0.0 <= snapshot["rag_recall_at5"] <= 1.0
    assert 0.0 <= snapshot["rag_mrr"] <= 1.0
    assert snapshot["evaluated_at"]
