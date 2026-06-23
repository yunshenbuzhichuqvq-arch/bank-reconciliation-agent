from __future__ import annotations

from pathlib import Path

from scripts.build_rule_chunks import build_rule_chunks
from scripts.eval_rag import evaluate_cases, main


ROOT = Path(__file__).resolve().parents[1]


def test_hybrid_smoke_hits_are_not_worse_than_dense(tmp_path: Path) -> None:
    chunks_path = tmp_path / "rule_chunks.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_enterprise.json",
        output_path=chunks_path,
    )

    dense_summary = evaluate_cases(
        chunks_path=chunks_path,
        chroma_path=tmp_path / "dense-chroma",
        mode="dense",
    )
    hybrid_summary = evaluate_cases(
        chunks_path=chunks_path,
        chroma_path=tmp_path / "hybrid-chroma",
        mode="hybrid_rerank",
    )

    assert hybrid_summary.hit_count >= dense_summary.hit_count


def test_eval_script_main_prints_comparison_report(tmp_path: Path, capsys) -> None:
    chunks_path = tmp_path / "rule_chunks.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_enterprise.json",
        output_path=chunks_path,
    )

    main(["--chunks", str(chunks_path), "--chroma", str(tmp_path / "chroma")])

    output = capsys.readouterr().out
    assert "mode\thit_count" in output
    assert "dense" in output
    assert "hybrid_rerank" in output
    assert "avg_reranker_score" in output
