from bank_reconciliation_agent.core.config import Settings
from bank_reconciliation_agent.schemas.rag import (
    RagSearchItem,
    RagSearchRequest,
    RagSearchResponse,
)


def test_settings_include_mvp2a2_rag_flags_and_thresholds() -> None:
    settings = Settings()

    assert settings.enable_rag_rewrite is False
    assert settings.enable_rag_hybrid is False
    assert settings.enable_rag_reranker is False
    assert settings.rag_dense_top_n == 20
    assert settings.rag_bm25_top_n == 20
    assert settings.rag_rerank_top_k == 5
    assert settings.rag_rrf_k == 60
    assert settings.rag_dense_min_score == 0.341
    assert settings.rag_reranker_min_score == 0.3
    assert settings.rag_low_score == 0.5


def test_rag_search_request_remains_backwards_compatible() -> None:
    request = RagSearchRequest(query="x")

    assert request.query == "x"
    assert request.scenario_type == "BANK_ENTERPRISE"
    assert request.enable_rewrite is False
    assert request.enable_hybrid is False
    assert request.enable_reranker is False


def test_rag_search_item_remains_backwards_compatible() -> None:
    item = RagSearchItem(
        chunk_id="chunk-1",
        source="rule",
        source_name="Rule 1",
        source_url="https://example.com/rule-1",
        source_file="rules/rule-1.md",
        section_title="Section 1",
        element_type="paragraph",
        business_tags=["amount_mismatch"],
        score=0.9,
        content="rule content",
    )

    assert item.dense_score is None
    assert item.bm25_score is None
    assert item.reranker_score is None
    assert item.fusion_rank is None


def test_rag_search_response_supports_optional_rewritten_query() -> None:
    response = RagSearchResponse(items=[], rewritten_query=None)

    assert response.rewritten_query is None
