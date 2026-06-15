import json
from pathlib import Path

from bank_reconciliation_agent.rag.retriever import RuleRetriever
from scripts import eval_rag


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEARING_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks_bank_clearing.jsonl"


def _load_clearing_chunks() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in CLEARING_CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_bank_clearing_corpus_has_desaturated_chunk_set(tmp_path: Path) -> None:
    chunks = _load_clearing_chunks()

    assert len(chunks) >= 25

    report = eval_rag.evaluate_eval_set(
        [
            eval_rag.EvalCase(
                id="clearing-desaturation",
                scenario_type="BANK_CLEARING",
                error_type="CORPUS_DESATURATION",
                query="清算 单边 缺失 跨日 T+1 金额 文件 异常 查询查复 证据 留痕",
                expected_chunk_ids=[str(chunk["chunk_id"]) for chunk in chunks],
            )
        ],
        retriever=RuleRetriever(chunks_path=CLEARING_CHUNKS_PATH, chroma_path=tmp_path / "chroma"),
        top_k=5,
    )

    summary = report["summaries"][0]
    assert summary["scenario_type"] == "BANK_CLEARING"
    assert 0.0 < summary["recall_at_5"] < 1.0
