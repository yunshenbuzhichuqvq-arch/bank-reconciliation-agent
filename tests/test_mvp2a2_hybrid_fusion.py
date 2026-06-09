import json
from pathlib import Path

from bank_reconciliation_agent.rag.fusion import fuse_rrf
from bank_reconciliation_agent.rag.retriever import ChromaRuleStore
from bank_reconciliation_agent.rag.sparse import Bm25Index
from scripts.build_rule_chunks import build_rule_chunks


ROOT = Path(__file__).resolve().parents[1]


def _load_chunks(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_bm25_index_returns_ranked_hits_for_chinese_query(tmp_path: Path) -> None:
    chunks_path = tmp_path / "rule_chunks.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources.json",
        output_path=chunks_path,
    )
    chunks = _load_chunks(chunks_path)
    index = Bm25Index()
    index.build(chunks)

    results = index.query("金额差异 对账不平", top_k=3)

    assert results
    assert len(results) <= 3
    assert results == sorted(results, key=lambda item: item[1], reverse=True)


def test_bm25_index_uses_same_chunk_ids_as_dense_store(tmp_path: Path) -> None:
    chunks_path = tmp_path / "rule_chunks.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources.json",
        output_path=chunks_path,
    )
    chunks = _load_chunks(chunks_path)
    index = Bm25Index()
    index.build(chunks)
    store = ChromaRuleStore(chunks_path=chunks_path, chroma_path=tmp_path / "chroma")

    dense_hits = store.query("金额差异 对账不平", top_k=3)

    assert {chunk["chunk_id"] for chunk in chunks} == index.chunk_ids
    assert {metadata["chunk_id"] for _, metadata, _ in dense_hits} <= index.chunk_ids


def test_fuse_rrf_merges_dense_and_sparse_hits_with_continuous_ranks() -> None:
    dense_hits = [
        (
            0.95,
            {
                "chunk_id": "chunk-a",
                "source_name": "Rule A",
                "source_url": "https://example.com/a",
                "source_file": "rules/a.md",
                "section_title": "A",
                "element_type": "paragraph",
                "business_tags": '["amount_mismatch"]',
            },
            "alpha content",
        ),
        (
            0.80,
            {
                "chunk_id": "chunk-b",
                "source_name": "Rule B",
                "source_url": "https://example.com/b",
                "source_file": "rules/b.md",
                "section_title": "B",
                "element_type": "paragraph",
                "business_tags": '["single_side_missing"]',
            },
            "beta content",
        ),
    ]
    sparse_hits = [
        ("chunk-b", 12.0),
        ("chunk-c", 10.0),
    ]

    fused = fuse_rrf(dense_hits, sparse_hits, k=60)

    assert [hit.fusion_rank for hit in fused] == [1, 2, 3]
    assert {hit.chunk_id for hit in fused} == {"chunk-a", "chunk-b", "chunk-c"}
    assert fused[0].chunk_id == "chunk-b"
    assert fused[0].dense_score == 0.8
    assert fused[0].bm25_score == 12.0
