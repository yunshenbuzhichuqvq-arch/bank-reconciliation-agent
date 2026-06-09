from __future__ import annotations

from dataclasses import replace

from bank_reconciliation_agent.rag.fusion import FusedHit
from bank_reconciliation_agent.rag.retriever import RuleRetriever
from bank_reconciliation_agent.schemas.rag import RagSearchRequest


class StubStore:
    def __init__(self, dense_hits: list[tuple[float, dict[str, str], str]]) -> None:
        self._dense_hits = dense_hits
        self._hits_by_chunk_id = {metadata["chunk_id"]: (score, metadata, content) for score, metadata, content in dense_hits}
        self.queries: list[tuple[str, int, str]] = []
        self.get_by_ids_calls: list[tuple[list[str], str]] = []

    def collection(self, scenario_type: str = "BANK_ENTERPRISE") -> "StubCollection":
        return StubCollection(len(self._dense_hits))

    def query(
        self,
        query_text: str,
        top_k: int,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[tuple[float, dict[str, str], str]]:
        self.queries.append((query_text, top_k, scenario_type))
        return self._dense_hits[:top_k]

    def get_by_ids(
        self,
        chunk_ids: list[str],
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[tuple[float, dict[str, str], str]]:
        self.get_by_ids_calls.append((chunk_ids, scenario_type))
        return [self._hits_by_chunk_id[chunk_id] for chunk_id in chunk_ids if chunk_id in self._hits_by_chunk_id]


class StubCollection:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class StubRewriter:
    def __init__(self, rewritten_query: str) -> None:
        self.rewritten_query = rewritten_query
        self.calls: list[tuple[str, str]] = []

    def rewrite(self, query: str, *, scenario_type: str) -> str:
        self.calls.append((query, scenario_type))
        return self.rewritten_query


class StubSparseIndex:
    def __init__(self, hits: list[tuple[str, float]]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, int]] = []

    def query(self, text: str, top_k: int) -> list[tuple[str, float]]:
        self.calls.append((text, top_k))
        return self.hits[:top_k]


class StubReranker:
    def __init__(self, score_by_chunk_id: dict[str, float]) -> None:
        self.score_by_chunk_id = score_by_chunk_id
        self.calls: list[tuple[str, int, list[str]]] = []

    def rerank(self, query: str, items: list[FusedHit], top_k: int) -> list[FusedHit]:
        self.calls.append((query, top_k, [item.chunk_id for item in items]))
        ranked = [
            replace(item, reranker_score=self.score_by_chunk_id[item.chunk_id])
            for item in items
            if item.chunk_id in self.score_by_chunk_id
        ]
        ranked.sort(key=lambda item: item.reranker_score or 0.0, reverse=True)
        return ranked[:top_k]


def _dense_hit(
    chunk_id: str,
    dense_score: float,
    *,
    content: str = "rule content",
) -> tuple[float, dict[str, str], str]:
    return (
        dense_score,
        {
            "chunk_id": chunk_id,
            "source_name": f"Rule {chunk_id}",
            "source_url": f"https://example.com/{chunk_id}",
            "source_file": f"rules/{chunk_id}.md",
            "section_title": f"Section {chunk_id}",
            "element_type": "paragraph",
            "business_tags": '["amount_mismatch"]',
        },
        content,
    )


def test_search_dense_only_matches_mvp0_behavior_when_all_flags_disabled() -> None:
    store = StubStore(
        [
            _dense_hit("chunk-high", 0.91),
            _dense_hit("chunk-low", 0.40),
        ]
    )
    retriever = RuleRetriever(store=store)

    response = retriever.search(
        RagSearchRequest(
            query="金额差异",
            top_k=2,
            min_score=0.5,
        )
    )

    assert [item.chunk_id for item in response.items] == ["chunk-high"]
    assert response.rewritten_query is None
    assert response.items[0].score == 0.91
    assert response.items[0].dense_score is None
    assert store.queries == [("金额差异", 2, "BANK_ENTERPRISE")]


def test_search_hybrid_populates_dense_bm25_and_fusion_rank() -> None:
    store = StubStore(
        [
            _dense_hit("chunk-a", 0.92, content="金额差异 对账不平"),
            _dense_hit("chunk-b", 0.81, content="金额差异 手续费"),
        ]
    )
    sparse = StubSparseIndex([("chunk-b", 12.0), ("chunk-a", 8.0)])
    retriever = RuleRetriever(store=store, sparse_index=sparse)

    response = retriever.search(
        RagSearchRequest(
            query="金额差异 对账不平",
            top_k=3,
            enable_hybrid=True,
        )
    )

    assert [item.chunk_id for item in response.items] == ["chunk-a", "chunk-b"]
    assert response.items[0].dense_score == 0.92
    assert response.items[0].bm25_score == 8.0
    assert response.items[0].fusion_rank == 1
    assert response.items[1].dense_score == 0.81
    assert response.items[1].bm25_score == 12.0
    assert response.items[1].fusion_rank == 2
    assert sparse.calls == [("金额差异 对账不平", 20)]


def test_search_hybrid_backfills_bm25_only_hits_into_search_items(monkeypatch) -> None:
    monkeypatch.setattr("bank_reconciliation_agent.rag.retriever.settings.rag_dense_top_n", 2)
    store = StubStore(
        [
            _dense_hit("chunk-a", 0.92, content="手续费处理规则"),
            _dense_hit("chunk-b", 0.81, content="余额核对规则"),
            _dense_hit("chunk-c", 0.40, content="仅供回填的金额差异规则"),
        ]
    )
    sparse = StubSparseIndex([("chunk-c", 15.0), ("chunk-a", 8.0)])
    retriever = RuleRetriever(store=store, sparse_index=sparse)

    response = retriever.search(
        RagSearchRequest(
            query="金额差异 对账不平",
            top_k=3,
            enable_hybrid=True,
            min_score=0.0,
        )
    )

    chunk_ids = [item.chunk_id for item in response.items]

    assert "chunk-c" in chunk_ids
    chunk_c = next(item for item in response.items if item.chunk_id == "chunk-c")
    assert chunk_c.source_file == "rules/chunk-c.md"
    assert chunk_c.content == "仅供回填的金额差异规则"
    assert chunk_c.dense_score is None
    assert chunk_c.bm25_score == 15.0
    assert chunk_c.fusion_rank is not None
    assert store.get_by_ids_calls == [(["chunk-c"], "BANK_ENTERPRISE")]


def test_search_hybrid_keeps_dense_hit_when_bm25_also_matches_and_min_score_same() -> None:
    store = StubStore([_dense_hit("chunk-a", 0.40, content="金额差异 对账不平")])
    sparse = StubSparseIndex([("chunk-a", 12.0)])
    retriever = RuleRetriever(store=store, sparse_index=sparse)

    response = retriever.search(
        RagSearchRequest(
            query="金额差异 对账不平",
            top_k=1,
            enable_hybrid=True,
            min_score=0.3,
        )
    )

    assert [item.chunk_id for item in response.items] == ["chunk-a"]
    assert response.items[0].dense_score == 0.4
    assert response.items[0].bm25_score == 12.0


def test_search_reranker_sorts_by_reranker_score_and_applies_top_5_cutoff() -> None:
    dense_hits = [_dense_hit(f"chunk-{index}", 0.9 - (index * 0.01)) for index in range(6)]
    store = StubStore(dense_hits)
    sparse = StubSparseIndex([(f"chunk-{index}", float(10 - index)) for index in range(6)])
    reranker = StubReranker({f"chunk-{index}": 0.2 + (index * 0.1) for index in range(6)})
    retriever = RuleRetriever(store=store, sparse_index=sparse, reranker=reranker)

    response = retriever.search(
        RagSearchRequest(
            query="金额差异",
            top_k=6,
            enable_hybrid=True,
            enable_reranker=True,
        )
    )

    assert [item.chunk_id for item in response.items] == [
        "chunk-5",
        "chunk-4",
        "chunk-3",
        "chunk-2",
        "chunk-1",
    ]
    assert all(item.reranker_score is not None for item in response.items)
    assert len(response.items) == 5
    assert reranker.calls == [("金额差异", 5, [f"chunk-{index}" for index in range(6)])]


def test_search_rewrite_uses_rewritten_query_and_returns_it_in_response() -> None:
    store = StubStore([_dense_hit("chunk-a", 0.88)])
    rewriter = StubRewriter("金额差异 对账 规则")
    retriever = RuleRetriever(store=store, rewriter=rewriter)

    response = retriever.search(
        RagSearchRequest(
            query="金额差异",
            top_k=1,
            enable_rewrite=True,
        )
    )

    assert response.rewritten_query == "金额差异 对账 规则"
    assert rewriter.calls == [("金额差异", "BANK_ENTERPRISE")]
    assert store.queries == [("金额差异 对账 规则", 1, "BANK_ENTERPRISE")]
