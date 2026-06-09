from bank_reconciliation_agent.rag.embedding import HashEmbeddingProvider
from bank_reconciliation_agent.rag.fusion import FusedHit
from bank_reconciliation_agent.rag.rerank import BgeReranker, LexicalReranker


def _hit(
    chunk_id: str,
    content: str,
    *,
    dense_score: float | None = None,
    bm25_score: float | None = None,
    fusion_score: float = 0.0,
    fusion_rank: int = 0,
) -> FusedHit:
    return FusedHit(
        chunk_id=chunk_id,
        dense_score=dense_score,
        bm25_score=bm25_score,
        fusion_score=fusion_score,
        fusion_rank=fusion_rank,
        metadata={"chunk_id": chunk_id},
        content=content,
    )


def test_hash_embedding_provider_wraps_existing_hash_embedding() -> None:
    provider = HashEmbeddingProvider()

    embeddings = provider.embed(["金额差异", "单边缺失"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == len(embeddings[1])
    assert embeddings[0] != embeddings[1]


def test_lexical_reranker_is_deterministic_and_scores_in_range() -> None:
    reranker = LexicalReranker()
    items = [
        _hit(
            "chunk-high",
            "金额差异 对账不平 需要保留银行端金额和清算端金额",
            dense_score=0.8,
            bm25_score=10.0,
            fusion_score=0.03,
            fusion_rank=1,
        ),
        _hit(
            "chunk-low",
            "单边缺失 需要查询查复",
            dense_score=0.7,
            bm25_score=4.0,
            fusion_score=0.02,
            fusion_rank=2,
        ),
    ]

    first = reranker.rerank("金额差异 对账不平", items, top_k=2)
    second = reranker.rerank("金额差异 对账不平", items, top_k=2)

    assert [hit.chunk_id for hit in first] == [hit.chunk_id for hit in second]
    assert [hit.reranker_score for hit in first] == [hit.reranker_score for hit in second]
    assert all(hit.reranker_score is not None for hit in first)
    assert all(0.0 <= hit.reranker_score <= 1.0 for hit in first if hit.reranker_score is not None)
    assert first[0].chunk_id == "chunk-high"
    assert first[0].reranker_score > first[1].reranker_score


def test_lexical_reranker_applies_top_k_cutoff() -> None:
    reranker = LexicalReranker()
    items = [
        _hit("chunk-1", "金额差异 对账不平", dense_score=0.9, fusion_score=0.03, fusion_rank=1),
        _hit("chunk-2", "金额差异", dense_score=0.8, fusion_score=0.02, fusion_rank=2),
        _hit("chunk-3", "查询查复", dense_score=0.7, fusion_score=0.01, fusion_rank=3),
    ]

    ranked = reranker.rerank("金额差异 对账不平", items, top_k=2)

    assert len(ranked) == 2


def test_bge_reranker_is_placeholder() -> None:
    reranker = BgeReranker()

    try:
        reranker.rerank("金额差异", [], top_k=1)
    except NotImplementedError:
        pass
    else:
        raise AssertionError("BgeReranker should raise NotImplementedError")
